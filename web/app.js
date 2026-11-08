(() => {
  "use strict";

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const STORE = "fridge-to-plate";

  const state = {
    basket: [], method: "ppr", staples: true, diverse: false, tab: "cook",
    mapMode: "around", seed: 0, dish: "", recipe: null, meta: null, famById: {}, ingByName: {},
    cy: null, fullMap: null, focusFamily: null, ticket: 0,
  };

  const METHOD_TEXT = {
    ppr: "a random walk on the recipe–ingredient graph that starts from your fridge (personalised PageRank)",
    tfidf: "TF-IDF similarity, where rare ingredients count more",
    overlap: "how many of your ingredients each recipe uses",
  };

  // ---------- helpers ----------
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const fam = (id) => state.famById[id] || state.famById[-1];

  function tint(hex, amount = 0.78) {
    const n = parseInt(hex.slice(1), 16);
    const mix = (c) => Math.round(c + (255 - c) * amount);
    return `rgb(${mix(n >> 16)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
  }

  function photo(ing, cls = "", title = false) {
    const t = title ? ` title="${esc(ing.name)}" role="img" aria-label="${esc(ing.name)}"` : ' aria-hidden="true"';
    if (ing.img) return `<span class="photo ${cls}"${t}><img src="${esc(ing.img)}" alt="" loading="lazy"></span>`;
    const f = fam(ing.family);
    return `<span class="photo initial ${cls}" style="--tint:${tint(f.color)}"${t}>${esc(ing.name[0].toUpperCase())}</span>`;
  }

  async function api(path, body) {
    const options = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    const res = await fetch(path, options);
    if (!res.ok) {
      let message = `The server answered ${res.status}.`;
      try { message = (await res.json()).detail || message; } catch (e) { /* keep default */ }
      throw new Error(message);
    }
    return res.json();
  }

  function save() {
    try { localStorage.setItem(STORE, JSON.stringify({ basket: state.basket, method: state.method, staples: state.staples, dish: state.dish, recipe: state.recipe, tab: state.tab })); } catch (e) { /* storage unavailable */ }
  }

  function restore() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE) || "null");
      if (!saved) return;
      state.basket = (saved.basket || []).filter((n) => state.ingByName[n]);
      if (typeof saved.dish === "string") state.dish = saved.dish;
      if (Number.isInteger(saved.recipe)) state.recipe = saved.recipe;
      if (["cook", "plan", "shop", "map", "chef"].includes(saved.tab)) state.tab = saved.tab;
      if (METHOD_TEXT[saved.method]) state.method = saved.method;
      if (typeof saved.staples === "boolean") state.staples = saved.staples;
    } catch (e) { /* ignore */ }
  }

  const icons = {
    clock: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    plate: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/></svg>',
    book: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/></svg>',
    home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11l8-7 8 7v9H4z"/></svg>',
    bag: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h14l-1 12H6zM9 8V6a3 3 0 0 1 6 0v2"/></svg>',
    star: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg>',
  };

  // ---------- fridge ----------
  function addIngredient(name) {
    if (!state.ingByName[name] || state.basket.includes(name)) return;
    state.basket.push(name);
    state.seed = 0;
    changed();
  }

  function removeIngredient(name) {
    state.basket = state.basket.filter((n) => n !== name);
    state.seed = 0;
    changed();
  }

  function changed() {
    save();
    renderBasket();
    renderPlates();
    showView();
    refresh();
  }

  function renderBasket() {
    const list = $("#basket");
    list.innerHTML = state.basket.map((n) => {
      const ing = state.ingByName[n];
      return `<li>${photo(ing)}<span class="name">${esc(n)}</span>
        <button type="button" data-remove="${esc(n)}" aria-label="Remove ${esc(n)}">×</button></li>`;
    }).join("");
    $("#basket-empty").hidden = state.basket.length > 0;
    $("#clear").hidden = state.basket.length < 2;
  }

  function setupSearch() {
    const input = $("#add");
    const box = $("#suggest");
    let options = [];
    let active = -1;

    function close() { box.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; }

    function render() {
      const q = input.value.trim().toLowerCase();
      if (!q) { close(); return; }
      const exact = [], starts = [], contains = [];
      for (const ing of state.meta.ingredients) {
        if (state.basket.includes(ing.name)) continue;
        if (ing.name === q) exact.push(ing);
        else if (ing.name.startsWith(q)) starts.push(ing);
        else if (ing.name.includes(q)) contains.push(ing);
      }
      options = exact.concat(starts, contains).slice(0, 8);
      if (!options.length) {
        box.innerHTML = `<li aria-disabled="true">No ingredient called “${esc(q)}”.</li>`;
      } else {
        box.innerHTML = options.map((ing, i) => `<li role="option" data-i="${i}" aria-selected="${i === active}">
          ${photo(ing)}<span>${esc(ing.name)}</span><small>${fmt(ing.recipes)} recipes</small></li>`).join("");
      }
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    function choose(i) {
      if (!options[i]) return;
      addIngredient(options[i].name);
      input.value = "";
      close();
      input.focus();
    }

    input.addEventListener("input", () => { active = -1; render(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { active = Math.min(active + 1, options.length - 1); render(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); render(); e.preventDefault(); }
      else if (e.key === "Enter") { choose(active >= 0 ? active : 0); e.preventDefault(); }
      else if (e.key === "Escape") { close(); }
    });
    box.addEventListener("mousedown", (e) => {
      const li = e.target.closest("li[data-i]");
      if (li) { e.preventDefault(); choose(Number(li.dataset.i)); }
    });
    input.addEventListener("blur", () => setTimeout(close, 120));
  }

  // ---------- welcome plates ----------
  function renderPlates() {
    const skip = new Set(state.meta.staples.concat(["salt and pepper", "water", "salt"]));
    const pool = state.meta.ingredients.filter((i) => !skip.has(i.name));
    const withPhoto = pool.filter((i) => i.img);
    const picks = (withPhoto.length >= 18 ? withPhoto : pool).slice(0, 18);
    $("#plates").innerHTML = picks.map((ing) => `<li><button type="button" data-add="${esc(ing.name)}" aria-pressed="${state.basket.includes(ing.name)}">
      ${photo(ing)}<span class="label">${esc(ing.name)}</span><small>in ${fmt(ing.recipes)} recipes</small></button></li>`).join("");
  }

  // ---------- views ----------
  function showView() {
    const empty = state.basket.length === 0;
    const visible = empty && !["map", "plan"].includes(state.tab) ? "welcome" : state.tab;
    for (const id of ["welcome", "cook", "plan", "shop", "map", "chef"]) $("#" + id).hidden = id !== visible;
    $$(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === state.tab)));
    $$(".method button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.method === state.method)));
    $("#staples").checked = state.staples;
    $("#diverse").checked = state.diverse;
  }

  let refreshTimer = null;
  function refresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      const ticket = ++state.ticket;
      const loaders = { cook: loadCook, plan: loadPlan, shop: loadShop, map: loadMap, chef: loadChef };
      if (state.basket.length || ["map", "plan"].includes(state.tab)) loaders[state.tab](ticket).catch((err) => showError(err));
    }, 120);
  }

  function showError(err) {
    const target = { cook: "#dishes", plan: "#plan-body", shop: "#shop-list", map: "#map-lead", chef: "#chef-body" }[state.tab];
    $(target).innerHTML = `<p class="error">${esc(err.message)} Check that the server is running, then reload the page.</p>`;
  }

  const query = (extra = {}) => Object.assign({
    basket: state.basket, method: state.method, staples: state.staples, diverse: state.diverse, k: 10,
  }, extra);

  // ---------- cook ----------
  async function loadCook(ticket) {
    $("#dishes").innerHTML = '<p class="loading">Finding dishes…</p>';
    const data = await api("/api/recommend", query());
    if (ticket !== state.ticket) return;
    $("#cook-title").textContent = state.diverse ? "One dish from each cuisine family" : "Dishes you can make";
    $("#cook-lead").textContent = `Ranked by ${METHOD_TEXT[state.method]}. Open a dish for its ingredients and method.`;
    if (!data.recipes.length) {
      $("#dishes").innerHTML = '<p class="loading">No recipe uses these ingredients. Try removing one.</p>';
      return;
    }
    $("#dishes").innerHTML = data.recipes.map((r, i) => dishHtml(r, i, "cook")).join("");
  }

  function dishHtml(r, i, prefix) {
    const f = fam(r.family);
    const total = r.have.length + r.missing.length;
    const shown = 16;
    const strip = r.have.slice(0, shown).map((x) => photo(x, "", true)).join("")
      + (r.missing.length ? '<span class="gap"></span>' : "")
      + r.missing.slice(0, Math.max(0, shown - r.have.length)).map((x) => photo(x, "missing", true)).join("");
    const minutes = r.minutes ? `<span>${icons.clock}${r.minutes} min</span>` : "";
    const rating = r.rating ? `<span>${icons.star}${r.rating} <small>(${fmt(r.reviews)} reviews)</small></span>` : "";
    const ingredients = r.have.map((x) => `<li>${photo(x)}<span>${esc(x.name)}</span></li>`).join("")
      + r.missing.map((x) => `<li>${photo(x, "missing")}<span>${esc(x.name)}</span><span class="buy">to buy</span></li>`).join("");
    return `<article class="dish">
      <button type="button" class="dish-head" aria-expanded="false" aria-controls="${prefix}-${i}">
        <div><h3>${esc(r.name)}</h3><span class="fam"><span class="dot" style="--c:${f.color}"></span>${esc(f.name)}</span></div>
        <div class="dish-meta">${minutes}${rating}</div>
        <div class="strip">${strip}</div>
        <div class="have"><span class="meter"><i style="width:${Math.round(100 * r.have.length / total)}%"></i></span>
          You have ${r.have.length} of its ${total} ingredients</div>
      </button>
      <div class="dish-body" id="${prefix}-${i}" hidden>
        <div><h4>Ingredients</h4><ul class="ing-list">${ingredients}</ul></div>
        <div><h4>Method</h4><ol class="steps">${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div>
      </div>
    </article>`;
  }

  // ---------- plan ----------
  const EXAMPLES = ["lasagna", "pad thai", "risotto", "banana bread", "beef stew", "guacamole", "carbonara"];
  const STATUS = {
    fridge: () => `<span class="status st-fridge">${icons.check}In your fridge</span>`,
    kitchen: () => `<span class="status st-kitchen">${icons.home}Kitchen basic</span>`,
    buy: () => `<span class="status st-buy">${icons.bag}To buy</span>`,
  };

  function setupDishSearch() {
    const input = $("#dish");
    const box = $("#dish-suggest");
    let options = [];
    let active = -1;
    let timer = null;
    let seq = 0;

    function close() { box.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; }

    function option(o, i) {
      const selected = `aria-selected="${i === active}"`;
      if (o.kind === "dish") {
        return `<li role="option" data-i="${i}" ${selected}><span class="kind">${icons.plate}</span>
          <span>${esc(o.name)}</span><small>${fmt(o.n)} recipes</small></li>`;
      }
      const rating = o.rating ? `${o.rating} ★, ` : "";
      return `<li role="option" data-i="${i}" ${selected}><span class="kind k-recipe">${icons.book}</span>
        <span>${esc(o.name)}</span><small>${rating}${fmt(o.reviews)} reviews</small></li>`;
    }

    function render() {
      const q = input.value.trim();
      if (!options.length) {
        box.innerHTML = `<li aria-disabled="true">No dish or recipe in the catalogue starts with “${esc(q)}”.</li>`;
      } else {
        const dishes = options.filter((o) => o.kind === "dish");
        const recipes = options.filter((o) => o.kind === "recipe");
        let i = 0;
        box.innerHTML = (dishes.length ? '<li class="group-label" role="presentation">Dishes</li>' + dishes.map((o) => option(o, i++)).join("") : "")
          + (recipes.length ? '<li class="group-label" role="presentation">Recipes</li>' + recipes.map((o) => option(o, i++)).join("") : "");
      }
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    async function lookUp() {
      const q = input.value.trim();
      if (q.length < 2) { options = []; close(); return; }
      const mine = ++seq;
      const data = await api(`/api/dishes?q=${encodeURIComponent(q)}`);
      if (mine !== seq) return;
      options = data.dishes.map((d) => Object.assign({ kind: "dish" }, d))
        .concat(data.recipes.map((r) => Object.assign({ kind: "recipe" }, r)));
      active = -1;
      render();
    }

    function choose(i) {
      const o = options[i];
      if (!o) return;
      state.dish = o.name;
      state.recipe = o.kind === "recipe" ? o.id : null;
      input.value = o.name;
      close();
      save();
      refresh();
    }

    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => lookUp().catch(close), 120); });
    input.addEventListener("keydown", (e) => {
      const open = !box.hidden && options.length;
      if (e.key === "ArrowDown" && open) { active = Math.min(active + 1, options.length - 1); render(); e.preventDefault(); }
      else if (e.key === "ArrowUp" && open) { active = Math.max(active - 1, 0); render(); e.preventDefault(); }
      else if (e.key === "Enter" && open && active >= 0) { choose(active); e.preventDefault(); }
      else if (e.key === "Escape") { close(); }
    });
    box.addEventListener("mousedown", (e) => {
      const li = e.target.closest("li[data-i]");
      if (li) { e.preventDefault(); choose(Number(li.dataset.i)); }
    });
    input.addEventListener("blur", () => setTimeout(close, 150));
    $("#plan-form").addEventListener("submit", (e) => {
      e.preventDefault();
      clearTimeout(timer);
      seq += 1;
      close();
      state.dish = input.value.trim();
      state.recipe = null;
      save();
      refresh();
    });
  }

  function listCard(toBuy, fine) {
    return `<aside class="list-card">
      <h3>Shopping list</h3>
      <p class="count">${toBuy.length ? `${toBuy.length} ingredient${toBuy.length > 1 ? "s" : ""} to buy` : "You have everything it needs."}</p>
      <ul>${toBuy.map((i) => `<li>${photo(i)}<span>${esc(i.name)}</span></li>`).join("")}</ul>
      ${toBuy.length ? '<button type="button" class="btn quiet" id="copy-list">Copy the list</button>' : ""}
      <p class="fine">${fine}</p></aside>`;
  }

  async function loadPlan(ticket) {
    $("#examples").innerHTML = EXAMPLES.map((d) => `<button type="button" data-dish="${esc(d)}">${esc(d)}</button>`).join("");
    if (document.activeElement !== $("#dish")) $("#dish").value = state.dish;
    const body = $("#plan-body");
    if (!state.dish && state.recipe === null) { body.innerHTML = ""; return; }
    body.innerHTML = '<p class="loading">Reading the recipes…</p>';
    const data = await api("/api/plan", { dish: state.dish, recipe: state.recipe, basket: state.basket, staples: state.staples });
    if (ticket !== state.ticket) return;
    if (!data.n) {
      body.innerHTML = `<p class="note">No rated recipe is called “${esc(state.dish)}”.
        ${data.suggestion ? `<button type="button" class="link" data-dish="${esc(data.suggestion)}">Try ${esc(data.suggestion)}</button>` : "Try a shorter or more common name."}</p>`;
      return;
    }
    const kitchen = state.staples ? " and kitchen basics" : "";
    const toBuy = data.items.filter((i) => i.status === "buy");

    if (data.mode === "recipe") {
      const r = data.recipes[0];
      state.shoppingList = `${r.name}: shopping list\n` + toBuy.map((i) => `- ${i.name}`).join("\n");
      const facts = [r.minutes ? `${r.minutes} minutes` : "", r.rating ? `rated ${r.rating} out of 5 by ${fmt(r.reviews)} reviewers` : ""].filter(Boolean).join(", ");
      body.innerHTML = `<div class="plan-head"><h2>${esc(r.name)}</h2>
          <p>A Food.com recipe${facts ? `, ${esc(facts)}` : ""}.</p></div>
        <div class="plan-grid">
          <ul class="needs">${data.items.map((i) => `<li>${photo(i)}
            <div><div class="name">${esc(i.name)}</div>${STATUS[i.status]()}</div><div></div></li>`).join("")}</ul>
          ${listCard(toBuy, `Everything this recipe uses, minus your fridge${kitchen}.`)}
        </div>
        <h3 class="sub">Method</h3>
        <ol class="steps method-steps">${r.steps.map((step) => `<li>${esc(step)}</li>`).join("")}</ol>`;
      return;
    }

    const title = data.dish.charAt(0).toUpperCase() + data.dish.slice(1);
    state.shoppingList = `${title}: shopping list\n` + toBuy.map((i) => `- ${i.name}`).join("\n");
    body.innerHTML = `<div class="plan-head"><h2>${esc(title)}</h2>
        <p>What the ${fmt(data.n)} rated recipes with this name usually contain.</p></div>
      <div class="plan-grid">
        <ul class="needs">${data.items.map((i) => `<li>${photo(i)}
          <div><div class="name">${esc(i.name)}</div>${STATUS[i.status]()}</div>
          <div class="bar"><span class="track"><i style="width:${Math.round(100 * i.share)}%"></i></span>
            <span>in ${Math.round(100 * i.share)}% of the recipes</span></div></li>`).join("")}</ul>
        ${listCard(toBuy, `Ingredients used by at least a quarter of the recipes, minus your fridge${kitchen}.`)}
      </div>
      <h3 class="sub">Versions that need the fewest purchases</h3>
      <p class="lead">Recipes with this name that contain at least half of its usual ingredients, sorted by how many ingredients you would have to buy, then by rating.</p>
      <div class="dishes">${data.recipes.map((r, i) => dishHtml(r, i, "plan")).join("")}</div>`;
  }

  async function copyList(button) {
    const text = state.shoppingList || "";
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy the list"; }, 1600);
  }

  // ---------- shop ----------
  async function loadShop(ticket) {
    $("#shop-list").innerHTML = '<li class="loading">Looking for the best additions…</li>';
    const data = await api("/api/shop", query({ method: "ppr" }));
    if (ticket !== state.ticket) return;
    $("#shop-lead").textContent = `These ingredients come up most often in your ${data.of} best-matching recipes, found by the graph walk from your fridge. Add one to see what it opens up.`;
    $("#shop-list").innerHTML = data.items.map((ing) => {
      const f = fam(ing.family);
      return `<li>${photo(ing)}
        <div><div class="shop-name">${esc(ing.name)}</div><span class="fam"><span class="dot" style="--c:${f.color}"></span>${esc(f.name)}</span></div>
        <div class="bar"><span class="track"><i style="width:${Math.round(100 * ing.in_best / data.of)}%"></i></span>
          <span>In ${ing.in_best} of your ${data.of} best recipes</span></div>
        <button type="button" class="btn quiet" data-add="${esc(ing.name)}">Add to fridge</button></li>`;
    }).join("") || '<li class="loading">Nothing to suggest yet.</li>';
  }

  // ---------- map ----------
  function cyStyle() {
    return [
      { selector: "node", style: {
        "background-color": "data(color)", width: "data(size)", height: "data(size)",
        label: "data(lbl)", "font-family": "Figtree, system-ui, sans-serif", "font-size": 12, "font-weight": 500,
        color: "#18211c", "text-valign": "bottom", "text-margin-y": 4,
        "text-outline-color": "#ffffff", "text-outline-width": 2, "border-width": 1, "border-color": "#ffffff",
        "min-zoomed-font-size": 7,
      } },
      { selector: "node[img]", style: {
        "background-image": "data(img)", "background-fit": "contain", "background-color": "#ffffff",
        "background-width": "78%", "background-height": "78%", "border-width": 3, "border-color": "data(color)",
      } },
      { selector: "node.basket", style: {
        "border-width": 4, "border-color": "#1e4d3a", "font-size": 15, "font-weight": 700, "z-index": 10,
      } },
      { selector: "node.labelled", style: { label: "data(name)" } },
      { selector: "node:selected", style: { "border-width": 4, "border-color": "#9c2f5a", "z-index": 20 } },
      { selector: "edge", style: {
        width: "mapData(npmi, 0.1, 0.6, 0.6, 4.5)", "line-color": "#c3cec6", opacity: 0.7, "curve-style": "haystack",
      } },
      { selector: "edge.touch", style: { "line-color": "#7f9b8b", opacity: 0.85 } },
      { selector: "edge.thin", style: { width: 0.7, opacity: 0.35 } },
      { selector: ".faded", style: { opacity: 0.1 } },
      { selector: "edge.faded", style: { opacity: 0.03 } },
    ];
  }

  function ensureCy() {
    if (state.cy) return state.cy;
    const cy = cytoscape({
      container: $("#cy"), style: cyStyle(), minZoom: 0.15, maxZoom: 4, wheelSensitivity: 0.3,
      textureOnViewport: true, hideEdgesOnViewport: true, boxSelectionEnabled: false,
    });
    const tip = document.createElement("div");
    tip.className = "map-tip";
    Object.assign(tip.style, {
      position: "absolute", pointerEvents: "none", padding: "6px 10px", borderRadius: "8px", fontSize: "13px",
      background: "#18211c", color: "#fff", whiteSpace: "nowrap", transform: "translate(-50%, -130%)", display: "none", zIndex: 5,
    });
    $(".map-canvas").appendChild(tip);
    cy.on("mouseover", "node", (e) => {
      const d = e.target.data();
      const p = e.target.renderedPosition();
      tip.innerHTML = `<strong>${esc(d.name)}</strong><br>${esc(fam(d.family).name)}<br>in ${fmt(d.recipes)} recipes`;
      Object.assign(tip.style, { left: `${p.x}px`, top: `${p.y - d.size * cy.zoom() / 2}px`, display: "block" });
    });
    cy.on("mouseout", "node", () => { tip.style.display = "none"; });
    cy.on("viewport", () => { tip.style.display = "none"; });
    cy.on("tap", "node", (e) => { focusNode(e.target.id()); });
    cy.on("tap", (e) => { if (e.target === cy) clearFocus(); });
    let zoomTimer = null;
    cy.on("zoom", () => {
      clearTimeout(zoomTimer);
      zoomTimer = setTimeout(() => {
        if (state.mapMode === "full") cy.nodes().toggleClass("labelled", cy.zoom() > 1.6);
      }, 80);
    });
    state.cy = cy;
    return cy;
  }

  async function loadMap(ticket) {
    const mode = state.basket.length ? state.mapMode : "full";
    $$(".segmented button").forEach((b) => {
      b.setAttribute("aria-checked", String(b.dataset.map === mode));
      if (b.dataset.map === "around") b.disabled = !state.basket.length;
    });
    $("#detail").hidden = true;
    state.focusFamily = null;
    const data = mode === "full"
      ? (state.fullMap || (state.fullMap = await api("/api/map/full")))
      : await api("/api/map/around", query());
    if (ticket !== state.ticket) return;
    const cy = ensureCy();
    cy.elements().remove();
    cy.add(mode === "full" ? fullElements(data) : aroundElements(data));
    if (mode === "full") {
      cy.layout({ name: "preset", fit: true, padding: 30 }).run();
      $("#map-lead").textContent = `All ${fmt(data.nodes.length)} connected ingredients of the catalogue. Ingredients cooked together sit close, and each keeps its three strongest links. Zoom in to read every name.`;
    } else {
      cy.layout({
        name: "cose", animate: false, randomize: false, padding: 50, numIter: 2500, gravity: 0.6,
        nodeRepulsion: () => 120000, idealEdgeLength: () => 100, edgeElasticity: () => 80, nodeOverlap: 40,
      }).run();
      $("#map-lead").textContent = "Your ingredients and the ones most often cooked with them, more than chance would predict.";
    }
    renderLegend(mode);
    $("#find-list").innerHTML = data.nodes.map((n) => `<option value="${esc(n.name)}"></option>`).join("");
  }

  function aroundElements(data) {
    const max = Math.max(...data.nodes.map((n) => n.recipes));
    const basket = new Set(data.nodes.filter((n) => n.basket).map((n) => n.name));
    const nodes = data.nodes.map((n) => ({
      group: "nodes", classes: n.basket ? "basket" : "",
      data: Object.assign({ id: n.name, name: n.name, lbl: n.name, family: n.family, recipes: n.recipes,
        color: fam(n.family).color, size: n.basket ? 66 : 22 + 30 * Math.sqrt(n.recipes / max) }, n.img ? { img: n.img } : {}),
    }));
    const edges = data.edges.map((e) => ({
      group: "edges", classes: basket.has(e.source) || basket.has(e.target) ? "touch" : "",
      data: { id: `${e.source}|${e.target}`, source: e.source, target: e.target, npmi: e.npmi },
    }));
    return nodes.concat(edges);
  }

  function fullElements(data) {
    const basket = new Set(state.basket);
    const max = Math.max(...data.nodes.map((n) => n.recipes));
    const labelled = new Set(data.nodes.slice().sort((a, b) => b.recipes - a.recipes).slice(0, 45).map((n) => n.name));
    const nodes = data.nodes.map((n) => ({
      group: "nodes", classes: basket.has(n.name) ? "basket" : "", position: { x: n.x, y: n.y },
      data: { id: n.name, name: n.name, lbl: labelled.has(n.name) || basket.has(n.name) ? n.name : "",
        family: n.family, recipes: n.recipes, color: fam(n.family).color,
        size: basket.has(n.name) ? 26 : 5 + 22 * Math.sqrt(n.recipes / max) },
    }));
    const edges = data.edges.map((e) => ({
      group: "edges", classes: "thin", data: { id: `${e.source}|${e.target}`, source: e.source, target: e.target, npmi: e.npmi },
    }));
    return nodes.concat(edges);
  }

  function renderLegend(mode) {
    const counts = {};
    state.cy.nodes().forEach((n) => { counts[n.data("family")] = (counts[n.data("family")] || 0) + 1; });
    const fams = state.meta.families.filter((f) => counts[f.id]);
    $("#legend").innerHTML = `<h3>Cuisine families (Louvain communities)</h3>
      <ul>${fams.map((f) => `<li><button type="button" data-family="${f.id}" aria-pressed="false">
        <span class="dot" style="--c:${f.color}"></span>${esc(f.name)}<small>${counts[f.id]}</small></button></li>`).join("")}</ul>
      <div class="keys">
        <div><svg viewBox="0 0 44 18" aria-hidden="true"><circle cx="5" cy="9" r="3" fill="#9aa69e"/><circle cx="16" cy="9" r="5" fill="#9aa69e"/><circle cx="33" cy="9" r="8" fill="#9aa69e"/></svg>Bigger: used in more recipes</div>
        <div><svg viewBox="0 0 44 18" aria-hidden="true"><line x1="2" y1="5" x2="42" y2="5" stroke="#9aa69e" stroke-width="1"/><line x1="2" y1="13" x2="42" y2="13" stroke="#9aa69e" stroke-width="5"/></svg>Thicker: paired more than chance (NPMI)</div>
        ${state.basket.length ? '<div><svg viewBox="0 0 44 18" aria-hidden="true"><circle cx="22" cy="9" r="7" fill="#fff" stroke="#1e4d3a" stroke-width="3"/></svg>In your fridge</div>' : ""}
      </div>
      <p class="hint">${mode === "full" ? "Click a family to isolate it, or an ingredient to see its best partners." : "Click an ingredient to see its best partners."}</p>`;
  }

  function toggleFamily(id) {
    const cy = state.cy;
    state.focusFamily = state.focusFamily === id ? null : id;
    $$("#legend [data-family]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.family) === state.focusFamily)));
    cy.elements().removeClass("faded");
    if (state.focusFamily === null) return;
    const keep = cy.nodes().filter((n) => n.data("family") === state.focusFamily);
    cy.nodes().not(keep).addClass("faded");
    cy.edges().filter((e) => !keep.contains(e.source()) || !keep.contains(e.target())).addClass("faded");
  }

  function clearFocus() {
    if (!state.cy) return;
    state.cy.elements().removeClass("faded");
    state.cy.nodes().unselect();
    $("#detail").hidden = true;
    state.focusFamily = null;
    $$("#legend [data-family]").forEach((b) => b.setAttribute("aria-pressed", "false"));
  }

  async function focusNode(name) {
    const cy = state.cy;
    let node = cy.getElementById(name);
    if (node.empty() && state.mapMode === "around") {
      state.mapMode = "full";
      await loadMap(++state.ticket);
      node = cy.getElementById(name);
    }
    if (node.nonempty()) {
      cy.elements().addClass("faded");
      node.closedNeighborhood().removeClass("faded");
      cy.nodes().unselect();
      node.select();
      if (state.mapMode === "full") cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1.4) }, { duration: 300 });
    }
    showDetail(name);
  }

  async function showDetail(name) {
    const box = $("#detail");
    box.hidden = false;
    box.innerHTML = '<p class="loading">Loading…</p>';
    const ing = await api(`/api/ingredient/${encodeURIComponent(name)}`);
    const f = fam(ing.family);
    const max = Math.max(...ing.partners.map((p) => p.npmi), 0.01);
    const inFridge = state.basket.includes(name);
    if (state.cy && state.cy.getElementById(name).selected()) {
      ing.partners.forEach((p) => state.cy.getElementById(p.name).removeClass("faded"));
    }
    box.innerHTML = `<button type="button" class="close" aria-label="Close">×</button>
      <div class="detail-head">${photo(ing)}<div><h2>${esc(ing.name)}</h2>
      <span class="fam"><span class="dot" style="--c:${f.color}"></span>${esc(f.name)}</span></div></div>
      <p class="stat">Used in ${fmt(ing.recipes)} rated recipes</p>
      <button type="button" class="btn${inFridge ? " quiet" : ""}" data-add="${esc(name)}" ${inFridge ? "disabled" : ""}>${inFridge ? "In your fridge" : "Add to fridge"}</button>
      <h4>Goes best with</h4>
      <ul class="partners">${ing.partners.map((p) => `<li>${photo(p)}
        <button type="button" data-focus="${esc(p.name)}">${esc(p.name)}</button>
        <span class="mini"><i style="width:${Math.round(60 * p.npmi / max)}px"></i>NPMI ${p.npmi}, together in ${fmt(p.together)} recipes</span></li>`).join("")
        || "<li>No strong partner: this ingredient goes with everything and nothing in particular.</li>"}</ul>`;
  }

  // ---------- chef ----------
  async function loadChef(ticket) {
    const body = $("#chef-body");
    body.innerHTML = '<p class="loading">Picking ingredients that go together…</p>';
    const data = await api("/api/chef", { basket: state.basket, seed: state.seed, write: false });
    if (ticket !== state.ticket) return;
    body.innerHTML = chefHtml(data) + '<div id="recipe-slot"></div>' + chefActions();
    const slot = $("#recipe-slot");
    if (!state.meta.chef_writer) {
      slot.innerHTML = '<p class="note">To have the method written, start the server with an ANTHROPIC_API_KEY environment variable.</p>';
      return;
    }
    slot.innerHTML = '<p class="loading">Writing the method…</p>';
    const full = await api("/api/chef", { basket: state.basket, seed: state.seed, write: true });
    if (ticket !== state.ticket) return;
    slot.innerHTML = full.recipe ? recipeHtml(full.recipe) : `<p class="note">${esc(full.note || "")}</p>`;
  }

  function chefHtml(data) {
    const mine = data.ingredients.filter((i) => !i.added);
    const added = data.ingredients.filter((i) => i.added);
    const token = (i) => `<li>${photo(i)}<span class="label">${esc(i.name)}</span>
      ${i.added ? `<span class="why">goes with ${i.links.map((l) => esc(l.with)).join(", ")}</span>` : ""}</li>`;
    const c = data.closest;
    const novel = c.shared >= data.ingredients.length
      ? `This exact combination already exists: <strong>${esc(c.name)}</strong>.`
      : `New combination. The closest existing recipe, <strong>${esc(c.name)}</strong>, shares ${c.shared} of its ${c.of} ingredients with it.`;
    return `<div class="chain">
        <div class="chain-group"><h4>From your fridge</h4><ul>${mine.map(token).join("")}</ul></div>
        <div class="chain-group added"><h4>Added by the map, in order</h4><ol>${added.map(token).join("")}</ol></div>
      </div>
      <p class="novel">${novel}</p>`;
  }

  function recipeHtml(r) {
    const steps = Array.isArray(r.steps) ? r.steps : [];
    return `<article class="recipe"><h2>${esc(r.title || "Untitled dish")}</h2>
      <p class="summary">${esc(r.summary || "")}${r.minutes ? ` About ${esc(r.minutes)} minutes.` : ""}</p>
      <ol class="steps">${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      <p class="byline">Method written by Claude (${esc(state.meta.chef_model)}) from the ingredients chosen by the graph. Not tested in a kitchen.</p></article>`;
  }

  function chefActions() {
    return `<div class="chef-actions"><button type="button" class="btn" id="another">Try another combination</button>
      ${state.seed ? '<button type="button" class="btn quiet" id="first">Back to the first idea</button>' : ""}</div>`;
  }

  // ---------- events ----------
  function bindEvents() {
    document.addEventListener("click", (e) => {
      const t = e.target.closest("button");
      if (!t) return;
      if (t.dataset.add) addIngredient(t.dataset.add);
      else if (t.dataset.remove) removeIngredient(t.dataset.remove);
      else if (t.dataset.tab) { state.tab = t.dataset.tab; save(); showView(); refresh(); }
      else if (t.dataset.method) { state.method = t.dataset.method; save(); showView(); if (state.tab === "cook") refresh(); }
      else if (t.dataset.map) { state.mapMode = t.dataset.map; refresh(); }
      else if (t.dataset.family !== undefined) toggleFamily(Number(t.dataset.family));
      else if (t.dataset.focus) focusNode(t.dataset.focus);
      else if (t.dataset.dish) { state.dish = t.dataset.dish; state.recipe = null; $("#dish").value = state.dish; save(); refresh(); }
      else if (t.id === "copy-list") copyList(t);
      else if (t.classList.contains("dish-head")) {
        const open = t.getAttribute("aria-expanded") === "true";
        t.setAttribute("aria-expanded", String(!open));
        $("#" + t.getAttribute("aria-controls")).hidden = open;
      } else if (t.classList.contains("close")) clearFocus();
      else if (t.id === "another") { state.seed += 1; refresh(); }
      else if (t.id === "first") { state.seed = 0; refresh(); }
      else if (t.id === "clear") { state.basket = []; changed(); }
      else if (t.id === "fit" && state.cy) state.cy.fit(undefined, 30);
    });
    $("#staples").addEventListener("change", (e) => { state.staples = e.target.checked; save(); refresh(); });
    $("#diverse").addEventListener("change", (e) => { state.diverse = e.target.checked; refresh(); });
    $("#find").addEventListener("change", (e) => {
      const name = e.target.value.trim().toLowerCase();
      if (state.ingByName[name] && state.cy) focusNode(name);
    });
  }

  // ---------- start ----------
  async function start() {
    try {
      state.meta = await api("/api/meta");
    } catch (err) {
      $("#main").innerHTML = `<p class="error">${esc(err.message)} Start the server with “python server.py”, then reload.</p>`;
      return;
    }
    for (const f of state.meta.families) state.famById[f.id] = f;
    for (const i of state.meta.ingredients) state.ingByName[i.name] = i;
    const photos = state.meta.ingredients.some((i) => i.img);
    $("#source").textContent = `${fmt(state.meta.recipes)} Food.com recipes with at least five ratings.${photos ? " Ingredient photos: TheMealDB." : ""}`;
    restore();
    setupSearch();
    setupDishSearch();
    bindEvents();
    renderBasket();
    renderPlates();
    showView();
    refresh();
  }

  start();
})();
