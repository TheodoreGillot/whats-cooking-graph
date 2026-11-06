"""Sensitivity of the results to the graph-model thresholds.

Rebuilds the ingredient graph for 27 combinations of (min_recipes, min_cooc,
min_npmi) and reports, for each, the graph size, the largest-component share and
the Louvain communities/modularity. Writes results/sensitivity.csv.
"""
import csv
import itertools
import json

import networkx as nx

from config import PROCESSED_DIR, RESULTS_DIR, SEED
from graph import build_ingredient_graph, clean_recipes


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with (PROCESSED_DIR / "recipes.json").open(encoding="utf-8") as handle:
        recipes = json.load(handle)
    cleaned = clean_recipes(recipes)

    min_recipes_values = [10, 20, 30]
    min_cooc_values = [5, 10, 15]
    min_npmi_values = [0.05, 0.10, 0.15]

    rows = []
    for min_recipes, min_cooc, min_npmi in itertools.product(
        min_recipes_values, min_cooc_values, min_npmi_values
    ):
        graph = build_ingredient_graph(cleaned, min_recipes, min_cooc, min_npmi)
        components = list(nx.connected_components(graph))
        largest = max(components, key=len)
        lcc = graph.subgraph(largest).copy()
        isolated = sum(1 for v in graph if graph.degree(v) == 0)

        partition = list(nx.community.louvain_communities(
            lcc, weight="npmi", resolution=1.0, seed=SEED
        ))
        modularity = nx.community.modularity(lcc, partition, weight="npmi")

        rows.append({
            "min_recipes": min_recipes,
            "min_cooc": min_cooc,
            "min_npmi": min_npmi,
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "lcc_size": len(largest),
            "lcc_share": round(len(largest) / graph.number_of_nodes(), 4),
            "isolated": isolated,
            "communities": len(partition),
            "modularity": round(modularity, 4),
        })

    with (RESULTS_DIR / "sensitivity.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    community_range = (min(r["communities"] for r in rows), max(r["communities"] for r in rows))
    modularity_range = (min(r["modularity"] for r in rows), max(r["modularity"] for r in rows))
    share_range = (min(r["lcc_share"] for r in rows), max(r["lcc_share"] for r in rows))
    print(f"27 settings: communities {community_range[0]}-{community_range[1]}, "
          f"modularity {modularity_range[0]}-{modularity_range[1]}")
    print(f"LCC share: {share_range[0]}-{share_range[1]}")
    print("wrote results/sensitivity.csv")


if __name__ == "__main__":
    main()
