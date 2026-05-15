import torch
from transformers import Blip2Processor, Blip2ForConditionalGeneration # <-- CHANGED
from PIL import Image
import sqlite3
from sklearn.linear_model import LogisticRegression
import joblib
from pathlib import Path
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION (UPDATED) ---
DB_PATH = "webapp/vinted_clothes.db"
MODEL_PATH = "preference_model_blip2.joblib" # Use a new model file
# THIS IS YOUR NEW, MORE POWERFUL MODEL
BLIP2_MODEL_ID = "Salesforce/blip2-flan-t5-xl"

# --- SETUP ---
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"AI Trainer: Using device: {device}")

# --- 1. Load the "Art Historian" (BLIP-2 Model) ---
print(f"AI Trainer: Loading BLIP-2 model ({BLIP2_MODEL_ID}). This may take a while...")
try:
    # Use torch.float16 for GPUs to save memory and speed up
    model = Blip2ForConditionalGeneration.from_pretrained(BLIP2_MODEL_ID, torch_dtype=torch.float16).to(device)
    processor = Blip2Processor.from_pretrained(BLIP2_MODEL_ID)
    print("AI Trainer: BLIP-2 model loaded successfully.")
except Exception as e:
    print(f"AI Trainer: CRITICAL ERROR - Could not load BLIP-2 model. {e}")
    model = None

def get_image_embedding(image_path):
    """
    Takes an image path and returns its "Style Fingerprint" using BLIP-2.
    FIXED: Better path handling for Windows/Linux.
    """
    if not model:
        return None
    
    try:
        # Handle different path formats
        if not image_path:
            print(f"Warning: Empty image path")
            return None
        # Convert to Path object and normalize
        img_path =  Path(image_path.lstrip('/'))
        
        full_image_path = Path(__file__).parent / img_path
        
        # Load and process image
        image = Image.open(full_image_path).convert("RGB")
        
        # Prepare the image for the model
        inputs = processor(images=image, return_tensors="pt").to(device, torch.float16)

        # Get the vision embedding
        with torch.no_grad():
            vision_outputs = model.vision_model(**inputs)
        
        # Extract the style fingerprint
        embedding = vision_outputs.pooler_output
        return embedding.cpu().numpy().flatten()
        
    except Exception as e:
        print(f"Could not process image {image_path}: {type(e).__name__}: {e}")
        return None

# ===================================================================
# The rest of the script (retrain_and_predict) is IDENTICAL to before!
# It doesn't care which expert provides the fingerprint, only that it gets one.
# This shows the power of good software design.
# ===================================================================

def retrain_and_predict():
    """The main retraining function."""
    logging.info("\n--- [AI - BLIP2] Starting Retraining and Prediction Cycle ---")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # --- 2. Fetch Your Ratings ---
    c.execute("SELECT i.image_url, r.rating FROM ratings r JOIN items i ON r.item_id = i.id")
    rated_items = c.fetchall()
    
    if len(rated_items) < 10:
        # Using logging.warning is slightly better for this kind of message
        logging.warning(f"[AI] Not enough ratings ({len(rated_items)}). Need at least 10. Aborting.")
        conn.close()
        return

    # --- 3. Create "Style Fingerprints" for Rated Items ---
    logging.info(f"[AI] Generating style fingerprints for {len(rated_items)} rated items...")
    X_train, y_train = [], []
    for image_url, rating in rated_items:
        if not image_url: continue
        embedding = get_image_embedding(image_url)
        if embedding is not None:
            X_train.append(embedding)
            y_train.append(rating)

    if not X_train:
        logging.warning("[AI] Could not generate any fingerprints for training. Aborting.")
        conn.close()
        return

    # --- 4. Train Your "Personal Taste Model" ---
    logging.info(f"[AI] Training Personal Taste Model on {len(X_train)} fingerprints...")
    taste_model = LogisticRegression(class_weight='balanced', max_iter=1000)
    taste_model.fit(X_train, y_train)
    joblib.dump(taste_model, MODEL_PATH)
    logging.info(f"[AI] New taste model saved to {MODEL_PATH}")

    # --- 5. Re-score All Unseen Items ---
    c.execute("SELECT id, image_url FROM items WHERE shown = 0")
    unseen_items = c.fetchall()
    logging.info(f"[AI] Re-scoring {len(unseen_items)} unseen items...")
    
    items_to_update = []
    for item_id, image_url in unseen_items:
        if not image_url: continue
        embedding = get_image_embedding(image_url)
        if embedding is not None:
            score = taste_model.predict_proba([embedding])[0][1]
            items_to_update.append((score, item_id))

    # --- 6. Update the Database ---
    if items_to_update:
        logging.info(f"[AI] Updating database with {len(items_to_update)} new scores...")
        c.executemany("UPDATE items SET predicted_score = ? WHERE id = ?", items_to_update)
        conn.commit()
    
    logging.info("[AI] Retraining and prediction cycle complete. ---")
    conn.close()

if __name__ == "__main__":
    print("Executing manual retraining with BLIP-2...")
    retrain_and_predict()