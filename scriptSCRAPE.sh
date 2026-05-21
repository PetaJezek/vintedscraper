#!/bin/bash
# Usage:
#   ./scriptSCRAPE.sh          — full run, saves vinted_items.json
#   ./scriptSCRAPE.sh debug    — dry run, 5 items, no files written

cd "$(dirname "$0")"
source .venv/bin/activate

if [ "$1" = "debug" ]; then
    echo "=== DEBUG RUN (dry-run, limit 30) ==="
    python vinted_scraper.py #--dry-run --limit 30
    echo ""
    echo "Check debug_pages/ for saved HTML of items that passed the filter"
else
    python vinted_scraper.py
    python db_creator.py
    python feedback_server.py &
    FEEDBACK_PID=$!
    echo "feedback_server running (pid $FEEDBACK_PID) — Ctrl+C to stop"
    firefox vinted_viewer.html &
    wait $FEEDBACK_PID
fi
