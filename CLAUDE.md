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

### Next up: main webapp overhaul (`webapp/`)

The React SPA needs to be split into three distinct modes:

1. **Training mode** — show unscored items one at a time (or in a grid), let the user like/dislike to build up a labelled dataset in the `ratings` table. This is what the current swipe UI does but should be clearly labelled as "building training data".

2. **Testing / review mode** — after running `ai_style_scorer.py`, show scored items sorted by score so the user can verify the model is picking the right things. Should allow filtering by score threshold and category. Useful for sanity-checking before a full swipe session.

3. **Swipe / recommendation mode** — the polished end-use flow: show AI-recommended items (high `predicted_score`) that haven't been seen yet, ordered by score descending. Swipe or click like/dislike. This is the main consumer-facing mode.

**Suggested approach:** add a mode switcher (top nav or sidebar tabs) to `webapp/` React app. Each mode maps to existing API endpoints; no new backend endpoints should be needed. Backend already orders by `predicted_score DESC` in `/api/next_item`.

**Backend note:** `webapp/backend.py` currently has a stub `retrain` endpoint. Eventually it should shell out to `train_style_model.py` with the accumulated `ratings` as training data, then re-run `ai_style_scorer.py` to update `predicted_score` for all items.
