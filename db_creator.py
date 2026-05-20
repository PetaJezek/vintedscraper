import sqlite3
import json
import os

# Ensure this path is correct for where you run this script
DB_PATH = "webapp/vinted_clothes.db"
JSON_PATH = "vinted_items.json"
# Ensure this path is correct for where the images are relative to this script
IMAGES_FOLDER = "vinted_images"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Create ratings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
            rating INTEGER NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create items table with the 'brand' column
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY, url TEXT, scraped_at TEXT, tag TEXT, title TEXT,
            brand TEXT, price TEXT, location TEXT, size TEXT, description TEXT,
            image_url TEXT, shown INTEGER DEFAULT 0, predicted_score REAL
        )
    ''')

    conn.commit()
    conn.close()


def migrate_db():
    """Add columns that were missing from older DB versions created by backend.py."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = {row[1] for row in c.execute("PRAGMA table_info(items)").fetchall()}
    additions = {
        "url":        "TEXT",
        "scraped_at": "TEXT",
        "tag":        "TEXT",
        "location":   "TEXT",
    }
    for col, typ in additions.items():
        if col not in existing:
            c.execute(f"ALTER TABLE items ADD COLUMN {col} {typ}")
            print(f"  migrated: added column '{col}'")
    conn.commit()
    conn.close()


def populate_items():
    if not os.path.exists(JSON_PATH):
        print(f"Error: JSON file not found at {JSON_PATH}")
        return
        
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    
    if isinstance(items, dict):
        items = [items]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for item in items:
        # --- UPDATED BRAND EXTRACTION LOGIC ---
        brand_to_store = None
        
        # Strategy 1: Try to extract from the 'location' field first
        location_text = item.get("location", "")
        if location_text and "Brand" in location_text:
            lines = location_text.strip().split('\n')
            for line in lines:
                if line.startswith("Brand"):
                    brand_to_store = line.replace("Brand", "").strip()
                    break
        
        # Strategy 2 (Fallback): If no brand was found, try to get it from the title
        if not brand_to_store:
            title = item.get("title", "")
            if title:
                # Assume the first word of the title is the brand
                brand_to_store = title.split(' ')[0]
        # --- END OF UPDATED LOGIC ---

        # --- UPDATED IMAGE URL LOGIC ---
        # This creates a URL path, NOT a file path. This is crucial.
        image_path_to_store = None
        local_image_path = item.get("image_url")
        if local_image_path:
            image_filename = os.path.basename(local_image_path)
            # This must match the mount path in your backend.py!
            image_path_to_store = f"/images/{image_filename}"
        # --- END OF UPDATED IMAGE URL LOGIC ---

        c.execute('''
            INSERT INTO items (
                id, url, scraped_at, tag, title, brand, price, location, size, description, image_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                url        = excluded.url,
                scraped_at = excluded.scraped_at,
                tag        = excluded.tag,
                title      = excluded.title,
                brand      = excluded.brand,
                price      = excluded.price,
                location   = excluded.location,
                size       = excluded.size,
                description= excluded.description,
                image_url  = excluded.image_url
        ''', (
            item.get("id"), item.get("url"), item.get("scraped_at"), item.get("tag"), item.get("title"),
            brand_to_store,
            item.get("price"), item.get("location"), item.get("size"), item.get("description"),
            image_path_to_store
        ))

    conn.commit()
    conn.close()
    print(f"✅ Database populated/updated with {len(items)} items.")


if __name__ == "__main__":
    init_db()
    migrate_db()
    populate_items()