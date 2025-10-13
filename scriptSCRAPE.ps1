# Start Chrome with remote debugging
#Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=C:\temp\chrome_debug_profile"

# Run Python script
python vinted_scraper.py

python db_creator.py
# Open HTML file in default browser
Start-Process "vinted_viewer.html"

scriptWEB.ps1
scriptAI.ps1