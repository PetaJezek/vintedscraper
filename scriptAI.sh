#!/bin/bash
# Train the MLP on accumulated ratings, then score all items.
# Run this from the terminal when you want to retrain.
# The webapp Retrain button does the same thing.
#
# Usage:
#   ./scriptAI.sh               — default alpha 0.5
#   ./scriptAI.sh --alpha 0.6   — trust FashionCLIP more

set -e
cd "$(dirname "$0")"
source .venv/bin/activate

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI PIPELINE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Compute embeddings for any new images first
echo "▶  Computing embeddings for any new images..."
python compute_embeddings.py
echo ""

if [ ! -f "train_mlp.py" ]; then
    echo "❌  train_mlp.py not found — write your training script first."
    echo "    See mlp_model.py for the StyleMLP class to use."
    echo ""
    exit 1
fi

echo "▶  Training MLP..."
python train_mlp.py
echo ""

if [ ! -f "style_mlp.pt" ]; then
    echo "❌  training finished but style_mlp.pt was not saved."
    echo "    Make sure your script ends with: torch.save(model, 'style_mlp.pt')"
    echo ""
    exit 1
fi

echo "▶  Scoring all items with new MLP..."
python score_with_mlp.py "$@"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Done. Open the app — items are ranked by your model."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
