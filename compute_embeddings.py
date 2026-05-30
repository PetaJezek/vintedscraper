"""
Compute FashionCLIP + DINOv2 embeddings for all scraped item images.
Saves to embeddings.npz. Incremental — skips items already processed.

Run after every scrape:
    python compute_embeddings.py

Output: embeddings.npz
    item_ids  : (N,)        string item IDs
    clip_embs : (N, 768)    L2-normalised FashionCLIP vectors
    dino_embs : (N, 1024)   L2-normalised DINOv2 CLS-token vectors
"""
import json
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from PIL import Image
from tqdm import tqdm
from transformers import CLIPModel, CLIPProcessor, AutoImageProcessor, AutoModel

# ── config ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).resolve().parent
ITEMS_JSON     = BASE_DIR / 'vinted_items.json'
IMAGES_DIR     = BASE_DIR / 'webapp' / 'vinted_images'
OUTPUT_FILE    = BASE_DIR / 'embeddings.npz'

FASHIONCLIP_ID = 'Marqo/marqo-fashionCLIP'
DINOV2_ID      = 'facebook/dinov2-large'
BATCH_SIZE     = 16   # lower if you hit OOM; both models loaded simultaneously
# ─────────────────────────────────────────────────────────────────────────────


def resolve_image(item: dict) -> Path | None:
    """Map an item's image_url to an absolute path, return None if missing."""
    raw = item.get('image_url', '')
    if not raw:
        return None
    # stored as /images/<filename> or webapp/vinted_images/<filename>
    filename = Path(raw).name
    p = IMAGES_DIR / filename
    return p if p.exists() else None


def load_models(device: str):
    print(f'Loading FashionCLIP  ({FASHIONCLIP_ID})...')
    clip_model = CLIPModel.from_pretrained(FASHIONCLIP_ID).to(device).eval()
    clip_proc  = CLIPProcessor.from_pretrained(FASHIONCLIP_ID)

    print(f'Loading DINOv2       ({DINOV2_ID})...')
    dino_proc  = AutoImageProcessor.from_pretrained(DINOV2_ID)
    dino_model = AutoModel.from_pretrained(DINOV2_ID).to(device).eval()

    return clip_model, clip_proc, dino_model, dino_proc


@torch.no_grad()
def encode_clip_batch(images: list, model, processor, device: str) -> np.ndarray:
    inputs = processor(images=images, return_tensors='pt').to(device)
    feats  = model.get_image_features(**inputs)
    return F.normalize(feats, p=2, dim=1).cpu().numpy()


@torch.no_grad()
def encode_dino_batch(images: list, model, processor, device: str) -> np.ndarray:
    inputs = processor(images=images, return_tensors='pt').to(device)
    # CLS token from the last hidden state
    feats  = model(**inputs).last_hidden_state[:, 0]
    return F.normalize(feats, p=2, dim=1).cpu().numpy()


def flush_batch(batch_ids, batch_imgs, clip_model, clip_proc,
                dino_model, dino_proc, device,
                out_ids, out_clip, out_dino):
    if not batch_imgs:
        return
    clip_vecs = encode_clip_batch(batch_imgs, clip_model, clip_proc, device)
    dino_vecs = encode_dino_batch(batch_imgs, dino_model, dino_proc, device)
    for i, item_id in enumerate(batch_ids):
        out_ids.append(item_id)
        out_clip.append(clip_vecs[i])
        out_dino.append(dino_vecs[i])


def main():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'Device: {device}\n')

    with open(ITEMS_JSON, encoding='utf-8') as f:
        items = json.load(f)
    print(f'Items in JSON: {len(items)}')

    # Load existing results so we only process new items
    existing_ids: set[str] = set()
    old_ids:  list = []
    old_clip: np.ndarray | None = None
    old_dino: np.ndarray | None = None

    if OUTPUT_FILE.exists():
        saved = np.load(OUTPUT_FILE)
        old_ids  = saved['item_ids'].tolist()
        old_clip = saved['clip_embs']   # (M, 768)
        old_dino = saved['dino_embs']   # (M, 1024)
        existing_ids = set(old_ids)
        print(f'Already computed:   {len(existing_ids)} — skipping those\n')

    todo = [
        (str(item['id']), resolve_image(item))
        for item in items
        if str(item['id']) not in existing_ids
    ]
    todo = [(iid, p) for iid, p in todo if p is not None]
    print(f'To process: {len(todo)}\n')

    if not todo:
        print('Nothing new to compute.')
        return

    clip_model, clip_proc, dino_model, dino_proc = load_models(device)
    print()

    new_ids:  list[str]    = []
    new_clip: list         = []
    new_dino: list         = []

    batch_ids:  list[str] = []
    batch_imgs: list      = []

    for item_id, img_path in tqdm(todo, desc='Embedding images'):
        try:
            img = Image.open(img_path).convert('RGB')
        except Exception as e:
            tqdm.write(f'  skip {img_path.name}: {e}')
            continue

        batch_ids.append(item_id)
        batch_imgs.append(img)

        if len(batch_imgs) >= BATCH_SIZE:
            flush_batch(batch_ids, batch_imgs,
                        clip_model, clip_proc, dino_model, dino_proc, device,
                        new_ids, new_clip, new_dino)
            batch_ids, batch_imgs = [], []

    # Remaining partial batch
    flush_batch(batch_ids, batch_imgs,
                clip_model, clip_proc, dino_model, dino_proc, device,
                new_ids, new_clip, new_dino)

    # Merge with existing and save
    if old_clip is not None and new_clip:
        all_ids  = np.array(old_ids + new_ids)
        all_clip = np.vstack([old_clip, np.array(new_clip, dtype=np.float32)])
        all_dino = np.vstack([old_dino, np.array(new_dino, dtype=np.float32)])
    elif old_clip is not None:
        all_ids, all_clip, all_dino = np.array(old_ids), old_clip, old_dino
    else:
        all_ids  = np.array(new_ids)
        all_clip = np.array(new_clip, dtype=np.float32)
        all_dino = np.array(new_dino, dtype=np.float32)

    np.savez(OUTPUT_FILE, item_ids=all_ids, clip_embs=all_clip, dino_embs=all_dino)
    print(f'\nSaved {len(all_ids)} embeddings → {OUTPUT_FILE}')
    print(f'  clip shape: {all_clip.shape}   dino shape: {all_dino.shape}')


if __name__ == '__main__':
    main()
