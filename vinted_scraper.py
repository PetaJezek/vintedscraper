#!/usr/bin/env python3
"""
Vinted scraper with animated terminal UI.

Flow:
  1. Walk catalog pages → collect item URLs
  2. Visit each item page → check location, extract data, download image
  3. Items saved to OUTPUT_FILE; seen IDs tracked in SEEN_IDS_FILE
"""

import argparse
import asyncio
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from _db import save_items_to_db, init_db

import aiohttp
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

OUTPUT_FILE       = "vinted_items.json"
SEEN_IDS_FILE     = "seen_item_ids.json"
IMAGES_FOLDER     = "webapp/vinted_images"
DEBUG_FOLDER      = "debug_pages"
COOKIES_FILE      = "vinted_cookies.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

MAX_PAGES_PER_URL = 10                  # catalog pages per search URL
DEBUG_LIMIT       = 30                  # max items to process (None = unlimited)
CONCURRENT_ITEMS  = 2                   # parallel item-page workers
RATE_LIMIT_PAUSE  = 40                  # seconds to sleep on rate-limit
CATALOG_WAIT_MS   = 3000               # ms to wait after catalog page loads
ITEM_WAIT_MS      = 3000               # ms to wait after item page loads

IMAGE_SCRAPE_MODE = 'catalog'           # 'catalog' = thumbnail from tile
                                        # 'item'    = full image from item page

# ── Debug / dry-run flags ─────────────────────────────────────────────────────
DRY_RUN               = False            # set False to write output files
SAVE_PASSED_HTML      = True           # save HTML for items that pass the filter
SAVE_FAILED_HTML      = False           # save catalog HTML when no items found

# ── VPN (Mullvad) rotation on rate-limit ─────────────────────────────────────
VPN_COUNTRIES = ["cz", "de", "at", "sk", "hu", "ch", "nl"]

# ── Search URLs ───────────────────────────────────────────────────────────────
# How to build a URL:
#   1. Open vinted.cz, set your filters (category, size, price, etc.)
#   2. Copy the URL from the address bar
#   3. REMOVE search_id=… and time=… — they are session-specific and expire
#   4. Add &page={page} at the end
SCRAPE_URLS = [
    {
        "url": (
            "https://www.vinted.cz/catalog"
            "?size_ids[]=210&size_ids[]=211"
            "&page={page}"
        ),
        "tag": "XL-XXL all categories",
    },
    {
        "url": (
            "https://www.vinted.cz/catalog"
            "?catalog[]=76"
            "&page={page}"
        ),
        "tag": "T-shirts",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# POLISH FILTER
# ══════════════════════════════════════════════════════════════════════════════

POLISH_INDICATORS = [
    "Poland",        # English
    "Polska",        # Polish self-name
    "Polsko",        # Czech/Slovak word for Poland
    ", PL",          # "City, PL"  ← common short format
    "(PL)",          # "(PL)" format
    "🇵🇱",           # flag emoji (some Vinted locales use this)
]


def is_polish(page_text: str) -> tuple[bool, str]:
    lower = page_text.lower()
    for indicator in POLISH_INDICATORS:
        if indicator.lower() in lower:
            return True, indicator
    return False, ""


# ══════════════════════════════════════════════════════════════════════════════
# TERMINAL UI
# ══════════════════════════════════════════════════════════════════════════════

_console = Console()


@dataclass
class ScraperState:
    section: str = ""
    page_num: int = 0
    items_total: int = 0
    items_checked: int = 0
    saved: int = 0
    polish: int = 0
    skipped: int = 0
    polish_urls: list = field(default_factory=list)
    status_msg: str = ""


def _build_panel(state: ScraperState) -> Panel:
    BAR_WIDTH = 36
    done  = state.items_checked
    total = max(state.items_total, 1)
    filled = int(BAR_WIDTH * done / total)
    bar    = "█" * filled + "░" * (BAR_WIDTH - filled)
    pct    = int(100 * done / total)

    t = Text()
    t.append("\n")
    t.append(f"  {state.section}", style="bold cyan")
    if state.page_num:
        t.append(f"  ·  fetching catalog page {state.page_num}", style="dim")
    t.append("\n\n")

    t.append(f"  {bar}  ", style="green")
    t.append(f"{done}", style="bold white")
    t.append(f" / {state.items_total}  ")
    t.append(f"({pct}%)", style="dim")
    t.append("\n\n")

    t.append("  ✓ saved  ", style="dim")
    t.append(f"{state.saved:<5d}", style="bold green")
    t.append("  ✗ polish  ", style="dim")
    t.append(f"{state.polish:<5d}", style="bold red")
    t.append("  ⚠ skipped  ", style="dim")
    t.append(f"{state.skipped}", style="bold yellow")
    t.append("\n")

    if state.status_msg:
        t.append(f"\n  {state.status_msg}\n", style="dim italic")

    return Panel(
        t,
        title="[bold blue] VINTED SCRAPER [/]",
        border_style="blue",
        padding=(0, 1),
    )


# ══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def extract_item_id(url: str) -> str | None:
    m = re.search(r'/items/(\d+)', url)
    return m.group(1) if m else None


def load_seen_ids() -> set:
    try:
        with open(SEEN_IDS_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen_ids(seen: set) -> None:
    with open(SEEN_IDS_FILE, 'w') as f:
        json.dump(list(seen), f)


def save_debug_html(filename: str, html: str) -> None:
    folder = Path(DEBUG_FOLDER)
    folder.mkdir(exist_ok=True)
    (folder / filename).write_text(html, encoding='utf-8')


async def download_image(
    session: aiohttp.ClientSession,
    url: str,
    item_id: str,
    state: ScraperState,
) -> str | None:
    dest = Path(IMAGES_FOLDER) / f"{item_id}.jpg"
    if dest.exists():
        return str(dest)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                dest.write_bytes(await resp.read())
                return str(dest)
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# SESSION / LOGIN
# ══════════════════════════════════════════════════════════════════════════════

async def ensure_session(pw, relogin: bool = False):
    """Return (browser, context) with a valid Vinted session.

    First tries saved cookies. If missing, expired, or relogin=True, opens a
    visible browser so the user can log in manually, then saves the cookies and
    switches to headless for the actual scrape.
    """
    cookies_path = Path(COOKIES_FILE)

    AUTH_PATHS = ("login", "register", "signup")

    def _on_auth_page(url: str) -> bool:
        return any(p in url for p in AUTH_PATHS)

    if not relogin and cookies_path.exists():
        saved = json.loads(cookies_path.read_text())
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(saved)
        page = await context.new_page()
        try:
            await page.goto("https://www.vinted.cz/", wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1500)
            if not _on_auth_page(page.url):
                await page.close()
                _console.print("[green]✓ Session restored from saved cookies[/]\n")
                return browser, context
        except Exception:
            pass
        await browser.close()
        _console.print("[yellow]Saved session expired — logging in again…[/]\n")

    _console.print("\n[bold yellow]Login required.[/] Opening browser window…")
    _console.print("  Log in to [cyan]vinted.cz[/] then wait — cookies are saved automatically.")

    # Try to use the real system Chromium/Chrome for login so Google OAuth works.
    # Playwright's bundled Chromium is flagged by Google's "app may not be secure" check.
    import shutil as _shutil
    _sys_chromium = (
        _shutil.which("google-chrome")
        or _shutil.which("chromium")
        or _shutil.which("chromium-browser")
    )

    vis_context = None
    _vis_browser = None

    _PROFILE_CANDIDATES = [
        Path.home() / ".config" / "google-chrome",
        Path.home() / ".config" / "chromium",
        Path.home() / ".config" / "BraveSoftware" / "Brave-Browser",
    ]

    # First: try persistent context with real profile (only if browser not already running)
    for profile_dir in _PROFILE_CANDIDATES:
        if not profile_dir.exists():
            continue
        try:
            vis_context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                executable_path=_sys_chromium or None,
                args=["--disable-blink-features=AutomationControlled"],
            )
            _console.print(f"  [dim]Using profile: {profile_dir}[/]\n")
            break
        except Exception:
            pass  # profile locked (browser already running) — try next

    # Fallback: plain Playwright Chromium with a clean temp profile
    if vis_context is None:
        _console.print(
            "  [yellow]Could not open your browser profile (close Chromium/Chrome first to use Google login).[/]"
        )
        _console.print("  [yellow]Falling back — use [bold]'Continue with email'[/bold] on the Vinted page, not Google.[/]\n")
        _vis_browser = await pw.chromium.launch(
            headless=False,
            executable_path=_sys_chromium or None,
        )
        vis_context = await _vis_browser.new_context(user_agent=USER_AGENT)

    page = await vis_context.new_page()
    await page.goto(
        "https://www.vinted.cz/member/signup/select_type?ref_url=%2F",
        wait_until="domcontentloaded",
        timeout=30_000,
    )

    try:
        await page.wait_for_function(
            "() => !['login','register','signup'].some(p => window.location.href.includes(p))",
            timeout=180_000,
        )
        await page.wait_for_timeout(2000)
        all_cookies = await vis_context.cookies()
        # Save only Vinted cookies — don't persist the user's Google/other cookies
        vinted_cookies = [c for c in all_cookies if "vinted" in c.get("domain", "")]
        cookies_path.write_text(json.dumps(vinted_cookies))
        _console.print(f"[green]✓ Logged in — session saved to {COOKIES_FILE}[/]\n")
        cookies = vinted_cookies
    except PlaywrightTimeout:
        _console.print("[red]Login timed out — continuing without login[/]\n")
        cookies = []

    await vis_context.close()
    if _vis_browser:
        await _vis_browser.close()

    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=USER_AGENT)
    if cookies:
        await context.add_cookies(cookies)
    return browser, context


# ══════════════════════════════════════════════════════════════════════════════
# VPN ROTATION
# ══════════════════════════════════════════════════════════════════════════════

_last_vpn_change: datetime | None = None


def rotate_vpn(state: ScraperState) -> None:
    global _last_vpn_change
    import random
    now = datetime.now()
    if _last_vpn_change and (now - _last_vpn_change) < timedelta(minutes=1):
        remaining = 60 - int((now - _last_vpn_change).total_seconds())
        state.status_msg = f"VPN cooldown: {remaining}s remaining"
        return
    country = random.choice(VPN_COUNTRIES)
    state.status_msg = f"VPN → switching to {country.upper()}…"
    try:
        subprocess.run(
            ["mullvad", "relay", "set", "location", country],
            check=True, capture_output=True,
        )
        subprocess.run(["mullvad", "reconnect"], check=True, capture_output=True)
        _last_vpn_change = now
        state.status_msg = f"VPN → {country.upper()} connected"
    except FileNotFoundError:
        state.status_msg = "VPN: mullvad not found"
    except subprocess.CalledProcessError:
        state.status_msg = "VPN: rotation failed"


# ══════════════════════════════════════════════════════════════════════════════
# CATALOG PAGE SCRAPING
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_catalog_page(
    page,
    catalog_url: str,
    page_num: int,
    state: ScraperState,
) -> list[dict]:
    state.page_num = page_num
    url = catalog_url.replace("{page}", str(page_num)) if "{page}" in catalog_url else catalog_url

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(CATALOG_WAIT_MS)
    except PlaywrightTimeout:
        return []
    except Exception:
        return []

    anchors = await page.query_selector_all("a[href*='/items/']")
    if not anchors:
        if SAVE_FAILED_HTML:
            save_debug_html(f"catalog_empty_p{page_num}.html", await page.content())
        return []

    seen_hrefs: set[str] = set()
    items: list[dict] = []

    for anchor in anchors:
        href = await anchor.get_attribute("href") or ""
        if "/items/" not in href:
            continue
        full_url = href if href.startswith("http") else f"https://www.vinted.cz{href}"
        if full_url in seen_hrefs:
            continue
        seen_hrefs.add(full_url)

        image_url = None
        if IMAGE_SCRAPE_MODE == 'catalog':
            img = await anchor.query_selector("img")
            if img:
                image_url = (
                    await img.get_attribute("data-src")
                    or await img.get_attribute("src")
                )

        items.append({"url": full_url, "image_url": image_url})

    return items


# ══════════════════════════════════════════════════════════════════════════════
# ITEM PAGE SCRAPING
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_item(
    context,
    catalog_item: dict,
    seen_ids: set,
    session: aiohttp.ClientSession,
    url_tag: str,
    state: ScraperState,
) -> dict | None:
    url     = catalog_item["url"]
    item_id = extract_item_id(url)

    if not item_id or item_id in seen_ids:
        return None

    page = await context.new_page()
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(ITEM_WAIT_MS)
        except PlaywrightTimeout:
            state.skipped += 1
            state.items_checked += 1
            return None

        page_text = await page.evaluate("() => document.body.innerText")

        # ── Rate-limit check ───────────────────────────────────────────────
        rate_signals = ["moc návštěv", "too many", "rate limit"]
        if any(s in page_text.lower() for s in rate_signals):
            state.status_msg = f"Rate limited — pausing {RATE_LIMIT_PAUSE}s…"
            rotate_vpn(state)
            await page.close()
            await asyncio.sleep(RATE_LIMIT_PAUSE)
            state.status_msg = ""
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(ITEM_WAIT_MS)
            page_text = await page.evaluate("() => document.body.innerText")
            if any(s in page_text.lower() for s in rate_signals):
                state.skipped += 1
                state.items_checked += 1
                return None

        # ── Page-gone check ────────────────────────────────────────────────
        gone_signals = ["page does not exist", "stránka neexistuje", "nenalezeno"]
        if any(s in page_text.lower() for s in gone_signals):
            seen_ids.add(item_id)
            state.skipped += 1
            state.items_checked += 1
            return None

        # ── Polish filter ──────────────────────────────────────────────────
        polish, _ = is_polish(page_text)
        if polish:
            state.polish += 1
            state.polish_urls.append(url)
            seen_ids.add(item_id)
            state.items_checked += 1
            return None

        if SAVE_PASSED_HTML:
            save_debug_html(f"passed_{item_id}.html", await page.content())

        # ── Extract item data ──────────────────────────────────────────────
        data: dict = {
            "id":         item_id,
            "url":        url,
            "scraped_at": datetime.now().isoformat(),
            "tag":        url_tag,
        }

        h1 = await page.query_selector("h1")
        if h1:
            data["title"] = (await h1.inner_text()).strip()

        for sel in ["[data-testid='item-price']", "[class*='price']"]:
            el = await page.query_selector(sel)
            if el:
                data["price"] = (await el.inner_text()).strip()
                break

        for sel in ["[data-testid='item-brand']", "[class*='brand']"]:
            el = await page.query_selector(sel)
            if el:
                data["brand"] = (await el.inner_text()).strip()
                break

        for sel in ["[data-testid='item-size']", "[class*='size']"]:
            el = await page.query_selector(sel)
            if el:
                data["size"] = (await el.inner_text()).strip()
                break
        if "size" not in data:
            m = re.search(r'(?:size|velikost)[:\s]+([A-Z0-9/]+)', page_text, re.IGNORECASE)
            if m:
                data["size"] = m.group(1)

        for sel in ["[data-testid='item-description']", "[class*='description']"]:
            el = await page.query_selector(sel)
            if el:
                data["description"] = (await el.inner_text()).strip()[:500]
                break

        for sel in ["[data-testid*='location']", "[class*='location']"]:
            el = await page.query_selector(sel)
            if el:
                data["location"] = (await el.inner_text()).strip()
                break

        img_url = catalog_item.get("image_url")
        if IMAGE_SCRAPE_MODE == 'item' or not img_url:
            for sel in [
                "img[data-testid='item-photo']",
                "img[class*='photo']",
                "main img",
            ]:
                img_el = await page.query_selector(sel)
                if img_el:
                    img_url = await img_el.get_attribute("src")
                    break

        if img_url:
            local_path = await download_image(session, img_url, item_id, state)
            data["image_url"] = local_path or img_url

        seen_ids.add(item_id)
        state.saved += 1
        state.items_checked += 1
        return data

    except Exception:
        state.skipped += 1
        state.items_checked += 1
        return None
    finally:
        await page.close()


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE
# ══════════════════════════════════════════════════════════════════════════════

def save_items(new_items: list[dict]) -> int:
    existing: list = []
    try:
        with open(OUTPUT_FILE, encoding='utf-8') as f:
            existing = json.load(f)
    except FileNotFoundError:
        pass
    existing.extend(new_items)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    return len(existing)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main(dry_run: bool = False, limit: int | None = None, relogin: bool = False) -> None:
    Path(IMAGES_FOLDER).mkdir(parents=True, exist_ok=True)

    effective_limit = limit if limit is not None else DEBUG_LIMIT
    effective_dry   = dry_run or DRY_RUN

    seen_ids      = load_seen_ids()
    state         = ScraperState()
    all_new_items: list[dict] = []
    total_catalog = 0

    async with async_playwright() as pw:
        browser, context = await ensure_session(pw, relogin=relogin)

        with Live(_build_panel(state), refresh_per_second=10, console=_console) as live:
            async with aiohttp.ClientSession() as http:
                catalog_page = await context.new_page()

                for config in SCRAPE_URLS:
                    url_template = config["url"]
                    tag          = config["tag"]

                    state.section       = tag
                    state.page_num      = 0
                    state.items_total   = 0
                    state.items_checked = 0
                    live.update(_build_panel(state))

                    catalog_items: list[dict] = []
                    for page_num in range(1, MAX_PAGES_PER_URL + 1):
                        page_items = await scrape_catalog_page(
                            catalog_page, url_template, page_num, state
                        )
                        live.update(_build_panel(state))
                        catalog_items.extend(page_items)
                        if not page_items:
                            break
                        if effective_limit and len(catalog_items) >= effective_limit:
                            catalog_items = catalog_items[:effective_limit]
                            break

                    total_catalog     += len(catalog_items)
                    state.items_total  = len(catalog_items)
                    live.update(_build_panel(state))

                    semaphore = asyncio.Semaphore(CONCURRENT_ITEMS)

                    async def process(
                        ci: dict,
                        _tag: str = tag,
                        _state: ScraperState = state,
                        _live: Live = live,
                    ) -> dict | None:
                        async with semaphore:
                            result = await scrape_item(context, ci, seen_ids, http, _tag, _state)
                            _live.update(_build_panel(_state))
                            return result

                    results = await asyncio.gather(*[process(ci) for ci in catalog_items])
                    new_items = [r for r in results if r is not None]
                    all_new_items.extend(new_items)

        await browser.close()

    # ── Persist ───────────────────────────────────────────────────────────────
    if effective_dry:
        outcome = f"[dim]dry-run — nothing written[/dim]"
    elif all_new_items:
        total_in_file = save_items(all_new_items)
        save_seen_ids(seen_ids)
        outcome = f"[dim]saved {len(all_new_items)} new items (file total: {total_in_file})[/dim]"
    else:
        outcome = "[dim]no new items saved[/dim]"

    # ── Final summary ─────────────────────────────────────────────────────────
    _console.print()
    _console.rule("[bold blue]DONE[/]")
    _console.print(f"  [bold]Total found[/]  {total_catalog}")
    _console.print(f"  [green]✓ Saved      {state.saved}[/]")
    _console.print(f"  [red]✗ Polish     {state.polish}[/]")
    _console.print(f"  [yellow]⚠ Skipped    {state.skipped}[/]")
    _console.print(f"  {outcome}")

    if state.polish_urls:
        sample = state.polish_urls[:5]
        _console.print()
        _console.print(
            f"  [bold]Polish items[/] [dim](sample — {len(sample)} of {len(state.polish_urls)})[/]"
        )
        for u in sample:
            _console.print(f"  [cyan]{u}[/]")

    _console.rule()
    _console.print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vinted scraper")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run without writing vinted_items.json or seen_item_ids.json",
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Process at most N items (overrides DEBUG_LIMIT in config)",
    )
    parser.add_argument(
        "--relogin", action="store_true",
        help=f"Ignore saved cookies and force a fresh login (deletes {COOKIES_FILE})",
    )
    args = parser.parse_args()
    if args.relogin:
        Path(COOKIES_FILE).unlink(missing_ok=True)
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit, relogin=args.relogin))
