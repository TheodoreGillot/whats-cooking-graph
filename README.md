# What's Cooking? A graph analysis

Graph-analytics project: turn a set of recipes into a graph of ingredients (two
ingredients are linked when they are cooked together) and investigate whether the
graph's communities match the world's cuisines.

**Status:** data acquisition and validation.

## Data

Source: Kaggle "What's Cooking?" competition — training set of 39,774 recipes
across 20 cuisines, originally from Yummly
(<https://www.kaggle.com/competitions/whats-cooking>).

The data is **not** committed to this repository (Kaggle competition rules forbid
redistributing it). Fetch it locally as described below.

### One-time setup

1. Create a Kaggle account and accept the competition rules at
   <https://www.kaggle.com/competitions/whats-cooking/rules>.
2. Create a Kaggle API token (Kaggle → Settings → API → "Create New Token") and
   expose it as an environment variable:

   ```bash
   export KAGGLE_API_TOKEN="KGAT_..."    # Windows (cmd): set KAGGLE_API_TOKEN=KGAT_...
   ```

### Install

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Fetch and validate

```bash
python src/fetch_data.py
python src/validate_data.py
```

Expected output: `recipes: 39774  cuisines: 20  distinct ingredients: 6714`.

## Layout

```
src/
  config.py        shared paths and dataset expectations
  fetch_data.py    download the competition data with kagglehub
  validate_data.py unpack the archives and sanity-check train.json
data/
  raw/             fetched archives and train.json (gitignored)
  processed/       derived datasets (gitignored)
```
