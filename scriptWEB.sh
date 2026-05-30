#!/bin/bash
# Start the Vinted AI web server.
# Pulls latest code, rebuilds frontend if the source is newer than the build,
# prints a QR code, then starts the FastAPI backend on port 8000.

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  VINTED AI  —  starting server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Pull latest
echo "▶  Pulling latest..."
git pull --ff-only 2>/dev/null || echo "   (no remote / already up to date)"
echo ""

# Rebuild frontend only if source is newer than the build output
NEEDS_BUILD=false
if [ ! -f "webapp/build/index.html" ]; then
    NEEDS_BUILD=true
elif [ -n "$(find webapp-new/src -newer webapp/build/index.html 2>/dev/null | head -1)" ]; then
    NEEDS_BUILD=true
elif [ "webapp-new/index.html" -nt "webapp/build/index.html" ]; then
    NEEDS_BUILD=true
fi

if [ "$NEEDS_BUILD" = true ]; then
    echo "▶  Frontend source changed — rebuilding..."
    (cd webapp-new && npm run build)
    cp -r webapp-new/dist/. webapp/build/
    echo "   ✅ Build done"
    echo ""
else
    echo "▶  Frontend up to date, skipping build."
    echo ""
fi

# Get local IP for QR code
LOCAL_IP=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
URL="http://${LOCAL_IP}:8000"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🌐  $URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if command -v qrencode &>/dev/null; then
    qrencode -t ANSIUTF8 "$URL"
else
    echo "  (tip: sudo apt install qrencode  for a QR code here)"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ctrl+C to stop"
echo ""

# Start backend — binds 0.0.0.0 so phones on the same WiFi can reach it
cd webapp && uvicorn backend:app --host 0.0.0.0 --port 8000
