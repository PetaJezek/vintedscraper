#!/bin/bash



echo "Starting ngrok on port 8000..."
ngrok http 127.0.0.1:8000 &
NGROK_PID=$!

echo "Starting Python backend..."
python ./webapp/backend.py

read -p "Press Enter to exit"
kill $NGROK_PID
