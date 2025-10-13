Start-Process powershell -ArgumentList "ngrok http 8000"
Start-Process powershell -ArgumentList "python .\webapp\backend.py; Read-Host 'Press Enter to exit'"