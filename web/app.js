"use strict";

const byId = id => document.getElementById(id);
const title = text => text.charAt(0).toUpperCase() + text.slice(1);
const dex = id => "#" + String(id).padStart(4, "0");
const pageSize = 10;
const statLabels = {
  hp: "HP", attack: "Attack", defense: "Defense", special_attack: "Sp. Attack",
  special_defense: "Sp. Defense", speed: "Speed",
};
const typeColors = {
  normal: "#73716a", fire: "#c35519", water: "#2768ba", electric: "#a67a00",
  grass: "#378034", ice: "#168184", fighting: "#a63c38", poison: "#874a9a",
  ground: "#926834", flying: "#635ca6", psychic: "#ae4471", bug: "#697c1d",
  rock: "#877338", ghost: "#62417e", dragon: "#553ba3", dark: "#62514c",
  steel: "#586978", fairy: "#ad527b",
};

let species = [];
let matches = [];
let page = 0;
let selected;

function node(tag, text, cssClass) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cssClass) element.className = cssClass;
  return element;
}

function bar(label, value, max, color) {
  const row = node("div", undefined, "bar");
  const track = node("div", undefined, "track");
  const fill = node("span", undefined, "fill");
  track.setAttribute("aria-hidden", "true");
  fill.style.width = `${Math.min(100, value * 100 / max)}%`;
  if (color) fill.style.backgroundColor = color;
  track.append(fill);
  row.append(node("span", label), track, node("strong", value));
  return row;
}

function facts(pokemon) {
  const list = node("dl", undefined, "facts");
  for (const [label, value] of [
    ["Base stat total", pokemon.total], ["Height", `${pokemon.height_m} m`],
    ["Weight", `${pokemon.weight_kg} kg`],
  ]) {
    const entry = node("div");
    entry.append(node("dt", label), node("dd", value));
    list.append(entry);
  }
  return list;
}

function jumpTo(pokemon) {
  let index = matches.indexOf(pokemon);
  if (index < 0) {
    byId("query").value = pokemon.id;
    byId("type").value = "";
    byId("generation").value = "";
    applyFilters();
    index = matches.indexOf(pokemon);
  }
  selected = pokemon;
  page = Math.floor(index / pageSize);
  renderList();
  renderProfile();
  document.querySelector('.row[aria-pressed="true"]')?.focus();
}

function renderProfile() {
  const profile = byId("profile");
  profile.replaceChildren();
  if (!selected) {
    profile.append(node("h2", "No matching Pokémon"), node("p", "Try clearing a filter or searching another name."));
    return;
  }
  const pokemon = selected;
  const hero = node("div", undefined, "hero");
  const sprite = node("img", undefined, "sprite");
  sprite.alt = `${pokemon.name} sprite`;
  sprite.onerror = () => { sprite.hidden = true; };
  sprite.src = `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${pokemon.pokemon_id}.png`;
  const heading = node("div");
  heading.append(node("p", `${dex(pokemon.id)} · GENERATION ${pokemon.generation}`, "eyebrow"), node("h2", pokemon.name));
  if (pokemon.genus) heading.append(node("p", pokemon.genus, "muted"));
  for (const type of pokemon.types) heading.append(node("span", title(type), "badge"));
  if (pokemon.legendary) heading.append(node("span", "Legendary", "badge"));
  if (pokemon.mythical) heading.append(node("span", "Mythical", "badge"));
  hero.append(sprite, heading);
  profile.append(hero, facts(pokemon), node("h3", "Base stats"));
  for (const [key, label] of Object.entries(statLabels)) {
    profile.append(bar(label, pokemon.stats[key], 255));
  }
  profile.append(node("h3", "Abilities"));
  if (pokemon.abilities.length === 0) profile.append(node("p", "No ability recorded.", "muted"));
  for (const ability of pokemon.abilities) {
    profile.append(node("span", ability.name + (ability.hidden ? " · Hidden" : ""), "badge"));
  }
  profile.append(node("h3", "Direct evolutions"));
  const relatives = species.filter(entry => entry.id === pokemon.evolves_from || entry.evolves_from === pokemon.id);
  if (relatives.length === 0) profile.append(node("p", "No direct evolution recorded.", "muted"));
  for (const relative of relatives) {
    const direction = relative.id === pokemon.evolves_from ? "From" : "To";
    const button = node("button", `${direction} ${relative.name}`, "link-button");
    button.type = "button";
    button.onclick = () => jumpTo(relative);
    profile.append(button);
  }
}

function renderList() {
  const list = byId("species-list");
  list.replaceChildren();
  const pageCount = Math.ceil(matches.length / pageSize);
  for (const pokemon of matches.slice(page * pageSize, (page + 1) * pageSize)) {
    const row = node("button", undefined, "row");
    row.type = "button";
    row.setAttribute("aria-pressed", String(selected === pokemon));
    row.append(node("span", dex(pokemon.id), "number"), node("strong", pokemon.name), node("span", pokemon.total, "number"));
    row.onclick = () => {
      selected = pokemon;
      list.querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed", "false");
      row.setAttribute("aria-pressed", "true");
      renderProfile();
    };
    const item = node("li");
    item.append(row);
    list.append(item);
  }
  byId("previous").disabled = page === 0;
  byId("next").disabled = page >= pageCount - 1;
  byId("page-number").textContent = pageCount ? `${page + 1} / ${pageCount}` : "0 results";
}

function renderChart() {
  const chart = byId("type-chart");
  chart.replaceChildren();
  const counts = new Map();
  for (const pokemon of matches) {
    for (const type of pokemon.types) counts.set(type, (counts.get(type) || 0) + 1);
  }
  const ordered = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!ordered.length) chart.append(node("p", "No types to chart.", "muted"));
  for (const [type, count] of ordered) {
    chart.append(bar(title(type), count, ordered[0][1], typeColors[type]));
  }
}

function normalize(text) {
  return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function applyFilters() {
  const query = normalize(byId("query").value.trim());
  const number = /^#?\d+$/.test(query) ? Number(query.replace("#", "")) : null;
  const type = byId("type").value;
  const generation = Number(byId("generation").value);
  const sort = byId("sort").value;
  matches = species.filter(pokemon => {
    const found = number !== null ? pokemon.id === number :
      normalize(pokemon.name).includes(query) || pokemon.slug.includes(query);
    return found && (!type || pokemon.types.includes(type)) && (!generation || pokemon.generation === generation);
  });
  if (sort === "total") matches.sort((a, b) => b.total - a.total || a.id - b.id);
  if (sort === "name") matches.sort((a, b) => a.name.localeCompare(b.name));
  page = 0;
  if (!matches.includes(selected)) selected = matches[0];
  byId("matching-count").textContent = matches.length.toLocaleString();
  byId("status").textContent = `${matches.length.toLocaleString()} matching species · right column in the list shows base stat total`;
  renderList();
  renderProfile();
  renderChart();
}

function option(select, value, label) {
  const entry = node("option", label);
  entry.value = value;
  select.append(entry);
}

async function start() {
  try {
    const response = await fetch("data/pokedex.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const snapshot = await response.json();
    species = snapshot.pokemon;
    const generations = [...new Set(species.map(pokemon => pokemon.generation))].sort((a, b) => a - b);
    for (const type of [...new Set(species.flatMap(pokemon => pokemon.types))].sort()) option(byId("type"), type, title(type));
    for (const generation of generations) option(byId("generation"), generation, `Generation ${generation}`);
    byId("species-count").textContent = species.length.toLocaleString();
    byId("generation-count").textContent = generations.length;
    const meta = snapshot.meta;
    const storage = meta.storage ? ` · ${meta.storage}` : "";
    const checked = meta.last_api_check ? ` · API checked ${new Date(meta.last_api_check).toLocaleString()}` : "";
    byId("snapshot").textContent = `Default forms · seed ${meta.revision.slice(0, 9)}${storage}${checked}`;
    for (const id of ["type", "generation", "sort"]) byId(id).addEventListener("change", applyFilters);
    byId("query").addEventListener("input", applyFilters);
    document.querySelector(".filters").addEventListener("submit", event => event.preventDefault());
    document.querySelector(".filters").addEventListener("reset", () => setTimeout(applyFilters, 0));
    byId("previous").onclick = () => { page--; renderList(); };
    byId("next").onclick = () => { page++; renderList(); };
    applyFilters();
  } catch (error) {
    byId("status").textContent = "Could not load the snapshot. Start serve.py from the project folder and check that web/data/pokedex.json exists.";
    console.error(error);
  }
}

start();
