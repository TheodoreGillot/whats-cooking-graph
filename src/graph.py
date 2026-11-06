"""Graph model: from recipes to the ingredient co-occurrence graph.

Two stages:
  1. a bipartite graph recipes <-> ingredients (the raw model);
  2. an undirected weighted projection on ingredients, where an edge means two
     ingredients are cooked together more often than chance (NPMI filter).
"""
import itertools
import math
from collections import Counter

import networkx as nx


def normalize(name: str) -> str:
    """Lowercase, drop ®/™ and collapse whitespace. Synonyms are deliberately
    not merged (e.g. "garlic" vs "garlic cloves"); this is a known limitation."""
    return " ".join(name.lower().replace("®", "").replace("™", "").split())


def clean_recipes(raw_recipes):
    """Return recipes with normalised, de-duplicated, sorted ingredient lists."""
    cleaned = []
    for recipe in raw_recipes:
        cleaned.append({
            "id": recipe["id"],
            "cuisine": recipe["cuisine"],
            "ingredients": sorted({normalize(i) for i in recipe["ingredients"]}),
        })
    return cleaned


def build_bipartite(recipes):
    """Stage 1: bipartite graph, recipes on one side, ingredients on the other."""
    graph = nx.Graph()
    for recipe in recipes:
        recipe_node = f"recipe_{recipe['id']}"
        graph.add_node(recipe_node, kind="recipe", cuisine=recipe["cuisine"])
        for ingredient in recipe["ingredients"]:
            graph.add_node(ingredient, kind="ingredient")
            graph.add_edge(recipe_node, ingredient)
    return graph


def build_ingredient_graph(recipes, min_recipes, min_cooc, min_npmi):
    """Stage 2: weighted projection on ingredients, filtered by NPMI.

    Nodes are ingredients seen in at least `min_recipes` recipes. An edge links
    two ingredients that co-occur in at least `min_cooc` recipes and whose
    normalised PMI exceeds `min_npmi`. Edge attributes: `count` (number of
    shared recipes), `npmi`, and `distance = 1 - npmi`.
    """
    total = len(recipes)
    frequency = Counter(i for r in recipes for i in r["ingredients"])
    kept = {i for i, count in frequency.items() if count >= min_recipes}

    cooc = Counter()
    for recipe in recipes:
        present = [i for i in recipe["ingredients"] if i in kept]
        cooc.update(itertools.combinations(present, 2))

    graph = nx.Graph()
    graph.add_nodes_from(sorted(kept))
    nx.set_node_attributes(graph, {i: frequency[i] for i in kept}, "recipes")

    for (a, b), shared in cooc.items():
        if shared < min_cooc:
            continue
        p_ab = shared / total
        p_a = frequency[a] / total
        p_b = frequency[b] / total
        pmi = math.log(p_ab / (p_a * p_b))
        npmi = pmi / -math.log(p_ab)
        if npmi > min_npmi:
            graph.add_edge(a, b, count=shared, npmi=round(npmi, 6),
                           distance=round(1 - npmi, 6))

    return graph
