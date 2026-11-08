"""Map What's Cooking ingredient names onto Food.com canonical names.

Input : data/raw/train.json, data/raw/ingr_map.pkl
Output: data/processed/whats_cooking_canonical.json (same structure as train.json)

Rules, tried in this order for each normalised name:
1. a name checked by hand (SAME_AS) -> its Food.com name
2. a raw Food.com name -> its canonical name (ingr_map, cleaned as in clean_foodcom.py)
3. already a Food.com canonical name -> unchanged
4. remove preparation words (MODIFIERS) and retry 1-3
5. otherwise the name is kept (it exists only in What's Cooking)
"""
import json
from collections import Counter

from config import RAW_DIR, PROCESSED_DIR, TRAIN_FILENAME
from graph import normalize
from clean_foodcom import build_ingredient_map

MODIFIERS = {"large", "small", "medium", "chopped", "fresh", "freshly", "minced",
             "grated", "shredded", "sliced", "diced", "finely", "peeled", "extra-virgin",
             "melted"}

# What's Cooking name -> Food.com canonical name, checked by hand
SAME_AS = {
    "mayonaise": "mayonnaise",
    "tumeric": "turmeric",
    "corn starch": "cornstarch",
    "jalapeno chilies": "jalapeno",
    "crushed red pepper": "red pepper flake",
    "fat free less sodium chicken broth": "chicken broth",
    "low salt chicken broth": "chicken broth",
    "reduced sodium chicken broth": "chicken broth",
    "beansprouts": "bean sprout",
    "confectioners sugar": "powdered sugar",
    "feta cheese crumbles": "feta",
    "parmigiano reggiano cheese": "parmigiano-reggiano cheese",
    "pinenuts": "pine nut",
    "yellow corn meal": "yellow cornmeal",
    "chile pepper": "chili pepper",
    "fresh ginger root": "gingerroot",
    "ginger root": "gingerroot",
    "half & half": "half-and-half",
    "shiitake": "shiitake mushroom",
    "chillies": "chili",
    "chiles": "chile",
    "bread crumbs": "breadcrumb",
    "dry bread crumbs": "dry breadcrumb",
    "green chile": "green chili",
    "serrano chile": "serrano chili",
    "sriracha": "sriracha sauce",
    "chinese five-spice powder": "five-spice powder",
    "monterey jack": "monterey jack cheese",
    "tomato purée": "tomato puree",
    "cilantro sprigs": "cilantro",
    "bacon slices": "bacon",
    "thyme sprigs": "fresh thyme",
    "kalamata": "kalamata olive",
    "pitted kalamata olives": "kalamata olive",
    "tabasco pepper sauce": "tabasco sauce",
    "all purpose unbleached flour": "unbleached all-purpose flour",
    "fettucine": "fettuccine",
    "asian fish sauce": "fish sauce",
    "daikon": "daikon radish",
    "crème fraîche": "creme fraiche",
    "szechwan peppercorns": "szechuan peppercorn",
    "cotija": "cotija cheese",
}


def lookup(name, mapping, canonical):
    if name in SAME_AS:
        return SAME_AS[name]
    if name in mapping:
        return mapping[name]
    if name in canonical:
        return name
    return None


def to_canonical(name, mapping, canonical):
    found = lookup(name, mapping, canonical)
    if found:
        return found
    stripped = " ".join(w for w in name.split() if w not in MODIFIERS)
    return lookup(stripped, mapping, canonical)


def main():
    mapping = build_ingredient_map()
    canonical = set(mapping.values())
    wrong = [t for t in SAME_AS.values() if t not in canonical]
    print("SAME_AS targets that are not Food.com names:", wrong)

    with (RAW_DIR / TRAIN_FILENAME).open(encoding="utf-8") as handle:
        recipes = json.load(handle)

    uses = Counter(normalize(i) for r in recipes for i in r["ingredients"])
    matched = {name: to_canonical(name, mapping, canonical) for name in uses}
    total = sum(uses.values())
    exact = sum(c for name, c in uses.items() if name in mapping or name in canonical)
    covered = sum(c for name, c in uses.items() if matched[name])
    print(f"ingredient uses matched: exact {exact / total:.1%} -> with rules {covered / total:.1%}")
    print("distinct names:", len(uses), "->", len({matched[n] or n for n in uses}))

    missing = Counter({name: c for name, c in uses.items() if not matched[name]})
    print("most frequent unmatched:", missing.most_common(30))

    for recipe in recipes:
        names = {normalize(i) for i in recipe["ingredients"]}
        recipe["ingredients"] = sorted({matched[n] or n for n in names})

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with (PROCESSED_DIR / "whats_cooking_canonical.json").open("w", encoding="utf-8") as handle:
        json.dump(recipes, handle, ensure_ascii=False)
    print("saved", len(recipes), "recipes")


if __name__ == "__main__":
    main()