"""Web demo "Fridge to plate": a small API around src/recommend.py plus a designed page.

Run:   python server.py      then open http://127.0.0.1:8000

Needs data/processed/foodcom_recipes.pkl (src/clean_foodcom.py) and
results/foodcom_ingredient_graph.graphml (last cell of notebook 04).
Optional: ingredient photos in data/images/ (src/fetch_images.py) and an
ANTHROPIC_API_KEY environment variable for the recipe writer.
"""
import difflib
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import networkx as nx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT / "src"))

from recommend import load_catalogue, build_matrix, query_vector, score_ppr, recommend  # noqa: E402

GRAPH_FILE = ROOT / "results" / "foodcom_ingredient_graph.graphml"
LAYOUT_FILE = ROOT / "results" / "foodcom_layout.json"
IMAGE_DIR = ROOT / "data" / "images"
WEB_DIR = ROOT / "web"

STAPLES = ["salt", "pepper", "black pepper", "water", "oil", "olive oil", "vegetable oil",
           "butter", "sugar"]
CHEF_MODEL = os.environ.get("CHEF_MODEL", "claude-sonnet-5-5")

# A community is named after the first signature ingredient it contains.
FAMILY_NAMES = {
    "baking powder": "Baking and desserts",
    "chicken broth": "Soups and stews",
    "olive oil": "Mediterranean",
    "soy sauce": "East Asian",
    "worcestershire sauce": "Grill and barbecue",
    "tortilla": "Mexican",
    "vodka": "Drinks",
}
# Validated categorical palette (dataviz reference order), one colour per family.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
NO_FAMILY = {"id": -1, "name": "Unconnected", "color": "#a3a39b"}


# ---------- data, loaded once ----------
print("Loading recipes and graph...")
df = load_catalogue(min_reviews=5)
B, vocab, index = build_matrix(df)
freq = np.asarray(B.sum(axis=0)).ravel().astype(int)
G = nx.read_graphml(GRAPH_FILE)
staples = [s for s in STAPLES if s in index]

families = []
for k in sorted({int(c) for _, c in G.nodes(data="community") if int(c) >= 0}):
    members = [n for n, c in G.nodes(data="community") if int(c) == k]
    members.sort(key=lambda n: -G.nodes[n]["recipes"])
    name = next((label for sig, label in FAMILY_NAMES.items() if sig in members), None)
    families.append({"id": k, "name": name or " and ".join(members[:2]).capitalize(),
                     "color": PALETTE[k % len(PALETTE)], "size": len(members),
                     "top": members[:6]})
family_by_id = {f["id"]: f for f in families}


def family_of_node(name):
    c = int(G.nodes[name]["community"]) if name in G else -1
    return family_by_id.get(c, NO_FAMILY)


manifest = {}
if (IMAGE_DIR / "manifest.json").exists():
    manifest = json.loads((IMAGE_DIR / "manifest.json").read_text(encoding="utf-8"))


def image_of(name):
    return f"/img/{manifest[name]}" if name in manifest else None


def ingredient_info(name):
    fam = family_of_node(name)
    return {"name": name, "img": image_of(name), "family": fam["id"],
            "recipes": int(freq[index[name]]) if name in index else 0}


def compute_layout():
    """Positions for the full map (largest component), cached in results/."""
    if LAYOUT_FILE.exists():
        return json.loads(LAYOUT_FILE.read_text(encoding="utf-8"))
    print("Computing the map layout once (about a minute)...")
    H = G.subgraph(max(nx.connected_components(G), key=len))
    try:
        pos = nx.forceatlas2_layout(H, weight="npmi", seed=42, max_iter=300)
    except AttributeError:  # networkx < 3.4
        pos = nx.spring_layout(H, weight="npmi", seed=42, iterations=200)
    # Rotate so that the longest direction is horizontal (screens are wide).
    names = list(pos)
    xy = np.array([pos[n] for n in names], dtype=float)
    xy -= xy.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov(xy.T))
    xy = xy @ vectors[:, ::-1]
    xy -= xy.min(axis=0)
    xy *= 1000 / xy.max()
    layout = {n: [round(float(x), 1), round(float(y), 1)] for n, (x, y) in zip(names, xy)}
    LAYOUT_FILE.parent.mkdir(exist_ok=True)
    LAYOUT_FILE.write_text(json.dumps(layout), encoding="utf-8")
    return layout


layout = compute_layout()

# Food.com keeps some variants of one ingredient apart. For shopping they are the same thing.
SAME_INGREDIENT = [
    ["garlic", "garlic clove"], ["flour", "all-purpose flour"], ["egg", "large egg"],
    ["pepper", "black pepper"] + sorted(n for n in index if n.endswith(" black pepper")),
    ["ground beef", "lean ground beef", "extra lean ground beef"],
    ["sugar", "white sugar", "granulated sugar"],
    ["vanilla", "vanilla extract"], ["cilantro", "fresh cilantro"], ["chicken broth", "chicken stock"],
    ["beef broth", "beef stock"], ["parmesan cheese", "parmesan"], ["onion", "yellow onion"],
    ["parsley", "fresh parsley"], ["ginger", "fresh ginger", "gingerroot"],
    ["lemon juice", "fresh lemon juice"], ["butter", "unsalted butter"], ["basil", "fresh basil"],
    ["salt", "kosher salt", "sea salt"],
]
group_of = {}
for group in SAME_INGREDIENT:
    members = [n for n in group if n in index]
    for n in members:
        group_of[n] = members


def same_as(name):
    return group_of.get(name, [name])


recipe_names = df["name"].fillna("").str.replace(r"\s+", " ", regex=True).str.lower()
name_words = sorted({w for n in recipe_names for w in re.findall(r"[a-z]+", n) if len(w) > 2})
recipe_row = {int(i): k for k, i in enumerate(df["id"])}

# Words that describe a recipe but are not a dish ("easy", "my", "crock pot"...).
DISH_STOP = set("""a an and the of with for in on or to from my our your his her mom moms grandma grandmas aunt
easy easiest best quick simple super homemade healthy healthier low fat free style recipe de la le el no not
very really good great perfect ultimate famous favorite favourite yummy delicious awesome world ever old fashioned
new light lighter skinny fast minute minutes crock pot slow cooker oamc copycat version like amazing tasty""".split())


def build_dish_phrases():
    """Dish names for the search box: 1- to 3-word phrases found in at least 3 recipe names."""
    counts = Counter()
    for name in recipe_names:
        tokens = [w for w in re.findall(r"[a-z]+", name) if len(w) > 1]
        grams = set()
        for k in (1, 2, 3):
            for i in range(len(tokens) - k + 1):
                g = tokens[i:i + k]
                if g[0] not in DISH_STOP and g[-1] not in DISH_STOP:
                    grams.add(" ".join(g))
        counts.update(grams)
    phrases = {p: c for p, c in counts.items() if c >= 3}
    longest = {}  # "beef short" is dropped when "beef short ribs" covers almost all its recipes
    for p, c in phrases.items():
        head = p.rsplit(" ", 1)[0]
        if head != p:
            longest[head] = max(longest.get(head, 0), c)
    for p in [p for p in phrases if p.endswith("s") and p[:-1] in phrases]:
        phrases[p[:-1]] += phrases.pop(p)  # "cookies" counted with "cookie" (the search covers plurals)
    return {p: c for p, c in phrases.items() if longest.get(p, 0) < 0.8 * c}


dish_phrases = build_dish_phrases()
print(f"Ready: {len(df):,} recipes, {len(vocab):,} ingredients, {len(families)} families.")


# ---------- helpers ----------
def pretty(text):
    """Undo Food.com's tokenisation: 'nif s grilled , 1 / 2 cup' -> "Nif's grilled, 1/2 cup"."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    text = re.sub(r"\b(\w+) n (\w+)\b", r"\1 'n' \2", text)
    text = re.sub(r"\b(\w+) s\b", r"\1's", text)
    text = re.sub(r"(\d) / (\d)", r"\1/\2", text)
    text = re.sub(r" ([,.;:!?)])", r"\1", text)
    text = text.replace("( ", "(")
    return text[:1].upper() + text[1:]


def recipe_family(ings):
    labels = [int(G.nodes[i]["community"]) for i in ings if i in G and int(G.nodes[i]["community"]) >= 0]
    return max(set(labels), key=labels.count) if labels else -1


def basket_names(names):
    names = [n for n in names if n in index]
    if not names:
        raise HTTPException(400, "None of these ingredients is in the catalogue.")
    return names


class Query(BaseModel):
    basket: list[str]
    method: str = "ppr"
    restart: float = 0.99
    staples: bool = True
    diverse: bool = False
    k: int = 8


class ChefQuery(BaseModel):
    basket: list[str]
    seed: int = 0
    write: bool = True


# ---------- API ----------
app = FastAPI(title="Fridge to plate")


@app.get("/api/meta")
def meta():
    order = np.argsort(-freq)
    return {
        "ingredients": [ingredient_info(vocab[j]) for j in order],
        "families": families + [NO_FAMILY],
        "staples": staples,
        "recipes": len(df),
        "chef_writer": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "chef_model": CHEF_MODEL,
    }


@app.post("/api/recommend")
def api_recommend(q: Query):
    names = basket_names(q.basket)
    pool = recommend(df, B, index, names, q.method, k=200 if q.diverse else q.k,
                     restart=q.restart, staples=staples if q.staples else ())
    pool["family"] = pool["ingredients"].apply(recipe_family)
    if q.diverse:
        pool = pool.drop_duplicates("family")
    return {"recipes": [recipe_json(r, r["matched"], r["missing"]) for _, r in pool.head(q.k).iterrows()]}


def recipe_json(r, have, missing):
    return {
        "id": int(r["id"]),
        "name": pretty(r["name"]),
        "minutes": None if r["minutes"] != r["minutes"] else int(r["minutes"]),
        "rating": None if r["mean_rating"] != r["mean_rating"] else round(float(r["mean_rating"]), 1),
        "reviews": int(r["n_reviews"]),
        "family": recipe_family(r["ingredients"]),
        "have": [ingredient_info(i) for i in have],
        "missing": [ingredient_info(i) for i in missing],
        "steps": [pretty(s) for s in r["steps"]],
    }


class PlanQuery(BaseModel):
    dish: str = ""
    recipe: Optional[int] = None  # a Food.com recipe id: plan that exact recipe
    basket: list[str] = []
    staples: bool = True


@app.get("/api/dishes")
def api_dishes(q: str = ""):
    """Suggestions for the dish search: dish names, then the most reviewed matching recipes."""
    q = re.sub(r"\s+", " ", q.lower()).strip()
    if len(q) < 2:
        return {"dishes": [], "recipes": []}
    dishes = sorted((p for p in dish_phrases if p.startswith(q)), key=lambda p: -dish_phrases[p])[:5]
    hits = np.where(recipe_names.str.contains(rf"\b{re.escape(q)}", regex=True).to_numpy())[0]
    hits = hits[np.argsort(-df["n_reviews"].to_numpy()[hits], kind="stable")][:6]
    recipes = []
    for r in hits:
        row = df.iloc[r]
        rating = row["mean_rating"]
        recipes.append({"id": int(row["id"]), "name": pretty(row["name"]), "reviews": int(row["n_reviews"]),
                        "rating": None if rating != rating else round(float(rating), 1)})
    return {"dishes": [{"name": p, "n": dish_phrases[p]} for p in dishes], "recipes": recipes}


def find_dish(text):
    """Recipes named with the exact phrase; if fewer than 3, with every word in any order."""
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return np.array([], dtype=int), words
    phrase = r"\s+".join(re.escape(w) for w in words)
    ids = np.where(recipe_names.str.contains(rf"\b{phrase}(?:s|es)?\b", regex=True).to_numpy())[0]
    if len(ids) >= 3:
        return ids, words
    mask = np.ones(len(df), dtype=bool)
    for w in words:
        mask &= recipe_names.str.contains(rf"\b{re.escape(w)}(?:s|es)?\b", regex=True).to_numpy()
    return np.where(mask)[0], words


@app.post("/api/plan")
def api_plan(q: PlanQuery):
    if q.recipe is not None:
        return plan_recipe(q)
    ids, words = find_dish(q.dish)
    if not len(ids):
        close = [difflib.get_close_matches(w, name_words, n=1, cutoff=0.75) for w in words]
        guess = " ".join(c[0] if c else w for c, w in zip(close, words))
        return {"mode": "dish", "dish": q.dish, "n": 0, "items": [], "recipes": [],
                "suggestion": guess if words and guess != " ".join(words) else None}

    fridge = {m for n in q.basket if n in index for m in same_as(n)}
    kitchen = {m for n in (staples if q.staples else []) for m in same_as(n)}

    # Share of the matching recipes that use each ingredient (variants counted once).
    R = B[ids]
    share = np.asarray(R.sum(axis=0)).ravel() / len(ids)
    for members in {tuple(g) for g in group_of.values()}:
        cols = [index[m] for m in members]
        if share[cols].max() == 0:
            continue
        top = cols[int(np.argmax(share[cols]))]
        union = (np.asarray(R[:, cols].sum(axis=1)).ravel() > 0).mean()
        share[cols] = 0
        share[top] = union
    order = [j for j in np.argsort(-share) if share[j] > 0]
    core = [j for j in order if share[j] >= 0.25][:16]
    if len(core) < 5:
        core = [j for j in order if share[j] >= 0.1][:8]

    def status(name):
        names = same_as(name)
        if any(n in fridge for n in names):
            return "fridge"
        if any(n in kitchen for n in names):
            return "kitchen"
        return "buy"

    items = [dict(ingredient_info(vocab[j]), share=round(float(share[j]), 2), status=status(vocab[j])) for j in core]

    # Versions: recipes with at least half of the typical ingredients (no 3-ingredient shortcuts),
    # sorted by how many ingredients would have to be bought, then by rating.
    hits = np.zeros(len(ids))
    for j in core:
        cols = [index[m] for m in same_as(vocab[j])]
        hits += np.asarray(R[:, cols].sum(axis=1)).ravel() > 0
    keep = np.where(hits >= max(1, (len(core) + 1) // 2))[0]
    if not len(keep):
        keep = np.arange(len(ids))
    owned = np.zeros(B.shape[1])
    owned[[index[n] for n in fridge | kitchen if n in index]] = 1
    n_missing = np.diff(R.indptr)[keep] - R[keep] @ owned
    rating = df["mean_rating"].fillna(0).to_numpy()[ids[keep]]
    reviews = df["n_reviews"].to_numpy()[ids[keep]]
    best = keep[np.lexsort((-reviews, -rating, n_missing))[:6]]
    recipes = []
    for r in ids[best]:
        row = df.iloc[r]
        missing = [i for i in row["ingredients"] if i not in fridge and i not in kitchen]
        have = [i for i in row["ingredients"] if i not in missing]
        recipes.append(recipe_json(row, have, missing))
    return {"mode": "dish", "dish": " ".join(words), "n": int(len(ids)), "items": items, "recipes": recipes,
            "suggestion": None}


def plan_recipe(q):
    if q.recipe not in recipe_row:
        raise HTTPException(404, "This recipe is not in the catalogue.")
    row = df.iloc[recipe_row[q.recipe]]
    fridge = {m for n in q.basket if n in index for m in same_as(n)}
    kitchen = {m for n in (staples if q.staples else []) for m in same_as(n)}
    items = []
    for name in row["ingredients"]:
        status = "fridge" if name in fridge else "kitchen" if name in kitchen else "buy"
        items.append(dict(ingredient_info(name), share=None, status=status))
    missing = [i["name"] for i in items if i["status"] == "buy"]
    have = [i["name"] for i in items if i["status"] != "buy"]
    return {"mode": "recipe", "dish": pretty(row["name"]), "n": 1, "items": items,
            "recipes": [recipe_json(row, have, missing)], "suggestion": None}


@app.post("/api/shop")
def api_shop(q: Query):
    names = basket_names(q.basket)
    qv = query_vector(names, index, B.shape[1])
    y, x = score_ppr(B, qv, q.restart)
    best = np.argsort(-y)[:30]
    in_best = np.asarray(B[best].sum(axis=0)).ravel()
    owned = [index[n] for n in names + (staples if q.staples else [])]
    in_best[owned] = 0
    x[owned] = -np.inf
    candidates = [j for j in np.argsort(-x)[:40] if in_best[j] > 0]
    candidates.sort(key=lambda j: (-in_best[j], -x[j]))
    items = []
    for j in candidates[:12]:
        info = ingredient_info(vocab[j])
        info["in_best"] = int(in_best[j])
        items.append(info)
    return {"items": items, "of": len(best)}


def edges_between(nodes):
    return [{"source": u, "target": v, "npmi": round(float(d["npmi"]), 3), "count": int(d["count"])}
            for u, v, d in G.subgraph(nodes).edges(data=True)]


@app.post("/api/map/around")
def map_around(q: Query):
    names = [n for n in basket_names(q.basket) if n in G]
    score = {}
    for n in names:
        for m, d in G[n].items():
            if m not in names:
                score[m] = score.get(m, 0) + float(d["npmi"])
    chosen = set(names)
    for n in names:  # each basket ingredient keeps its 3 strongest partners
        chosen.update(m for m, _ in sorted(G[n].items(), key=lambda kv: -kv[1]["npmi"])[:3])
    for m in sorted(score, key=lambda m: -score[m]):  # then the best shared partners
        if len(chosen) >= len(names) + 16:
            break
        chosen.add(m)
    nodes = [dict(ingredient_info(n), basket=n in names) for n in chosen]
    return {"nodes": nodes, "edges": edges_between(chosen)}


_full_map = None


@app.get("/api/map/full")
def map_full():
    global _full_map
    if _full_map is None:
        keep = set()
        for n in layout:
            for m, _ in sorted(G[n].items(), key=lambda kv: -kv[1]["npmi"])[:3]:
                keep.add(tuple(sorted((n, m))))
        nodes = [dict(ingredient_info(n), x=p[0], y=p[1]) for n, p in layout.items()]
        edges = [{"source": u, "target": v, "npmi": round(float(G[u][v]["npmi"]), 3)} for u, v in keep]
        _full_map = {"nodes": nodes, "edges": edges}
    return _full_map


@app.get("/api/ingredient/{name}")
def api_ingredient(name: str):
    if name not in index:
        raise HTTPException(404, f"Unknown ingredient: {name}")
    info = ingredient_info(name)
    partners = sorted(G[name].items(), key=lambda kv: -kv[1]["npmi"])[:8] if name in G else []
    info["partners"] = [dict(ingredient_info(m), npmi=round(float(d["npmi"]), 2), together=int(d["count"]))
                        for m, d in partners]
    return info


def invent(names, seed, size):
    """Grow the basket with the ingredients that go best with everything already chosen."""
    rng = random.Random(seed)
    chosen = [n for n in names if n in G and G.degree(n) > 0]
    added = []
    while len(chosen) < size:
        score = {}
        for c in set().union(*(G[n] for n in chosen)) - set(chosen) - set(STAPLES):
            score[c] = sum(float(G[c][n]["npmi"]) for n in chosen if G.has_edge(c, n)) / len(chosen)
        if not score:
            break
        top = sorted(score, key=lambda c: -score[c])[:3 if seed else 1]
        pick = rng.choices(top, weights=[score[c] for c in top])[0]
        links = sorted(((n, float(G[pick][n]["npmi"])) for n in chosen if G.has_edge(pick, n)),
                       key=lambda kv: -kv[1])[:3]
        added.append((pick, links))
        chosen.append(pick)
    return chosen, dict(added)


def write_recipe(ingredients):
    import anthropic  # optional dependency, only needed for the writer

    prompt = (
        "Write one home-cooking recipe whose main ingredients are exactly: "
        + ", ".join(ingredients)
        + ". You may also use salt, pepper, oil, butter, water and sugar, and nothing else. "
        "Answer with JSON only, with the keys: title (at most 8 words), summary (one sentence), "
        "minutes (an integer), steps (a list of 4 to 8 short instructions)."
    )
    client = anthropic.Anthropic()
    message = client.messages.create(model=CHEF_MODEL, max_tokens=1200,
                                     messages=[{"role": "user", "content": prompt}])
    text = message.content[0].text
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


@app.post("/api/chef")
def api_chef(q: ChefQuery):
    names = basket_names(q.basket)
    in_graph = [n for n in names if n in G and G.degree(n) > 0]
    if not in_graph:
        raise HTTPException(400, "None of these ingredients is in the ingredient map.")
    size = min(len(in_graph) + 4, 10)
    chosen, added = invent(in_graph, q.seed, size)

    have = np.zeros(B.shape[1])
    have[[index[n] for n in chosen]] = 1
    shared = B @ have
    jaccard = shared / (np.diff(B.indptr) + len(chosen) - shared)
    j = int(np.argmax(jaccard))

    result = {
        "ingredients": [dict(ingredient_info(n), added=n in added,
                             links=[{"with": m, "npmi": round(v, 2)} for m, v in added.get(n, [])])
                        for n in chosen],
        "closest": {"name": pretty(df.iloc[j]["name"]), "shared": int(shared[j]),
                    "of": int(np.diff(B.indptr)[j])},
        "recipe": None,
        "note": None,
    }
    if not q.write:
        return result
    if not os.environ.get("ANTHROPIC_API_KEY"):
        result["note"] = "Set the ANTHROPIC_API_KEY environment variable to have the recipe written."
        return result
    try:
        result["recipe"] = write_recipe(chosen)
    except Exception as error:  # network, key or parsing problem: keep the graph part
        result["note"] = f"The recipe writer is unavailable ({type(error).__name__})."
    return result


if IMAGE_DIR.exists():
    app.mount("/img", StaticFiles(directory=IMAGE_DIR), name="img")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
