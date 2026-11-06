"""Central configuration: filesystem paths and dataset expectations.

Every path is derived from the repository root, so the scripts behave the same
no matter which directory they are invoked from.
"""
from pathlib import Path

# Repository root = parent directory of src/
ROOT = Path(__file__).resolve().parent.parent

# Data layout
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"

# Kaggle competition handle and the file we care about
COMPETITION = "whats-cooking"
TRAIN_FILENAME = "train.json"

# Expected shape of the training set, checked by validate_data.py
EXPECTED_RECIPES = 39_774
EXPECTED_CUISINES = 20

# Graph model parameters
#  - keep an ingredient as a node if it appears in at least MIN_RECIPES recipes
#  - draw an edge between two ingredients if they co-occur in at least
#    MIN_COOC recipes AND their normalised pointwise mutual information is
#    above MIN_NPMI (i.e. they co-occur clearly more than chance)
MIN_RECIPES = 20
MIN_COOC = 10
MIN_NPMI = 0.10
