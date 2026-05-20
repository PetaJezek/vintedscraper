
import json
from fastapi import FastAPI, HTTPException, Depends, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import sqlite3
import secrets
from datetime import datetime, timedelta
from typing import Optional
import hashlib
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI(title="Fashion Swipe API")

# Security
security = HTTPBearer()

# ============ CONFIGURATION ============
# Change these to your own values!
ACCESS_TOKEN = "your-secret-token-change-this"  # Simple token auth
# Or generate a random one:
# ACCESS_TOKEN = secrets.token_urlsafe(32)
# Print it and save it: print(f"Your token: {ACCESS_TOKEN}")

# Alternative: Use a password (will be hashed)
PASSWORD = "lokiloki"  # Change this!
PASSWORD_HASH = hashlib.sha256(PASSWORD.encode()).hexdigest()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ AUTH FUNCTIONS ============

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the access token"""
    token = credentials.credentials
    
    if token != ACCESS_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token

class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@app.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login with password to get access token"""
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    
    if password_hash != PASSWORD_HASH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    return LoginResponse(access_token=ACCESS_TOKEN)

# ============ DATABASE SETUP ============
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "vinted_clothes.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            title TEXT,
            brand TEXT,
            price TEXT,
            image_url TEXT,
            description TEXT,
            size TEXT,
            shown INTEGER DEFAULT 0,
            predicted_score REAL
        )
    ''')
    
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
    brand: str
    price: str
    image_url: str
    description: str = ""
    size: str = ""

# ============ ENDPOINTS (ALL PROTECTED) ============
@app.get("/api/stats")
async def get_stats(token: str = Depends(verify_token)):
    """Get user rating statistics - PROTECTED"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM ratings WHERE rating = 1")
    liked = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM ratings WHERE rating = 0")
    disliked = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM items WHERE shown = 1")
    shown = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM items")
    total = c.fetchone()[0]

    conn.close()

    return {
        "liked": liked,
        "disliked": disliked,
        "total_rated": liked + disliked,
        "items_shown": shown,
        "items_remaining": total - shown
    }

@app.get("/api/next_item")
async def get_next_item(token: str = Depends(verify_token)):
    """Get next item to rate - PROTECTED"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, url, title, brand, price, image_url, description, size
        FROM items
        WHERE shown = 0
        ORDER BY predicted_score DESC, RANDOM()
        LIMIT 1
    """)

    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="No more items")

    return {
    "id": row[0],
    "url": row[1],          # <<< ADD THIS LINE
    "title": row[2],
    "brand": row[3],
    "price": row[4],
    "image": row[5],
    "description": row[6],
    "size": row[7]
}

@app.post("/api/rate")
async def rate_item(rating: Rating, token: str = Depends(verify_token)):
    """Submit a rating for an item - PROTECTED"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "INSERT INTO ratings (item_id, rating) VALUES (?, ?)",
        (rating.item_id, rating.rating)
    )

    c.execute(
        "UPDATE items SET shown = 1 WHERE id = ?",
        (rating.item_id,)
    )

    conn.commit()

    # Check if should retrain
    c.execute("SELECT COUNT(*) FROM ratings")
    count = c.fetchone()[0]
    conn.close()

    should_retrain = count > 0 and count % 20 == 0

    if should_retrain:
        print("🔄 Triggering model retraining...")
        # retrain_model()  # Uncomment when ready

    return {"status": "success", "message": "Rating saved"}

@app.post("/api/items/import")
async def import_items(items: list[Item], token: str = Depends(verify_token)):
    """Import items from your Vinted scraper - PROTECTED"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    for item in items:
        c.execute("""
            INSERT OR REPLACE INTO items
            (id, title, brand, price, image_url, description, size, predicted_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.id, item.title, item.brand, item.price,
            item.image_url, item.description, item.size, 0.5
        ))

    conn.commit()
    conn.close()

    return {"status": "success", "imported": len(items)}

@app.get("/api/ratings/export")
async def export_ratings(token: str = Depends(verify_token)):
    """Export all ratings for model training - PROTECTED"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT r.item_id, r.rating, i.title, i.brand, i.image_url
        FROM ratings r
        JOIN items i ON r.item_id = i.id
        ORDER BY r.timestamp
    """)

    ratings = []
    for row in c.fetchall():
        ratings.append({
            "item_id": row[0],
            "rating": row[1],
            "title": row[2],
            "brand": row[3],
            "image_url": row[4]
        })

    conn.close()
    return ratings

@app.get("/api/items/all")
async def get_all_items(token: str = Depends(verify_token)):
    """Return all items for the debug viewer - PROTECTED"""
    conn = sqlite3.connect(DB_PATH)
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

POLISH_REMOVED_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), "polish_removed.json")

@app.post("/api/flag_polish")
async def flag_polish(item: dict = Body(...), token: str = Depends(verify_token)):
    """Flag an item as Polish — appends to polish_removed.json for blocklist building."""
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

@app.post("/api/retrain")
async def trigger_retrain(token: str = Depends(verify_token)):
    """Manually trigger model retraining - PROTECTED"""
    print("🧠 Starting model retraining...")
    #retrain_model()
    return {"status": "retraining_started"}
    

# =======================================================
# --- NEW SECTION TO SERVE THE REACT FRONTEND ---
# =======================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(SCRIPT_DIR, "build")

if os.path.exists(BUILD_DIR) and os.path.isdir(BUILD_DIR):
    # This line serves the static files (like CSS, JS, images) from the build folder.
    app.mount("/static", StaticFiles(directory=os.path.join(BUILD_DIR, "static")), name="static")

    # This is a "catch-all" route. If a request doesn't match any of the API routes above,
    # it will serve the main index.html file of your React app.
    app.mount("/images", StaticFiles(directory=os.path.join(SCRIPT_DIR, "vinted_images")), name="images")

    @app.get("/{full_path:path}", response_class=FileResponse)
    async def serve_react_app(full_path: str):
        return FileResponse(os.path.join(BUILD_DIR, "index.html"))
else:
    # If the build folder is not found, we keep the original root endpoint as a fallback.
    @app.get("/")
    async def root_fallback():
        return {
            "status": "Fashion Swipe API Running",
            "error": "React build folder not found. UI will not be served.",
            "script_directory": SCRIPT_DIR # A helper to see where the script thinks it is
        }


# ============ STARTUP ============
if __name__ == "__main__":
    import uvicorn

    # Generate a secure token if using default
    if ACCESS_TOKEN == "your-secret-token-change-this":
        generated_token = secrets.token_urlsafe(32)
        print("=" * 60)
        print("⚠️  WARNING: Using default token!")
        print(f"🔑 Your secure token: {generated_token}")
        print("=" * 60)
        print("Add this to your backend.py:")
        print(f'ACCESS_TOKEN = "{generated_token}"')
        print("=" * 60)

    print("🚀 Starting Fashion Swipe Backend...")
    print(f"🔒 Authentication: ENABLED")
    print(f"📱 Access: http://0.0.0.0:8000")

    uvicorn.run(app, host="0.0.0.0", port=8000)