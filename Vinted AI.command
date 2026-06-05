#!/bin/bash
# macOS: double-click in Finder to launch the cockpit.
cd "$(dirname "$0")"
source .venv/bin/activate
python launcher.py
