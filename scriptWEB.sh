#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

# Pull latest changes
echo "📦 Pulling latest..."
git pull --ff-only 2>/dev/null || echo "(no remote or already up to date)"

# Build frontend if dist is missing
if [ ! -f webapp/build/index.html ]; then
    echo "🔨 Building frontend..."
    (cd webapp-new && npm run build) && cp -r webapp-new/dist/. webapp/build/
fi

# Get local IP
LOCAL_IP=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
URL="http://${LOCAL_IP}:8000"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🌐  Vinted AI  —  $URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Print QR code if qrencode is available
if command -v qrencode &>/dev/null; then
    qrencode -t ANSIUTF8 "$URL"
else
    echo "  (tip: sudo apt install qrencode  for a QR code here)"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ctrl+C to stop"
echo ""

# Start backend (binds 0.0.0.0 so phones on the same WiFi can reach it)
cd webapp && uvicorn backend:app --host 0.0.0.0 --port 8000
