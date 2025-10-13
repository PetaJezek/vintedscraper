import torch
from sentence_transformers import SentenceTransformer
from transformers import CLIPProcessor, CLIPModel, CLIPTokenizer
from PIL import Image
import json
import numpy as np
from pathlib import Path

# --- MODEL SELECTION ---
# Choose one of these models:
MODEL_CHOICE = 'fashionclip2'  # Options: 'fashionclip', 'fashionclip2', 'clip-large', 'clip-base'

MODEL_CONFIGS = {
    'fashionclip': {
        'name': 'patrickjohncyh/fashion-clip',
        'type': 'huggingface',
        'description': 'Fashion-CLIP trained on fashion datasets'
    },
    'fashionclip2': {
        'name': 'Marqo/marqo-fashionCLIP',
        'type': 'huggingface', 
        'description': 'Marqo Fashion-CLIP variant'
    },
    'clip-large': {
        'name': 'clip-ViT-L-14',
        'type': 'sentence-transformers',
        'description': 'Larger CLIP model (better than base)'
    },
    'clip-base': {
        'name': 'clip-ViT-B-32',
        'type': 'sentence-transformers',
        'description': 'Standard CLIP (what you were using)'
    }
}

# --- CONFIGURATION ---
TASTE_PROFILE_FILE = 'my_taste_profile.npy'
NEGATIVE_PROFILE_FILE = 'negative_profile.npy'
SCRAPED_ITEMS_FILE = 'vinted_items.json'
OUTPUT_FILE = 'scored_items.json'

# --- SCORING PARAMETERS ---
MIN_SCORE_THRESHOLD = 70.0
USE_NEGATIVE_PROFILE = True  # Set to False to disable negative scoring

# Scoring weights (only used if negative profile exists)
POSITIVE_WEIGHT = 0.7
NEGATIVE_WEIGHT = 0.3
NEGATIVE_PENALTY_POWER = 1.5


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
        inputs = processor(text=prompts, return_tensors="pt", padding=True).to(device)
        with torch.no_grad():
            text_features = model.get_text_features(**inputs)
        text_features = torch.nn.functional.normalize(text_features, p=2, dim=1)
        return text_features
    else:
        # sentence-transformers
        text_features = model.encode(prompts, convert_to_tensor=True, device=device)
        text_features = torch.nn.functional.normalize(text_features, p=2, dim=1)
        return text_features

def load_fashion_model(model_choice):
    """Load the selected fashion model."""
    config = MODEL_CONFIGS[model_choice]
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    print(f"🧠 Loading {config['description']}...")
    print(f"   Model: {config['name']}")
    print(f"   Device: {device}")
    
    if config['type'] == 'huggingface':
        # Load HuggingFace CLIP model
        model = CLIPModel.from_pretrained(config['name']).to(device)
        processor = CLIPProcessor.from_pretrained(config['name'])
        return model, processor, device, 'huggingface'
    else:
        # Load sentence-transformers model
        model = SentenceTransformer(config['name'], device=device)
        return model, None, device, 'sentence-transformers'


def encode_image_hf(image, model, processor, device):
    """Encode image using HuggingFace CLIP model."""
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        image_features = model.get_image_features(**inputs)
    image_features = torch.nn.functional.normalize(image_features, p=2, dim=1)
    return image_features


def encode_image_st(image, model, device):
    """Encode image using sentence-transformers model."""
    embedding = model.encode(image, convert_to_tensor=True, device=device)
    embedding = torch.nn.functional.normalize(embedding, p=2, dim=0)
    return embedding.unsqueeze(0)


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
            image = Image.open(img_path).convert("RGB")
            
            if model_type == 'huggingface':
                embedding = encode_image_hf(image, model, processor, device)
            else:
                embedding = encode_image_st(image, model, device)
            
            embeddings.append(embedding)
        except Exception as e:
            print(f"      ⚠️  Failed to process {img_path.name}: {e}")
            continue
    
    if not embeddings:
        return None
    
    # Stack and normalize
    stacked = torch.cat(embeddings, dim=0)
    return stacked


# --- LOAD MODEL ---
model, processor, device, model_type = load_fashion_model(MODEL_CHOICE)

# --- LOAD OR CREATE PROFILES ---
print(f"\n{'='*60}")
print("Loading taste profiles...")
print(f"{'='*60}")

positive_text_embeds = encode_texts(positive_prompts, model, processor, device, model_type)
negative_text_embeds = encode_texts(negative_prompts, model, processor, device, model_type)

# Try to load existing profiles
try:
    taste_profile = np.load(TASTE_PROFILE_FILE)
    taste_profile_tensor = torch.tensor(taste_profile, device=device)
    taste_profile_tensor = torch.cat([taste_profile_tensor, positive_text_embeds], dim=0)
    print(f"✅ Loaded positive profile ({len(taste_profile)} items)")
except FileNotFoundError:
    print(f"⚠️  No saved positive profile found.")
    print(f"   Creating new profile from 'pinterest_images' folder...")
    taste_profile_tensor = create_profile_from_images(
        'pinterest_images', model, processor, device, model_type
    )
    if taste_profile_tensor is None:
        print("❌ Cannot create positive profile. Exiting.")
        exit()
    # Save for next time
    np.save(TASTE_PROFILE_FILE, taste_profile_tensor.cpu().numpy())
    print(f"✅ Created and saved positive profile")

# Load negative profile if enabled
has_negative_profile = False
negative_profile_tensor = None

if USE_NEGATIVE_PROFILE:
    try:
        negative_profile = np.load(NEGATIVE_PROFILE_FILE)
        if len(negative_profile) > 0:
            negative_profile_tensor = torch.tensor(negative_profile, device=device)
            negative_profile_tensor = torch.cat([negative_profile_tensor, negative_text_embeds], dim=0)
            has_negative_profile = True
            print(f"✅ Loaded negative profile ({len(negative_profile)} items)")
    except FileNotFoundError:
        print(f"⚠️  No saved negative profile found.")
        print(f"   Creating new profile from 'negative_images' folder...")
        negative_profile_tensor = create_profile_from_images(
            'negative_images', model, processor, device, model_type
        )
        if negative_profile_tensor is not None:
            has_negative_profile = True
            np.save(NEGATIVE_PROFILE_FILE, negative_profile_tensor.cpu().numpy())
            print(f"✅ Created and saved negative profile")
        else:
            print(f"ℹ️  No negative profile available")

# --- LOAD ITEMS ---
try:
    with open(SCRAPED_ITEMS_FILE, 'r', encoding='utf-8') as f:
        items = json.load(f)
    print(f"✅ Loaded {len(items)} items to score")
except FileNotFoundError:
    print(f"❌ Error: Could not find '{SCRAPED_ITEMS_FILE}'.")
    exit()

# --- SCORE ITEMS ---
print(f"\n{'='*60}")
print(f"🎯 Scoring items with {MODEL_CONFIGS[MODEL_CHOICE]['description']}")
print(f"{'='*60}\n")

scored_items = []

for i, item in enumerate(items):
    image_path_str = item.get('image_url')
    if not image_path_str or not Path(image_path_str).exists():
        continue
    
    try:
        # Load and encode item image
        image = Image.open(image_path_str).convert("RGB")
        
        if model_type == 'huggingface':
            item_embedding = encode_image_hf(image, model, processor, device)
        else:
            item_embedding = encode_image_st(image, model, device)
        
        # Calculate positive similarity
        positive_similarities = torch.matmul(item_embedding, taste_profile_tensor.T)
        best_positive_similarity = torch.max(positive_similarities).item()
        positive_score = (best_positive_similarity + 1) / 2
        
        # Calculate negative score if applicable
        negative_score = 0.0
        if has_negative_profile:
            negative_similarities = torch.matmul(item_embedding, negative_profile_tensor.T)
            best_negative_similarity = torch.max(negative_similarities).item()
            negative_match = (best_negative_similarity + 1) / 2
            negative_score = negative_match ** NEGATIVE_PENALTY_POWER
        
        # Calculate final score
        if has_negative_profile:
            positive_contribution = positive_score * POSITIVE_WEIGHT
            negative_contribution = negative_score * NEGATIVE_WEIGHT
            final_score_0_to_1 = (positive_contribution - negative_contribution + NEGATIVE_WEIGHT) / (POSITIVE_WEIGHT + NEGATIVE_WEIGHT)
        else:
            final_score_0_to_1 = positive_score
        
        final_score_0_to_1 = max(0.0, min(1.0, final_score_0_to_1))
        final_score = final_score_0_to_1 * 100
        
        # Store results
        item['ai_score'] = round(final_score, 2)
        item['debug_positive'] = round(positive_score * 100, 1)
        item['debug_negative'] = round(negative_score * 100, 1)
        
        # Debug output
        title = item.get('title', 'Unknown')[:50]
        print(f"{title:<50} | Pos: {positive_score*100:5.1f}% | Neg: {negative_score*100:5.1f}% | Final: {final_score:5.1f}%", end="")
        
        if final_score >= MIN_SCORE_THRESHOLD:
            scored_items.append(item)
            print(" ✨")
        else:
            print(" ❌")
        
    except Exception as e:
        print(f"   ⚠️  Error processing item: {e}")
        continue

# Sort and save
scored_items.sort(key=lambda x: x['ai_score'], reverse=True)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(scored_items, f, indent=2, ensure_ascii=False)

# Summary
print(f"\n{'='*60}")
print(f"✅ SCORING COMPLETE")
print(f"{'='*60}")

if scored_items:
    print(f"📊 Found {len(scored_items)} items above {MIN_SCORE_THRESHOLD}% threshold")
    print(f"💾 Saved to: {OUTPUT_FILE}")
    print(f"\n🏆 TOP 5 MATCHES:")
    for idx, item in enumerate(scored_items[:5], 1):
        score = item['ai_score']
        title = item['title'][:45]
        print(f"   {idx}. [{score:5.1f}%] {title}")
else:
    print(f"❌ No items scored above {MIN_SCORE_THRESHOLD}%")
    print(f"💡 Try lowering MIN_SCORE_THRESHOLD or check your profiles")

print(f"{'='*60}\n")