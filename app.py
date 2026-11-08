"""Demo: what can I cook with what I have?   Run with:  streamlit run app.py"""
import sys
from pathlib import Path

sys.path.append("src")

import networkx as nx
import numpy as np
import streamlit as st
from pyvis.network import Network

from recommend import load_catalogue, build_matrix, query_vector, score_ppr, recommend

GRAPH_FILE = Path("results/foodcom_ingredient_graph.graphml")
PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
           "#f032e6", "#9a6324", "#469990", "#808000", "#000075", "#a9a9a9"]
STAPLES = ["salt", "pepper", "black pepper", "water", "oil", "olive oil", "vegetable oil",
           "butter", "sugar"]

st.set_page_config(page_title="Fridge to plate", page_icon="🍳", layout="wide")


# ---------- 1. Data: loaded once, then cached ----------
@st.cache_resource
def load():
    df = load_catalogue(min_reviews=5)
    B, vocab, index = build_matrix(df)
    G = nx.read_graphml(GRAPH_FILE) if GRAPH_FILE.exists() else None
    return df, B, vocab, index, G


# ---------- 2. Helpers ----------
def family_of(ings, G):
    """Most common ingredient community in a recipe = its 'cuisine family'."""
    labels = [G.nodes[i]["community"] for i in ings if i in G and G.nodes[i]["community"] >= 0]
    return max(set(labels), key=labels.count) if labels else -1


def neighbourhood_html(G, names, n_neigh=6):
    nodes = {n for n in names if n in G}
    for n in list(nodes):
        best = sorted(G[n].items(), key=lambda kv: -kv[1]["npmi"])[:n_neigh]
        nodes.update(m for m, _ in best)
    sub = G.subgraph(nodes)
    net = Network(height="560px", width="100%", cdn_resources="in_line")
    for n in sub.nodes:
        c = int(sub.nodes[n]["community"])
        net.add_node(n, label=n, size=28 if n in names else 12,
                     color=PALETTE[c % len(PALETTE)] if c >= 0 else "#cccccc",
                     title=f"community {c} - in {sub.nodes[n]['recipes']} recipes")
    for u, v, d in sub.edges(data=True):
        net.add_edge(u, v, value=float(d["npmi"]), title=f"NPMI {d['npmi']:.2f}")
    return net.generate_html()


# ---------- 3. Page: inputs ----------
df, B, vocab, index, G = load()

st.title("🍳 Fridge to plate")
st.caption(f"{len(df):,} Food.com recipes · {len(vocab):,} ingredients · "
           "personalised PageRank on the recipe–ingredient graph")
st.caption("PageRank puts the right recipe first most often when you list what you want to "
           "cook; TF-IDF copes better when you list everything in your fridge.")

with st.sidebar:
    method = st.radio("Method", ["ppr", "tfidf", "overlap"],
                      format_func={"ppr": "Personalised PageRank",
                                   "tfidf": "TF-IDF (baseline)",
                                   "overlap": "Ingredients in common (baseline)"}.get)
    k = st.slider("Number of recipes", 3, 20, 6)
    restart = st.select_slider("Restart probability (PageRank)",
                               [0.1, 0.3, 0.5, 0.7, 0.9, 0.99], value=0.99)
    use_staples = st.checkbox("I always have salt, pepper, oil, butter, sugar", True)
    diverse = st.checkbox("Different meals (one per cuisine family)", True, disabled=G is None)

names = st.multiselect("What do you have?", vocab, placeholder="Type an ingredient…")
staples = [s for s in STAPLES if s in index] if use_staples else []

if not names:
    st.info("Pick a few ingredients to get started.")
    st.stop()

# ---------- 4. Page: three tabs ----------
tab_cook, tab_buy, tab_map = st.tabs(["Cook now", "What to buy", "Ingredient map"])

with tab_cook:
    pool = recommend(df, B, index, names, method, k=200 if diverse else k,
                     restart=restart, staples=staples)
    if diverse and G is not None:
        pool["family"] = pool["ingredients"].apply(lambda l: family_of(l, G))
        pool = pool.drop_duplicates("family")
    for _, r in pool.head(k).iterrows():
        share = len(r["matched"]) / len(r["ingredients"])
        rating = f"{r['mean_rating']:.1f}★ ({r['n_reviews']})" if r["n_reviews"] else "no rating"
        minutes = f"{r['minutes']:.0f} min" if r["minutes"] == r["minutes"] else "? min"
        with st.expander(f"**{r['name']}** — you have {share:.0%} · {minutes} · {rating}"):
            st.write("✅ " + ", ".join(r["matched"]))
            st.write("🛒 " + (", ".join(r["missing"]) or "nothing!"))
            for i, step in enumerate(r["steps"], 1):
                st.write(f"{i}. {step}")

with tab_buy:
    _, x = score_ppr(B, query_vector(names, index, B.shape[1]), restart)
    x[[index[n] for n in names + staples if n in index]] = -np.inf
    st.write("Ingredients the random walk reaches most often from your basket:")
    st.write(", ".join(vocab[j] for j in np.argsort(-x)[:10]))

with tab_map:
    if G is None:
        st.warning(f"{GRAPH_FILE} not found: run the last cell of notebook 04 first.")
    else:
        st.iframe(neighbourhood_html(G, names), height=580)