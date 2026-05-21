# Start Chrome with remote debugging
#Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=C:\temp\chrome_debug_profile"

# Run Python script
python vinted_scraper.py

python _db.py
# Open HTML file in default browser
#Start-Process "vinted_viewer.html"

$feedbackJob = Start-Process python -ArgumentList "feedback_server.py" -PassThru
Write-Host "feedback_server running (pid $($feedbackJob.Id)) — close this window to stop"

#.\scriptAI.ps1

python clean_sold_items.py

python .\webapp\retrain_model.py


.\scriptWEB.ps1
