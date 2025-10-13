import torch
from sentence_transformers import SentenceTransformer
from PIL import Image
import numpy as np
from pathlib import Path
import os

# --- CONFIGURATION ---
MODEL_NAME = 'clip-ViT-B-32'

# --- Positive Profile ---
POSITIVE_SOURCE_FOLDER = 'pinterest_images'
POSITIVE_OUTPUT_FILE = 'my_taste_profile.npy'

# --- Negative Profile ---
NEGATIVE_SOURCE_FOLDER = 'negative_images'
NEGATIVE_OUTPUT_FILE = 'negative_profile.npy'

def create_profile(source_folder, output_file, model, device):
    """A reusable function to create a style profile from a folder of images."""
    print(f"\n{'='*60}")
    print(f"Creating profile for: '{source_folder}'")
    print(f"{'='*60}")

    source_path = Path(source_folder)
    if not source_path.is_dir():
        print(f"⚠️  Warning: The folder '{source_folder}' was not found. Skipping.")
        return False

    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    image_paths = [p for p in source_path.iterdir() if p.suffix.lower() in valid_extensions]

    if not image_paths:
        print(f"✅ No images found in '{source_folder}'. A blank profile will be created.")
        # Save an empty array if no images are found
        np.save(output_file, np.array([]))
        return True

    print(f"✅ Found {len(image_paths)} images to analyze.")
    all_embeddings = []

    for i, image_path in enumerate(image_paths):
        print(f"   ({i+1}/{len(image_paths)}) Processing: {image_path.name}")
        try:
            image = Image.open(image_path).convert("RGB")
            image_embedding = model.encode(image, convert_to_tensor=True, device=device)
            all_embeddings.append(image_embedding)
        except Exception as e:
            print(f"      ⚠️  Could not process this image. Skipping. Error: {e}")
            continue

    if not all_embeddings:
        print("❌ No images were successfully processed. Cannot create a taste profile.")
        np.save(output_file, np.array([]))
        return False

    print(f"\n🧬 Stacking {len(all_embeddings)} fingerprints...")
    stacked_embeddings = torch.stack(all_embeddings)
    norm_embeddings = torch.nn.functional.normalize(stacked_embeddings, p=2, dim=1)
    profile_matrix = norm_embeddings.cpu().numpy()

    np.save(output_file, profile_matrix)
    print(f"💾 Profile saved as: '{output_file}'")
    return True

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("🧠 Loading the AI model...")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"   Using device: {device}")
    model = SentenceTransformer(MODEL_NAME, device=device)

    # Create Positive Profile
    create_profile(POSITIVE_SOURCE_FOLDER, POSITIVE_OUTPUT_FILE, model, device)

    # Create Negative Profile
    create_profile(NEGATIVE_SOURCE_FOLDER, NEGATIVE_OUTPUT_FILE, model, device)

    print(f"\n{'='*60}")
    print(f"🎉 Success! Profile creation complete.")
    print(f"{'='*60}\n")