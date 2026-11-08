"""Detect and characterise the communities of the ingredient graph.

Runs Louvain and label propagation, compares them to a raw-count baseline,
measures the agreement with the "home cuisine" labels (NMI), and checks
robustness across random seeds and resolution values. Writes results/.
"""
import csv
import json
import random
import statistics

import networkx as nx
from sklearn.metrics import normalized_mutual_info_score

from config import (
    MIN_COOC,
    MIN_RECIPES,
    PROCESSED_DIR,
    RESULTS_DIR,
    SEED,
)
from graph import (
    build_ingredient_graph,
    clean_recipes,
    ingredient_profiles,
    load_graph,
)


def _community_labels(nodes, partition):
    """Map each node to the index of its community (for NMI)."""
    label = {}
    for index, community in enumerate(partition):
        for node in community:
            label[node] = index
    return [label[n] for n in nodes]


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    graph = load_graph(PROCESSED_DIR / "ingredient_graph.pkl")
    with (PROCESSED_DIR / "recipes.json").open(encoding="utf-8") as handle:
        recipes = json.load(handle)
    profiles = ingredient_profiles(recipes, set(graph.nodes()))

    # Largest connected component: isolated ingredients have no community
    # structure, so the community analysis focuses on the LCC.
    lcc_nodes = max(nx.connected_components(graph), key=len)
    lcc = graph.subgraph(lcc_nodes).copy()
    lcc_sorted = sorted(lcc_nodes)
    home_cuisine = [profiles[n]["home_cuisine"] for n in lcc_sorted]

    # Louvain, seeded and weighted by NPMI.
    louvain = list(nx.community.louvain_communities(
        lcc, weight="npmi", resolution=1.0, seed=SEED
    ))
    louvain_modularity = nx.community.modularity(lcc, louvain, weight="npmi")

    # Label propagation (unweighted; asynchronous variant with a fixed seed).
    lpa = list(nx.community.asyn_lpa_communities(lcc, seed=SEED))
    lpa_modularity = nx.community.modularity(lcc, lpa, weight="npmi")

    # Raw-count baseline: same graph but without the NPMI filter.
    cleaned = clean_recipes(recipes)
    raw_graph = build_ingredient_graph(cleaned, MIN_RECIPES, MIN_COOC, min_npmi=-2.0)
    raw_louvain = list(nx.community.louvain_communities(
        raw_graph, weight="count", resolution=1.0, seed=SEED
    ))
    raw_modularity = nx.community.modularity(raw_graph, raw_louvain, weight="count")

    # Agreement with home-cuisine labels.
    louvain_labels = _community_labels(lcc_sorted, louvain)
    lpa_labels = _community_labels(lcc_sorted, lpa)
    nmi_louvain = normalized_mutual_info_score(home_cuisine, louvain_labels)
    nmi_lpa = normalized_mutual_info_score(home_cuisine, lpa_labels)

    # Baseline for NMI: the same partition against shuffled home-cuisine labels.
    rng = random.Random(SEED)
    shuffled_nmi = []
    for _ in range(200):
        labels = home_cuisine[:]
        rng.shuffle(labels)
        shuffled_nmi.append(normalized_mutual_info_score(labels, louvain_labels))

    # Baseline for modularity: same degrees, random wiring (unweighted, because
    # rewiring does not keep edge weights, so the real graph is compared unweighted too).
    rewired = nx.Graph(lcc)
    nx.double_edge_swap(rewired, nswap=5 * rewired.number_of_edges(),
                        max_tries=100 * rewired.number_of_edges(), seed=SEED)
    real_unweighted = nx.community.modularity(
        lcc, nx.community.louvain_communities(lcc, seed=SEED))
    rewired_unweighted = nx.community.modularity(
        rewired, nx.community.louvain_communities(rewired, seed=SEED))
    
    # Robustness across seeds.
    seed_nmi = []
    for seed in [1, 2, 3, 4, 5]:
        partition = list(nx.community.louvain_communities(
            lcc, weight="npmi", resolution=1.0, seed=seed
        ))
        labels = _community_labels(lcc_sorted, partition)
        seed_nmi.append(normalized_mutual_info_score(louvain_labels, labels))

    # Robustness across resolutions.
    resolution_counts = {}
    for resolution in [0.5, 1.0, 1.5, 2.0]:
        partition = list(nx.community.louvain_communities(
            lcc, weight="npmi", resolution=resolution, seed=SEED
        ))
        resolution_counts[str(resolution)] = len(partition)

    results = {
        "louvain": {
            "communities": len(louvain),
            "modularity": round(louvain_modularity, 4),
            "sizes": sorted((len(c) for c in louvain), reverse=True),
        },
        "label_propagation": {
            "communities": len(lpa),
            "modularity": round(lpa_modularity, 4),
        },
        "baseline_raw_count": {
            "communities": len(raw_louvain),
            "modularity": round(raw_modularity, 4),
        },
        "nmi_with_home_cuisine": {
            "louvain": round(nmi_louvain, 4),
            "label_propagation": round(nmi_lpa, 4),
        },

                "nmi_shuffled_baseline": {
            "mean": round(statistics.mean(shuffled_nmi), 4),
            "max": round(max(shuffled_nmi), 4),
        },

        "modularity_vs_rewired_unweighted": {
            "real": round(real_unweighted, 4),
            "rewired": round(rewired_unweighted, 4),
        },

        "robustness_seeds": {
            "nmi": [round(v, 4) for v in seed_nmi],
            "min": round(min(seed_nmi), 4),
            "max": round(max(seed_nmi), 4),
        },
        "robustness_resolutions": resolution_counts,
    }

    with (RESULTS_DIR / "communities.json").open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)

    _write_community_profiles(lcc, louvain, profiles)

    print(f"louvain: {len(louvain)} communities, modularity {results['louvain']['modularity']}")
    print(f"label propagation: {len(lpa)} communities, modularity {results['label_propagation']['modularity']}")
    print(f"raw-count baseline: {len(raw_louvain)} communities, modularity {results['baseline_raw_count']['modularity']}")
    print(f"NMI with home cuisine: louvain {nmi_louvain:.4f}, lpa {nmi_lpa:.4f}")
    print(f"NMI with shuffled labels: mean {statistics.mean(shuffled_nmi):.4f}, max {max(shuffled_nmi):.4f}")
    print(f"unweighted modularity: real {real_unweighted:.4f} vs degree-preserving rewired {rewired_unweighted:.4f}")
    print(f"seed NMI range: {min(seed_nmi):.3f}-{max(seed_nmi):.3f}")
    print(f"resolutions: {resolution_counts}")
    print("wrote results/communities.json, results/community_profiles.csv")


def _write_community_profiles(graph, partition, profiles):
    """Per community: size, dominant home cuisines and top ingredients by degree."""
    with (RESULTS_DIR / "community_profiles.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["community", "size", "dominant_cuisines", "top_ingredients"])

        for index, community in enumerate(partition):
            subgraph = graph.subgraph(community)
            degrees = sorted(subgraph.degree(), key=lambda kv: kv[1], reverse=True)
            top_ingredients = " | ".join(v for v, _ in degrees[:5])

            cuisine_counts = {}
            for node in community:
                cuisine_counts[profiles[node]["home_cuisine"]] = (
                    cuisine_counts.get(profiles[node]["home_cuisine"], 0) + 1
                )
            dominant = " | ".join(
                c for c, _ in sorted(cuisine_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
            )

            writer.writerow([index, len(community), dominant, top_ingredients])


if __name__ == "__main__":
    main()
