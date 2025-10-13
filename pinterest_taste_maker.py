import asyncio
import json
import aiohttp
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError
from pathlib import Path

# --- CONFIGURATION ---
OUTPUT_FILE = "pinterest_favorites.json"
IMAGES_FOLDER = "pinterest_images"

# Your Pinterest board or search URLs
PINTEREST_URLS = [
    # Examples - replace with YOUR boards or searches:
    "https://cz.pinterest.com/petajezku/pants-ai/",
    "https://cz.pinterest.com/petajezku/clothes/"
    # or search URL:
]

MAX_PINS = 100  # How many pins to scrape (set to None for all)
SCROLL_PAUSE = 2  # Seconds to wait between scrolls

# Create images folder
Path(IMAGES_FOLDER).mkdir(exist_ok=True)


async def download_image(session, url, pin_id):
    """Download image and save locally."""
    try:
        image_path = Path(IMAGES_FOLDER) / f"{pin_id}.jpg"
        
        # Skip if already exists
        if image_path.exists():
            print(f"   📸 Image already exists: {pin_id}.jpg")
            return f"{IMAGES_FOLDER}/{pin_id}.jpg"
        
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                content = await response.read()
                with open(image_path, 'wb') as f:
                    f.write(content)
                print(f"   📸 Image saved: {pin_id}.jpg")
                return f"{IMAGES_FOLDER}/{pin_id}.jpg"
            else:
                print(f"   ⚠️  Image download failed: HTTP {response.status}")
    except Exception as e:
        print(f"   ⚠️  Image download failed: {e}")
    
    return None


async def scrape_pinterest_board(page, url, session, max_pins=None):
    """Scrape pins from a Pinterest board or search."""
    print(f"\n{'='*80}")
    print(f"📌 Scraping Pinterest: {url}")
    print(f"{'='*80}\n")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        
        pins_data = []
        seen_pin_ids = set()
        scroll_count = 0
        
        while True:
            # Check if we've hit the limit
            if max_pins and len(pins_data) >= max_pins:
                print(f"\n✅ Reached maximum pins limit ({max_pins})")
                break
            
            # Find all pin elements on current view
            # Pinterest uses dynamic classes, so we look for data attributes
            pin_elements = await page.query_selector_all('[data-test-id="pin"], [data-test-id="pinWrapper"], div[class*="Pj7"]')
            
            if not pin_elements:
                print("   ⚠️  No pins found. Trying alternative selector...")
                pin_elements = await page.query_selector_all('div[data-grid-item="true"]')
            
            print(f"   🔍 Found {len(pin_elements)} pin elements on page...")
            
            # Extract data from each pin
            for pin in pin_elements:
                try:
                    # Get the link to extract pin ID
                    link_elem = await pin.query_selector('a[href*="/pin/"]')
                    if not link_elem:
                        continue
                    
                    href = await link_elem.get_attribute('href')
                    if not href or '/pin/' not in href:
                        continue
                    
                    # Extract pin ID from URL
                    pin_id = href.split('/pin/')[1].split('/')[0].split('?')[0]
                    
                    # Skip if already processed
                    if pin_id in seen_pin_ids:
                        continue
                    
                    seen_pin_ids.add(pin_id)
                    
                    # Get image URL
                    img_elem = await pin.query_selector('img')
                    if not img_elem:
                        continue
                    
                    img_url = await img_elem.get_attribute('src')
                    if not img_url or 'avatar' in img_url.lower():
                        continue
                    
                    # Get alt text as description
                    alt_text = await img_elem.get_attribute('alt')
                    
                    print(f"   ✅ Found pin: {pin_id} - {alt_text[:40] if alt_text else 'No description'}...")
                    
                    # Download image
                    local_image_path = await download_image(session, img_url, pin_id)
                    
                    pins_data.append({
                        'pin_id': pin_id,
                        'url': f"https://www.pinterest.com/pin/{pin_id}/",
                        'description': alt_text or 'No description',
                        'image_url': img_url,
                        'local_image_path': local_image_path,
                        'scraped_at': datetime.now().isoformat()
                    })
                    
                    if max_pins and len(pins_data) >= max_pins:
                        break
                        
                except Exception as e:
                    continue
            
            # Check if we got new pins
            if len(pins_data) == 0:
                print("   ⚠️  No pins extracted yet. Page might not have loaded properly.")
            
            # Scroll down to load more pins
            print(f"   ⬇️  Scrolling to load more pins... (found {len(pins_data)} so far)")
            
            previous_height = await page.evaluate('document.body.scrollHeight')
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(SCROLL_PAUSE * 1000)
            
            new_height = await page.evaluate('document.body.scrollHeight')
            
            # Check if we've reached the bottom
            if new_height == previous_height:
                scroll_count += 1
                if scroll_count >= 3:  # Try 3 times before giving up
                    print("\n   📍 Reached end of page")
                    break
            else:
                scroll_count = 0
        
        return pins_data
        
    except TimeoutError:
        print(f"   ⏱️  Page timeout")
        return []
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
        import traceback
        traceback.print_exc()
        return []


async def main():
    print("🎨 Pinterest Taste Profile Scraper")
    print("="*80)
    
    if not PINTEREST_URLS or PINTEREST_URLS[0].startswith("https://www.pinterest.com/YourUsername"):
        print("❌ ERROR: Please configure your Pinterest board URLs first!")
        print("   Edit the PINTEREST_URLS list at the top of this script.")
        print("\n   Examples:")
        print("   - Your board: https://www.pinterest.com/yourusername/your-board-name/")
        print("   - Search: https://www.pinterest.com/search/pins/?q=minimalist%20fashion")
        return
    
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as pw:
            # Connect to existing Chrome with debugging port
            print("\n🚀 Connecting to Chrome (port 9222)...")
            try:
                browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
                context = browser.contexts[0]
                page = context.pages[0]
            except Exception as e:
                print(f"❌ Could not connect to Chrome!")
                print(f"Make sure Chrome is running with: chrome.exe --remote-debugging-port=9222")
                print(f"Error: {e}")
                return

            all_pins = []
            
            # Process each Pinterest URL
            for pinterest_url in PINTEREST_URLS:
                pins = await scrape_pinterest_board(page, pinterest_url, session, MAX_PINS)
                all_pins.extend(pins)
                
                # Stop if we've reached the limit across all boards
                if MAX_PINS and len(all_pins) >= MAX_PINS:
                    all_pins = all_pins[:MAX_PINS]
                    break
            
            # Save results
            if all_pins:
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_pins, f, indent=2, ensure_ascii=False)
                
                print(f"\n{'='*80}")
                print(f"✨ SCRAPING COMPLETE")
                print(f"{'='*80}")
                print(f"📊 Total pins scraped: {len(all_pins)}")
                print(f"💾 Data saved to: {OUTPUT_FILE}")
                print(f"📁 Images saved to: {IMAGES_FOLDER}/")
                print(f"{'='*80}\n")
                print(f"✅ Next step: Run 'create_taste_profile.py' to create your AI taste profile!")
            else:
                print(f"\n⚠️  No pins were scraped. Please check:")
                print("   1. You're logged into Pinterest in your browser")
                print("   2. The URLs are correct")
                print("   3. The page loaded properly")


if __name__ == "__main__":
    asyncio.run(main())