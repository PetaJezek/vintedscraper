"""
Train the StyleMLP on your swipe + compare ratings.

Reads:   webapp/vinted_clothes.db   (ratings table)
         embeddings.npz              (precomputed FashionCLIP + DINOv2 vectors)
Writes:  style_mlp.pt                (trained model, ready for score_with_mlp.py)

Rating → training target:
  0  dislike    → 0.05   (model should output near 0, well below 0.3)
  1  like       → 0.80   (model should output above 0.7)
  2  superlike  → 0.95   (model should output above 0.85)
"""

import sqlite3
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from pathlib import Path

from mlp_model import StyleMLP

BASE_DIR = Path(__file__).resolve().parent

# ── config ────────────────────────────────────────────────────────────────────
ALPHA       = 0.5    # FashionCLIP weight; DINOv2 gets (1 - ALPHA)
EPOCHS      = 150
LR          = 3e-4
BATCH_SIZE  = 32
HIDDEN_DIMS = (256, 64)   # conservative for small datasets; bump to (512, 128) at 1000+ ratings
DROPOUT     = 0.3
VAL_SPLIT   = 0.15        # fraction of data held out for validation

TARGETS = {
    0: 0.05,   # dislike
    1: 0.80,   # like
    2: 0.95,   # superlike
}
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH         = BASE_DIR / 'webapp' / 'vinted_clothes.db'
EMBEDDINGS_FILE = BASE_DIR / 'embeddings.npz'
OUTPUT_FILE     = BASE_DIR / 'style_mlp.pt'


# Category order must stay fixed — it defines the one-hot encoding
CATEGORIES = ['pants', 'tshirt', 'jumper', 'outerwear', 'dress',
               'shorts', 'shoes', 'accessory', 'suit', 'unknown']
CAT_INDEX  = {c: i for i, c in enumerate(CATEGORIES)}


def category_onehot(tag: str | None) -> torch.Tensor:
    vec = torch.zeros(len(CATEGORIES))
    vec[CAT_INDEX.get(tag or 'unknown', CAT_INDEX['unknown'])] = 1.0
    return vec


def load_ratings() -> dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT item_id, rating FROM ratings").fetchall()
    conn.close()
    return {str(item_id): rating for item_id, rating in rows}


def load_tags() -> dict[str, str]:
    """item_id → category tag from the DB."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, tag FROM items").fetchall()
    conn.close()
    return {str(item_id): (tag or 'unknown') for item_id, tag in rows}


def build_dataset(alpha: float):
    ratings = load_ratings()
    tags    = load_tags()

    counts = {r: sum(1 for v in ratings.values() if v == r) for r in TARGETS}
    print(f"Ratings in DB:  dislike={counts[0]}  like={counts[1]}  superlike={counts[2]}")

    if sum(counts.values()) == 0:
        raise RuntimeError("No ratings found. Swipe some items first.")

    data      = np.load(EMBEDDINGS_FILE)
    emb_ids   = data['item_ids'].tolist()
    clip_embs = F.normalize(torch.tensor(data['clip_embs'], dtype=torch.float32), p=2, dim=1)
    dino_embs = F.normalize(torch.tensor(data['dino_embs'], dtype=torch.float32), p=2, dim=1)
    combined  = torch.cat([alpha * clip_embs, (1 - alpha) * dino_embs], dim=1)  # (N, 1792)

    X, y = [], []
    for i, item_id in enumerate(emb_ids):
        if item_id in ratings:
            cat_vec = category_onehot(tags.get(item_id))
            X.append(torch.cat([combined[i], cat_vec]))   # 1792 + 10 = 1802
            y.append(TARGETS[ratings[item_id]])

    missing = sum(1 for iid in ratings if iid not in set(emb_ids))
    if missing:
        print(f"  ⚠️  {missing} rated items have no embedding yet — run compute_embeddings.py")

    if not X:
        raise RuntimeError("No rated items found in embeddings.npz. Run compute_embeddings.py first.")

    X = torch.stack(X)
    y = torch.tensor(y, dtype=torch.float32)
    print(f"Dataset:  {len(X)} items  |  embedding dim: {X.shape[1]}  (1792 visual + 10 category)")
    return X, y


def split(X, y, val_frac):
    """Stratified-ish split: shuffle then cut."""
    idx = torch.randperm(len(X))
    cut = max(1, int(len(X) * val_frac))
    val_idx, trn_idx = idx[:cut], idx[cut:]
    return X[trn_idx], y[trn_idx], X[val_idx], y[val_idx]


def class_weights(y: torch.Tensor) -> torch.Tensor:
    """Inverse-frequency weights so rare superlikes aren't drowned out."""
    w = torch.ones(len(y))
    for target in TARGETS.values():
        mask  = (y == target)
        count = mask.sum().item()
        if count > 0:
            w[mask] = len(y) / (len(TARGETS) * count)
    return w


def train(X_trn, y_trn, X_val, y_val) -> StyleMLP:
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Device: {device}  |  train={len(X_trn)}  val={len(X_val)}\n")

    X_trn, y_trn = X_trn.to(device), y_trn.to(device)
    X_val, y_val = X_val.to(device), y_val.to(device)
    w_trn = class_weights(y_trn).to(device)

    model     = StyleMLP(input_dim=X_trn.shape[1], hidden_dims=HIDDEN_DIMS, dropout=DROPOUT).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    loader = DataLoader(TensorDataset(X_trn, y_trn, w_trn), batch_size=BATCH_SIZE, shuffle=True)

    best_val_loss = float('inf')
    best_state    = None

    for epoch in range(1, EPOCHS + 1):
        # ── train ──
        model.train()
        trn_loss = 0.0
        for xb, yb, wb in loader:
            optimizer.zero_grad()
            pred = torch.sigmoid(model(xb).squeeze(-1))
            loss = (wb * (pred - yb) ** 2).mean()
            loss.backward()
            optimizer.step()
            trn_loss += loss.item()
        scheduler.step()

        # ── validate ──
        model.eval()
        with torch.no_grad():
            val_pred = torch.sigmoid(model(X_val).squeeze(-1))
            val_loss = ((val_pred - y_val) ** 2).mean().item()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state    = {k: v.clone() for k, v in model.state_dict().items()}

        if epoch % 25 == 0 or epoch == EPOCHS:
            avg_trn = trn_loss / len(loader)
            gap     = avg_trn - val_loss
            flag    = "  ⚠️  overfitting" if gap > 0.05 else ""
            print(f"  epoch {epoch:3d}/{EPOCHS}   trn={avg_trn:.4f}   val={val_loss:.4f}{flag}")

    model.load_state_dict(best_state)
    print(f"\nBest val loss: {best_val_loss:.4f}")
    return model


def evaluate(model, X, y):
    model.eval()
    with torch.no_grad():
        scores = torch.sigmoid(model(X).squeeze(-1)).numpy()
    y_np = y.numpy()

    print("\nPer-class accuracy on full dataset:")
    for rating, target in TARGETS.items():
        label     = {0: 'dislike', 1: 'like', 2: 'superlike'}[rating]
        threshold = {0: 0.3, 1: 0.7, 2: 0.85}[rating]
        direction = {0: 'below', 1: 'above', 2: 'above'}[rating]
        mask      = (y_np == target)
        if not mask.any():
            continue
        if direction == 'above':
            pct = (scores[mask] > threshold).mean() * 100
        else:
            pct = (scores[mask] < threshold).mean() * 100
        avg = scores[mask].mean()
        print(f"  {label:10s}  avg={avg:.3f}   {pct:.0f}% {direction} {threshold}")


def main():
    print("=" * 52)
    print("  TRAINING StyleMLP")
    print("=" * 52 + "\n")

    X, y = build_dataset(ALPHA)

    if len(X) < 20:
        print(f"\n⚠️  Only {len(X)} rated items — swipe more before training for reliable results.")

    X_trn, y_trn, X_val, y_val = split(X, y, VAL_SPLIT)
    model = train(X_trn, y_trn, X_val, y_val)

    torch.save(model, OUTPUT_FILE)
    print(f"\nSaved → {OUTPUT_FILE}")

    evaluate(model, X.cpu(), y.cpu())

    print("\n" + "=" * 52)
    print("  Done. score_with_mlp.py will run automatically next.")
    print("=" * 52 + "\n")


if __name__ == '__main__':
    main()
