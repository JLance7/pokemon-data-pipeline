"""Refresh the local Pokémon catalog from PokéAPI and load it into SQLite."""

import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pipeline import STAT_KEYS

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "mimic.db"
SEED = ROOT / "web" / "data" / "pokedex.json"
API = "https://pokeapi.co/api/v2/"

CREATE_POKEMON = """
CREATE TABLE IF NOT EXISTS pokemon (
    id INTEGER PRIMARY KEY,
    pokemon_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    genus TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    height_m REAL NOT NULL CHECK (height_m >= 0),
    weight_kg REAL NOT NULL CHECK (weight_kg >= 0),
    stats TEXT NOT NULL,
    total INTEGER NOT NULL CHECK (total > 0),
    types TEXT NOT NULL,
    abilities TEXT NOT NULL,
    legendary INTEGER NOT NULL,
    mythical INTEGER NOT NULL,
    evolves_from INTEGER
)
"""
FIELDS = ("id", "pokemon_id", "name", "slug", "genus", "generation", "height_m",
          "weight_kg", "stats", "total", "types", "abilities", "legendary", "mythical",
          "evolves_from")
NESTED = {"stats", "types", "abilities"}


def get_json(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "pokeapi.co" or not parsed.path.startswith("/api/v2/"):
        raise ValueError(f"Unexpected PokéAPI URL: {url}")
    request = Request(url, headers={"User-Agent": "Pokemon-Local-ETL", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def reference_id(resource):
    return int(resource["url"].rstrip("/").rsplit("/", 1)[-1])


def extract_new_species(known_ids):
    url = API + "pokemon-species/?limit=2000"
    visited = set()
    records = {}
    expected_count = None
    while url:
        if url in visited:
            raise ValueError("PokéAPI repeated a pagination link.")
        visited.add(url)
        page = get_json(url)
        if expected_count is None:
            expected_count = page["count"]
        for item in page["results"]:
            key = reference_id(item)
            if key in records:
                raise ValueError(f"PokéAPI listed species {key} twice.")
            records[key] = item["url"]
        url = page["next"]
    if len(records) != expected_count:
        raise ValueError("PokéAPI returned an incomplete species list.")
    return [records[key] for key in sorted(records.keys() - known_ids)]


def transform_species(url):
    species = get_json(url)
    varieties = [item["pokemon"]["url"] for item in species["varieties"] if item["is_default"]]
    if len(varieties) != 1:
        raise ValueError(f"Expected one default form for {species['name']}.")
    pokemon = get_json(varieties[0])
    if reference_id(pokemon["species"]) != species["id"]:
        raise ValueError("The default form belongs to a different species.")
    slug = species["name"]
    english_name = next((item["name"] for item in species["names"] if item["language"]["name"] == "en"), None)
    genus = next((item["genus"] for item in species["genera"] if item["language"]["name"] == "en"), "")
    stats = {item["stat"]["name"].replace("-", "_"): item["base_stat"] for item in pokemon["stats"]}
    if set(stats) != set(STAT_KEYS) or len(pokemon["stats"]) != len(STAT_KEYS) or min(stats.values()) < 1:
        raise ValueError(f"Invalid base stats for {slug}.")
    types = [item["type"]["name"] for item in sorted(pokemon["types"], key=lambda item: item["slot"])]
    if len(types) not in (1, 2) or len(set(types)) != len(types):
        raise ValueError(f"Invalid type assignments for {slug}.")
    previous = species["evolves_from_species"]
    return {
        "id": species["id"], "pokemon_id": pokemon["id"], "slug": slug,
        "name": english_name or slug.replace("-", " ").title(), "genus": genus,
        "generation": reference_id(species["generation"]), "types": types,
        "height_m": pokemon["height"] / 10, "weight_kg": pokemon["weight"] / 10,
        "stats": stats, "total": sum(stats.values()),
        "legendary": species["is_legendary"], "mythical": species["is_mythical"],
        "evolves_from": reference_id(previous) if previous else None,
        "abilities": [{"name": item["ability"]["name"].replace("-", " ").title(), "hidden": item["is_hidden"]}
                      for item in sorted(pokemon["abilities"], key=lambda item: item["slot"])],
    }


def row_values(pokemon):
    return tuple(json.dumps(pokemon[field], ensure_ascii=False) if field in NESTED else pokemon[field]
                 for field in FIELDS)


def load_database(seed, updates, checked_at):
    columns = ", ".join(FIELDS)
    placeholders = ", ".join("?" for _ in FIELDS)
    assignments = ", ".join(f"{field}=excluded.{field}" for field in FIELDS if field != "id")
    with closing(sqlite3.connect(str(DATABASE))) as db, db:
        db.execute(CREATE_POKEMON)
        db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.executemany(f"INSERT INTO pokemon ({columns}) VALUES ({placeholders}) ON CONFLICT(id) DO NOTHING",
                       map(row_values, seed["pokemon"]))
        db.executemany(f"INSERT INTO pokemon ({columns}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {assignments}",
                       map(row_values, updates))
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('seed', ?)", (json.dumps(seed["meta"]),))
        if checked_at:
            db.execute("INSERT INTO metadata VALUES ('last_api_check', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (checked_at,))
        if updates:
            db.execute("INSERT INTO metadata VALUES ('last_api_refresh', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (checked_at,))
        return db.execute("SELECT COUNT(*) FROM pokemon").fetchone()[0]


def read_database():
    with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        metadata = dict(db.execute("SELECT key, value FROM metadata").fetchall())
        pokemon = [dict(row) for row in db.execute("SELECT * FROM pokemon ORDER BY id")]
    for row in pokemon:
        for field in NESTED:
            row[field] = json.loads(row[field])
        row["legendary"] = bool(row["legendary"])
        row["mythical"] = bool(row["mythical"])
    meta = json.loads(metadata["seed"])
    meta.update(count=len(pokemon), storage="SQLite")
    for field in ("last_api_check", "last_api_refresh"):
        if field in metadata:
            meta[field] = metadata[field]
    return {"meta": meta, "pokemon": pokemon}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--pokemon", help="Refresh a specific species by Dex number or API slug.")
    modes.add_argument("--seed-only", action="store_true", help="Load the included snapshot without a network request.")
    args = parser.parse_args()
    if args.pokemon and not re.fullmatch("[a-z0-9]+(?:-[a-z0-9]+)*", args.pokemon):
        parser.error("--pokemon must be a Dex number or lowercase API slug")
    try:
        seed = json.loads(SEED.read_text(encoding="utf-8"))
        if args.seed_only:
            urls = []
        elif args.pokemon:
            urls = [API + f"pokemon-species/{args.pokemon}/"]
        else:
            known = {item["id"] for item in seed["pokemon"]}
            if DATABASE.exists():
                with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
                    known.update(row[0] for row in db.execute("SELECT id FROM pokemon"))
            urls = extract_new_species(known)
        updates = [transform_species(url) for url in urls]
        checked = None if args.seed_only else datetime.now(timezone.utc).isoformat(timespec="seconds")
        count = load_database(seed, updates, checked)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, f"ETL failed. Existing catalog records were retained. {error}\n")
    print(f"mimic.db contains {count:,} species. {len(updates):,} fetched from the live API.")


if __name__ == "__main__":
    main()
