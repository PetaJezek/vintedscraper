@echo off
REM Windows: double-click to launch the cockpit.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python launcher.py
