
import json
import os
import subprocess
from fastapi import FastAPI, HTTPException, Depends, status, Body, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import sqlite3
import secrets
import hashlib
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="Fashion Swipe API")

security = HTTPBearer()

# ============ CONFIGURATION ============
ACCESS_TOKEN = "ahoj"
PASSWORD = "lokiloki"
PASSWORD_HASH = hashlib.sha256(PASSWORD.encode()).hexdigest()

ITEMS_TO_RETRAIN = 100

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(SCRIPT_DIR, "vinted_clothes.db")
POLISH_REMOVED_FILE = os.path.join(ROOT_DIR, "polish_removed.json")

# ============ AUTH ============

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != ACCESS_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})
    return credentials.credentials

class LoginRequest(BaseModel):
    password: str

@app.post("/api/login")
async def login(request: LoginRequest):
    if hashlib.sha256(request.password.encode()).hexdigest() != PASSWORD_HASH:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    return {"access_token": ACCESS_TOKEN, "token_type": "bearer"}

# ============ DATABASE SETUP ============

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL,
        rating INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        brand TEXT,
        price TEXT,
        image_url TEXT,
        description TEXT,
        size TEXT,
        tag TEXT,
        scraped_at TEXT,
        shown INTEGER DEFAULT 0,
        predicted_score REAL
    )''')
    # Add sold column if it doesn't exist yet (safe to run on old DBs)
    try:
        c.execute("ALTER TABLE items ADD COLUMN sold INTEGER DEFAULT NULL")
        conn.commit()
    except Exception:
        pass  # column already exists
    conn.commit()
    conn.close()

init_db()

# ============ MODELS ============

class Rating(BaseModel):
    item_id: str
    rating: int

class Item(BaseModel):
    id: str
    title: str
    brand: str = ""
    price: str = ""
    image_url: str = ""
    description: str = ""
    size: str = ""

# ============ API ENDPOINTS ============

@app.get("/api/stats")
async def get_stats(token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM ratings WHERE rating = 1")
    liked = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM ratings WHERE rating = 0")
    disliked = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM ratings WHERE rating = 2")
    super_liked = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM items WHERE shown = 1")
    shown = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM items")
    total = c.fetchone()[0]
    # Score histogram (10 buckets 0-100)
    c.execute("SELECT predicted_score FROM items WHERE predicted_score IS NOT NULL")
    scores = [r[0] for r in c.fetchall()]
    histogram = [0] * 10
    for s in scores:
        bucket = min(int(s / 10), 9)
        histogram[bucket] += 1
    mx = max(histogram) or 1
    histogram_pct = [round(v / mx * 100) for v in histogram]
    # Top categories
    c.execute("SELECT tag, COUNT(*) as cnt FROM items WHERE tag IS NOT NULL AND tag != 'unknown' GROUP BY tag ORDER BY cnt DESC LIMIT 5")
    top_cats = [r[0] for r in c.fetchall()]
    conn.close()
    return {
        "total": total,
        "rated": liked + disliked + super_liked,
        "liked": liked,
        "disliked": disliked,
        "super_liked": super_liked,
        "shown": shown,
        "score_histogram": histogram_pct,
        "top_categories": top_cats,
    }

@app.get("/api/next_item")
async def get_next_item(
    order: str = Query("random"),   # random | best
    context: str = Query("training"),  # training | buy
    token: str = Depends(verify_token),
):
    conn = get_conn()
    c = conn.cursor()

    order_sql = "RANDOM()" if order == "random" else "predicted_score DESC"
    where_clauses = ["shown = 0"]
    if context == "buy":
        where_clauses.append("(sold IS NULL OR sold = 0)")
    where_sql = " AND ".join(where_clauses)

    c.execute(f"""
        SELECT id, url, title, brand, price, image_url, description, size, predicted_score, tag
        FROM items
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT 1
    """)

    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No more items")

    return {
        "id": row[0],
        "url": row[1],
        "title": row[2],
        "brand": row[3],
        "price": row[4],
        "image_url": row[5],
        "description": row[6],
        "size": row[7],
        "predicted_score": row[8],
        "tag": row[9],
    }

@app.post("/api/rate")
async def rate_item(rating: Rating, background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()
    # Upsert rating (replace if already rated)
    c.execute("INSERT OR REPLACE INTO ratings (item_id, rating) VALUES (?, ?)", (rating.item_id, rating.rating))
    c.execute("UPDATE items SET shown = 1 WHERE id = ?", (rating.item_id,))
    conn.commit()
    c.execute("SELECT COUNT(*) FROM ratings")
    count = c.fetchone()[0]
    conn.close()
    if count > 0 and count % ITEMS_TO_RETRAIN == 0:
        print(f"🔄 Auto-retraining at {count} ratings...")
        background_tasks.add_task(_retrain)
    return {"status": "success"}

@app.post("/api/undo")
async def undo_last(token: str = Depends(verify_token)):
    """Undo the last rating and return the item so it can be re-shown."""
    conn = get_conn()
    c = conn.cursor()
    # Get last rated item
    c.execute("SELECT item_id FROM ratings ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No ratings to undo")
    item_id = row[0]
    c.execute("DELETE FROM ratings WHERE id = (SELECT MAX(id) FROM ratings)")
    c.execute("UPDATE items SET shown = 0 WHERE id = ?", (item_id,))
    # Fetch the item to return
    c.execute("SELECT id, url, title, brand, price, image_url, description, size, predicted_score, tag FROM items WHERE id = ?", (item_id,))
    r = c.fetchone()
    conn.commit()
    conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "item": {
            "id": r[0], "url": r[1], "title": r[2], "brand": r[3],
            "price": r[4], "image_url": r[5], "description": r[6],
            "size": r[7], "predicted_score": r[8], "tag": r[9],
        }
    }

@app.get("/api/ratings")
async def get_ratings(token: str = Depends(verify_token)):
    """Return all liked items (rating >= 1) with their details."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT i.id, i.url, i.title, i.brand, i.price, i.image_url, i.size, i.tag, i.predicted_score, r.rating
        FROM ratings r
        JOIN items i ON r.item_id = i.id
        WHERE r.rating >= 1
        ORDER BY r.rating DESC, r.timestamp DESC
    """)
    items = []
    for row in c.fetchall():
        items.append({
            "id": row[0], "url": row[1], "title": row[2], "brand": row[3],
            "price": row[4], "image_url": row[5], "size": row[6], "tag": row[7],
            "predicted_score": row[8], "rating": row[9],
        })
    conn.close()
    return items

@app.post("/api/retrain")
async def trigger_retrain(background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    background_tasks.add_task(_retrain)
    return {"status": "retraining_started"}

@app.post("/api/rescore")
async def trigger_rescore(background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    background_tasks.add_task(_rescore)
    return {"status": "rescore_started"}

@app.post("/api/build_blocklist")
async def trigger_build_blocklist(background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    background_tasks.add_task(_build_blocklist)
    return {"status": "blocklist_build_started"}

@app.post("/api/check_sold")
async def trigger_check_sold(background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    """Check which items are sold by fetching their Vinted URLs."""
    background_tasks.add_task(_check_sold)
    return {"status": "check_sold_started"}

def _retrain():
    try:
        from retrain_model import retrain_and_predict
        retrain_and_predict()
    except Exception as e:
        print(f"Retrain error: {e}")

def _rescore():
    try:
        result = subprocess.run(
            ["python", os.path.join(ROOT_DIR, "ai_style_scorer.py"),
             "--scraped-items", os.path.join(ROOT_DIR, "vinted_items.json"),
             "--output", os.path.join(ROOT_DIR, "scored_items.json")],
            cwd=ROOT_DIR, capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Rescore error: {result.stderr}")
    except Exception as e:
        print(f"Rescore error: {e}")

def _build_blocklist():
    try:
        result = subprocess.run(
            ["python", os.path.join(ROOT_DIR, "build_polish_blocklist.py")],
            cwd=ROOT_DIR, capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Blocklist error: {result.stderr}")
    except Exception as e:
        print(f"Blocklist error: {e}")

def _check_sold():
    """Fetch each item's Vinted URL and mark sold if it 404s or redirects away."""
    import urllib.request
    import urllib.error
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, url FROM items WHERE url IS NOT NULL AND (sold IS NULL)")
    rows = c.fetchall()
    print(f"🔍 Checking {len(rows)} items for sold status...")
    updated = 0
    for item_id, url in rows:
        if not url:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=8)
            # If page loads and contains "sold" signal — mark sold
            body = resp.read(4096).decode("utf-8", errors="ignore").lower()
            is_sold = "item-sold" in body or '"is_closed":true' in body or "sold-banner" in body
            c.execute("UPDATE items SET sold = ? WHERE id = ?", (1 if is_sold else 0, item_id))
            updated += 1
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                c.execute("UPDATE items SET sold = 1 WHERE id = ?", (item_id,))
                updated += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    print(f"✅ Sold check done — updated {updated} items")

@app.post("/api/flag_polish")
async def flag_polish(item: dict = Body(...), token: str = Depends(verify_token)):
    existing: list = []
    try:
        with open(POLISH_REMOVED_FILE, encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    ids = {str(i.get("id")) for i in existing}
    if str(item.get("id")) not in ids:
        existing.append(item)
        with open(POLISH_REMOVED_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    return {"status": "saved", "total_flagged": len(existing)}

@app.post("/api/items/import")
async def import_items(items: list[Item], token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()
    for item in items:
        c.execute("""
            INSERT OR REPLACE INTO items (id, title, brand, price, image_url, description, size, predicted_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (item.id, item.title, item.brand, item.price, item.image_url, item.description, item.size, 0.5))
    conn.commit()
    conn.close()
    return {"status": "success", "imported": len(items)}

@app.get("/api/items/all")
async def get_all_items(token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, url, title, brand, price, image_url, size, tag, scraped_at, shown, predicted_score
        FROM items
        ORDER BY predicted_score DESC NULLS LAST, scraped_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "url": r[1], "title": r[2], "brand": r[3],
            "price": r[4], "image_url": r[5], "size": r[6], "tag": r[7],
            "scraped_at": r[8], "shown": bool(r[9]),
            "predicted_score": r[10],
            "ai_score": (r[10] * 100) if r[10] is not None else None,
        }
        for r in rows
    ]

# ============ STATIC FILES ============

# Images served at /images/
IMAGES_DIR = os.path.join(SCRIPT_DIR, "vinted_images")
if os.path.isdir(IMAGES_DIR):
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# React SPA — serve from webapp/build/
BUILD_DIR = os.path.join(SCRIPT_DIR, "build")

if os.path.isdir(BUILD_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(BUILD_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_spa(full_path: str):
        requested = os.path.join(BUILD_DIR, full_path)
        if os.path.isfile(requested):
            return FileResponse(requested)
        return FileResponse(os.path.join(BUILD_DIR, "index.html"))
else:
    @app.get("/")
    async def root_fallback():
        return {"status": "Fashion Swipe API running", "note": "Build the React app and copy dist/ to webapp/build/"}

# ============ STARTUP ============
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Fashion Swipe Backend on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
