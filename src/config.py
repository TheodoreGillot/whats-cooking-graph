"""Central configuration: filesystem paths and dataset expectations.

Every path is derived from the repository root, so the scripts behave the same
no matter which directory they are invoked from.
"""
from pathlib import Path

# Repository root = parent directory of src/
ROOT = Path(__file__).resolve().parent.parent

# Data layout
RAW_DIR = ROOT / "data" / "raw"

# Kaggle competition handle and the file we care about
COMPETITION = "whats-cooking"
TRAIN_FILENAME = "train.json"

# Expected shape of the training set, checked by validate_data.py
EXPECTED_RECIPES = 39_774
EXPECTED_CUISINES = 20
