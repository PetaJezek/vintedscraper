#!/bin/bash

# Start Chrome with remote debugging (Linux equivalent)
# google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome_debug_profile &

# Run Python scripts
python vinted_scraper.py
python db_creator.py

# Open HTML file in default browser (xdg-open is standard for Linux)
xdg-open vinted_viewer.html

# Call the other scripts
bash scriptWEB.sh
bash scriptAI.sh
