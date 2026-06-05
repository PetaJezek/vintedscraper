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
            image_url TEXT, shown INTEGER DEFAULT 0, predicted_score REAL,
            color TEXT, condition TEXT, category_path TEXT, hashtags TEXT,
            price_value REAL, currency TEXT
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
        "url":           "TEXT",
        "scraped_at":    "TEXT",
        "tag":           "TEXT",
        "location":      "TEXT",
        "color":         "TEXT",
        "condition":     "TEXT",
        "category_path": "TEXT",
        "hashtags":      "TEXT",
        "price_value":   "REAL",
        "currency":      "TEXT",
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
        # --- BRAND EXTRACTION LOGIC ---
        # Strategy 0: the scraper now extracts a real brand from the page JSON.
        brand_to_store = (item.get("brand") or "").strip() or None

        # Strategy 1 (legacy fallback): pull a "Brand …" line out of location text
        location_text = item.get("location", "")
        if not brand_to_store and location_text and "Brand" in location_text:
            for line in location_text.strip().split('\n'):
                if line.startswith("Brand"):
                    brand_to_store = line.replace("Brand", "").strip()
                    break

        # Strategy 2 (legacy fallback): first word of the title
        if not brand_to_store:
            title = item.get("title", "")
            if title:
                brand_to_store = title.split(' ')[0]
        # --- END OF BRAND LOGIC ---

        # --- UPDATED IMAGE URL LOGIC ---
        # This creates a URL path, NOT a file path. This is crucial.
        image_path_to_store = None
        local_image_path = item.get("image_url")
        if local_image_path:
            image_filename = os.path.basename(local_image_path)
            # This must match the mount path in your backend.py!
            image_path_to_store = f"/images/{image_filename}"
        # --- END OF UPDATED IMAGE URL LOGIC ---

        # Hashtags arrive as a list in the JSON — store as a comma-joined string
        hashtags = item.get("hashtags")
        hashtags_str = ", ".join(hashtags) if isinstance(hashtags, list) else (hashtags or None)

        c.execute('''
            INSERT INTO items (
                id, url, scraped_at, tag, title, brand, price, location, size, description, image_url,
                color, condition, category_path, hashtags, price_value, currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                url           = excluded.url,
                scraped_at    = excluded.scraped_at,
                tag           = excluded.tag,
                title         = excluded.title,
                brand         = excluded.brand,
                price         = excluded.price,
                location      = excluded.location,
                size          = excluded.size,
                description   = excluded.description,
                image_url     = excluded.image_url,
                color         = excluded.color,
                condition     = excluded.condition,
                category_path = excluded.category_path,
                hashtags      = excluded.hashtags,
                price_value   = excluded.price_value,
                currency      = excluded.currency
        ''', (
            item.get("id"), item.get("url"), item.get("scraped_at"), item.get("tag"), item.get("title"),
            brand_to_store,
            item.get("price"), item.get("location"), item.get("size"), item.get("description"),
            image_path_to_store,
            item.get("color"), item.get("condition"), item.get("category_path"), hashtags_str,
            item.get("price_value"), item.get("currency"),
        ))

    conn.commit()
    conn.close()
    print(f"✅ Database populated/updated with {len(items)} items.")


if __name__ == "__main__":
    init_db()
    migrate_db()
    populate_items()