# VintedScraper

## Overview

`vintedscraper` is a fashion item scraping and AI scoring pipeline for Vinted and Pinterest data. It lets you:

- scrape Vinted listings and download product images
- build a taste profile from Pinterest images
- train a binary style classifier from labeled images and ratings
- score scraped Vinted items for matching your style
- optionally use category-aware heuristics and a backend rating service

The repository is organized as a small AI pipeline rather than a polished product. Use the files below to run data collection, model training, and scoring.

---

## Contents

- `vinted_scraper.py` - scrape Vinted listings, filter by country, download images, and create `vinted_items.json`
- `pinterest_taste_maker.py` - scrape Pinterest boards/searches and save pins plus local image copies
- `create_taste_profile.py` - build positive / negative taste profiles from image folders
- `train_style_model.py` - train a binary fashion classifier from image folders and optional rated items
- `ai_style_scorer.py` - score scraped items using profile similarity or a trained classifier
- `style_utils.py` - shared utilities for image encoding, model loading, and category extraction
- `webapp/backend.py` - FastAPI backend for rating items and importing scraped items
- `requirements.txt` - Python dependencies

---

## Quick Start Examples

These examples show the fast path for using the project.

### Create a taste profile from Pinterest/negative images

```bash
source .venv/bin/activate
python create_taste_profile.py
```

### Scrape Vinted items

```bash
source .venv/bin/activate
python vinted_scraper.py
```

### Train a style classifier

```bash
python train_style_model.py \
  --positive-folder pinterest_images \
  --negative-folder negative_images \
  --output style_classifier.joblib \
  --model-choice clip-base
```

### Score scraped items

```bash
python ai_style_scorer.py \
  --scraped-items vinted_items.json \
  --output scored_items.json \
  --classifier-file style_classifier.joblib \
  --min-score 70
```

---

## Prerequisites

- Python 3.11+ (project uses `torch`, `transformers`, `sentence-transformers`, `scikit-learn`)
- `playwright` and a Chromium browser for web scraping
- optional Chrome/Chromium launched with remote debugging for Pinterest scraping

### Recommended setup

```bash
cd /home/jeza/Downloads/vintedscraper
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

---

## Data layout

The repository expects these folders and files:

- `pinterest_images/` - positive style examples from Pinterest
- `negative_images/` - negative style examples for contrast scoring
- `webapp/vinted_images/` - downloaded Vinted item images
- `vinted_items.json` - scraped item metadata from Vinted
- `my_taste_profile.npy` - saved positive taste profile
- `negative_profile.npy` - saved negative taste profile
- `style_classifier.joblib` - trained classifier saved by `train_style_model.py`
- `scored_items.json` - final scored items output from `ai_style_scorer.py`

> Note: If a taste profile file is missing, `ai_style_scorer.py` will attempt to create one automatically from `pinterest_images/` or `negative_images/`.

---

## 1) Create a taste profile

This step converts a folder of Pinterest-style images into a normalized embedding profile.

### Option A: Use existing image folders

```bash
source .venv/bin/activate
python create_taste_profile.py
```

This will create:

- `my_taste_profile.npy`
- `negative_profile.npy`

### Option B: Scrape Pinterest images first

Edit `pinterest_taste_maker.py` and fill in your board or search URLs in `PINTEREST_URLS`. Then run:

```bash
source .venv/bin/activate
python pinterest_taste_maker.py
```

After scraping, run `create_taste_profile.py` to turn downloaded Pinterest pins into a profile.

> `pinterest_taste_maker.py` expects Chrome/Chromium running with remote debugging enabled, e.g.:
> `google-chrome --remote-debugging-port=9222`

---

## 2) Scrape Vinted items

`vinted_scraper.py` is not CLI-driven. Configure the script at the top by changing:

- `SCRAPE_URLS` - search pages to crawl
- `MAX_PAGES_PER_URL` - pages to traverse
- `IMAGE_SCRAPE_MODE` - `catalog` or `item`
- `RATE_LIMIT_PAUSE` - pause time when blocked

Then run:

```bash
source .venv/bin/activate
python vinted_scraper.py
```

The scraper will produce:

- `vinted_items.json`
- `seen_item_ids.json`
- downloaded images under `webapp/vinted_images/`

---

## 3) Train a style classifier

If you want to use a supervised classifier instead of pure profile similarity, use `train_style_model.py`.

### Basic training command

```bash
source .venv/bin/activate
python train_style_model.py \
  --positive-folder pinterest_images \
  --negative-folder negative_images \
  --output style_classifier.joblib \
  --model-choice clip-base
```

### With rated scraped items

If you have a JSON export of rated items (with `image_url` or `local_image_path` and `rating` 0/1), train using that file:

```bash
python train_style_model.py \
  --positive-folder pinterest_images \
  --negative-folder negative_images \
  --ratings-json vinted_items.json \
  --output style_classifier.joblib
```

### Category-specific training

Use `--categories` to filter by category text and `--category-models` to train separate classifiers per category.

```bash
python train_style_model.py \
  --ratings-json vinted_items.json \
  --categories tshirt pants \
  --category-models
```

### Trainer options

- `--model-choice` - embedding model, one of `fashionclip`, `fashionclip2`, `clip-large`, `clip-base`
- `--output` - classifier path
- `--output-dir` - directory where category classifiers are saved
- `--classifier` - classifier type (`rf` only)
- `--test-size` - evaluation split fraction
- `--random-state` - random seed

---

## 4) Score scraped items

`ai_style_scorer.py` can score `vinted_items.json` using either:

- a trained classifier (`style_classifier.joblib`), or
- similarity to a taste profile plus optional negative profile scoring.

### Basic scoring command

```bash
source .venv/bin/activate
python ai_style_scorer.py \
  --scraped-items vinted_items.json \
  --output scored_items.json \
  --classifier-file style_classifier.joblib \
  --min-score 70
```

### If you want to skip negative profile scoring

```bash
python ai_style_scorer.py --no-negative
```

### Scoring options

- `--model-choice` - model to embed images for scoring
- `--positive-profile` - path to positive taste profile
- `--negative-profile` - path to negative taste profile
- `--min-score` - minimum score threshold
- `--classifier-file` - use a classifier if available

### Output

`scored_items.json` is written with scored item objects and includes fields such as:

- `ai_score` - final score in percent
- `style_model` - `classifier` or `similarity`
- `debug_positive` / `debug_negative` - component scores
- `category` - inferred clothing category

---

## 5) Category extraction

`style_utils.py` contains category keyword rules used by the pipeline.

Supported categories include:

- `pants`
- `tshirt`
- `jumper`
- `outerwear`
- `dress`
- `shorts`
- `shoes`
- `accessory`
- `suit`
- `unknown`

To add or refine category matching, edit `CATEGORY_KEYWORDS` in `style_utils.py`.

---

## 6) Web backend (optional)

The repository includes a FastAPI backend in `webapp/backend.py` for rating items and importing scraped data.

### Start the backend

```bash
cd webapp
uvicorn backend:app --reload --port 8000
```

### Notes

- `webapp/backend.py` uses simple bearer token auth and password hashing.
- Update `ACCESS_TOKEN` and `PASSWORD` before production use.
- The backend stores ratings and imported items in `webapp/vinted_clothes.db`.

---

## Models and embeddings

The project supports these embedding backends in `style_utils.py`:

- `fashionclip` - `patrickjohncyh/fashion-clip`
- `fashionclip2` - `Marqo/marqo-fashionCLIP`
- `clip-large` - `clip-ViT-L-14`
- `clip-base` - `clip-ViT-B-32`

Use `--model-choice` consistently during training and scoring for best results.

---

## Troubleshooting

### Dependency issues

Use the project virtual environment and install from `requirements.txt`.

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Missing profile files

If `my_taste_profile.npy` or `negative_profile.npy` are missing, run `create_taste_profile.py` after populating `pinterest_images/` or `negative_images/`.

### Playwright or browser issues

If scraping fails, install Chromium and launch the browser when required.

```bash
python -m playwright install chromium
```

### `joblib` not found

Ensure you run commands under `.venv/bin/python` or activate the virtual environment.

---

## Recommended workflow

1. Install dependencies
2. Collect or add positive images in `pinterest_images/`
3. Add negative / non-drip images in `negative_images/`
4. Run `create_taste_profile.py`
5. Scrape Vinted with `vinted_scraper.py`
6. Train the classifier with `train_style_model.py`
7. Score the scraped items with `ai_style_scorer.py`
8. Optionally inspect the results in `scored_items.json` or load them into the web backend

---

## Notes

- This repository is intended as a research / prototyping pipeline.
- The code assumes local image files and JSON metadata are present.
- Scoring quality improves when you provide real positive and negative examples and/or human ratings.

If you want, I can also add a quick `examples/` section or a shell script for the full pipeline. 