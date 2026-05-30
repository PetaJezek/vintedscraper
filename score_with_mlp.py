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

CATEGORIES = ['pants', 'tshirt', 'jumper', 'outerwear', 'dress',
               'shorts', 'shoes', 'accessory', 'suit', 'unknown']
CAT_INDEX  = {c: i for i, c in enumerate(CATEGORIES)}


def category_onehot(tag: str | None) -> torch.Tensor:
    vec = torch.zeros(len(CATEGORIES))
    vec[CAT_INDEX.get(tag or 'unknown', CAT_INDEX['unknown'])] = 1.0
    return vec


def load_tags(db_path: str) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, tag FROM items").fetchall()
    conn.close()
    return {str(iid): (tag or 'unknown') for iid, tag in rows}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--embeddings', default=str(BASE_DIR / 'embeddings.npz'))
    p.add_argument('--mlp',        default=str(BASE_DIR / 'style_mlp.pt'))
    p.add_argument('--db',         default=str(BASE_DIR / 'webapp' / 'vinted_clothes.db'))
    p.add_argument('--alpha',      type=float, default=0.5,
                   help='Weight for FashionCLIP; DINOv2 gets (1-alpha). Default 0.5.')
    return p.parse_args()


def load_combined(embeddings_path: str, alpha: float, tags: dict[str, str]):
    """Load embeddings.npz, append category one-hot, return (item_ids, tensor)."""
    data = np.load(embeddings_path)
    item_ids  = data['item_ids'].tolist()
    clip_embs = F.normalize(torch.tensor(data['clip_embs'], dtype=torch.float32), p=2, dim=1)
    dino_embs = F.normalize(torch.tensor(data['dino_embs'], dtype=torch.float32), p=2, dim=1)
    visual    = torch.cat([alpha * clip_embs, (1.0 - alpha) * dino_embs], dim=1)  # (N, 1792)

    cat_vecs  = torch.stack([category_onehot(tags.get(iid)) for iid in item_ids])
    combined  = torch.cat([visual, cat_vecs], dim=1)   # (N, 1802)
    return item_ids, combined


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
    tags = load_tags(args.db)
    item_ids, combined = load_combined(args.embeddings, args.alpha, tags)
    print(f'  {len(item_ids)} items   embedding dim: {combined.shape[1]}  (1792 visual + 10 category)')
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
