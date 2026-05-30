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
HIDDEN_DIMS = (512, 128)
DROPOUT     = 0.3

TARGETS = {
    0: 0.05,   # dislike
    1: 0.80,   # like
    2: 0.95,   # superlike
}
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH         = BASE_DIR / 'webapp' / 'vinted_clothes.db'
EMBEDDINGS_FILE = BASE_DIR / 'embeddings.npz'
OUTPUT_FILE     = BASE_DIR / 'style_mlp.pt'


def load_ratings() -> dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT item_id, rating FROM ratings").fetchall()
    conn.close()
    return {str(item_id): rating for item_id, rating in rows}


def build_dataset(alpha: float):
    ratings = load_ratings()

    counts = {r: sum(1 for v in ratings.values() if v == r) for r in TARGETS}
    print(f"Ratings in DB:  dislike={counts[0]}  like={counts[1]}  superlike={counts[2]}")

    if sum(counts.values()) == 0:
        raise RuntimeError("No ratings found. Swipe some items first.")

    # Load precomputed embeddings
    data      = np.load(EMBEDDINGS_FILE)
    emb_ids   = data['item_ids'].tolist()
    clip_embs = F.normalize(torch.tensor(data['clip_embs'], dtype=torch.float32), p=2, dim=1)
    dino_embs = F.normalize(torch.tensor(data['dino_embs'], dtype=torch.float32), p=2, dim=1)
    combined  = torch.cat([alpha * clip_embs, (1 - alpha) * dino_embs], dim=1)  # (N, 1792)

    # Match rated items to their embedding vectors
    X, y = [], []
    missing = 0
    for i, item_id in enumerate(emb_ids):
        if item_id in ratings:
            X.append(combined[i])
            y.append(TARGETS[ratings[item_id]])
        elif item_id not in ratings:
            pass  # unrated — skip
    # Count items rated but not yet embedded
    embedded_ids = set(emb_ids)
    missing = sum(1 for iid in ratings if iid not in embedded_ids)
    if missing:
        print(f"  ⚠️  {missing} rated items have no embedding yet — run compute_embeddings.py")

    if not X:
        raise RuntimeError("No rated items found in embeddings.npz. Run compute_embeddings.py first.")

    X = torch.stack(X)
    y = torch.tensor(y, dtype=torch.float32)
    print(f"Training set:   {len(X)} items  |  embedding dim: {X.shape[1]}\n")
    return X, y


def class_weights(y: torch.Tensor) -> torch.Tensor:
    """Weight each sample inversely by class frequency so rare ratings aren't ignored."""
    w = torch.ones(len(y))
    for target in TARGETS.values():
        mask  = (y == target)
        count = mask.sum().item()
        if count > 0:
            w[mask] = len(y) / (len(TARGETS) * count)
    return w


def train(X: torch.Tensor, y: torch.Tensor) -> StyleMLP:
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Device: {device}")

    X = X.to(device)
    y = y.to(device)
    w = class_weights(y).to(device)

    model     = StyleMLP(input_dim=X.shape[1], hidden_dims=HIDDEN_DIMS, dropout=DROPOUT).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    loader = DataLoader(TensorDataset(X, y, w), batch_size=BATCH_SIZE, shuffle=True)

    best_loss  = float('inf')
    best_state = None

    for epoch in range(1, EPOCHS + 1):
        model.train()
        epoch_loss = 0.0
        for xb, yb, wb in loader:
            optimizer.zero_grad()
            pred = torch.sigmoid(model(xb).squeeze(-1))
            loss = (wb * (pred - yb) ** 2).mean()  # weighted MSE
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step()

        avg = epoch_loss / len(loader)
        if avg < best_loss:
            best_loss  = avg
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        if epoch % 25 == 0 or epoch == EPOCHS:
            print(f"  epoch {epoch:3d}/{EPOCHS}   loss = {avg:.4f}")

    model.load_state_dict(best_state)
    print(f"\nBest loss: {best_loss:.4f}")
    return model


def evaluate(model: StyleMLP, X: torch.Tensor, y: torch.Tensor):
    model.eval()
    with torch.no_grad():
        scores = torch.sigmoid(model(X).squeeze(-1)).numpy()
    y_np = y.numpy()

    print("\nScore distribution on training set:")
    for rating, target in TARGETS.items():
        label = {0: 'dislike', 1: 'like', 2: 'superlike'}[rating]
        mask  = (y_np == target)
        if mask.any():
            avg = scores[mask].mean()
            print(f"  {label:10s}  target={target:.2f}   model avg={avg:.3f}")

    # How many liked items actually score above 0.7?
    liked_mask     = (y_np >= TARGETS[1])
    disliked_mask  = (y_np <= TARGETS[0])
    if liked_mask.any():
        above_threshold = (scores[liked_mask] > 0.7).mean() * 100
        print(f"\n  {above_threshold:.0f}% of liked items score above 0.7")
    if disliked_mask.any():
        below_threshold = (scores[disliked_mask] < 0.3).mean() * 100
        print(f"  {below_threshold:.0f}% of disliked items score below 0.3")


def main():
    print("=" * 52)
    print("  TRAINING StyleMLP")
    print("=" * 52 + "\n")

    X, y = build_dataset(ALPHA)
    model = train(X, y)

    torch.save(model, OUTPUT_FILE)
    print(f"\nSaved → {OUTPUT_FILE}")

    evaluate(model, X.cpu(), y.cpu())

    print("\n" + "=" * 52)
    print("  Done. Run score_with_mlp.py to update the DB.")
    print("=" * 52 + "\n")


if __name__ == '__main__':
    main()
