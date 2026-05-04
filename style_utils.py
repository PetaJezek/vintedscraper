import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import torch
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import CLIPProcessor, CLIPModel

BASE_DIR = Path(__file__).resolve().parent

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

VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

CATEGORY_KEYWORDS = [
    ('pants', ['pants', 'trousers', 'jeans', 'denim', 'chinos', 'cargo', 'slacks', 'leggings']),
    ('tshirt', ['t-shirt', 't shirt', 'tee', 'tee-shirt', 'shirt', 'top', 'vest', 'tank']),
    ('jumper', ['sweater', 'jumper', 'hoodie', 'hoodies', 'sweatshirt', 'knit', 'cardigan', 'jersey']),
    ('outerwear', ['jacket', 'coat', 'parka', 'blazer', 'bomber', 'windbreaker', 'raincoat', 'anorak']),
    ('dress', ['dress', 'gown', 'romper', 'jumpsuit']),
    ('shorts', ['shorts']),
    ('shoes', ['shoes', 'sneakers', 'trainers', 'boots', 'sandals', 'loafers', 'heels']),
    ('accessory', ['bag', 'belt', 'cap', 'hat', 'scarf', 'gloves', 'sunglasses', 'jewelry', 'jewellery', 'watch']),
    ('suit', ['suit', 'tailored', 'formal']),
]


def resolve_path(path: Union[str, Path]) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ''
    return re.sub(r'[^0-9a-zA-ZčČžŽýÝáÁéÉíÍóÓúÚâÂêÊîÎôÔûÛäÄëËïÏöÖüÜčČšŠ ́̀]', ' ', text.lower())


def extract_category_from_text(title: Optional[str] = None,
                               description: Optional[str] = None,
                               tag: Optional[str] = None,
                               brand: Optional[str] = None,
                               size: Optional[str] = None) -> str:
    """Extract a clothing category label from item text metadata."""
    text = ' '.join(filter(None, [title, description, tag, brand, size]))
    normalized = normalize_text(text)

    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in normalized:
                return category

    return 'unknown'


def load_image_model(model_choice: str):
    """Load an image embedding model for CLIP-style encoding."""
    config = MODEL_CONFIGS[model_choice]
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    if config['type'] == 'huggingface':
        model = CLIPModel.from_pretrained(config['name']).to(device)
        processor = CLIPProcessor.from_pretrained(config['name'])
        return model, processor, device, 'huggingface'

    model = SentenceTransformer(config['name'], device=device)
    return model, None, device, 'sentence-transformers'


def encode_image(image: Image.Image, model, processor, device: str, model_type: str):
    """Encode a PIL image into a normalized embedding vector."""
    if model_type == 'huggingface':
        inputs = processor(images=image, return_tensors='pt').to(device)
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
        image_features = torch.nn.functional.normalize(image_features, p=2, dim=1)
        return image_features

    embedding = model.encode(image, convert_to_tensor=True, device=device)
    if embedding.ndim == 1:
        embedding = embedding.unsqueeze(0)
    return torch.nn.functional.normalize(embedding, p=2, dim=1)


def find_images(folder: Union[str, Path]) -> List[Path]:
    folder_path = resolve_path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return []
    return sorted([p for p in folder_path.iterdir() if p.suffix.lower() in VALID_IMAGE_EXTENSIONS])
