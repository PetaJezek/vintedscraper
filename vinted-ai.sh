#!/bin/bash
# Linux: double-click (or run ./vinted-ai.sh) to launch the cockpit.
cd "$(dirname "$0")"
source .venv/bin/activate
python launcher.py
