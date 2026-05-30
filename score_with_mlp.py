"""
Score all items using pre-computed embeddings and your trained StyleMLP.
Updates predicted_score in the database (0.0 – 1.0).

Usage:
    python score_with_mlp.py                    # defaults
    python score_with_mlp.py --alpha 0.6        # trust FashionCLIP more
    python score_with_mlp.py --mlp my_mlp.pt    # different checkpoint

Expects:
    embeddings.npz   — from compute_embeddings.py
    style_mlp.pt     — saved with torch.save(model, 'style_mlp.pt')
"""
import argparse
import sqlite3
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path

from mlp_model import StyleMLP  # same class you use in training

BASE_DIR = Path(__file__).resolve().parent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--embeddings', default=str(BASE_DIR / 'embeddings.npz'))
    p.add_argument('--mlp',        default=str(BASE_DIR / 'style_mlp.pt'))
    p.add_argument('--db',         default=str(BASE_DIR / 'webapp' / 'vinted_clothes.db'))
    p.add_argument('--alpha',      type=float, default=0.5,
                   help='Weight for FashionCLIP; DINOv2 gets (1-alpha). Default 0.5.')
    return p.parse_args()


def load_combined(embeddings_path: str, alpha: float):
    """Load embeddings.npz and return (item_ids, combined_tensor)."""
    data = np.load(embeddings_path)
    item_ids  = data['item_ids'].tolist()
    clip_embs = torch.tensor(data['clip_embs'], dtype=torch.float32)
    dino_embs = torch.tensor(data['dino_embs'], dtype=torch.float32)

    # Re-normalise (should already be unit vectors, but be safe)
    clip_embs = F.normalize(clip_embs, p=2, dim=1)
    dino_embs = F.normalize(dino_embs, p=2, dim=1)

    combined = torch.cat([alpha * clip_embs, (1.0 - alpha) * dino_embs], dim=1)
    return item_ids, combined          # combined shape: (N, 1792)


def update_db(db_path: str, scores: dict[str, float]):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executemany(
        "UPDATE items SET predicted_score = ? WHERE id = ?",
        [(score, item_id) for item_id, score in scores.items()],
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return updated


def main():
    args = parse_args()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'Device: {device}')

    print(f'Loading embeddings from {args.embeddings}...')
    item_ids, combined = load_combined(args.embeddings, args.alpha)
    print(f'  {len(item_ids)} items   embedding dim: {combined.shape[1]}')
    print(f'  alpha={args.alpha}  (FashionCLIP {args.alpha:.0%} / DINOv2 {1-args.alpha:.0%})')

    print(f'\nLoading MLP from {args.mlp}...')
    mlp = torch.load(args.mlp, map_location=device, weights_only=False)
    mlp.eval()

    print('Scoring...')
    with torch.no_grad():
        logits = mlp(combined.to(device)).squeeze(-1)
        scores = torch.sigmoid(logits).cpu().numpy()

    scores_by_id = {iid: float(s) for iid, s in zip(item_ids, scores)}

    updated = update_db(args.db, scores_by_id)
    print(f'Updated {updated} rows in {args.db}')

    # Preview top / bottom 5
    ranked = sorted(scores_by_id.items(), key=lambda x: x[1], reverse=True)
    print('\nTop 5:')
    for iid, s in ranked[:5]:
        print(f'  {iid}  {s:.4f}')
    print('Bottom 5:')
    for iid, s in ranked[-5:]:
        print(f'  {iid}  {s:.4f}')


if __name__ == '__main__':
    main()
