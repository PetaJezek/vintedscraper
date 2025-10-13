import os
import shutil
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # This is important to allow your HTML file to talk to the server

# --- CONFIGURATION ---
# Make sure these paths are correct relative to where you run the server
VINTED_IMAGES_FOLDER = 'vinted_images'
NEGATIVE_IMAGES_FOLDER = 'negative_images'

@app.route('/move_to_negative', methods=['POST'])
def move_to_negative():
    data = request.get_json()
    image_name = data.get('image_name')

    if not image_name:
        return jsonify({'status': 'error', 'message': 'No image name provided'}), 400

    # Construct the full paths
    source_path = os.path.join(VINTED_IMAGES_FOLDER, image_name)
    destination_path = os.path.join(NEGATIVE_IMAGES_FOLDER, image_name)

    # Create the negative folder if it doesn't exist
    os.makedirs(NEGATIVE_IMAGES_FOLDER, exist_ok=True)

    if os.path.exists(source_path):
        try:
            shutil.move(source_path, destination_path)
            print(f"✅ Moved {image_name} to negative_images")
            return jsonify({'status': 'success', 'message': f'Moved {image_name}'})
        except Exception as e:
            print(f"❌ Error moving {image_name}: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    else:
        print(f"⚠️  Image not found to move: {source_path}")
        return jsonify({'status': 'error', 'message': 'Image not found at source'}), 404

if __name__ == '__main__':
    print("🚀 Feedback server starting...")
    print(f"   Watching folder: '{os.path.abspath(VINTED_IMAGES_FOLDER)}'")
    print(f"   Moving to folder: '{os.path.abspath(NEGATIVE_IMAGES_FOLDER)}'")
    # You can change the port if 5000 is already in use
    app.run(port=5000, debug=True)