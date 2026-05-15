import argparse
import joblib
import torch
from sentence_transformers import SentenceTransformer
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import json
import numpy as np
from pathlib import Path

from style_utils import (BASE_DIR, MODEL_CONFIGS, encode_image,
                         extract_category_from_text, load_image_model, resolve_path)

# --- MODEL SELECTION ---
# Choose one of these models:
MODEL_CHOICE = 'fashionclip2'  # Options: 'fashionclip', 'fashionclip2', 'clip-large', 'clip-base'

# --- CONFIGURATION ---
TASTE_PROFILE_FILE = 'my_taste_profile.npy'
NEGATIVE_PROFILE_FILE = 'negative_profile.npy'
SCRAPED_ITEMS_FILE = 'vinted_items.json'
OUTPUT_FILE = 'scored_items.json'
CLASSIFIER_FILE = BASE_DIR / 'style_classifier.joblib'

# --- SCORING PARAMETERS ---
MIN_SCORE_THRESHOLD = 70.0
USE_NEGATIVE_PROFILE = True  # Set to False to disable negative scoring

# Scoring weights (only used if negative profile exists)
POSITIVE_WEIGHT = 0.7
NEGATIVE_WEIGHT = 0.3
NEGATIVE_PENALTY_POWER = 1.5


def parse_args():
    parser = argparse.ArgumentParser(description='Score scraped Vinted items against your style profile or classifier.')
    parser.add_argument('--model-choice', default=MODEL_CHOICE,
                        choices=['fashionclip', 'fashionclip2', 'clip-large', 'clip-base'],
                        help='Embedding model to use for scoring.')
    parser.add_argument('--scraped-items', default=SCRAPED_ITEMS_FILE,
                        help='Input JSON file containing scraped items.')
    parser.add_argument('--output', default=OUTPUT_FILE,
                        help='Output JSON file for scored items.')
    parser.add_argument('--classifier-file', default=str(CLASSIFIER_FILE),
                        help='Optional trained classifier file to use instead of similarity scoring.')
    parser.add_argument('--min-score', type=float, default=MIN_SCORE_THRESHOLD,
                        help='Minimum score threshold to include an item.')
    parser.add_argument('--positive-profile', default=TASTE_PROFILE_FILE,
                        help='Positive taste profile file.')
    parser.add_argument('--negative-profile', default=NEGATIVE_PROFILE_FILE,
                        help='Negative taste profile file.')
    parser.add_argument('--no-negative', action='store_true',
                        help='Do not use negative profile scoring.')
    return parser.parse_args()

positive_prompts = [
    "loose relaxed fit menswear",
    "earthy tone minimalist streetwear outfit",
    "vintage japanese 2000s casual fashion",
    "soft textured knit and wide pants outfit",
    "retro bohemian neutral aesthetic",
]

negative_prompts = [
    "bright tight slim fit clothing",
    "corporate office fashion",
    "sporty gym outfit with logos",
    "fast fashion colorful outfit",
    "mall fashion jeans and graphic tee",
]


def encode_texts(prompts, model, processor, device, model_type):
    """Encode text prompts using the same model type."""
    if model_type == 'huggingface':
        inputs = processor(text=prompts, return_tensors='pt', padding=True).to(device)
        with torch.no_grad():
            text_features = model.get_text_features(**inputs)
        return torch.nn.functional.normalize(text_features, p=2, dim=1)

    text_features = model.encode(prompts, convert_to_tensor=True, device=device)
    return torch.nn.functional.normalize(text_features, p=2, dim=1)


def create_profile_from_images(folder, model, processor, device, model_type):
    """Create an embedding profile from a folder of images."""
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"   ⚠️  Folder '{folder}' not found, skipping.")
        return None

    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    image_paths = [p for p in folder_path.iterdir() if p.suffix.lower() in valid_extensions]
    if not image_paths:
        print(f"   ⚠️  No images in '{folder}', skipping.")
        return None

    print(f"   Processing {len(image_paths)} images from '{folder}'...")
    embeddings = []
    for img_path in image_paths:
        try:
            image = Image.open(img_path).convert('RGB')
            embedding = encode_image(image, model, processor, device, model_type)
            embeddings.append(embedding)
        except Exception as e:
            print(f"      ⚠️  Failed to process {img_path.name}: {e}")
            continue

    if not embeddings:
        return None

    stacked = torch.cat(embeddings, dim=0)
    return stacked


def score_items(items, model, processor, device, model_type, taste_profile_tensor,
                negative_profile_tensor, has_negative_profile, style_classifier,
                min_score_threshold=MIN_SCORE_THRESHOLD):
    scored_items = []

    for item in items:
        image_path_str = item.get('image_url')
        if not image_path_str:
            continue

        image_path = resolve_path(image_path_str)
        if not image_path.exists():
            continue

        category = extract_category_from_text(
            item.get('title', ''),
            item.get('description', ''),
            item.get('tag', ''),
            item.get('brand', ''),
            item.get('size', '')
        )
        item['category'] = category

        try:
            image = Image.open(image_path).convert('RGB')
            item_embedding = encode_image(image, model, processor, device, model_type)

            final_score_0_to_1 = 0.0
            positive_score = 0.0
            negative_score = 0.0
            score_source = 'similarity'

            if style_classifier is not None:
                features = item_embedding.cpu().numpy()
                try:
                    probabilities = style_classifier.predict_proba(features)[0]
                    if hasattr(style_classifier, 'classes_') and 1 in style_classifier.classes_:
                        class_idx = list(style_classifier.classes_).index(1)
                    else:
                        class_idx = probabilities.argmax()
                    final_score_0_to_1 = float(probabilities[class_idx])
                except Exception:
                    final_score_0_to_1 = float(style_classifier.predict(features)[0])
                score_source = 'classifier'
                item['debug_positive'] = round(final_score_0_to_1 * 100, 1)
                item['debug_negative'] = 0.0
            else:
                if taste_profile_tensor is None:
                    continue

                positive_similarities = torch.matmul(item_embedding, taste_profile_tensor.T)
                best_positive_similarity = torch.max(positive_similarities).item()
                positive_score = (best_positive_similarity + 1) / 2

                if has_negative_profile and negative_profile_tensor is not None:
                    negative_similarities = torch.matmul(item_embedding, negative_profile_tensor.T)
                    best_negative_similarity = torch.max(negative_similarities).item()
                    negative_match = (best_negative_similarity + 1) / 2
                    negative_score = negative_match ** NEGATIVE_PENALTY_POWER

                if has_negative_profile:
                    positive_contribution = positive_score * POSITIVE_WEIGHT
                    negative_contribution = negative_score * NEGATIVE_WEIGHT
                    final_score_0_to_1 = (positive_contribution - negative_contribution + NEGATIVE_WEIGHT) / (POSITIVE_WEIGHT + NEGATIVE_WEIGHT)
                else:
                    final_score_0_to_1 = positive_score

                item['debug_positive'] = round(positive_score * 100, 1)
                item['debug_negative'] = round(negative_score * 100, 1)

            final_score_0_to_1 = max(0.0, min(1.0, final_score_0_to_1))
            final_score = final_score_0_to_1 * 100

            item['ai_score'] = round(final_score, 2)
            item['style_model'] = score_source

            title = item.get('title', 'Unknown')[:50]
            category_label = category[:12]
            print(f"{title:<50} | Cat: {category_label:<12} | Score: {final_score:5.1f}% | Source: {score_source}", end='')

            if final_score >= min_score_threshold:
                scored_items.append(item)
                print(' ✨')
            else:
                print(' ❌')

        except Exception as e:
            print(f"   ⚠️  Error processing item: {e}")
            continue

    return scored_items


def main():
    args = parse_args()

    model, processor, device, model_type = load_image_model(args.model_choice)

    classifier_file = Path(args.classifier_file)
    style_classifier = None
    if classifier_file.exists():
        try:
            classifier_data = joblib.load(classifier_file)
            style_classifier = classifier_data.get('classifier') if isinstance(classifier_data, dict) else classifier_data
            print(f"✅ Loaded style classifier from {classifier_file.name}")
        except Exception as e:
            print(f"⚠️ Failed to load style classifier: {e}")

    print(f"\n{'='*60}")
    print("Loading taste profiles...")
    print(f"{'='*60}")

    positive_text_embeds = encode_texts(positive_prompts, model, processor, device, model_type)
    negative_text_embeds = encode_texts(negative_prompts, model, processor, device, model_type)

    try:
        taste_profile = np.load(args.positive_profile)
        taste_profile_tensor = torch.tensor(taste_profile, device=device)
        taste_profile_tensor = torch.cat([taste_profile_tensor, positive_text_embeds], dim=0)
        print(f"✅ Loaded positive profile ({len(taste_profile)} items)")
    except FileNotFoundError:
        print(f"⚠️  No saved positive profile found at {args.positive_profile}.")
        print(f"   Creating new profile from 'pinterest_images' folder...")
        taste_profile_tensor = create_profile_from_images(
            'pinterest_images', model, processor, device, model_type
        )
        if taste_profile_tensor is None:
            print("❌ Cannot create positive profile. Exiting.")
            return
        np.save(args.positive_profile, taste_profile_tensor.cpu().numpy())
        print(f"✅ Created and saved positive profile")

    has_negative_profile = False
    negative_profile_tensor = None

    if USE_NEGATIVE_PROFILE and not args.no_negative:
        try:
            negative_profile = np.load(args.negative_profile)
            if len(negative_profile) > 0:
                negative_profile_tensor = torch.tensor(negative_profile, device=device)
                negative_profile_tensor = torch.cat([negative_profile_tensor, negative_text_embeds], dim=0)
                has_negative_profile = True
                print(f"✅ Loaded negative profile ({len(negative_profile)} items)")
        except FileNotFoundError:
            print(f"⚠️  No saved negative profile found at {args.negative_profile}.")
            print(f"   Creating new profile from 'negative_images' folder...")
            negative_profile_tensor = create_profile_from_images(
                'negative_images', model, processor, device, model_type
            )
            if negative_profile_tensor is not None:
                has_negative_profile = True
                np.save(args.negative_profile, negative_profile_tensor.cpu().numpy())
                print(f"✅ Created and saved negative profile")
            else:
                print(f"ℹ️  No negative profile available")

    try:
        with open(args.scraped_items, 'r', encoding='utf-8') as f:
            items = json.load(f)
        print(f"✅ Loaded {len(items)} items to score")
    except FileNotFoundError:
        print(f"❌ Error: Could not find '{args.scraped_items}'.")
        return

    print(f"\n{'='*60}")
    print(f"🎯 Scoring items with {MODEL_CONFIGS[args.model_choice]['description']}")
    print(f"{'='*60}\n")

    scored_items = score_items(
        items,
        model,
        processor,
        device,
        model_type,
        taste_profile_tensor,
        negative_profile_tensor,
        has_negative_profile,
        style_classifier,
        min_score_threshold=args.min_score,
    )

    scored_items.sort(key=lambda x: x['ai_score'], reverse=True)

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(scored_items, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"✅ SCORING COMPLETE")
    print(f"{'='*60}")

    if scored_items:
        print(f"📊 Found {len(scored_items)} items above {MIN_SCORE_THRESHOLD}% threshold")
        print(f"💾 Saved to: {args.output}")
        print(f"\n🏆 TOP 5 MATCHES:")
        for idx, item in enumerate(scored_items[:5], 1):
            score = item['ai_score']
            title = item['title'][:45]
            print(f"   {idx}. [{score:5.1f}%] {title}")
    else:
        print(f"❌ No items scored above {MIN_SCORE_THRESHOLD}%")
        print(f"💡 Try lowering MIN_SCORE_THRESHOLD or check your profiles")

    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
