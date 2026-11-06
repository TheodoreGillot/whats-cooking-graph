"""Analyse the centrality of ingredients.

Computes degree, strength, betweenness (unweighted and weighted), closeness,
eigenvector and PageRank centrality, their top-10 rankings, and Spearman
correlations between centrality and ingredient properties. Writes
results/top10.csv, results/spearman.csv, results/centrality.json and
figures/betweenness_vs_diversity.png.
"""
import csv
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from scipy import stats

from config import FIGURES_DIR, PROCESSED_DIR, RESULTS_DIR
from graph import ingredient_profiles, load_graph


def _top(scores, k=10):
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    graph = load_graph(PROCESSED_DIR / "ingredient_graph.pkl")
    with (PROCESSED_DIR / "recipes.json").open(encoding="utf-8") as handle:
        recipes = json.load(handle)

    profiles = ingredient_profiles(recipes, set(graph.nodes()))

    measures = {
        "degree": dict(graph.degree()),
        "strength": dict(graph.degree(weight="npmi")),
        "betweenness": nx.betweenness_centrality(graph),
        "betweenness_weighted": nx.betweenness_centrality(graph, weight="distance"),
        "closeness": nx.closeness_centrality(graph),
        "eigenvector": nx.eigenvector_centrality(graph, max_iter=10000),
        "pagerank": nx.pagerank(graph, weight="npmi"),
    }

    # Top-10 table for the five headline measures.
    headline = ["degree", "betweenness", "closeness", "eigenvector", "pagerank"]
    with (RESULTS_DIR / "top10.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank"] + headline)
        for rank in range(10):
            row = [rank + 1]
            for name in headline:
                row.append(_top(measures[name])[rank][0])
            writer.writerow(row)

    # Spearman correlations.
    nodes = sorted(graph.nodes())
    # Betweenness is 0 for isolated ingredients (no shortest path goes through
    # them) and their diversity is noise, so this correlation is computed on the
    # non-isolated ingredients (equivalently, the largest component).
    active = [n for n in nodes if graph.degree(n) > 0]
    rho_betw_div, p_betw_div = stats.spearmanr(
        [measures["betweenness"][n] for n in active],
        [profiles[n]["diversity"] for n in active],
    )
    rho_deg_freq, p_deg_freq = stats.spearmanr(
        [measures["degree"][n] for n in nodes],
        [profiles[n]["recipes"] for n in nodes],
    )
    rho_betw_w, p_betw_w = stats.spearmanr(
        [measures["betweenness"][n] for n in nodes],
        [measures["betweenness_weighted"][n] for n in nodes],
    )

    correlations = {
        "betweenness_vs_diversity": {"rho": round(rho_betw_div, 4), "p": float(p_betw_div)},
        "degree_vs_frequency": {"rho": round(rho_deg_freq, 4), "p": float(p_deg_freq)},
        "betweenness_weighted_vs_unweighted": {"rho": round(rho_betw_w, 4), "p": float(p_betw_w)},
    }
    with (RESULTS_DIR / "spearman.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["correlation", "rho", "p_value"])
        for name, values in correlations.items():
            writer.writerow([name, values["rho"], values["p"]])

    # How many headline measures put each ingredient in the top 10.
    headline_sets = {name: {v for v, _ in _top(measures[name])} for name in headline}
    consensus = {}
    for node in nodes:
        consensus[node] = sum(1 for s in headline_sets.values() if node in s)
    consensus_top = sorted(consensus.items(), key=lambda kv: kv[1], reverse=True)[:10]

    results = {
        "top10": {name: [{"ingredient": v, "value": round(s, 6)} for v, s in _top(measures[name])]
                  for name in measures},
        "consensus_top10": [{"ingredient": v, "count": c} for v, c in consensus_top],
        "correlations": correlations,
    }
    with (RESULTS_DIR / "centrality.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)

    _plot_betweenness_diversity(nodes, measures["betweenness"], profiles)

    print("top-1 by measure:")
    for name in headline:
        v, s = _top(measures[name], 1)[0]
        print(f"  {name:>10}: {v} ({s:.4f})")
    print("consensus (top-10 in most headline measures):")
    for v, c in consensus_top[:5]:
        print(f"  {v}: {c}/5")
    for name, values in correlations.items():
        print(f"  rho({name}) = {values['rho']}")
    print("wrote results/top10.csv, spearman.csv, centrality.json, figures/betweenness_vs_diversity.png")


def _plot_betweenness_diversity(nodes, betweenness, profiles):
    xs = [betweenness[n] for n in nodes]
    ys = [profiles[n]["diversity"] for n in nodes]

    plt.figure(figsize=(7, 4.5))
    plt.scatter(xs, ys, s=12, color="#2f5bd3", alpha=0.5)

    for v, _ in _top(betweenness, 8):
        plt.annotate(v, (betweenness[v], profiles[v]["diversity"]), fontsize=7,
                     xytext=(4, 4), textcoords="offset points")

    plt.xlabel("betweenness centrality")
    plt.ylabel("cuisine diversity")
    plt.title("Bridges are cross-cuisine ingredients")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "betweenness_vs_diversity.png", dpi=150)
    plt.close()


if __name__ == "__main__":
    main()
