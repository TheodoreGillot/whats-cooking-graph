"""Clean the Food.com recipes and attach their ratings.

Input : data/raw/RAW_recipes.csv, data/raw/RAW_interactions.csv, data/raw/ingr_map.pkl
Output: data/processed/foodcom_recipes.pkl

Rules:
1. tags / steps / ingredients are parsed from text with ast.literal_eval.
2. Corrupted canonical names in ingr_map.pkl are repaired (CANONICAL_FIXES):
   flmy -> flour, wrong Latin plurals (fetum -> feta, pastum -> pasta, ...),
   olife -> olive, "mini" cut out of words (ature, cre mushroom).
3. A merge raw name -> canonical name is kept only if they share a word
   (punctuation and plurals ignored) and every word of the canonical name
   appears in some raw name; otherwise the raw name is kept.
   Exceptions checked by hand: ACCEPTED synonyms (green onions -> scallion, ...),
   KEEP_RAW names, OVERRIDES redirections.
4. minutes <= 0 or > 1 day are set to missing.
5. A 'cuisines' column lists the What's Cooking cuisines found in the tags.
6. n_reviews and mean_rating use rated reviews only (rating > 0).
"""

import re
import ast
from pathlib import Path
import pandas as pd
from config import RAW_DIR, PROCESSED_DIR

RAW = Path(RAW_DIR)
PROCESSED = Path(PROCESSED_DIR)

CUISINES = ["brazilian", "british", "cajun_creole", "chinese", "filipino", "french",
            "greek", "indian", "irish", "italian", "jamaican", "japanese", "korean",
            "mexican", "moroccan", "russian", "southern_us", "spanish", "thai",
            "vietnamese"]
TAG_TO_CUISINE = {c: c for c in CUISINES}
TAG_TO_CUISINE.update({"english": "british", "caribbean": "jamaican", "cajun": "cajun_creole",
                       "creole": "cajun_creole", "southern-united-states": "southern_us"})
MAX_MINUTES = 24 * 60

# Corrupted canonical names in ingr_map.pkl (regex -> correct text)
CANONICAL_FIXES = {
    r"flmy\b": "flour",                       # "our" became "my": flmy, cornflmy
    r"\bfetum\b": "feta",                     # -a read as a Latin plural
    r"\bpastum\b": "pasta",
    r"\bpolentum\b": "polenta",
    r"\btamarus\b": "tamari",                 # -i read as a Latin plural
    r"\bhavartus\b": "havarti",
    r"\bolife\b": "olive",                    # olives -> olife (like knives -> knife)
    r"\bcouscou\b": "couscous",
    r"\bcre mushroom\b": "cremini mushroom",  # "mini" cut out of "cremini"
    r"^ature ": "",                           # "mini" cut out of "miniature"
}

# Merges with no shared word that are correct (synonyms, brands)
ACCEPTED = {"annatto", "artificial sweetener", "cooking spray", "scallion"}

KEEP_RAW = {"green onion dip", "green onion dip mix", "dried green onion flakes"}

# Raw names checked by hand: raw name -> treat it like this other raw name
OVERRIDES = {
    "fisher chef's naturals slivered almonds": "slivered almonds",
    "blanched slivered almonds": "slivered almonds",
    "splenda sweetened cranberry juice": "cranberry juice",
    "sausage-filled ravioli": "ravioli",
}

def words(text):
    """Lowercase words, punctuation removed, plurals reduced: 'Tomatoes,' -> ['tomato']."""
    out = []
    for w in re.findall(r"[a-z]+", str(text).lower()):
        if w.endswith("ies"):
            w = w[:-3] + "y"                       # berries -> berry
        elif w.endswith(("oes", "ches", "shes", "sses", "xes")):
            w = w[:-2]                             # tomatoes -> tomato, peaches -> peach
        elif w.endswith("s") and not w.endswith(("ss", "us")):
            w = w[:-1]                             # onions -> onion (not asparagus, swiss)
        out.append(w)
    return out


def shares_a_word(raw, canonical):
    return len(set(words(raw)) & set(words(canonical))) > 0


def build_ingredient_map():
    m = pd.read_pickle(RAW / "ingr_map.pkl")
    for bad, good in CANONICAL_FIXES.items():
        m["replaced"] = m["replaced"].str.replace(bad, good, regex=True)

    # a canonical name is clean if all its words appear in some raw name
    raw_vocab = {w for name in m["raw_ingr"] for w in words(name)}
    clean = m["replaced"].apply(lambda c: all(w in raw_vocab for w in words(c)))
    shared = m.apply(lambda row: shares_a_word(row["raw_ingr"], row["replaced"]), axis=1)
    ok = (shared | m["replaced"].isin(ACCEPTED)) & clean

    print("merges rejected (raw name kept):", (~ok).sum())

    m.loc[~ok, "replaced"] = m.loc[~ok, "raw_ingr"]
    mapping = dict(zip(m["raw_ingr"], m["replaced"]))
    for raw, same_as in OVERRIDES.items():
        mapping[raw] = mapping.get(same_as, same_as)
    for raw in KEEP_RAW:
        mapping[raw] = raw
    return mapping

def main():
    recipes = pd.read_csv(RAW / "RAW_recipes.csv")
    for col in ["tags", "steps", "ingredients"]:
        recipes[col] = recipes[col].apply(ast.literal_eval)
    print("recipes:", len(recipes))

    mapping = build_ingredient_map()
    recipes["ingredients_raw"] = recipes["ingredients"]
    recipes["ingredients"] = recipes["ingredients_raw"].apply(
        lambda items: sorted({mapping.get(i, i) for i in items}))
    raw_names = {i for l in recipes["ingredients_raw"] for i in l}
    clean_names = {i for l in recipes["ingredients"] for i in l}
    print("ingredient names: raw", len(raw_names), "-> clean", len(clean_names))

    ok_time = (recipes["minutes"] > 0) & (recipes["minutes"] <= MAX_MINUTES)
    recipes["minutes"] = recipes["minutes"].where(ok_time)
    recipes["cuisines"] = recipes["tags"].apply(
        lambda tags: sorted({TAG_TO_CUISINE[t] for t in tags if t in TAG_TO_CUISINE}))
    print("missing minutes:", recipes["minutes"].isna().sum())
    print("recipes with a cuisine:", (recipes["cuisines"].str.len() > 0).sum())

    inter = pd.read_csv(RAW / "RAW_interactions.csv")
    rated = inter[inter["rating"] > 0]
    stats = rated.groupby("recipe_id")["rating"].agg(n_reviews="count", mean_rating="mean")
    recipes = recipes.merge(stats, left_on="id", right_index=True, how="left")
    recipes["n_reviews"] = recipes["n_reviews"].fillna(0).astype(int)
    print("recipes with >= 5 rated reviews:", (recipes["n_reviews"] >= 5).sum())

    recipes["name"] = recipes["name"].fillna("(no name)")
    recipes = recipes[recipes["ingredients"].str.len() > 0]
    keep = ["id", "name", "minutes", "n_steps", "steps", "description", "tags",
            "cuisines", "ingredients", "ingredients_raw", "n_reviews", "mean_rating"]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    recipes[keep].to_pickle(PROCESSED / "foodcom_recipes.pkl")
    print("saved", len(recipes), "recipes")


if __name__ == "__main__":
    main()