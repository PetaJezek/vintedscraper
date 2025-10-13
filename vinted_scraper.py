import asyncio
import random
import re
import json
import subprocess
import aiohttp
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, TimeoutError
from pathlib import Path

# --- CONFIGURATION ---
CONCURRENT_PAGES = 15
OUTPUT_FILE = "vinted_items.json"
SEEN_IDS_FILE = "seen_item_ids.json"
IMAGES_FOLDER = "webapp/vinted_images"
last_country_change = None

EU_COUNTRIES = ["cz", "de", "at", "pl", "sk", "hu", "ch", "nl"]


# Image scraping mode: 'catalog' (faster, from listing page) or 'item' (slower, from item page)
IMAGE_SCRAPE_MODE = 'catalog'  # Change to 'item' to scrape from individual item pages

# URLs to scrape with tags (add more if needed)
SCRAPE_URLS = [
    {
        "url": "https://www.vinted.cz/catalog?search_id=27178387662&catalog[]=5&size_ids[]=1647&size_ids[]=1648&page={page}&time=1759588326",
        "tag": "Everything but pants"
    },
    {
        "url": "https://www.vinted.cz/catalog?search_id=27178387662&catalog[]=5&size_ids[]=210&size_ids[]=211&page={page}&time=1759588199",
        "tag": "Pants"
    },
    {
        "url": "https://www.vinted.cz/catalog?search_id=27295437492&catalog[]=76&currency=CZK&page={page}&time=1759862512&price_to=550&size_ids[]=210&size_ids[]=211&size_ids[]=209",
        "tag": "Tshirts under 550 CZK"
    },
    {
        "url": "https://www.vinted.cz/catalog?search_id=27295689623&catalog[]=79&size_ids[]=210&size_ids[]=209&size_ids[]=211&page={page}&time=1759862632&price_to=1000&currency=CZK",
        "tag": "Jumpers under 1000 CZK"
    },
    {
        "url": "https://www.vinted.cz/",
        "tag": "Main Page"
    },
]

MAX_PAGES_PER_URL = 10  # How many pages to check per URL
DEBUG_LIMIT = None  # How many items to process (set to None for unlimited)
RATE_LIMIT_PAUSE = 40  # Seconds to wait when rate limited


# Create images folder
Path(IMAGES_FOLDER).mkdir(exist_ok=True)


def extract_item_id(url):
    """Extract unique item ID from Vinted URL."""
    match = re.search(r'/items/(\d+)', url)
    return match.group(1) if match else None


def load_seen_ids():
    """Load set of already scraped item IDs."""
    try:
        with open(SEEN_IDS_FILE, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen_ids(seen_ids):
    """Save set of scraped item IDs."""
    with open(SEEN_IDS_FILE, 'w') as f:
        json.dump(list(seen_ids), f)


async def download_image(session, url, item_id):
    """Download image and save locally."""
    try:
        image_path = Path(IMAGES_FOLDER) / f"{item_id}.jpg"
        
        # Skip if already exists
        if image_path.exists():
            print(f"   📸 Image already exists: {item_id}.jpg")
            return f"{IMAGES_FOLDER}/{item_id}.jpg"
        
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                content = await response.read()
                with open(image_path, 'wb') as f:
                    f.write(content)
                print(f"   📸 Image saved: {item_id}.jpg")
                return f"{IMAGES_FOLDER}/{item_id}.jpg"
            else:
                print(f"   ⚠️  Image download failed: HTTP {response.status}")
    except Exception as e:
        print(f"   ⚠️  Image download failed: {e}")
    
    return None


async def check_item(context, item_from_catalog, seen_ids, session, url_tag=None):
    """
    Checks if item is from Poland and extracts data if not.
    **MODIFIED** to use pre-scraped data from catalog.
    """
    # --- START OF MODIFIED SECTION ---
    # We now receive a dictionary from scrape_page, not just a link
    link = item_from_catalog['url']
    # We also receive the image url from the catalog, so we rename the parameter
    image_url_from_catalog = item_from_catalog.get('image_url_from_catalog')
    # --- END OF MODIFIED SECTION ---

    item_id = extract_item_id(link)
    
    # Skip if already scraped
    if item_id in seen_ids:
        print(f"⏭️  Skipping (already seen): {item_id}")
        return None
    
    page = await context.new_page()
    try:
        await page.goto(link, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for page load
        await page.wait_for_timeout(2000)
        
        # Check for rate limit
        page_text = await page.evaluate('() => document.body.innerText')
        
        # ==========================================================
        # YOUR RATE LIMIT LOGIC IS UNCHANGED
        # ==========================================================
        if 'moc návštěv' in page_text.lower() or 'too many' in page_text.lower() or 'too much' in page_text.lower() or 'rate limit' in page_text.lower():
            print(f"⚠️  RATE LIMITED! Item {item_id} - Pausing for {RATE_LIMIT_PAUSE} seconds...")
            change_country()
            await page.close()
            await asyncio.sleep(RATE_LIMIT_PAUSE)
            page = await context.new_page()
            await page.goto(link, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            page_text = await page.evaluate('() => document.body.innerText')
            
            if 'moc návštěv' in page_text.lower() or 'too many' in page_text.lower() or 'too much' in page_text.lower() or 'rate limit' in page_text.lower():
                print(f"   ⚠️  Still rate limited after retry - NOT adding to seen_ids")
                return None
        
        # ==========================================================
        # YOUR PAGE VALIDITY LOGIC IS UNCHANGED
        # ==========================================================
        if 'page does not exist' in page_text.lower() or 'stránka neexistuje' in page_text.lower() or 'nenalezeno' in page_text.lower() or 'price n/a' in page_text.lower():
            print(f"   ⚠️  Page does not exist: {item_id}")
            return None
        
        print(f"🔍 Checking location for: {item_id}")
        
        # ==========================================================
        # YOUR POLISH CHECKING LOGIC IS COMPLETELY UNCHANGED
        # ==========================================================
        is_polish = False
        location_patterns = [
            r'([A-Za-zÀ-ž\s]+),\s*(Poland|Polska)',
            r'\b(Poland|Polska)\b',
        ]
        
        for pattern in location_patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                is_polish = True
                print(f"   ❌ Polish item")
                break
        
        if is_polish:
            seen_ids.add(item_id)
            return None
        
        # --- START OF MODIFIED DATA EXTRACTION ---
        print(f"   ✅ Non-Polish - Finalizing data...")
        
        # Start with the data we already got from the catalog
        item_data = {
            "id": item_id,
            "url": link,
            "scraped_at": datetime.now().isoformat(),
            "tag": url_tag,
            "price": item_from_catalog.get('price'),
            "size": item_from_catalog.get('size'),
            "brand": item_from_catalog.get('brand'),
        }
        
        try:
            # Only scrape data from the page if it was MISSING from the catalog
            if not item_data.get("title"):
                title_elem = await page.query_selector('h1')
                if title_elem: item_data["title"] = (await title_elem.inner_text()).strip()
            
            if not item_data.get("price"):
                price_elem = await page.query_selector('[class*="web_ui__Text__text web_ui__Text__title"]')
                if price_elem: item_data["price"] = (await price_elem.inner_text()).strip()

            if not item_data.get("brand"):
                brand_elem = await page.query_selector('[class*="brand"]')
                if brand_elem: item_data["brand"] = (await brand_elem.inner_text()).strip()

            if not item_data.get("size"):
                size_match = re.search(r'Size[:\s]+([A-Z0-9]+)', page_text, re.IGNORECASE)
                if size_match: item_data["size"] = size_match.group(1)

            # Always get description from the item page
            desc_elem = await page.query_selector('[class*="description"]')
            if desc_elem: item_data["description"] = (await desc_elem.inner_text()).strip()[:500]
            
            # Image handling logic (same as before)
            img_url = image_url_from_catalog
            if IMAGE_SCRAPE_MODE == 'item' or not img_url:
                img_elem = await page.query_selector('img[class*="web_ui__Image__image"]')
                if img_elem: img_url = await img_elem.get_attribute('src')
            
            if img_url:
                local_path = await download_image(session, img_url, item_id)
                item_data["image_url"] = local_path or img_url
            
            seen_ids.add(item_id)
            
        except Exception as e:
            print(f"   ⚠️  Extraction error: {e}")
        
        return item_data
        # --- END OF MODIFIED DATA EXTRACTION ---

    except TimeoutError:
        print(f"   ⏱️  Timeout")
        return None
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
        return None
    finally:
        await page.close()


async def process_batch(context, items_from_catalog, semaphore, seen_ids, session, url_tag=None):
    """Process items from catalog concurrently."""
    async def process_with_semaphore(item_data):
        async with semaphore:
            # The item_data dictionary is now passed directly to check_item
            return await check_item(
                context, 
                item_data, 
                seen_ids, 
                session, 
                url_tag
            )
    
    tasks = [process_with_semaphore(item_data) for item_data in items_from_catalog]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


def save_items(items):
    """Append new items to JSON file."""
    try:
        # Load existing
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except FileNotFoundError:
            existing = []
        
        # Append new
        existing.extend(items)
        
        # Save
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {len(items)} new items (total: {len(existing)})")
    except Exception as e:
        print(f"⚠️  Save error: {e}")


async def scrape_page(page, catalog_url, page_num):
    """Get all item links and available data from a catalog page."""
    url = catalog_url.format(page=page_num) if "{page}" in catalog_url else catalog_url
    print(f"\n📄 Loading page {page_num}: {url}")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        
        selectors_to_try = [
            'div.feed-grid__item:not(.feed-grid__item--full-row)', # Main selector as of late 2023/2024
            '[data-testid="grid-item"]',
            '[data-testid="item-box"]',
            'div.new-item-box__container',
        ]
        
        tiles = []
        for selector in selectors_to_try:
            tiles = await page.query_selector_all(selector)
            if tiles:
                print(f"   ✓ Found {len(tiles)} items with selector: {selector}")
                break
        
        if not tiles:
            print(f"   ⚠️  No items found with any selector")
            html = await page.content()
            with open('debug_page.html', 'w', encoding='utf-8') as f: f.write(html)
            print(f"   💾 Saved page HTML to debug_page.html for inspection")
            return []
        
        items_from_catalog = []
        for tile in tiles:
            item_data = {}
            
            # --- Extract Link ---
            a = await tile.query_selector("a[href*='/items/']")
            if a:
                href = await a.get_attribute("href")
                if href:
                    item_data['url'] = "https://www.vinted.cz" + href if not href.startswith("http") else href
            
            # Skip if no URL found
            if not item_data.get('url'):
                continue

            # --- Extract Image ---
            if IMAGE_SCRAPE_MODE == 'catalog':
                img = await tile.query_selector('img[class*="Image-module__image"]')
                if img: item_data['image_url'] = await img.get_attribute('src')

            # --- Extract Price, Size, Brand ---
            # These are often in a secondary div. Let's find them all.
            details_divs = await tile.query_selector_all("div > span, div > h4, div > div")
            for detail_div in details_divs:
                text = await detail_div.inner_text()
                if not text: continue
                
                # Price is usually the first element with currency
                if 'CZK' in text or '€' in text or '$' in text:
                    if not item_data.get('price'): item_data['price'] = text.strip()
                # Brand is often in an h4 or has a specific data-testid
                elif await detail_div.get_attribute('data-testid') == 'item-box-brand':
                     if not item_data.get('brand'): item_data['brand'] = text.strip()
                # Size is often the last piece of text
                else:
                    # This is a heuristic: size is usually a short, non-price, non-brand text
                    if len(text.split()) < 3 and not item_data.get('size'):
                         # Attempt to assign brand if it's missing and size is found
                        if not item_data.get('brand'):
                             item_data['brand'] = item_data.get('size', text.strip()) # If size was already set, use it for brand as fallback
                             item_data['size'] = text.strip()
                        else:
                             item_data['size'] = text.strip()

            items_from_catalog.append(item_data)
        
        print(f"   Found {len(items_from_catalog)} items on page.")
        return items_from_catalog
        
    except TimeoutError:
        print(f"   ⏱️  Page timeout")
        return []
    except Exception as e:
        print(f"   ⚠️  Error in scrape_page: {e}")
        import traceback
        traceback.print_exc()
        return []


async def main():
    # Load seen IDs
    seen_ids = load_seen_ids()
    print(f"📋 Already scraped: {len(seen_ids)} items")
    print(f"🖼️  Image scrape mode: {IMAGE_SCRAPE_MODE.upper()}\n")
    
    # Create aiohttp session for image downloads
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as pw:
            # Connect to existing Chrome with debugging port
            print("🚀 Connecting to Chrome (port 9222)...")
            try:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
            except Exception as e:
                print(f"❌ Could not launch browser!")
                print(f"Error: {e}")
                return

            all_new_items = []
            
            # Process each catalog URL
            for catalog_config in SCRAPE_URLS:
                catalog_url = catalog_config["url"]
                url_tag = catalog_config["tag"]
                
                print(f"\n{'='*80}")
                print(f"🔍 Scraping catalog: {url_tag} - {catalog_url[:60]}...")
                print(f"{'='*80}")
                
                # Collect links from multiple pages
                all_links = []
                for page_num in range(1, MAX_PAGES_PER_URL + 1):
                    links = await scrape_page(page, catalog_url, page_num)
                    all_links.extend(links)
                    
                    # Stop if no items found
                    if not links:
                        print(f"   No more items, stopping pagination")
                        break
                    
                    # Check debug limit
                    if DEBUG_LIMIT and len(all_links) >= DEBUG_LIMIT:
                        print(f"   🛑 DEBUG LIMIT reached ({DEBUG_LIMIT} items)")
                        all_links = all_links[:DEBUG_LIMIT]
                        break
                
                print(f"\n📊 Total items to process: {len(all_links)}")
                print(f"   Processing with {CONCURRENT_PAGES} concurrent browsers...\n")
                
                # Process items concurrently
                semaphore = asyncio.Semaphore(CONCURRENT_PAGES)
                new_items = await process_batch(context, all_links, semaphore, seen_ids, session, url_tag)
                
                all_new_items.extend(new_items)
            
            # Save results
            if all_new_items:
                save_items(all_new_items)
                save_seen_ids(seen_ids)
                print(f"✅ Saved {len(all_new_items)} items to {OUTPUT_FILE}")
            else:
                print(f"⚠️  No new items to save")
            
            # Final stats
            print(f"\n{'='*80}")
            print(f"✨ SCRAPING COMPLETE")
            print(f"{'='*80}")
            print(f"📊 New non-Polish items: {len(all_new_items)}")
            print(f"📋 Total seen items: {len(seen_ids)}")
            print(f"💾 Data saved to: {OUTPUT_FILE}")
            print(f"📁 Images saved to: {IMAGES_FOLDER}/")
            print(f"{'='*80}\n")


async def continuous_scraper(interval_minutes=30):
    """Run scraper continuously."""
    print(f"🔄 Continuous mode (every {interval_minutes} min)")
    print("Press Ctrl+C to stop\n")
    
    while True:
        try:
            print(f"\n{'='*80}")
            print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*80}\n")
            
            await main()
            
            print(f"\n💤 Sleeping {interval_minutes} minutes...")
            await asyncio.sleep(interval_minutes * 60)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopped")
            break
        except Exception as e:
            print(f"\n⚠️  Error: {e}")
            await asyncio.sleep(300)

last_country_change = None

def change_country():
    global last_country_change

    current_time = datetime.now()

    # If last_country_change exists, check if at least 1 minute has passed
    if last_country_change is not None:
        time_diff = current_time - last_country_change
        if time_diff < timedelta(minutes=1):
            print(f"⏳ Please wait {60 - int(time_diff.total_seconds())} seconds before changing country again.")
            return

    # Select new random country
    new_country = random.choice(EU_COUNTRIES)
    print(f"🌍 Changing country to: {new_country.upper()}")

    try:
        subprocess.run(["mullvad", "relay", "set", "location", new_country], check=True)
        print(f"✅ Country changed to: {new_country.upper()}")

        print("🔄 Reconnecting to apply new location...")
        subprocess.run(["mullvad", "reconnect"], check=True)

        print("✅ Reconnected successfully. Please allow a few seconds for VPN to stabilize.")
        last_country_change = current_time

    except FileNotFoundError:
        print("❌ ERROR: The 'mullvad' command was not found.")
        print("   Please ensure Mullvad VPN CLI is installed and in your system's PATH.")

    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Mullvad command failed (exit code {e.returncode}).")
    
# change the country using the mullvad api


if __name__ == "__main__":
    # Run once:
    asyncio.run(main())
    
    # Or continuous (uncomment):
    # asyncio.run(continuous_scraper(interval_minutes=30))