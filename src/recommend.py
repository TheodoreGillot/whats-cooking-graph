"""Recipe recommendation on the recipe-ingredient bipartite graph.

B is the recipe x ingredient incidence matrix (1 if the recipe uses the ingredient):
it is the adjacency of the bipartite graph, stored as a sparse matrix so that a
random walk on 50k recipes takes milliseconds.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from config import PROCESSED_DIR


def load_catalogue(min_reviews=5):
    df = pd.read_pickle(Path(PROCESSED_DIR) / "foodcom_recipes.pkl")
    df = df[df["n_reviews"] >= min_reviews]
    return df.reset_index(drop=True)


def build_matrix(df):
    vocab = sorted({i for ings in df["ingredients"] for i in ings})
    index = {name: j for j, name in enumerate(vocab)}
    rows, cols = [], []
    for r, ings in enumerate(df["ingredients"]):
        for name in ings:
            rows.append(r)
            cols.append(index[name])
    B = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(df), len(vocab)))
    return B, vocab, index


def query_vector(names, index, n_ingredients):
    q = np.zeros(n_ingredients)
    for name in names:
        if name in index:
            q[index[name]] = 1
    return q


def score_overlap(B, q):
    """Baseline 1: number of the user's ingredients used by each recipe."""
    return B @ q

def score_ppr(B, q, restart=0.3, tol=1e-9, max_iter=200):
    """Personalised PageRank on the bipartite graph, restarting on the user's ingredients.

    Returns (recipe scores, ingredient scores). Same result as nx.pagerank with
    alpha = 1 - restart and personalization on the query ingredients.
    """
    if q.sum() == 0:
        raise ValueError("none of the ingredients is in the catalogue")
    deg_r = np.asarray(B.sum(axis=1)).ravel()
    deg_i = np.asarray(B.sum(axis=0)).ravel()
    e = q / q.sum()
    x = e.copy()                 # mass on ingredient nodes
    y = np.zeros(B.shape[0])     # mass on recipe nodes
    for _ in range(max_iter):
        y_new = (1 - restart) * (B @ (x / deg_i))
        x_new = restart * e + (1 - restart) * (B.T @ (y / deg_r))
        delta = np.abs(x_new - x).sum() + np.abs(y_new - y).sum()
        x, y = x_new, y_new
        if delta < tol:
            break
    return y, x

def score_tfidf(B, q):
    """Baseline 2: cosine similarity with rare ingredients weighted more (idf)."""
    df_i = np.asarray(B.sum(axis=0)).ravel()
    idf2 = np.log(B.shape[0] / df_i) ** 2
    recipe_norm = np.sqrt(B @ idf2)
    return (B @ (q * idf2)) / (recipe_norm + 1e-12)


def expected_rank(scores, target):
    """Rank of the target recipe; ties are counted as the average position."""
    s = scores[target]
    return 1 + (scores > s).sum() + ((scores == s).sum() - 1) / 2


def recommend(df, B, index, names, method="ppr", k=10, restart=0.3, staples=()):
    q = query_vector(names, index, B.shape[1])
    if method == "ppr":
        scores = score_ppr(B, q, restart)[0]
    elif method == "tfidf":
        scores = score_tfidf(B, q)
    else:
        scores = score_overlap(B, q)
    top = np.argsort(-scores)[:k]
    out = df.iloc[top][["id", "name", "minutes", "mean_rating", "n_reviews",
                        "ingredients", "steps"]].copy()
    have = set(names) | set(staples)
    out["matched"] = out["ingredients"].apply(lambda l: [i for i in l if i in have])
    out["missing"] = out["ingredients"].apply(lambda l: [i for i in l if i not in have])
    out["score"] = scores[top]
    return out


if __name__ == "__main__":
    import networkx as nx

    df = load_catalogue()
    B, vocab, index = build_matrix(df)
    print(f"{B.shape[0]:,} recipes x {B.shape[1]:,} ingredients, {B.nnz:,} edges")

    # Check: same scores as networkx PageRank on the first 2,000 recipes
    small = df.head(2000)
    Bs, vocab_s, index_s = build_matrix(small)
    G = nx.Graph()
    for r, ings in enumerate(small["ingredients"]):
        G.add_edges_from((f"r{r}", f"i:{i}") for i in ings)
    seeds = list(small["ingredients"].iloc[0])[:3]
    pr = nx.pagerank(G, alpha=0.7, personalization={f"i:{s}": 1 for s in seeds}, tol=1e-12)
    y, x = score_ppr(Bs, query_vector(seeds, index_s, len(vocab_s)), restart=0.3, tol=1e-12)
    diff = max(abs(y[r] - pr[f"r{r}"]) for r in range(len(small)))
    print("max difference with nx.pagerank:", diff)

    # Compare the two methods on one basket
    q = query_vector(["rice", "ginger", "soy sauce"], index, B.shape[1])
    for name, scores in [("overlap", score_overlap(B, q)), ("tf-idf", score_tfidf(B, q)),
                         ("ppr", score_ppr(B, q)[0])]:
        top = np.argsort(-scores)[:5]
        print(f"\n{name}: recipes tied with the best score:", (scores == scores[top[0]]).sum())
        print(df.iloc[top][["name", "n_reviews"]].assign(score=scores[top]))

    print()
    print(recommend(df, B, index, ["rice", "ginger", "soy sauce"], k=5)[["name", "matched", "missing"]])