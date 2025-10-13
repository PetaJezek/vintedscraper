from PIL import Image, ImageDraw, ImageFont
import os, math

def make_grid(folder, label, size=180, padding=5, max_images=100):
    """Create a square grid image from a folder of JPG/PNG images."""
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))][:max_images]
    if not files:
        raise ValueError(f"No images found in {folder}")

    n = math.ceil(math.sqrt(len(files)))
    grid = Image.new('RGB', ((size + padding) * n, (size + padding) * n), (240, 240, 240))

    for i, path in enumerate(files):
        try:
            img = Image.open(path).convert('RGB')
            img.thumbnail((size, size))
            x = (i % n) * (size + padding)
            y = (i // n) * (size + padding)
            grid.paste(img, (x, y))
        except Exception as e:
            print(f"⚠️ Skipped {path}: {e}")
            continue

    # Add a label banner
    banner = Image.new('RGB', (grid.width, 60), (30, 30, 30))
    grid_full = Image.new('RGB', (grid.width, grid.height + 60), (255, 255, 255))
    grid_full.paste(banner, (0, 0))
    grid_full.paste(grid, (0, 60))

    draw = ImageDraw.Draw(grid_full)
    draw.text((15, 15), label, fill=(255, 255, 255))
    return grid_full


# --- Generate both grids ---
pos_grid = make_grid('pinterest_images', 'POSITIVE (Your Style)')
neg_grid = make_grid('negative_images', 'NEGATIVE (Opposite Style)')

# Combine side by side
combined = Image.new('RGB', (pos_grid.width + neg_grid.width + 20,
                             max(pos_grid.height, neg_grid.height)),
                     (255, 255, 255))
combined.paste(pos_grid, (0, 0))
combined.paste(neg_grid, (pos_grid.width + 20, 0))

combined.save('comparison_grid.jpg')
print("✅ Saved comparison grid as comparison_grid.jpg")
