import json
import os
import shutil
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR             = os.path.dirname(os.path.abspath(__file__))
VINTED_IMAGES_FOLDER = os.path.join(BASE_DIR, "webapp", "vinted_images")
NEGATIVE_IMAGES_FOLDER = os.path.join(BASE_DIR, "negative_images")
VINTED_ITEMS_FILE    = os.path.join(BASE_DIR, "vinted_items.json")
POLISH_REMOVED_FILE  = os.path.join(BASE_DIR, "polish_removed.json")
DB_FILE              = os.path.join(BASE_DIR, "webapp", "vinted_clothes.db")


@app.route("/delete_item", methods=["POST"])
def delete_item():
    data = request.get_json()
    item_id = str(data.get("id", ""))
    image_url = data.get("image_url", "")
    image_name = image_url.split("/")[-1] if image_url else ""

    if not item_id:
        return jsonify({"status": "error", "message": "No id"}), 400

    # 1. move image to negative_images/
    if image_name:
        src = os.path.join(VINTED_IMAGES_FOLDER, image_name)
        dst = os.path.join(NEGATIVE_IMAGES_FOLDER, image_name)
        os.makedirs(NEGATIVE_IMAGES_FOLDER, exist_ok=True)
        if os.path.exists(src):
            shutil.move(src, dst)

    # 2. remove from vinted_items.json
    try:
        with open(VINTED_ITEMS_FILE, encoding="utf-8") as f:
            items = json.load(f)
        items = [i for i in items if str(i.get("id")) != item_id]
        with open(VINTED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # 3. remove from vinted_clothes.db
    if os.path.exists(DB_FILE):
        try:
            con = sqlite3.connect(DB_FILE)
            con.execute("DELETE FROM items WHERE id = ?", (item_id,))
            con.commit()
            con.close()
        except Exception as e:
            print(f"DB delete failed: {e}")

    print(f"✕ Hard deleted item {item_id}")
    return jsonify({"status": "ok"})


@app.route("/move_to_negative", methods=["POST"])
def move_to_negative():
    data = request.get_json()
    image_name = data.get("image_name")
    if not image_name:
        return jsonify({"status": "error", "message": "No image name provided"}), 400

    src = os.path.join(VINTED_IMAGES_FOLDER, image_name)
    dst = os.path.join(NEGATIVE_IMAGES_FOLDER, image_name)
    os.makedirs(NEGATIVE_IMAGES_FOLDER, exist_ok=True)

    if os.path.exists(src):
        shutil.move(src, dst)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Image not found"}), 404


@app.route("/flag_polish", methods=["POST"])
def flag_polish():
    item = request.get_json()
    item_id = str(item.get("id", ""))
    if not item_id:
        return jsonify({"status": "error", "message": "No id"}), 400

    # 1. append to polish_removed.json
    existing = []
    try:
        with open(POLISH_REMOVED_FILE, encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not any(str(i.get("id")) == item_id for i in existing):
        existing.append(item)
        with open(POLISH_REMOVED_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    # 2. remove from vinted_items.json
    try:
        with open(VINTED_ITEMS_FILE, encoding="utf-8") as f:
            items = json.load(f)
        items = [i for i in items if str(i.get("id")) != item_id]
        with open(VINTED_ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # 3. remove from vinted_clothes.db
    if os.path.exists(DB_FILE):
        try:
            con = sqlite3.connect(DB_FILE)
            con.execute("DELETE FROM items WHERE id = ?", (item_id,))
            con.commit()
            con.close()
        except Exception as e:
            print(f"DB delete failed: {e}")

    print(f"🇵🇱 Flagged as Polish: {item.get('title', item_id)!r}")
    return jsonify({"status": "ok", "total_flagged": len(existing)})


if __name__ == "__main__":
    print("Feedback server starting on http://localhost:5000")
    print(f"  Items file : {VINTED_ITEMS_FILE}")
    print(f"  DB file    : {DB_FILE}")
    print(f"  Polish file: {POLISH_REMOVED_FILE}")
    app.run(port=5000, debug=False)
