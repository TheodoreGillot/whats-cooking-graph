"""Build the processed data: cleaned recipes plus the ingredient graph.

Reads train.json from data/raw/, normalises ingredient names, builds the
bipartite and projected graphs, and writes everything under data/processed/.
"""
import json

import networkx as nx

from config import (
    MIN_COOC,
    MIN_NPMI,
    MIN_RECIPES,
    PROCESSED_DIR,
    RAW_DIR,
    TRAIN_FILENAME,
)
from graph import build_bipartite, build_ingredient_graph, clean_recipes


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / TRAIN_FILENAME
    if not raw_path.exists():
        raise SystemExit(f"{raw_path} missing: run `python src/fetch_data.py` first.")

    with raw_path.open(encoding="utf-8") as handle:
        raw_recipes = json.load(handle)

    recipes = clean_recipes(raw_recipes)
    bipartite = build_bipartite(recipes)
    ingredient_graph = build_ingredient_graph(
        recipes, MIN_RECIPES, MIN_COOC, MIN_NPMI
    )

    with (PROCESSED_DIR / "recipes.json").open("w", encoding="utf-8") as handle:
        json.dump(recipes, handle, ensure_ascii=False)
    nx.write_graphml(bipartite, PROCESSED_DIR / "bipartite.graphml")
    nx.write_graphml(ingredient_graph, PROCESSED_DIR / "ingredient_graph.graphml")

    isolated = sum(1 for v in ingredient_graph if ingredient_graph.degree(v) == 0)
    print(f"bipartite: {bipartite.number_of_nodes():,} nodes, {bipartite.number_of_edges():,} edges")
    print(
        f"ingredient graph: {ingredient_graph.number_of_nodes():,} nodes, "
        f"{ingredient_graph.number_of_edges():,} edges ({isolated} isolated)"
    )
    print("wrote data/processed/: recipes.json, bipartite.graphml, ingredient_graph.graphml")


if __name__ == "__main__":
    main()
