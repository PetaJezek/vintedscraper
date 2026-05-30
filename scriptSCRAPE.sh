#!/bin/bash
# Scrape Vinted, import to DB, compute embeddings for new images.
# Usage:
#   ./scriptSCRAPE.sh          — full run
#   ./scriptSCRAPE.sh debug    — dry run (no files written)

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  VINTED SCRAPER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$1" = "debug" ]; then
    echo "▶  Debug run..."
    python vinted_scraper.py
    echo ""
    echo "✅ Debug done."
    exit 0
fi

echo "▶  Pulling latest..."
git pull --ff-only 2>/dev/null || echo "   (no remote / already up to date)"
echo ""

echo "▶  Scraping Vinted..."
python vinted_scraper.py
echo ""

echo "▶  Importing to database..."
python db_creator.py
echo ""

echo "▶  Computing embeddings for new images..."
python compute_embeddings.py
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Scrape complete."
echo "  Next: train your MLP, then run ./scriptAI.sh to score items."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
