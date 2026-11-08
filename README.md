# What's Cooking? A graph analysis of recipes and ingredients

Graph-analytics project. We model recipes as a graph of ingredients (two ingredients
are linked when they are cooked together) in order to:

1. **analyse the ingredient graph**: structure, connectivity, central ingredients, and
   whether its communities match the world's cuisines;
2. **recommend recipes**: given the ingredients a user has, rank existing recipes using
   the recipe–ingredient graph.

**Status:** data acquisition, exploratory analysis (`notebooks/01`, `notebooks/02`), Food.com
cleaning (`src/clean_foodcom.py`) and the ingredient-graph analysis pipeline (`src/run_all.py`)
are in place. Next: the recipe recommender (personalised PageRank on the recipe–ingredient graph).

## Data

Two Kaggle datasets are used. They are **not** committed to this repository; fetch them
locally as described below.

| Dataset | What it brings | Size |
|---|---|---|
| [What's Cooking?](https://www.kaggle.com/competitions/whats-cooking) (Yummly) | cuisine label for every recipe → ground truth for the graph analysis | 39,774 recipes, 20 cuisines, 6,714 ingredient names |
| [Food.com Recipes and Interactions](https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions) (Majumder et al., EMNLP 2019) | recipe names, steps, cooking time, tags, user ratings → catalogue for the recommender | 231,637 recipes, 1,132,367 reviews |

Files expected in `data/raw/`:

```
train.json              What's Cooking training set
RAW_recipes.csv         Food.com recipes
RAW_interactions.csv    Food.com reviews and ratings
ingr_map.pkl            Food.com authors' ingredient-name map (has known bugs, see notebook 02)
```

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
source .venv/bin/activate            # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
```

### Fetch and validate

What's Cooking:

```bash
python src/fetch_data.py
python src/validate_data.py
```

Expected output: `recipes: 39774  cuisines: 20  distinct ingredients: 6714`.

Food.com (manual for now): download the dataset from its Kaggle page ("Download"), then
copy `RAW_recipes.csv`, `RAW_interactions.csv` and `ingr_map.pkl` into `data/raw/`.

## Exploratory analysis

```bash
jupyter notebook notebooks/
```

| Notebook | Content |
|---|---|
| `01_eda_whats_cooking.ipynb` | cuisines (very unbalanced), recipe sizes, long tail of ingredients, data-quality problems (uppercase, brands, quantities, synonyms), typical ingredients per cuisine, frequent vs associated (NPMI) ingredient pairs |
| `02_eda_foodcom.ipynb` | recipe sizes and cooking times, cuisine tags (17% of recipes), ingredient map and its bugs ("flour" → "flmy"), ratings, overlap with What's Cooking (84% of ingredient uses match exactly) |

## Layout

```
src/
  config.py         shared paths, dataset expectations, graph parameters
  fetch_data.py     download the What's Cooking data with kagglehub
  validate_data.py  unpack the archives and sanity-check train.json
  graph.py          bipartite graph and NPMI-filtered ingredient graph
  prepare_data.py   clean recipes and write the graphs to data/processed/
notebooks/
  01_eda_whats_cooking.ipynb
  02_eda_foodcom.ipynb
data/
  raw/              fetched files (gitignored)
  processed/        derived datasets (gitignored)
```

## References

- Kaggle & Yummly (2015). *What's Cooking?* <https://www.kaggle.com/competitions/whats-cooking>
- Majumder, B. P., Li, S., Ni, J., McAuley, J. (2019). *Generating Personalized Recipes from
  Historical User Preferences.* EMNLP 2019. (Food.com dataset)
