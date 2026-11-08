"""Download ingredient photos from TheMealDB for the web demo.

TheMealDB (https://www.themealdb.com) offers its API and ingredient pictures free
for educational and personal projects. The pictures are not committed: this script
downloads them into data/images/ (gitignored) and writes data/images/manifest.json,
which maps our ingredient names to picture files.

Matching, tried in order for each of our ingredient names:
1. ALIASES (our name -> TheMealDB name, e.g. scallion -> spring onion)
2. the same name, plurals ignored (egg = Eggs)
3. the name without its leading preparation words (fresh ground black pepper -> black pepper)
No picture is better than a wrong one, so nothing else is guessed (peanut butter is
never matched to butter).

Usage: python src/fetch_images.py
"""
import json
import time
import urllib.parse
import urllib.request
from collections import Counter

from config import PROCESSED_DIR, ROOT
from clean_foodcom import words

import pandas as pd

LIST_URL = "https://www.themealdb.com/api/json/v1/1/list.php?i=list"
IMAGE_URL = "https://www.themealdb.com/images/ingredients/{}.png"
OUT_DIR = ROOT / "data" / "images"
HEADERS = {"User-Agent": "Mozilla/5.0 (student project; graph analytics course)"}

# Leading words that can be dropped without changing the ingredient
DROPPABLE = {"fresh", "freshly", "dried", "chopped", "minced", "sliced", "diced", "grated",
             "shredded", "large", "small", "medium", "frozen", "canned", "boneless",
             "skinless", "lean", "unsalted", "salted", "cooked", "raw", "plain", "whole",
             "extra", "virgin", "light", "low", "fat", "free", "reduced", "sodium", "ground",
             "crushed", "finely", "packed", "pure", "organic", "baby"}

# Our name -> TheMealDB name (British names and synonyms)
ALIASES = {
    "scallion": "spring onion",
    "green onion": "spring onion",
    "cilantro": "coriander",
    "fresh cilantro": "coriander",
    "zucchini": "courgette",
    "eggplant": "aubergine",
    "powdered sugar": "icing sugar",
    "flour": "plain flour",
    "all-purpose flour": "plain flour",
    "cornstarch": "cornflour",
    "heavy cream": "double cream",
    "whipping cream": "double cream",
    "heavy whipping cream": "double cream",
    "half-and-half": "single cream",
    "ground beef": "minced beef",
    "lean ground beef": "minced beef",
    "shrimp": "prawns",
    "baking soda": "bicarbonate of soda",
    "bell pepper": "red pepper",
    "red bell pepper": "red pepper",
    "green bell pepper": "green pepper",
    "chicken broth": "chicken stock",
    "beef broth": "beef stock",
    "vegetable broth": "vegetable stock",
    "arugula": "rocket",
    "chili powder": "chilli powder",
    "chili": "chilli",
    "garbanzo bean": "chickpeas",
    "canola oil": "vegetable oil",
    "cheddar": "cheddar cheese",
    "parmesan cheese": "parmesan",
    "fresh ground black pepper": "black pepper",
    "pepper": "black pepper",
    "salt and pepper": "salt",
    "garlic powder": "garlic powder",
    "confectioners' sugar": "icing sugar",
    "cool whip": "double cream",
    "vanilla": "vanilla extract",
    "sesame oil": "sesame seed oil",
    "pecan": "pecan nuts",
    "ketchup": "tomato ketchup",
    "tomato paste": "tomato puree",
    "white sugar": "granulated sugar",
    "feta cheese": "feta",
    "dry mustard": "mustard powder",
    "chile": "chilli",
    "green chili": "green chilli",
    "jalapeno pepper": "jalapeno",
    "cayenne": "cayenne pepper",
    "lemon, juice of": "lemon juice",
    "barbecue sauce": "barbeque sauce",
    "hot sauce": "hotsauce",
    "skim milk": "milk",
    "celery rib": "celery",
    "salt & pepper": "salt",
    "salt & ground black pepper": "salt",
    "chicken breast half": "chicken breast",
}


def key(name):
    return " ".join(words(name))


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(), response.headers.get("Content-Type", "")


def candidates(name):
    """Keys to try for one of our names, best first."""
    keys = []
    if name in ALIASES:
        keys.append(key(ALIASES[name]))
    keys.append(key(name))
    parts = key(name).split()
    while len(parts) > 1 and parts[0] in DROPPABLE:
        parts = parts[1:]
        keys.append(" ".join(parts))
    return keys


def match(our_names, mealdb_names):
    by_key = {}
    for m in mealdb_names:
        by_key.setdefault(key(m), m)
    found = {}
    for name in our_names:
        for k in candidates(name):
            if k in by_key:
                found[name] = by_key[k]
                break
    return found


def main():
    recipes = pd.read_pickle(PROCESSED_DIR / "foodcom_recipes.pkl")
    recipes = recipes[recipes["n_reviews"] >= 5]
    uses = Counter(i for ings in recipes["ingredients"] for i in ings)

    data = json.loads(fetch(LIST_URL)[0])
    mealdb = [m["strIngredient"].strip() for m in data["meals"] if m.get("strIngredient")]
    thumbs = {m["strIngredient"].strip(): m.get("strThumb") for m in data["meals"] if m.get("strIngredient")}
    print("TheMealDB ingredients:", len(mealdb))

    found = match(list(uses), mealdb)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files, failed = {}, []
    for m in sorted(set(found.values())):
        filename = key(m).replace(" ", "_") + ".png"
        path = OUT_DIR / filename
        if not path.exists():
            urls = [u for u in [thumbs.get(m), IMAGE_URL.format(urllib.parse.quote(m))] if u]
            for url in urls:
                try:
                    content, kind = fetch(url)
                except Exception:
                    continue
                if kind.startswith("image"):
                    path.write_bytes(content)
                    break
            time.sleep(0.05)
        if path.exists():
            files[m] = filename
        else:
            failed.append(m)

    manifest = {name: files[m] for name, m in found.items() if m in files}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")

    top = [n for n, _ in uses.most_common(300)]
    covered_uses = sum(c for n, c in uses.items() if n in manifest) / sum(uses.values())
    print(f"pictures downloaded: {len(files)} (failed: {len(failed)})")
    print(f"our ingredients with a picture: {len(manifest)}; "
          f"top 300 covered: {sum(n in manifest for n in top)}; ingredient uses covered: {covered_uses:.0%}")
    print("most used without a picture:", [n for n in top if n not in manifest][:30])


if __name__ == "__main__":
    main()
