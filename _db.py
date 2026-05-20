import sqlite3
import json
from pathlib import Path

# --- CONFIGURATION ---
DB_PATH = Path("webapp/vinted_clothes.db")
JSON_PATH = Path("vinted_items.json")

def init_db():
    """Initializes the database and its tables if they don't exist."""
    # Ensure the parent directory for the DB exists
    DB_PATH.parent.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # --- FIXED ---
    # Removed the 'location' column as it's not provided by the scraper.
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            url TEXT,
            scraped_at TEXT,
            tag TEXT,
            title TEXT,
            brand TEXT,
            price TEXT,
            size TEXT,
            description TEXT,
            image_url TEXT,
            shown INTEGER DEFAULT 0,
            predicted_score REAL DEFAULT 0.5
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY,
            item_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items (id)
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully.")

def save_items_to_db(items):
    """
    Saves a list of item dictionaries to the database.
    It now trusts the data from the JSON file completely.
    """
    if not items:
        return 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    items_to_insert = []
    for item in items:
        # --- REMOVED ---
        # The entire "intelligent data cleaning" block was removed.
        # We now trust the 'brand' field directly from the JSON.
        
        # --- SIMPLIFIED ---
        # Use pathlib for clean and reliable path manipulation.
        image_path_to_store = None
        local_image_path = item.get("image_url")
        if local_image_path:
            # Creates a web-friendly path like '/images/item_id.jpg'
            image_filename = Path(local_image_path).name
            image_path_to_store = f"/vinted_images/{image_filename}" # TODO: edit images to vinted_images and then comment the edit in retrain_model.py too

        item_tuple = (
            item.get("id"),
            item.get("url"),
            item.get("scraped_at"),
            item.get("tag"),
            item.get("title"),
            item.get("brand"), # Use the brand directly from the JSON
            item.get("price"),
            item.get("size"), 
            item.get("description"),
            image_path_to_store
        )
        items_to_insert.append(item_tuple)
    
    # --- FIXED ---
    # The INSERT statement now matches the updated table structure (no 'location').
    c.executemany("""
        INSERT OR REPLACE INTO items 
        (id, url, scraped_at, tag, title, brand, price, size, description, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, items_to_insert)
    
    count = c.rowcount
    conn.commit()
    conn.close()
    
    print(f"💾 Processed {len(items)} items. {count} rows were inserted or updated in the database.")
    return count

def populate_from_json():
    """
    Standalone function to read vinted_items.json and populate the database.
    """
    if not JSON_PATH.exists():
        print(f"❌ Error: JSON file not found at {JSON_PATH}")
        return

    print(f"📖 Reading items from {JSON_PATH}...")
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        try:
            items = json.load(f)
        except json.JSONDecodeError:
            print(f"❌ Error: Could not decode JSON from {JSON_PATH}. The file might be empty or corrupt.")
            return
    
    if not items:
        print("JSON file is empty. Nothing to populate.")
        return

    if isinstance(items, dict):
        items = [items]

    print(f"Found {len(items)} items in JSON file.")
    save_items_to_db(items)

# ======================================================================
# --- MAIN FUNCTION FOR STANDALONE EXECUTION ---
# ======================================================================
if __name__ == "__main__":
    print("--- Running Database Manager Standalone ---")
    
    # Step 1: Ensure the database and tables exist
    init_db()
    
    # Step 2: Populate the database from the JSON file
    populate_from_json()
    
    print("\n--- Database population complete. ---")