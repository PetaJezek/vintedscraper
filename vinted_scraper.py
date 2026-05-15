import asyncio
import random
import re
import json
import subprocess
import time
import threading
from collections import defaultdict
from datetime import datetime, timedelta
import aiohttp
from playwright.async_api import async_playwright, TimeoutError
from pathlib import Path
from _db import save_items_to_db, init_db

# --- OPTIMIZED CONFIGURATION ---
CONCURRENT_PAGES = 12   # More conservative to avoid rate limits
MAX_PAGES_PER_URL = 5  # Fewer pages per run to appear less aggressive
RATE_LIMIT_PAUSE = 30  # Longer initial pause
DEBUG_LIMIT = None    # How many items to process (set to None for unlimited)

# Delays to mimic human behavior
DELAY_BETWEEN_ITEMS = (2, 5)  # (min, max) seconds between item checks
DELAY_BETWEEN_PAGES = (5, 10) # (min, max) seconds between catalog page loads

OUTPUT_FILE = "vinted_items.json"
SEEN_IDS_FILE = "seen_item_ids.json"
IMAGES_FOLDER = "webapp/vinted_images"
last_country_change = None

# --- BROWSER EMULATION ---
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
]

# --- SMART COUNTRY ROTATION ---
FAST_EU_COUNTRIES = ["de", "nl", "at", "ch", "cz", "be", "fr"]  # Usually faster
ALL_EU_COUNTRIES = ["cz", "de", "at", "pl", "sk", "hu", "ch", "nl", "be", "fr", "es", "it", "pt", "se", "fi", "no", "dk"]

# Image scraping mode: 'catalog' (faster) or 'item' (slower)
IMAGE_SCRAPE_MODE = 'catalog'

# URLs to scrape with tags (add more if needed)
SCRAPE_URLS = [
    {
        "url": "https://www.vinted.cz/catalog?search_id=27178387662&catalog[]=5&size_ids[]=1647&size_ids[]=1648&page={page}",
        "tag": "Everything but pants"
    },
    {
        "url": "https://www.vinted.cz/catalog?search_id=27178387662&catalog[]=5&size_ids[]=210&size_ids[]=211&size_ids[]=1642&size_ids[]=1662&size_ids[]=1643&size_ids[]=1644&size_ids[]=1645&size_ids[]=1646&page={page}",
        "tag": "Pants"
    },
    {
        "url": "https://www.vinted.cz/catalog?search_id=27295437492&catalog[]=76&currency=CZK&page={page}&time=1759862512&price_to=550&size_ids[]=210&size_ids[]=211&size_ids[]=209",
        "tag": "Tshirts under 550 CZK"
    },
    {
        "url": "https://www.vinted.cz/catalog?search_id=27295689623&catalog[]=79&size_ids[]=210&size_ids[]=209&size_ids[]=211&page={page}&time=1759862632&price_to=1000&currency=CZK",
        "tag": "Jumpers under 1000 CZK"
    }
]

# --- DIAGNOSTICS & METRICS ---

class ScraperMetrics:
    def __init__(self):
        self.start_time = time.time()
        self.metrics = {
            'page_loads': [],
            'item_checks': [],
            'image_downloads': [],
            'rate_limits': 0,
            'polish_items': 0,
            'successful_items': 0,
            'failed_items': 0,
            'countries_used': defaultdict(int),
            'total_wait_time': 0,
        }
        self.current_country = None

    def log_page_load(self, duration, items_found):
        self.metrics['page_loads'].append({
            'duration': duration,
            'items': items_found,
            'timestamp': time.time()
        })

    def log_item_check(self, duration, success, reason=None):
        self.metrics['item_checks'].append({
            'duration': duration,
            'success': success,
            'reason': reason,
            'timestamp': time.time()
        })

        if success:
            self.metrics['successful_items'] += 1
        else:
            self.metrics['failed_items'] += 1
            if reason == 'polish':
                self.metrics['polish_items'] += 1
            elif reason == 'rate_limit':
                self.metrics['rate_limits'] += 1

    def log_image_download(self, duration, success):
        self.metrics['image_downloads'].append({
            'duration': duration,
            'success': success,
            'timestamp': time.time()
        })

    def log_rate_limit(self, wait_time):
        self.metrics['rate_limits'] += 1
        self.metrics['total_wait_time'] += wait_time

    def log_country_change(self, country):
        self.current_country = country
        self.metrics['countries_used'][country] += 1

    def get_summary(self):
        elapsed = time.time() - self.start_time

        avg_page_load = sum(p['duration'] for p in self.metrics['page_loads']) / len(self.metrics['page_loads']) if self.metrics['page_loads'] else 0
        avg_item_check = sum(i['duration'] for i in self.metrics['item_checks']) / len(self.metrics['item_checks']) if self.metrics['item_checks'] else 0
        avg_image_dl = sum(i['duration'] for i in self.metrics['image_downloads']) / len(self.metrics['image_downloads']) if self.metrics['image_downloads'] else 0

        items_per_minute = (self.metrics['successful_items'] / elapsed) * 60 if elapsed > 0 else 0
        rate_limit_percentage = (self.metrics['rate_limits'] / len(self.metrics['item_checks'])) * 100 if self.metrics['item_checks'] else 0

        return {
            'total_time': elapsed,
            'successful_items': self.metrics['successful_items'],
            'failed_items': self.metrics['failed_items'],
            'polish_items': self.metrics['polish_items'],
            'rate_limits': self.metrics['rate_limits'],
            'items_per_minute': items_per_minute,
            'rate_limit_percentage': rate_limit_percentage,
            'avg_page_load_time': avg_page_load,
            'avg_item_check_time': avg_item_check,
            'avg_image_download_time': avg_image_dl,
            'total_wait_time': self.metrics['total_wait_time'],
            'countries_used': dict(self.metrics['countries_used']),
            'productive_time': elapsed - self.metrics['total_wait_time'],
        }

    def print_summary(self):
        summary = self.get_summary()
        print("\n" + "="*80)
        print("📊 SCRAPER PERFORMANCE REPORT")
        print("="*80)
        print(f"\n⏱️  TIME:")
        print(f"   Total elapsed:     {summary['total_time']/60:.1f} minutes")
        print(f"   Productive time:   {summary['productive_time']/60:.1f} minutes")
        print(f"   Wasted (waiting):  {summary['total_wait_time']/60:.1f} minutes ({summary['total_wait_time']/summary['total_time']*100:.1f}%)")
        print(f"\n✅ SUCCESS:")
        print(f"   Items scraped:     {summary['successful_items']}")
        print(f"   Rate:              {summary['items_per_minute']:.1f} items/minute")
        print(f"\n❌ FAILURES:")
        print(f"   Polish items:      {summary['polish_items']}")
        print(f"   Rate limits:       {summary['rate_limits']} ({summary['rate_limit_percentage']:.1f}%)")
        print(f"   Other failures:    {summary['failed_items'] - summary['polish_items'] - summary['rate_limits']}")
        print(f"\n⚡ PERFORMANCE:")
        print(f"   Avg page load:     {summary['avg_page_load_time']:.2f}s")
        print(f"   Avg item check:    {summary['avg_item_check_time']:.2f}s")
        print(f"   Avg image dl:      {summary['avg_image_download_time']:.2f}s")
        print(f"\n🌍 COUNTRIES USED:")
        for country, count in sorted(summary['countries_used'].items(), key=lambda x: x[1], reverse=True):
            print(f"   {country.upper()}: {count} times")
        print("="*80 + "\n")

# Global metrics instance
metrics = ScraperMetrics()

class RealTimeMonitor:
    def __init__(self, metrics_instance, interval=30):
        self.metrics = metrics_instance
        self.interval = interval
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _monitor_loop(self):
        while self.running:
            time.sleep(self.interval)
            if self.running:
                self._print_status()

    def _print_status(self):
        summary = self.metrics.get_summary()
        print(f"\n⏱️  [{datetime.now().strftime('%H:%M:%S')}] Status:")
        print(f"   Items: {summary['successful_items']} | "
              f"Rate: {summary['items_per_minute']:.1f}/min | "
              f"Rate limits: {summary['rate_limits']} | "
              f"Time: {summary['total_time']/60:.1f}m")

def save_metrics_to_file():
    summary = metrics.get_summary()
    with open('scraper_metrics.json', 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"💾 Metrics saved to scraper_metrics.json")


# --- RATE LIMIT & FAILURE HANDLING ---

class RateLimitHandler:
    """Implements exponential backoff for rate limiting."""
    def __init__(self):
        self.consecutive_rate_limits = 0
        self.backoff_time = RATE_LIMIT_PAUSE

    async def handle_rate_limit(self):
        self.consecutive_rate_limits += 1
        wait_time = min(self.backoff_time * (2 ** (self.consecutive_rate_limits - 1)), 300) # Max 5 mins
        print(f"🔴 RATE LIMIT #{self.consecutive_rate_limits}! Waiting {wait_time:.0f}s and changing country.")
        metrics.log_rate_limit(wait_time)
        change_country_smart()
        await asyncio.sleep(wait_time)

    def reset(self):
        if self.consecutive_rate_limits > 0:
            print(f"✅ Rate limit issue resolved after {self.consecutive_rate_limits} attempt(s).")
        self.consecutive_rate_limits = 0

class CircuitBreaker:
    """Prevents scraper from running if it's failing repeatedly."""
    def __init__(self, failure_threshold=10, recovery_time=60):  # Changed from 5 to 10 failures
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.last_failure_time = None
        self.is_open = False
        self.last_success_time = time.time()

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        # Only open circuit if failures are happening rapidly
        time_since_success = time.time() - self.last_success_time
        
        if self.failure_count >= self.failure_threshold and time_since_success < 120:  # 10 failures in 2 minutes
            if not self.is_open:
                print(f"🔴 CIRCUIT BREAKER OPENED: {self.failure_count} rapid failures.")
                print(f"   Pausing for {self.recovery_time}s...")
                self.is_open = True

    def record_success(self):
        if self.is_open:
            print("🟢 CIRCUIT BREAKER CLOSED. Resuming.")
        self.failure_count = 0
        self.is_open = False
        self.last_success_time = time.time()

    async def check(self):
        """Check if circuit breaker allows operation."""
        if self.is_open:
            elapsed = time.time() - self.last_failure_time
            if elapsed < self.recovery_time:
                # Instead of raising exception, just wait
                remaining = self.recovery_time - elapsed
                print(f"   ⏸️  Circuit breaker cooling down... {remaining:.0f}s remaining")
                await asyncio.sleep(min(remaining, 10))  # Wait max 10s at a time
                return False  # Signal to skip this item
            else:
                print("🟡 CIRCUIT BREAKER attempting recovery...")
                self.failure_count = self.failure_threshold // 2  # Reset partially
                self.is_open = False
        return True  # OK to proceed

# Global handlers
rate_limit_handler = RateLimitHandler()
circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_time=300)

# --- CORE SCRAPER LOGIC ---

Path(IMAGES_FOLDER).mkdir(exist_ok=True)

def extract_item_id(url):
    match = re.search(r'/items/(\d+)', url)
    return match.group(1) if match else None

def load_seen_ids():
    try:
        with open(SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, 'w') as f:
        json.dump(list(seen_ids), f)

async def download_image(session, url, item_id):
    """Download image and save locally - with better error handling."""
    start_time = time.time()
    
    if not url:
        print(f"   ⚠️  No image URL for item {item_id}")
        metrics.log_image_download(time.time() - start_time, False)
        return None
    
    try:
        image_path = Path(IMAGES_FOLDER) / f"{item_id}.jpg"
        
        # Skip if already exists
        if image_path.exists():
            # print(f"   📸 Image already exists: {item_id}.jpg")
            metrics.log_image_download(time.time() - start_time, True)
            return str(image_path)
        
        # Download image
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                content = await response.read()
                
                # Save to file
                with open(image_path, 'wb') as f:
                    f.write(content)
                
                print(f"   📸 Image saved: {item_id}.jpg ({len(content)} bytes)")
                metrics.log_image_download(time.time() - start_time, True)
                return str(image_path)
            else:
                print(f"   ⚠️  Image download failed: HTTP {response.status} for {item_id}")
                metrics.log_image_download(time.time() - start_time, False)
                return None
                
    except asyncio.TimeoutError:
        print(f"   ⏱️  Image download timeout for {item_id}")
        metrics.log_image_download(time.time() - start_time, False)
        return None
    except Exception as e:
        print(f"   ⚠️  Image download error for {item_id}: {type(e).__name__}: {str(e)[:50]}")
        metrics.log_image_download(time.time() - start_time, False)
        return None

async def scrape_page(page, catalog_url, page_num):
    """
    Get all item links from catalog page.
    UPDATED: Better image extraction from catalog tiles.
    """
    start_time = time.time()
    url = catalog_url.format(page=page_num) if "{page}" in catalog_url else catalog_url
    print(f"\n📄 Loading catalog page {page_num}: {url[:80]}")
    
    items_from_catalog = []
    try:
        delay = random.uniform(*DELAY_BETWEEN_PAGES)
        print(f"   ...waiting {delay:.1f}s before page load...")
        await asyncio.sleep(delay)

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector('div.feed-grid', timeout=20000)

        selectors_to_try = [
            'div.feed-grid__item:not(.feed-grid__item--full-row)',
            '[data-testid="grid-item"]',
            '[data-testid="item-box"]',
        ]
        
        tiles = []
        for selector in selectors_to_try:
            tiles = await page.query_selector_all(selector)
            if tiles:
                print(f"   ✓ Found {len(tiles)} items with selector: {selector}")
                break
        
        if not tiles:
            print(f"   ⚠️  No items found on page {page_num}.")
            metrics.log_page_load(time.time() - start_time, 0)
            return []
        
        for tile in tiles:
            item_data = {}
            
            # Get item URL
            a = await tile.query_selector("a[href*='/items/']")
            if a and (href := await a.get_attribute("href")):
                item_data['url'] = "https://www.vinted.cz" + href if not href.startswith("http") else href
            else:
                continue  # Skip if no URL
            
            # Try to get image from catalog (multiple selectors)
            if IMAGE_SCRAPE_MODE == 'catalog':
                img_selectors = [
                    'img[class*="Image-module__image"]',
                    'img[class*="ItemBox-module"]',
                    'img.feed-grid__item-image',
                    'img[data-testid="item-photo"]',
                    'img',  # Last resort: any img in the tile
                ]
                
                for img_selector in img_selectors:
                    img = await tile.query_selector(img_selector)
                    if img:
                        img_url = await img.get_attribute('src')
                        if img_url and 'http' in img_url:  # Valid URL
                            item_data['image_url_from_catalog'] = img_url
                            break
            
            items_from_catalog.append(item_data)
        
        # Debug: Show how many have images
        with_images = sum(1 for item in items_from_catalog if item.get('image_url_from_catalog'))
        print(f"   Found {len(items_from_catalog)} items ({with_images} with catalog images)")
    
    except Exception as e:
        print(f"   ⚠️  Error in scrape_page: {e}")
        import traceback
        traceback.print_exc()
    
    metrics.log_page_load(time.time() - start_time, len(items_from_catalog))
    return items_from_catalog

async def check_item(context, item_from_catalog, seen_ids, session, url_tag=None):
    """
    Check item and extract data.
    UPDATED: Better image extraction from item page with multiple selectors.
    """
    start_time = time.time()
    link = item_from_catalog.get('url')
    
    if not link:
        return None
    
    item_id = extract_item_id(link)
    if not item_id:
        return None

    if item_id in seen_ids:
        return None

    page = None
    try:
        delay = random.uniform(*DELAY_BETWEEN_ITEMS)
        await asyncio.sleep(delay)

        page = await context.new_page()
        print(f"🔍 Checking item {item_id} (waited {delay:.1f}s)")
        
        try:
            await page.goto(link, wait_until="commit", timeout=30000)
            await page.wait_for_selector('h1', timeout=15000)
        except Exception as e:
            print(f"   ⏱️  Timeout loading {item_id}")
            metrics.log_item_check(time.time() - start_time, False, 'timeout')
            return None
        
        page_text = await page.evaluate('() => document.body.innerText')
        
        # Check for rate limit
        if any(phrase in page_text.lower() for phrase in ['moc návštěv', 'too many requests', 'rate limit']):
            print(f"   🔴 Rate limited on {item_id}")
            await rate_limit_handler.handle_rate_limit()
            metrics.log_item_check(time.time() - start_time, False, 'rate_limit')
            return None
        
        # Check if page exists
        if any(phrase in page_text.lower() for phrase in ['stránka neexistuje', 'page does not exist', 'nenalezeno']):
            print(f"   ⚠️  Page doesn't exist: {item_id}")
            seen_ids.add(item_id)
            metrics.log_item_check(time.time() - start_time, False, 'page_not_exist')
            return None

        # Check if Polish
        is_polish = bool(re.search(r'\b(Poland|Polska)\b', page_text, re.IGNORECASE))
        if is_polish:
            print(f"   ❌ Polish item: {item_id}")
            seen_ids.add(item_id)
            metrics.log_item_check(time.time() - start_time, False, 'polish')
            return None

        print(f"   ✅ Non-Polish - Extracting data for {item_id}...")
        
        item_data = {
            "id": item_id,
            "url": link,
            "scraped_at": datetime.now().isoformat(),
            "tag": url_tag
        }
        
        # Extract text fields
        try:
            item_data["title"] = await page.locator('h1').first.inner_text(timeout=5000)
        except:
            item_data["title"] = "Unknown"
        
        try:
            item_data["price"] = await page.locator('[data-testid="item-price"]').first.inner_text(timeout=5000)
        except:
            price_match = re.search(r'([\d\s]+\s*(?:Kč|CZK|€))', page_text)
            item_data["price"] = price_match.group(1) if price_match else "N/A"
        
        # --- MODIFICATION START ---
        # Added a check for the new HTML structure first, before falling back to the old one.
        
        # Extract Brand
        try:
            # FIRST: Try the new selector based on your screenshot
            item_data["brand"] = await page.locator('span[itemprop="name"]').first.inner_text(timeout=2000)
        except:
            try:
                # SECOND: Fallback to the original data-testid selector
                item_data["brand"] = await page.locator('[data-testid="item-brand"]').first.inner_text(timeout=2000)
            except:
                # LAST: If both fail, set to Unknown
                item_data["brand"] = "Unknown"
        
        # Extract Size
        # Extract Size
        try:
            # FIRST: Try the new, precise selector based on your screenshot
            item_data["size"] = await page.locator('div[itemprop="size"]').first.inner_text(timeout=2000)
        except:
            try:
                # SECOND: Fallback to the original data-testid selector
                item_data["size"] = await page.locator('[data-testid="item-size"]').first.inner_text(timeout=2000)
            except:
                # LAST: Fallback to regex search
                size_match = re.search(r'Size[:\s]+([A-Z0-9/\-]+)', page_text, re.IGNORECASE)
                item_data["size"] = size_match.group(1) if size_match else "N/A"
        
        try:
            item_data["description"] = (await page.locator('div[class*="item-description"]').first.inner_text(timeout=5000))[:500]
        except:
            item_data["description"] = ""

        # ===== IMAGE EXTRACTION - THE CRITICAL PART =====
        img_url = item_from_catalog.get('image_url_from_catalog')
        
        if not img_url:
            print(f"   🔍 No catalog image, searching on item page...")
            img_selectors = [
                'img[class*="web_ui__Image__image"]',
                '[data-testid="item-photo"] img',
                'img[class*="ItemPhoto"]',
                '.item-photo img',
                'picture img',
                'img[alt*="photo"]',
            ]
            
            for selector in img_selectors:
                try:
                    img_elem = await page.locator(selector).first.element_handle(timeout=3000)
                    if img_elem:
                        img_url = await img_elem.get_attribute('src')
                        if img_url and 'http' in img_url:
                            print(f"   ✓ Found image with selector: {selector}")
                            break
                except:
                    continue
            
            if not img_url:
                try:
                    all_imgs = await page.query_selector_all('img')
                    print(f"   🔍 Checking {len(all_imgs)} images on page...")
                    
                    candidates = []
                    for img in all_imgs:
                        src = await img.get_attribute('src')
                        if src and 'http' in src and 'vinted' in src:
                            try:
                                width = await img.get_attribute('width')
                                height = await img.get_attribute('height')
                                if width and height:
                                    area = int(width) * int(height)
                                    candidates.append((src, area))
                            except:
                                candidates.append((src, 0))
                    
                    if candidates:
                        img_url = max(candidates, key=lambda x: x[1])[0]
                        print(f"   ✓ Selected largest image from {len(candidates)} candidates")
                    
                except Exception as e:
                    print(f"   ⚠️  Error finding images: {e}")
        
        if img_url:
            local_path = await download_image(session, img_url, item_id)
            if local_path:
                item_data["image_url"] = local_path
                print(f"   📸 Image saved successfully")
            else:
                item_data["image_url"] = img_url
                print(f"   ℹ️  Using remote image URL")
        else:
            item_data["image_url"] = None
            print(f"   ⚠️  No image URL found at all for {item_id}")
        
        seen_ids.add(item_id)
        
        print(f"   📦 {item_data.get('title', 'N/A')[:40]} | {item_data.get('price', 'N/A')}")
        
        rate_limit_handler.reset()
        circuit_breaker.record_success()
        metrics.log_item_check(time.time() - start_time, True)
        
        return item_data
        
    except Exception as e:
        print(f"   ⚠️  Error checking item {item_id}: {type(e).__name__}: {str(e)[:100]}")
        circuit_breaker.record_failure()
        metrics.log_item_check(time.time() - start_time, False, 'error')
        return None
        
    finally:
        if page and not page.is_closed():
            try:
                await page.close()
            except:
                pass

async def process_batch(context, items_from_catalog, semaphore, seen_ids, session, url_tag=None):
    """
    Process items concurrently with circuit breaker support.
    Now skips items during cooldown instead of halting everything.
    """
    async def process_with_semaphore(item):
        async with semaphore:
            # Check circuit breaker before processing
            can_proceed = await circuit_breaker.check()
            if not can_proceed:
                print(f"   ⏭️  Skipping item due to circuit breaker cooldown")
                return None
            
            return await check_item(context, item, seen_ids, session, url_tag)
    
    tasks = [process_with_semaphore(item_data) for item_data in items_from_catalog]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out None results and exceptions
    valid_results = []
    for r in results:
        if r is not None and not isinstance(r, Exception):
            valid_results.append(r)
        elif isinstance(r, Exception):
            print(f"   ⚠️  Task exception: {type(r).__name__}")
    
    return valid_results

def save_items(items):
    try:
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = []
        
        existing.extend(items)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved {len(items)} new items (total: {len(existing)})")
    except Exception as e:
        print(f"⚠️  Save error: {e}")

def clean_items_with_missing_images(items_to_check):
    """
    Filter items - keep items WITH images OR items where image download failed
    (we still want the data even if image is missing)
    """
    print(f"\n🧹 Checking {len(items_to_check)} items for valid data...")
    
    cleaned_items = []
    missing_images = 0
    
    for item in items_to_check:
        image_path_str = item.get("image_url")
        
        # Keep item if:
        # 1. Image exists on disk, OR
        # 2. Image URL is None (download failed, but we still have item data)
        
        if image_path_str and Path(image_path_str).exists():
            # Image exists - perfect!
            cleaned_items.append(item)
        elif image_path_str is None:
            # Image download failed, but we have the data
            # Still save the item, just without local image
            print(f"   ⚠️  Keeping item {item.get('id')} without image")
            cleaned_items.append(item)
            missing_images += 1
        else:
            # Image path was set but file doesn't exist - skip
            print(f"   ❌ Removing item {item.get('id')} - missing image: {image_path_str}")
            missing_images += 1
    
    if missing_images > 0:
        print(f"   ℹ️  {missing_images} items saved without images")
    print(f"   ✅ Kept {len(cleaned_items)} items with valid data")
    
    return cleaned_items

async def main():
    monitor = RealTimeMonitor(metrics, interval=60)
    monitor.start()

    try:
        init_db()
        print("Initializing database...")
        init_db()

        seen_ids = load_seen_ids()
        print(f"📋 Already seen: {len(seen_ids)} items")
        print(f"🖼️  Image scrape mode: {IMAGE_SCRAPE_MODE.upper()}\n")
        
        async with aiohttp.ClientSession() as session:
            async with async_playwright() as pw:
                print("🚀 Launching headless browser with optimizations...")
                browser = await pw.chromium.launch(headless=True)
                
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={'width': 1920, 'height': 1080},
                    locale='cs-CZ',
                )

                await context.add_cookies([{'name': 'locale', 'value': 'cs', 'domain': '.vinted.cz', 'path': '/'}])
                await context.set_extra_http_headers({
                    'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
                    'DNT': '1',
                })
                
                await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())
                await context.route("**/*{google-analytics,facebook,doubleclick,analytics}*", lambda route: route.abort())
                
                page = await context.new_page()

                all_new_items = []
                for catalog_config in SCRAPE_URLS:
                    catalog_url, url_tag = catalog_config["url"], catalog_config["tag"]
                    print(f"\n{'='*80}\n🔍 Scraping catalog: {url_tag} - {catalog_url[:60]}...\n{'='*80}")
                    
                    all_links = []
                    for page_num in range(1, MAX_PAGES_PER_URL + 1):
                        links = await scrape_page(page, catalog_url, page_num)
                        if not links: break
                        all_links.extend(links)
                        if DEBUG_LIMIT and len(all_links) >= DEBUG_LIMIT:
                            all_links = all_links[:DEBUG_LIMIT]
                            break
                    
                    BATCH_SIZE = 50
                    for i in range(0, len(all_links), BATCH_SIZE):
                        batch_links = all_links[i:i+BATCH_SIZE]
                        print(f"\n📦 Processing batch {i//BATCH_SIZE + 1}/{(len(all_links) + BATCH_SIZE - 1)//BATCH_SIZE}...")
                        
                        semaphore = asyncio.Semaphore(CONCURRENT_PAGES)
                        new_items_batch = await process_batch(context, batch_links, semaphore, seen_ids, session, url_tag)
                        
                        if new_items_batch:
                            cleaned_batch = clean_items_with_missing_images(new_items_batch)
                            if cleaned_batch:
                                save_items(cleaned_batch)
                                save_items_to_db(cleaned_batch)
                                save_seen_ids(seen_ids)
                                all_new_items.extend(cleaned_batch)
                        
                        if i + BATCH_SIZE < len(all_links):
                            print(f"--- 💤 Break between batches (30s) ---")
                            await asyncio.sleep(30)
                
                print(f"\n{'='*80}\n✨ SCRAPING COMPLETE\n{'='*80}")
                print(f"📊 New items found in this run: {len(all_new_items)}")
                print(f"📋 Total seen items now: {len(seen_ids)}")
                
    finally:
        monitor.stop()
        metrics.print_summary()
        save_metrics_to_file()

def change_country_smart():
    global last_country_change
    current_time = datetime.now()

    if last_country_change and (current_time - last_country_change) < timedelta(minutes=1):
        return

    if random.random() < 0.75:
        new_country = random.choice(FAST_EU_COUNTRIES)
        print(f"🌍 Choosing a fast country...")
    else:
        new_country = random.choice(ALL_EU_COUNTRIES)
        print(f"🌍 Choosing from all available countries for variety...")

    metrics.log_country_change(new_country)
    print(f"   → New country: {new_country.upper()}")
    
    try:
        subprocess.run(["mullvad", "relay", "set", "location", new_country], check=True, capture_output=True, text=True)
        print("   ✓ Country set. Reconnecting...")
        subprocess.run(["mullvad", "reconnect"], check=True, capture_output=True, text=True)
        print("   ✓ Reconnected. Waiting 5s for connection to stabilize...")
        time.sleep(5)
        last_country_change = current_time
    except FileNotFoundError:
        print("   ❌ ERROR: 'mullvad' command not found. Is Mullvad CLI installed?")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ ERROR: Mullvad command failed. Stderr: {e.stderr}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Manual interruption detected. Shutting down.")