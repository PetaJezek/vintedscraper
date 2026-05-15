import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from PIL import Image

from style_utils import (BASE_DIR, encode_image, extract_category_from_text,
                         find_images, load_image_model, resolve_path)


DEFAULT_MODEL_FILE = 'style_classifier.joblib'
DEFAULT_POSITIVE = 'pinterest_images'
DEFAULT_NEGATIVE = 'negative_images'


def parse_args():
    parser = argparse.ArgumentParser(
        description='Train a binary fashion style classifier from image folders and optional labels.'
    )
    parser.add_argument('--positive-folder', default=DEFAULT_POSITIVE,
                        help='Folder with positive (drip/style) images.')
    parser.add_argument('--negative-folder', default=DEFAULT_NEGATIVE,
                        help='Folder with negative (not drip) images.')
    parser.add_argument('--ratings-json', default=None,
                        help='Optional exported rated items JSON with image_url and rating fields.')
    parser.add_argument('--model-choice', default='clip-base',
                        choices=['fashionclip', 'fashionclip2', 'clip-large', 'clip-base'],
                        help='Embedding model to use for training.')
    parser.add_argument('--output', default=DEFAULT_MODEL_FILE,
                        help='Output path for the trained classifier file.')
    parser.add_argument('--output-dir', default='.',
                        help='Directory where classifier files should be saved.')
    parser.add_argument('--classifier', default='rf', choices=['rf'],
                        help='Type of classifier to train. Only random forest is supported for now.')
    parser.add_argument('--categories', nargs='*', default=None,
                        help='Optional category filter for rated examples (e.g. tshirt pants).')
    parser.add_argument('--category-models', action='store_true',
                        help='Train separate classifiers per category from rated data.')
    parser.add_argument('--test-size', type=float, default=0.2,
                        help='Fraction of data to hold out for evaluation.')
    parser.add_argument('--random-state', type=int, default=42,
                        help='Random seed for training reproducibility.')
    return parser.parse_args()


def load_labeled_images(folder: Path, label: int, model, processor, device, model_type):
    image_paths = find_images(folder)
    features = []
    labels = []

    if not image_paths:
        return features, labels

    print(f'   ✅ Found {len(image_paths)} images in {folder}')
    for image_path in image_paths:
        try:
            with Image.open(image_path).convert('RGB') as image:
                embedding = encode_image(image, model, processor, device, model_type)
                features.append(embedding.cpu().numpy().flatten())
                labels.append(label)
        except Exception as e:
            print(f'      ⚠️ Failed to encode {image_path.name}: {e}')
    return features, labels


def infer_item_category(item):
    return extract_category_from_text(
        item.get('title', ''),
        item.get('description', ''),
        item.get('tag', ''),
        item.get('brand', ''),
        item.get('size', '')
    )


def load_ratings_dataset(path: Path, model, processor, device, model_type, categories=None):
    if not path.exists():
        print(f'⚠️ Ratings JSON not found: {path}')
        return [], [], []

    with open(path, 'r', encoding='utf-8') as f:
        items = json.load(f)

    features = []
    labels = []
    item_categories = []
    processed = 0
    skipped = 0

    for item in items:
        rating = item.get('rating')
        if rating not in (0, 1):
            skipped += 1
            continue

        image_url = item.get('image_url') or item.get('local_image_path')
        if not image_url:
            skipped += 1
            continue

        category = item.get('category') or infer_item_category(item)
        if categories and category not in categories:
            skipped += 1
            continue

        image_path = Path(image_url)
        if not image_path.exists():
            image_path = resolve_path(image_url)

        if not image_path.exists():
            skipped += 1
            continue

        try:
            with Image.open(image_path).convert('RGB') as image:
                embedding = encode_image(image, model, processor, device, model_type)
                features.append(embedding.cpu().numpy().flatten())
                labels.append(int(rating))
                item_categories.append(category)
                processed += 1
        except Exception as e:
            skipped += 1
            print(f'      ⚠️ Failed to encode rating image {image_path}: {e}')

    print(f'   ✅ Loaded {processed} rated images, skipped {skipped}')
    return features, labels, item_categories


def make_classifier(choice: str, random_state: int):
    if choice == 'rf':
        return RandomForestClassifier(
            n_estimators=150,
            max_depth=16,
            n_jobs=-1,
            random_state=random_state,
            class_weight='balanced'
        )
    raise ValueError(f'Unsupported classifier: {choice}')


def main():
    args = parse_args()

    print('\n🎯 Training style classifier')
    print('============================================')
    print(f'Positive folder: {args.positive_folder}')
    print(f'Negative folder: {args.negative_folder}')
    if args.ratings_json:
        print(f'Ratings JSON: {args.ratings_json}')
    print(f'Model choice: {args.model_choice}')
    print('============================================\n')

    model, processor, device, model_type = load_image_model(args.model_choice)

    X = []
    y = []

    pos_features, pos_labels = load_labeled_images(
        Path(args.positive_folder), 1, model, processor, device, model_type
    )
    X.extend(pos_features)
    y.extend(pos_labels)

    neg_features, neg_labels = load_labeled_images(
        Path(args.negative_folder), 0, model, processor, device, model_type
    )
    X.extend(neg_features)
    y.extend(neg_labels)

    ratings_categories = []
    if args.ratings_json:
        ratings_features, ratings_labels, ratings_categories = load_ratings_dataset(
            Path(args.ratings_json), model, processor, device, model_type, categories=args.categories
        )
        X.extend(ratings_features)
        y.extend(ratings_labels)

    if len(X) < 10 or len(set(y)) < 2:
        raise RuntimeError(
            'Not enough labeled data to train a classifier. Add more positive/negative examples or use rated scraped items.'
        )

    X = np.vstack(X)
    y = np.array(y)

    print(f'✅ Total training examples: {len(y)} (positive={int((y == 1).sum())}, negative={int((y == 0).sum())})')

    if args.category_models and ratings_categories:
        categories = sorted(set(ratings_categories))
        print(f'🔧 Training category-specific models for: {categories}')
        os.makedirs(args.output_dir, exist_ok=True)
        for category in categories:
            indices = [i for i, c in enumerate(ratings_categories) if c == category]
            category_X = np.vstack([ratings_features[i] for i in indices])
            category_y = np.array([ratings_labels[i] for i in indices])
            if len(category_y) < 10 or len(set(category_y)) < 2:
                print(f'   ⚠️ Not enough data for category {category}, skipping')
                continue

            classifier = make_classifier(args.classifier, args.random_state)
            classifier.fit(category_X, category_y)

            y_pred = classifier.predict(category_X)
            y_prob = classifier.predict_proba(category_X)[:, 1]
            print(f'\n✅ Trained category classifier for {category}')
            print(classification_report(category_y, y_pred, digits=3))
            try:
                auc = roc_auc_score(category_y, y_prob)
                print(f'Category {category} ROC AUC: {auc:.3f}')
            except Exception:
                pass

            output_path = Path(args.output_dir) / f'{Path(args.output).stem}_{category}.joblib'
            joblib.dump({'classifier': classifier, 'category': category}, output_path)
            print(f'💾 Saved category classifier to: {output_path}')

    X = np.vstack(X)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=args.test_size,
        stratify=y,
        random_state=args.random_state
    )

    classifier = make_classifier(args.classifier, args.random_state)
    classifier.fit(X_train, y_train)

    y_pred = classifier.predict(X_test)
    y_prob = classifier.predict_proba(X_test)[:, 1]

    print('\n✅ Training complete')
    print('--------------------------------------------')
    print(classification_report(y_test, y_pred, digits=3))

    try:
        auc = roc_auc_score(y_test, y_prob)
        print(f'ROC AUC: {auc:.3f}')
    except Exception:
        pass

    output_path = Path(args.output)
    os.makedirs(output_path.parent, exist_ok=True)
    joblib.dump({'classifier': classifier}, output_path)
    print(f'💾 Saved classifier to: {output_path}')

    print('\nNext step: run ai_style_scorer.py to score scraped items with the trained classifier.\n')


if __name__ == '__main__':
    main()
