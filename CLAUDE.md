# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment setup

All Python scripts must run inside the `.venv` virtual environment:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium  # needed for scraping
```

Python 3.11 is required. The venv is at `.venv/` in the project root.

## Running the pipeline

The full pipeline runs in this order:

```bash
# 1. (Optional) Scrape Pinterest images and build taste profile
python pinterest_taste_maker.py      # requires Chrome with --remote-debugging-port=9222
python create_taste_profile.py       # produces my_taste_profile.npy and negative_profile.npy

# 2. Scrape Vinted listings
python vinted_scraper.py             # produces vinted_items.json + webapp/vinted_images/

# 3. Import into SQLite for the web UI
python db_creator.py                 # populates webapp/vinted_clothes.db

# 4. (Optional) Train a classifier
python train_style_model.py \
  --positive-folder pinterest_images \
  --negative-folder negative_images \
  --output style_classifier.joblib \
  --model-choice clip-base

# 5. AI score items
python ai_style_scorer.py \
  --scraped-items vinted_items.json \
  --output scored_items.json \
  --classifier-file style_classifier.joblib \
  --min-score 70

# 6. Start the web backend (serves React build + API)
cd webapp && uvicorn backend:app --reload --port 8000
```

The convenience shell scripts chain these steps:
- `scriptSCRAPE.sh` — scrape + db import + open viewer
- `scriptAI.sh` — Pinterest scrape + taste profile + scoring
- `scriptWEB.sh` — start ngrok tunnel + uvicorn backend

## Architecture

The project is a linear AI pipeline with a small web UI on top:

```
Pinterest images  ──► create_taste_profile.py ──► my_taste_profile.npy
                                                    negative_profile.npy
Vinted scraper    ──► vinted_items.json
                  ──► webapp/vinted_images/    ──► db_creator.py ──► vinted_clothes.db
                                                                          │
style_classifier.joblib ◄── train_style_model.py                         │
        │                                                                 │
        └──► ai_style_scorer.py ──► scored_items.json                    │
                                                                          ▼
                                                            webapp/backend.py (FastAPI)
                                                            webapp/build/  (React SPA)
```

**`style_utils.py`** is the shared library for the pipeline: model loading (`load_image_model`), image encoding (`encode_image`), category extraction (`extract_category_from_text`), and `MODEL_CONFIGS`. All pipeline scripts import from here. When adding a new embedding model, add it to `MODEL_CONFIGS` in `style_utils.py` and to the `--model-choice` choices in all CLI scripts.

**`vinted_scraper.py`** is configured at the top of the file (not via CLI flags): edit `SCRAPE_URLS`, `MAX_PAGES_PER_URL`, `IMAGE_SCRAPE_MODE`, and `RATE_LIMIT_PAUSE` directly. It uses async Playwright and writes `vinted_items.json` + images under `webapp/vinted_images/`.

**`db_creator.py`** bridges the scraper and the web UI. It reads `vinted_items.json` and writes to `webapp/vinted_clothes.db`. Image paths are stored as `/images/<filename>` URLs (matching the `/images` static mount in `backend.py`), not filesystem paths.

**`webapp/backend.py`** (FastAPI) serves:
- `/api/*` — protected endpoints (Bearer token auth; password is `lokiloki`, token is `your-secret-token-change-this` — change both before any real deployment)
- `/images/*` — static Vinted images from `webapp/vinted_images/`
- `/*` — React SPA from `webapp/build/`

The database schema has two tables: `items` (scraped metadata + `predicted_score`, `shown` flag) and `ratings` (0/1 per item). Items are served ordered by `predicted_score DESC` so highest-scoring unseen items appear first in the swipe UI.

## Key data files

| File | Producer | Consumer |
|------|----------|----------|
| `vinted_items.json` | `vinted_scraper.py` | `db_creator.py`, `ai_style_scorer.py`, `train_style_model.py` |
| `my_taste_profile.npy` | `create_taste_profile.py` | `ai_style_scorer.py` |
| `negative_profile.npy` | `create_taste_profile.py` | `ai_style_scorer.py` |
| `style_classifier.joblib` | `train_style_model.py` | `ai_style_scorer.py` |
| `scored_items.json` | `ai_style_scorer.py` | manual inspection |
| `webapp/vinted_clothes.db` | `db_creator.py` | `webapp/backend.py` |
| `seen_item_ids.json` | `vinted_scraper.py` | `vinted_scraper.py` (dedup) |

## Embedding models

Use the same `--model-choice` for training and scoring — embeddings are not cross-compatible.

- `fashionclip2` (default in scorer) — `Marqo/marqo-fashionCLIP`, best for fashion
- `fashionclip` — `patrickjohncyh/fashion-clip`
- `clip-large` — `clip-ViT-L-14` via sentence-transformers
- `clip-base` (default in trainer) — `clip-ViT-B-32` via sentence-transformers

Models are downloaded from HuggingFace on first use and cached in the default HF cache.

## Category system

Categories are keyword-matched from item text in `style_utils.py:CATEGORY_KEYWORDS`. Supported: `pants`, `tshirt`, `jumper`, `outerwear`, `dress`, `shorts`, `shoes`, `accessory`, `suit`, `unknown`. Edit `CATEGORY_KEYWORDS` there to add/refine matching.

## Roadmap / where we left off (2026-05-20)

### Completed
- `vinted_scraper.py` is working and produces `vinted_items.json` + images.
- `db_creator.py` fixed to use proper upsert (`ON CONFLICT DO UPDATE`) so re-importing never resets `shown` or `predicted_score`.
- `vinted_viewer.html` fully overhauled: dark sidebar layout, tag/size chip filters, price range, AI score slider, lazy-loaded card grid with colour-coded score badges, drag-and-drop file loading.

### Settled architecture decisions (2026-05-21)

- **No App Store** — PWA only. Friends tap "Add to Home Screen" on iPhone/Android, looks and works like a native app, free forever.
- **Local network** — each person runs the backend on their own computer (needs to be on to use the app anyway for GPU). Phone connects to computer via local WiFi.
- **Updates are automatic** — `build/` folder is committed to git. Script does `git pull` on startup → latest webapp served immediately. Friends never touch Node.js or npm.
- **QR code on script start** — `scriptWEB.sh` prints a QR code with the local IP. Scan → open → Add to Home Screen → done. One-time setup per person.
- **No Tailscale, no ngrok subscription** — local WiFi is enough since the computer needs to be on anyway.
- **Tech stack** — Vite + React, Framer Motion for swipe physics, React Router for screens, existing FastAPI backend untouched.

### Next up: Tinder-style swipe webapp (2026-05-21)

Replace the existing React SPA with a sleek mobile-first swipe app. Design goal: replace `vinted_viewer.html` for day-to-day use, feel native enough to eventually ship as a mobile app.

---

#### Swipe gestures
- **Right** → like (rating 1, store in `ratings` table)
- **Left** → dislike (rating 0)
- **Down** → super-like (rating 2 or weighted 1, visually distinct)
- **Up** → undo — go back to previous item
- Card should physically follow the finger/mouse with rotation and colour tint (green right, red left, gold down)

#### Queue modes (switchable from UI)
- **Random** — for training: pull unrated items in random order
- **Best first** — pull by `predicted_score DESC` (default recommendation mode)
- **Unseen only** — skip anything with a rating already
- **Similar to likes** — future: use embeddings to surface items close to positively-rated ones

#### Comparison / ranking mode ("which is better")
- Show N items at once (configurable, default 2–4)
- User picks the best one; runner-up gets a soft-negative signal
- Implements pairwise ELO ranking: each comparison updates relative scores
- Useful for calibrating the model when you can't tell if something is a hard like or not
- Results feed into `ratings` table as weighted pairs

#### Liked items gallery
- Full scrollable grid of everything rated positive/super-like
- Each card has a **"Open in Vinted"** button: `https://www.vinted.cz/items/{id}` — opens the Vinted app on mobile if installed, browser fallback
- Filter by category, score, date liked
- Tap to expand full detail

#### Actions / pipeline controls (accessible from UI, no terminal needed)
- **Retrain** button → POST `/api/retrain` → runs `train_style_model.py` on accumulated ratings in background, shows progress
- **Rescore** button → POST `/api/rescore` → runs `ai_style_scorer.py` to update `predicted_score` for all items
- **Build Polish blocklist** button → POST `/api/build_blocklist` → runs `build_polish_blocklist.py`
- All three show a spinner + success/error toast — no need to open a terminal

#### Profile / stats page
- Total items in DB, rated, unrated, liked, disliked, super-liked
- Model info: last trained, training set size, classifier file age
- Score distribution histogram
- Top categories in liked items
- Polish filter stats: items blocked this session, blocklist word count
- Recent activity feed

#### UI design principles
- Mobile-first, works on phone browser today (progressive enhancement toward app)
- Dark theme, glassmorphism cards, smooth spring physics on swipe
- No visible buttons during swiping — gesture-only with subtle icon hints
- Bottom nav: Swipe | Compare | Liked | Profile
- Haptic feedback via `navigator.vibrate()` on like/dislike

#### Tech approach
- Overhaul `webapp/` React SPA (don't build a new standalone HTML — keep the FastAPI backend)
- New backend endpoints needed: `/api/rescore`, `/api/build_blocklist`, `/api/ratings` (GET liked items), `/api/undo`
- `/api/next_item` needs a `?mode=random|best|unseen` query param
- Keep `feedback_server.py` (port 5000) for local file ops; `webapp/backend.py` (port 8000) for the app API
