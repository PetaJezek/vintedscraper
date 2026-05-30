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
import random
import re
import subprocess
import time
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

MAX_PAGES_PER_URL = 20                  # catalog pages per search URL
DEBUG_LIMIT       = 10                  # max items to process (None = unlimited)
CONCURRENT_ITEMS  = 2                   # parallel item-page workers
RATE_LIMIT_PAUSE  = 40                  # seconds to sleep on rate-limit
CATALOG_WAIT_MS   = 3000               # ms to wait after catalog page loads
ITEM_WAIT_MS      = 3000               # ms to wait after item page loads

IMAGE_SCRAPE_MODE = 'catalog'           # 'catalog' = thumbnail from tile
                                        # 'item'    = full image from item page

# ── Debug / dry-run flags ─────────────────────────────────────────────────────
DRY_RUN               = False            # set False to write output files
SAVE_PASSED_HTML      = True           # save HTML for items that pass the filter
SAVE_FAILED_HTML      = False           # save catalog HTML when no items found ── VPN (Mullvad) rotation on rate-limit ─────────────────────────────────────
VPN_COUNTRIES = ["cz", "de", "at", "sk", "hu", "ch", "nl"]

# ── Search URLs (fallback — edit scraper_config.txt instead) ─────────────────
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

FILTER_POLISH = False   # overridden by scraper_config.txt


def _load_scraper_config() -> None:
    """Read scraper_config.txt and override SCRAPE_URLS, MAX_PAGES_PER_URL, FILTER_POLISH."""
    global SCRAPE_URLS, MAX_PAGES_PER_URL, FILTER_POLISH
    config_path = Path("scraper_config.txt")
    if not config_path.exists():
        return

    urls: list[dict] = []
    for raw in config_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line and not line.startswith("http"):
            key, _, val = line.partition("=")
            key, val = key.strip().lower(), val.strip().lower()
            if key == "filter_polish":
                FILTER_POLISH = val in ("yes", "true", "1")
            elif key == "max_pages":
                try:
                    MAX_PAGES_PER_URL = int(val)
                except ValueError:
                    pass

        elif line.startswith("http"):
            url_part = line.split("#")[0].strip()
            tag      = line.split("#")[1].strip() if "#" in line else url_part
            if "{page}" not in url_part:
                sep = "&" if "?" in url_part else "?"
                url_part += f"{sep}page={{page}}"
            urls.append({"url": url_part, "tag": tag})

    if urls:
        SCRAPE_URLS = urls


_load_scraper_config()

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

_BLOCKLIST_FILE = Path("polish_blocklist.json")


def _load_polish_indicators() -> list[str]:
    indicators = list(POLISH_INDICATORS)
    if _BLOCKLIST_FILE.exists():
        try:
            words = json.loads(_BLOCKLIST_FILE.read_text(encoding="utf-8"))
            indicators.extend(words)
            _console.print(f"[dim]Loaded {len(words)} words from {_BLOCKLIST_FILE}[/]")
        except Exception:
            pass
    return indicators


def is_polish(page_text: str, indicators: list[str] = POLISH_INDICATORS) -> tuple[bool, str]:
    lower = page_text.lower()
    for indicator in indicators:
        if indicator.lower() in lower:
            return True, indicator
    return False, ""


# ══════════════════════════════════════════════════════════════════════════════
# TERMINAL UI
# ══════════════════════════════════════════════════════════════════════════════

_console = Console()


_SAVED_MSGS = [
    "finding the best drip",
    "ooh this one's giving main character energy",
    "yeah okay, this one slaps",
    "certified fit check passed",
    "your wardrobe will thank you",
    "now we're talking",
    "this is the one",
    "adding to the drip collection",
    "páni, to je pecka!",                           # CZ: wow, that's a banger!
    "to si musíš vzít",                             # CZ: you have to wear this
    "fashion fades, style is eternal — YSL",        # proverb
]
_POLISH_MSGS = [
    "you wouldn't wear this",
    "hard pass, moving on",
    "not today bestie",
    "the vibes are off",
    "this ain't it chief",
    "to bych si nevzal ani zadarmo",                # CZ: I wouldn't take this even for free
    "to vyzerá ako od babičky",                     # SK: looks like it's from grandma's
]
_SEEN_MSGS = [
    "already seen this one, next",
    "been there, scrolled that",
    "old news, keeping it moving",
    "co bylo, bylo",                                # CZ: what's done is done
]
_SKIPPED_MSGS = [
    "vinted is being shy",
    "connection issues, skipping",
    "clothes make the man — but this page won't load",
]
_CATALOG_MSGS = [
    "browsing the catalog",
    "scanning the racks",
    "flipping through the fits",
    "window shopping",
    "šetříme vám čas",                             # CZ: saving you time
]

_MSG_MIN_SECS = 4.0


@dataclass
class ScraperState:
    section: str = ""
    page_num: int = 0
    section_limit: int | None = None  # save limit per URL
    limit: int | None = None          # overall limit = section_limit * num_urls
    # global totals (accumulate across all sections)
    saved: int = 0
    polish: int = 0
    skipped: int = 0
    already_seen: int = 0
    # current-section totals (reset per section)
    section_total: int = 0
    section_saved: int = 0
    section_polish: int = 0
    section_skipped: int = 0
    section_seen: int = 0
    section_checked: int = 0
    polish_urls: list = field(default_factory=list)
    status_msg: str = ""
    fun_message: str = _CATALOG_MSGS[0]
    message_set_at: float = field(default_factory=time.time)


def _set_message(state: ScraperState, msg: str) -> None:
    now = time.time()
    if now - state.message_set_at >= _MSG_MIN_SECS:
        state.fun_message    = msg
        state.message_set_at = now


_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _spinner() -> str:
    return _SPINNER_FRAMES[int(time.time() * 8) % len(_SPINNER_FRAMES)]


def _dots() -> str:
    n = int(time.time() * 2) % 3 + 1
    return "·" * n + " " * (3 - n)


def _bounce_bar(width: int = 34) -> str:
    """Sweeping lit blob for no-limit / indeterminate mode."""
    p = (time.time() % 2.5) / 2.5 * 2   # 0 → 2
    if p > 1:
        p = 2 - p                         # bounce back 1 → 0
    center = int(p * (width - 1))
    row = []
    for i in range(width):
        d = abs(i - center)
        row.append("█" if d == 0 else "▓" if d <= 2 else "▒" if d <= 4 else "░")
    return "".join(row)


def _bar(done: int, total: int, width: int = 34) -> tuple[str, int]:
    total  = max(total, 1)
    filled = min(int(width * done / total), width)
    pct    = min(int(100 * done / total), 100)
    return "█" * filled + "░" * (width - filled), pct


def _build_panel(state: ScraperState) -> Panel:
    t = Text()
    t.append("\n")
    t.append(f"  {state.section}", style="bold cyan")
    if state.page_num:
        t.append(f"  ·  fetching catalog page {state.page_num}", style="dim")
    t.append("\n\n")

    if state.section_limit:
        # section bar — section_saved / section_limit (resets each URL)
        s_bar, s_pct = _bar(state.section_saved, state.section_limit)
        t.append(f"  {s_bar}  ", style="cyan")
        t.append(f"({s_pct}%)", style="dim")
        t.append("  this section\n")

        # overall bar — total saved / overall limit (all URLs combined)
        g_bar, g_pct = _bar(state.saved, state.limit or 1)
        t.append(f"  {g_bar}  ", style="green")
        t.append(f"({g_pct}%)", style="dim")
        t.append("  overall\n\n")
    else:
        # no limit — bouncing sweep + running counts
        t.append(f"  {_bounce_bar()}  ", style="cyan")
        t.append(f"✓ {state.section_saved} this section", style="dim")
        t.append("  |  ", style="dim")
        t.append(f"✓ {state.saved} overall\n\n", style="green")

    t.append("  ✓ saved  ", style="dim")
    t.append(f"{state.saved:<5d}", style="bold green")
    t.append("  ✗ polish  ", style="dim")
    t.append(f"{state.polish:<5d}", style="bold red")
    t.append("  ⚠ skipped  ", style="dim")
    t.append(f"{state.skipped:<5d}", style="bold yellow")
    t.append("  ↩ seen  ", style="dim")
    t.append(f"{state.already_seen}", style="bold blue")
    t.append("\n")

    spin = _spinner()
    dots = _dots()
    if state.status_msg:
        t.append(f"\n  {spin}  {state.status_msg}{dots}\n", style="dim italic")
    elif state.fun_message:
        base = state.fun_message.rstrip(". ")
        t.append(f"\n  {spin}  {base}{dots}\n", style="dim italic")

    return Panel(
        t,
        title="[bold blue] VINTED SCRAPER [/]",
        border_style="blue",
        padding=(0, 1),
    )


class _LivePanel:
    """Renderable that rebuilds itself on every Live tick so animations run continuously."""
    def __init__(self, state: ScraperState) -> None:
        self._state = state

    def __rich__(self):
        return _build_panel(self._state)


def _section_summary(state: ScraperState) -> str:
    saved   = state.section_saved
    polish  = state.section_polish
    skipped = state.section_skipped
    seen    = state.section_seen
    total   = state.section_total
    return (
        f"[bold cyan]✓ {state.section}[/]  [dim]—[/]  "
        f"[dim]{total} items[/]  "
        f"[green]✓ {saved} saved[/]  "
        f"[red]✗ {polish} polish[/]  "
        f"[yellow]⚠ {skipped} skipped[/]  "
        f"[blue]↩ {seen} seen[/]"
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
    polish_indicators: list[str] = POLISH_INDICATORS,
) -> dict | None:
    url     = catalog_item["url"]
    item_id = extract_item_id(url)

    if not item_id or item_id in seen_ids:
        state.already_seen   += 1
        state.section_seen   += 1
        
        state.section_checked += 1
        _set_message(state, random.choice(_SEEN_MSGS))
        return None

    page = await context.new_page()
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(ITEM_WAIT_MS)
        except PlaywrightTimeout:
            state.skipped         += 1
            state.section_skipped += 1
            
            state.section_checked += 1
            _set_message(state, random.choice(_SKIPPED_MSGS))
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
                state.skipped         += 1
                state.section_skipped += 1
                
                state.section_checked += 1
                _set_message(state, random.choice(_SKIPPED_MSGS))
                return None

        # ── Page-gone check ────────────────────────────────────────────────
        gone_signals = ["page does not exist", "stránka neexistuje", "nenalezeno"]
        if any(s in page_text.lower() for s in gone_signals):
            seen_ids.add(item_id)
            state.skipped         += 1
            state.section_skipped += 1
            
            state.section_checked += 1
            _set_message(state, random.choice(_SKIPPED_MSGS))
            return None

        # ── Polish filter (only active when filter_polish = yes in scraper_config.txt) ──
        if FILTER_POLISH:
            polish, _ = is_polish(page_text, polish_indicators)
            if polish:
                state.polish         += 1
                state.section_polish += 1
                state.polish_urls.append(url)
                seen_ids.add(item_id)
                state.section_checked += 1
                _set_message(state, random.choice(_POLISH_MSGS))
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
        state.saved          += 1
        state.section_saved  += 1
        
        state.section_checked += 1
        _set_message(state, random.choice(_SAVED_MSGS))
        return data

    except Exception:
        state.skipped         += 1
        state.section_skipped += 1
        
        state.section_checked += 1
        _set_message(state, random.choice(_SKIPPED_MSGS))
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

    polish_indicators = _load_polish_indicators()
    section_limit = limit if limit is not None else DEBUG_LIMIT
    overall_limit = section_limit * len(SCRAPE_URLS) if section_limit else None
    effective_dry = dry_run or DRY_RUN

    seen_ids      = load_seen_ids()
    state         = ScraperState(section_limit=section_limit, limit=overall_limit)
    all_new_items: list[dict] = []
    total_catalog = 0

    async with async_playwright() as pw:
        browser, context = await ensure_session(pw, relogin=relogin)

        live_panel = _LivePanel(state)
        with Live(live_panel, refresh_per_second=20, console=_console) as live:
            async with aiohttp.ClientSession() as http:
                catalog_page = await context.new_page()

                for config in SCRAPE_URLS:
                    if overall_limit and state.saved >= overall_limit:
                        break

                    url_template = config["url"]
                    tag          = config["tag"]

                    # reset section-level counters
                    state.section         = tag
                    state.page_num        = 0
                    state.section_total   = 0
                    state.section_checked = 0
                    state.section_saved   = 0
                    state.section_polish  = 0
                    state.section_skipped = 0
                    state.section_seen    = 0
                    state.fun_message     = random.choice(_CATALOG_MSGS)
                    state.message_set_at  = 0  # force first message to show immediately

                    semaphore = asyncio.Semaphore(CONCURRENT_ITEMS)

                    # fetch one catalog page → process its items → repeat until section limit hit
                    for page_num in range(1, MAX_PAGES_PER_URL + 1):
                        if section_limit and state.section_saved >= section_limit:
                            break

                        page_items = await scrape_catalog_page(
                            catalog_page, url_template, page_num, state
                        )
                        if not page_items:
                            break

                        state.section_total += len(page_items)
                        total_catalog       += len(page_items)

                        async def process(
                            ci: dict,
                            _tag: str = tag,
                            _state: ScraperState = state,
                            _slimit: int | None = section_limit,
                            _pi: list[str] = polish_indicators,
                        ) -> dict | None:
                            async with semaphore:
                                if _slimit and _state.section_saved >= _slimit:
                                    return None
                                return await scrape_item(context, ci, seen_ids, http, _tag, _state, _pi)

                        results = await asyncio.gather(*[process(ci) for ci in page_items])
                        all_new_items.extend(r for r in results if r is not None)

                    # print frozen section summary above the live panel
                    live.console.print(_section_summary(state))

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
    _console.print(f"  [blue]↩ Already seen {state.already_seen}[/]")
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
