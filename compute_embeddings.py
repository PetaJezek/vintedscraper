"""
Compute FashionCLIP image + DINOv2 + FashionCLIP text embeddings for scraped items.
Saves to embeddings.npz. Image embeddings are incremental (skip already-processed
images); text embeddings are recomputed every run so edited descriptions/hashtags
from a re-scrape are always reflected.

Run after every scrape:
    python compute_embeddings.py

Output: embeddings.npz
    item_ids  : (N,)        string item IDs
    clip_embs : (N, 768)    L2-normalised FashionCLIP image vectors
    dino_embs : (N, 1024)   L2-normalised DINOv2 CLS-token vectors
    text_embs : (N, 768)    L2-normalised FashionCLIP text vectors
                            (title + brand + category + colour + description + hashtags)
"""
import json
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from PIL import Image
from tqdm import tqdm
from transformers import CLIPModel, CLIPProcessor, AutoImageProcessor, AutoModel, logging as hf_logging

# ── config ────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).resolve().parent
ITEMS_JSON     = BASE_DIR / 'vinted_items.json'
IMAGES_DIR     = BASE_DIR / 'webapp' / 'vinted_images'
OUTPUT_FILE    = BASE_DIR / 'embeddings.npz'

FASHIONCLIP_ID = 'Marqo/marqo-fashionCLIP'
DINOV2_ID      = 'facebook/dinov2-large'
BATCH_SIZE     = 16   # lower if you hit OOM; both models loaded simultaneously
# ─────────────────────────────────────────────────────────────────────────────


def build_item_text(item: dict) -> str:
    """Assemble the text fields into one string for FashionCLIP's text encoder.

    Lead with the structured fields (title/brand/category/colour) since CLIP
    truncates at 77 tokens — the free-text description and hashtag spam come last.
    """
    parts: list[str] = []
    for key in ('title', 'brand', 'category_path', 'color'):
        val = item.get(key)
        if val:
            parts.append(str(val).strip())
    desc = item.get('description')
    if desc:
        parts.append(str(desc).strip())
    tags = item.get('hashtags')
    if tags:
        parts.append(' '.join(tags) if isinstance(tags, list) else str(tags))
    return ' '.join(p for p in parts if p).strip()


def resolve_image(item: dict) -> Path | None:
    """Map an item's image_url to an absolute path, return None if missing."""
    raw = item.get('image_url', '')
    if not raw:
        return None
    # stored as /images/<filename> or webapp/vinted_images/<filename>
    filename = Path(raw).name
    p = IMAGES_DIR / filename
    return p if p.exists() else None


def load_models(device: str, load_dino: bool = True):
    """Load FashionCLIP (always — needed for both image and text). DINOv2 only
    when there are new images to embed; text-only refreshes skip it."""
    hf_logging.set_verbosity_error()

    print(f'Loading FashionCLIP  ({FASHIONCLIP_ID})...')
    clip_model = CLIPModel.from_pretrained(FASHIONCLIP_ID).to(device).eval()
    clip_proc  = CLIPProcessor.from_pretrained(FASHIONCLIP_ID, use_fast=True)

    dino_model = dino_proc = None
    if load_dino:
        print(f'Loading DINOv2       ({DINOV2_ID})...')
        dino_proc  = AutoImageProcessor.from_pretrained(DINOV2_ID, use_fast=True)
        dino_model = AutoModel.from_pretrained(DINOV2_ID).to(device).eval()

    return clip_model, clip_proc, dino_model, dino_proc


@torch.no_grad()
def encode_clip_batch(images: list, model, processor, device: str) -> np.ndarray:
    inputs = processor(images=images, return_tensors='pt').to(device)
    feats  = model.get_image_features(**inputs)
    return F.normalize(feats, p=2, dim=1).cpu().numpy()


@torch.no_grad()
def encode_text_batch(texts: list, model, processor, device: str) -> np.ndarray:
    inputs = processor(
        text=texts, return_tensors='pt',
        padding=True, truncation=True, max_length=77,
    ).to(device)
    feats = model.get_text_features(**inputs)
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


def encode_all_text(item_ids, items_by_id, clip_model, clip_proc, device) -> np.ndarray:
    """Compute a FashionCLIP text embedding for every item id, in batches."""
    vecs: list = []
    ids = list(item_ids)
    for start in tqdm(range(0, len(ids), BATCH_SIZE), desc='Embedding text'):
        chunk = ids[start:start + BATCH_SIZE]
        texts = [build_item_text(items_by_id.get(str(iid), {})) for iid in chunk]
        vecs.append(encode_text_batch(texts, clip_model, clip_proc, device))
    return np.vstack(vecs).astype(np.float32) if vecs else np.empty((0, 0), np.float32)


def main():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'Device: {device}\n')

    with open(ITEMS_JSON, encoding='utf-8') as f:
        items = json.load(f)
    items_by_id = {str(item['id']): item for item in items}
    print(f'Items in JSON: {len(items)}')

    # Load existing image results so we only re-embed new images
    existing_ids: set[str] = set()
    old_ids:  list = []
    old_clip: np.ndarray | None = None
    old_dino: np.ndarray | None = None
    had_text = False

    if OUTPUT_FILE.exists():
        saved = np.load(OUTPUT_FILE)
        old_ids  = saved['item_ids'].tolist()
        old_clip = saved['clip_embs']   # (M, 768)
        old_dino = saved['dino_embs']   # (M, 1024)
        existing_ids = set(old_ids)
        had_text = 'text_embs' in saved.files
        print(f'Already computed:   {len(existing_ids)} images'
              f'{" (+text)" if had_text else ""} — skipping those\n')

    todo = [
        (str(item['id']), resolve_image(item))
        for item in items
        if str(item['id']) not in existing_ids
    ]
    todo = [(iid, p) for iid, p in todo if p is not None]
    print(f'New images to embed: {len(todo)}\n')

    if not todo and old_clip is None:
        print('Nothing to compute — no images found.')
        return

    # Text is (re)computed every run, so FashionCLIP always loads; DINOv2 only
    # loads when there are new images to embed.
    clip_model, clip_proc, dino_model, dino_proc = load_models(device, load_dino=bool(todo))
    print()

    # ── Image embeddings (incremental) ──────────────────────────────────────────
    new_ids:  list[str] = []
    new_clip: list      = []
    new_dino: list      = []

    if todo:
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
        flush_batch(batch_ids, batch_imgs,
                    clip_model, clip_proc, dino_model, dino_proc, device,
                    new_ids, new_clip, new_dino)

    # Merge image embeddings with existing
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

    # ── Text embeddings (all items, every run) ──────────────────────────────────
    all_text = encode_all_text(all_ids, items_by_id, clip_model, clip_proc, device)

    np.savez(OUTPUT_FILE, item_ids=all_ids, clip_embs=all_clip,
             dino_embs=all_dino, text_embs=all_text)
    print(f'\nSaved {len(all_ids)} embeddings → {OUTPUT_FILE}')
    print(f'  clip: {all_clip.shape}   dino: {all_dino.shape}   text: {all_text.shape}')


if __name__ == '__main__':
    main()
