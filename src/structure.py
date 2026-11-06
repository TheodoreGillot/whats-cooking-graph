"""Analyse the structure of the ingredient graph.

Computes size, density, degree statistics, connectivity (components) and
distances on the largest connected component, then writes
results/structure.json and figures/degree_distribution.png.
"""
import json

import matplotlib

matplotlib.use("Agg")  # headless backend: no display needed
import matplotlib.pyplot as plt
import networkx as nx

from config import FIGURES_DIR, PROCESSED_DIR, RESULTS_DIR
from graph import load_graph


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    graph = load_graph(PROCESSED_DIR / "ingredient_graph.pkl")

    n = graph.number_of_nodes()
    m = graph.number_of_edges()

    degrees = [d for _, d in graph.degree()]
    max_node, max_deg = max(graph.degree(), key=lambda kv: kv[1])
    top10 = sorted(graph.degree(), key=lambda kv: kv[1], reverse=True)[:10]

    components = list(nx.connected_components(graph))
    largest = max(components, key=len)
    isolated = [v for v in graph if graph.degree(v) == 0]

    # Distances are only finite inside a connected component, so we compute them
    # on the largest connected component (the convention stated in the report).
    lcc = graph.subgraph(largest).copy()
    diameter = nx.diameter(lcc)
    radius = nx.radius(lcc)
    avg_path = nx.average_shortest_path_length(lcc)
    centre = nx.center(lcc)

    # Clustering on the largest connected component: isolated nodes have no
    # well-defined clustering coefficient, so we follow the same convention as
    # for the distances above.
    clustering = nx.average_clustering(lcc)

    results = {
        "nodes": n,
        "edges": m,
        "density": round(nx.density(graph), 6),
        "degree": {
            "min": min(degrees),
            "mean": round(sum(degrees) / n, 4),
            "max": max_deg,
            "max_ingredient": max_node,
            "top10": [{"ingredient": v, "degree": d} for v, d in top10],
        },
        "components": {
            "count": len(components),
            "largest_size": len(largest),
            "isolated": len(isolated),
        },
        "distances": {
            "diameter": diameter,
            "radius": radius,
            "average_shortest_path": round(avg_path, 4),
            "centre": sorted(centre),
        },
        "clustering": round(clustering, 4),
    }

    with (RESULTS_DIR / "structure.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)

    _plot_degree_distribution(degrees)

    print(f"nodes {n}  edges {m}  density {results['density']}")
    print(f"degree: min {min(degrees)}  mean {results['degree']['mean']}  max {max_deg} ({max_node})")
    print(f"components {len(components)}  largest {len(largest)}  isolated {len(isolated)}")
    print(
        f"LCC: diameter {diameter}  radius {radius}  avg path "
        f"{results['distances']['average_shortest_path']}  {len(centre)} centres"
    )
    print(f"clustering {results['clustering']}")
    print("wrote results/structure.json, figures/degree_distribution.png")


def _plot_degree_distribution(degrees):
    plt.figure(figsize=(7, 4.5))
    plt.hist(degrees, bins=50, color="#2f5bd3", alpha=0.85)
    plt.yscale("log")
    plt.xlabel("degree")
    plt.ylabel("number of ingredients")
    plt.title("Degree distribution of the ingredient graph")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "degree_distribution.png", dpi=150)
    plt.close()


if __name__ == "__main__":
    main()
