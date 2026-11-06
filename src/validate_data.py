"""Unpack the Kaggle archives in data/raw/ and sanity-check the training set.

Kaggle ships nested archives (whats-cooking.zip -> train.json.zip -> train.json),
so we unpack one level at a time until train.json appears, then report the shape
of the dataset and its most common cuisines.
"""
import json
import zipfile
from collections import Counter
from pathlib import Path

from config import EXPECTED_CUISINES, EXPECTED_RECIPES, RAW_DIR, TRAIN_FILENAME


def _unpack() -> Path:
    """Unpack zip files in data/raw until the training file exists; return it."""
    train_path = RAW_DIR / TRAIN_FILENAME
    for _ in range(3):  # cap the number of nesting levels
        if train_path.exists():
            return train_path
        archives = sorted(RAW_DIR.glob("*.zip"))
        if not archives:
            break
        for archive in archives:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(RAW_DIR)

    if not train_path.exists():
        raise FileNotFoundError(
            f"{train_path} missing: run `python src/fetch_data.py` first."
        )
    return train_path


def validate() -> None:
    train_path = _unpack()
    with train_path.open(encoding="utf-8") as handle:
        recipes = json.load(handle)

    cuisine_counts = Counter(recipe["cuisine"] for recipe in recipes)
    ingredient_count = len({i for recipe in recipes for i in recipe["ingredients"]})

    print(f"file: {train_path}")
    print(f"recipes: {len(recipes)}")
    print(f"cuisines: {len(cuisine_counts)}")
    print(f"distinct ingredients: {ingredient_count}")
    print("most common cuisines:")
    for cuisine, count in cuisine_counts.most_common(5):
        print(f"  {cuisine:>16} {count}")

    assert len(recipes) == EXPECTED_RECIPES, (
        f"expected {EXPECTED_RECIPES} recipes, found {len(recipes)}"
    )
    assert len(cuisine_counts) == EXPECTED_CUISINES, (
        f"expected {EXPECTED_CUISINES} cuisines, found {len(cuisine_counts)}"
    )
    print("OK: this is the What's Cooking? training set.")


if __name__ == "__main__":
    validate()
