"""
Clean sold items from database and delete their images (Optimized Version)

This script:
1. Checks all items in the database that are not in the ratings table.
2. Visits their Vinted URLs concurrently using Playwright.
3. If an item's page indicates it is "Sold", the item and its corresponding
   image file are deleted.
4. Includes a --dry-run mode to preview actions on a random sample of items,
   printing the URLs of items that would be deleted.
"""

import asyncio
import sqlite3
import random
import json
from pathlib import Path
from datetime import datetime
import sys

from playwright.async_api import async_playwright, TimeoutError, Error

# --- CONFIGURATION ---
DB_PATH = "webapp/vinted_clothes.db"
IMAGES_FOLDER = "webapp/vinted_images"
# Increased concurrency for faster processing. Adjust based on your system's
# capabilities and network connection to avoid being blocked.
CONCURRENT_CHECKS = 10
# Reduced delay as modern web scraping relies more on intelligent waits.
CHECK_DELAY = (0.5, 1.5)
# Timeout for network requests in milliseconds.
PAGE_TIMEOUT = 20000
# User agent to mimic a real browser.
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# Keywords to identify a sold item.
SOLD_KEYWORDS = [
    'sold', 'prodáno', 'vyprodáno', 'již není k dispozici'
]

# --- STATISTICS ---
stats = {
    'total_items_to_check': 0, 'rated_skipped': 0, 'checked': 0,
    'sold_deleted': 0, 'active_kept': 0, 'errors_kept': 0,
    'images_deleted': 0
}

def get_items_to_check(is_dry_run=False, sample_size=100):
    """
    Get all items that are NOT in the ratings table.
    For a dry run, a random sample of items is retrieved.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # Get count of rated items, which will be skipped.
        c.execute("""
            SELECT COUNT(DISTINCT item_id) FROM ratings
        """)
        rated_count = c.fetchone()[0]
        stats['rated_skipped'] = rated_count

        # Base query for unrated items.
        query = """
            SELECT i.id, i.url
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            WHERE r.item_id IS NULL AND i.url IS NOT NULL
        """
        # For a dry run, select a random sample.
        if is_dry_run:
            query += f" ORDER BY RANDOM() LIMIT {sample_size}"

        c.execute(query)
        items = c.fetchall()

        stats['total_items_to_check'] = len(items)

        print(f"📋 Found {len(items)} unrated items to check.")
        print(f"✅ {rated_count} rated items are safe and will be skipped.")

        return items
    finally:
        conn.close()


async def check_if_sold(page, url, item_id):
    """
    Check if an item is sold by visiting its URL.
    Returns: True if sold, False if active, None if an error occurred.
    """
    try:
        await asyncio.sleep(random.uniform(*CHECK_DELAY))
        print(f"🔍 Checking ID: {item_id}")

        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)

        # Efficiently check for sold status using a specific selector.
        status_element = await page.query_selector('[data-testid="item-status--content"]')
        if status_element:
            status_text = (await status_element.inner_text()).lower()
            if 'sold' in status_text:
                return True

        # Fallback to checking the entire page text if the primary selector fails.
        page_text = (await page.evaluate('() => document.body.innerText')).lower()
        if any(keyword in page_text for keyword in SOLD_KEYWORDS):
            return True

        print(f"   ✅ Active - Will be kept.")
        return False

    except TimeoutError:
        print(f"   ⏱️  Timeout error for ID: {item_id}. Item will be kept.")
        stats['errors_kept'] += 1
        return None
    except Error as e:
        print(f"   ⚠️  Playwright error for ID: {item_id}: {e}. Item will be kept.")
        stats['errors_kept'] += 1
        return None


def delete_item(item_id):
    """
    Delete an item from the database and its corresponding image file.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        if c.rowcount > 0:
            print(f"   🗑️  Deleted item {item_id} from the database.")
            stats['sold_deleted'] += 1
            # Attempt to delete the image only after successful DB deletion.
            delete_item_image(item_id)
        else:
            print(f"   ℹ️  Item {item_id} not found in the database (already deleted?).")
    except sqlite3.Error as e:
        print(f"   ⚠️  Database error for ID {item_id}: {e}")
    finally:
        conn.close()

def delete_item_image(item_id):
    """Delete an item's image file."""
    image_path = Path(IMAGES_FOLDER) / f"{item_id}.jpg"
    if image_path.exists():
        try:
            image_path.unlink()
            print(f"   🖼️  Deleted image: {image_path.name}")
            stats['images_deleted'] += 1
        except OSError as e:
            print(f"   ⚠️  Could not delete image for ID {item_id}: {e}")
    else:
        print(f"   ℹ️  Image for item {item_id} not found.")


async def process_item(context, item, semaphore, is_dry_run=False, dry_run_sold_list=None):
    """
    Processes a single item: checks if it's sold and deletes it if necessary.
    """
    item_id, url = item
    async with semaphore:
        page = await context.new_page()
        try:
            is_sold = await check_if_sold(page, url, item_id)
            stats['checked'] += 1

            if is_sold:
                stats['sold_deleted'] += 1
                if is_dry_run:
                    # In dry run, print and add to the summary list.
                    print(f"   ❌ SOLD - Would be deleted: {url}")
                    if dry_run_sold_list is not None:
                        dry_run_sold_list.append(item)
                else:
                    # In a live run, print and then delete.
                    print(f"   ❌ SOLD - Deleting item: {url}")
                    delete_item(item_id)
            elif is_sold is False:
                stats['active_kept'] += 1
        finally:
            await page.close()

def save_log():
    """Saves the statistics to a log file."""
    log_entry = {'timestamp': datetime.now().isoformat(), 'stats': stats}
    log_file = Path('cleaning_log.json')
    try:
        if log_file.exists():
            with open(log_file, 'r') as f:
                logs = json.load(f)
        else:
            logs = []
        logs.append(log_entry)
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=4)
        print(f"\n💾 Log saved to {log_file}")
    except (IOError, json.JSONDecodeError) as e:
        print(f"\n⚠️ Could not save log file: {e}")

async def run_cleanup(is_dry_run=False):
    """Main function to run the cleaning process."""
    dry_run_sold_list = []
    if is_dry_run:
        print("="*80)
        print("👀 DRY RUN MODE - No actual deletions will occur.")
        print("="*80)
        items_to_check = get_items_to_check(is_dry_run=True, sample_size=100)
    else:
        print("="*80)
        print("🧹 VINTED SOLD ITEMS CLEANER")
        print("="*80)
        items_to_check = get_items_to_check()

    if not items_to_check:
        print("\n✅ No items to check. The database is clean.")
        return

    print(f"\n🚀 Starting checks with {CONCURRENT_CHECKS} concurrent workers...")
    print("="*80)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        # Block images and other non-essential resources to speed up page loads.
        await context.route("**/*.{png,jpg,jpeg,gif,svg,css,woff2}", lambda route: route.abort())

        semaphore = asyncio.Semaphore(CONCURRENT_CHECKS)
        tasks = [process_item(context, item, semaphore, is_dry_run, dry_run_sold_list) for item in items_to_check]
        await asyncio.gather(*tasks)
        await browser.close()

    # --- Summary ---
    summary_title = "DRY RUN PREVIEW" if is_dry_run else "CLEANING SUMMARY"
    print("\n" + "="*80)
    print(f"📊 {summary_title}")
    print("="*80)
    print(f"Total Unrated Items Queried: {stats['total_items_to_check']}")
    print(f"  - Items Checked:             {stats['checked']}")
    print(f"Results:")
    if is_dry_run:
        print(f"  - Would be Deleted:          {stats['sold_deleted']}")
    else:
        print(f"  - Sold and Deleted:          {stats['sold_deleted']}")
    print(f"  - Active and Kept:           {stats['active_kept']}")
    print(f"  - Errors (Kept):             {stats['errors_kept']}")
    if not is_dry_run:
        print(f"\n  - Images Deleted:            {stats['images_deleted']}")
    
    # If it was a dry run and we found items to delete, print the summary list.
    if is_dry_run and dry_run_sold_list:
        print("\n--- Items That Would Be Deleted ---")
        for item_id, url in dry_run_sold_list:
            print(f"  - ID: {item_id}, URL: {url}")

    print("="*80)

    if not is_dry_run:
        save_log()

if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        asyncio.run(run_cleanup(is_dry_run=True))
    else:
        print("⚠️  WARNING: This script will permanently delete sold items and their images.")
        print("   Items that have been rated are safe and will not be affected.")
        print("\nTo preview which items would be deleted without making changes, run:")
        print(f"   python {sys.argv[0]} --dry-run\n")
        
        asyncio.run(run_cleanup(is_dry_run=False))
        