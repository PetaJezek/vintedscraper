#!/bin/bash
# Score all items with the trained MLP and update the database.
# Run this after training your MLP (style_mlp.pt must exist).
# Also handles first-time embedding computation if needed.
#
# Usage:
#   ./scriptAI.sh               — score with default alpha 0.5
#   ./scriptAI.sh --alpha 0.6   — trust FashionCLIP more

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI SCORER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Make sure embeddings exist (incremental — skips already-computed items)
echo "▶  Computing embeddings for any new images..."
python compute_embeddings.py
echo ""

if [ ! -f "style_mlp.pt" ]; then
    echo "⚠️  No style_mlp.pt found."
    echo ""
    echo "  Train your MLP first, then save it with:"
    echo "    torch.save(model, 'style_mlp.pt')"
    echo ""
    echo "  See mlp_model.py for the architecture to use."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    exit 1
fi

echo "▶  Scoring items with MLP..."
python score_with_mlp.py "$@"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Scoring complete. Open the app — items are ranked by score."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
