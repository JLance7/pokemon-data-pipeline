"""Extract PokéAPI CSV tables and publish a validated Pokédex snapshot."""

import argparse
import csv
import io
import json
import os
import re
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
TABLES = ("pokemon", "pokemon_species", "pokemon_species_names", "pokemon_stats",
          "pokemon_types", "types", "pokemon_abilities", "abilities")
STAT_KEYS = ("hp", "attack", "defense", "special_attack", "special_defense", "speed")


def fetch(table, revision):
    url = f"https://raw.githubusercontent.com/PokeAPI/pokeapi/{revision}/data/v2/csv/{table}.csv"
    request = Request(url, headers={"User-Agent": "Local-Pokedex-Pipeline"})
    with urlopen(request, timeout=30) as response:
        rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    if not rows:
        raise ValueError(f"Empty source table: {table}")
    return rows


def group(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return grouped


def transform(tables):
    species = {row["id"]: row for row in tables["pokemon_species"]}
    names = {row["pokemon_species_id"]: row for row in tables["pokemon_species_names"]
             if row["local_language_id"] == "9"}
    type_names = {row["id"]: row["identifier"] for row in tables["types"]}
    ability_names = {row["id"]: row["identifier"] for row in tables["abilities"]}
    stats = group(tables["pokemon_stats"], "pokemon_id")
    types = group(tables["pokemon_types"], "pokemon_id")
    abilities = group(tables["pokemon_abilities"], "pokemon_id")
    seen = set()
    result = []

    for row in tables["pokemon"]:
        if row["is_default"] != "1":
            continue
        key = row["id"]
        species_id = row["species_id"]
        if species_id in seen:
            raise ValueError(f"More than one default Pokémon for species {species_id}")
        seen.add(species_id)
        source = species[species_id]
        stat_values = {int(item["stat_id"]): int(item["base_stat"]) for item in stats[key]}
        if set(stat_values) != set(range(1, 7)) or len(stats[key]) != 6 or min(stat_values.values()) < 1:
            raise ValueError(f"Invalid base stats for Pokémon {key}")
        pokemon_types = [type_names[item["type_id"]]
                         for item in sorted(types[key], key=lambda item: int(item["slot"]))]
        if len(pokemon_types) not in (1, 2) or len(set(pokemon_types)) != len(pokemon_types):
            raise ValueError(f"Invalid type assignments for Pokémon {key}")
        label = names.get(species_id, {})
        result.append({
            "id": int(species_id),
            "pokemon_id": int(key),
            "name": label.get("name") or source["identifier"].replace("-", " ").title(),
            "slug": source["identifier"],
            "genus": label.get("genus", ""),
            "generation": int(source["generation_id"]),
            "types": pokemon_types,
            "height_m": int(row["height"]) / 10,
            "weight_kg": int(row["weight"]) / 10,
            "stats": {name: stat_values[index] for index, name in enumerate(STAT_KEYS, 1)},
            "total": sum(stat_values.values()),
            "legendary": source["is_legendary"] == "1",
            "mythical": source["is_mythical"] == "1",
            "evolves_from": int(source["evolves_from_species_id"]) if source["evolves_from_species_id"] else None,
            "abilities": [{"name": ability_names[item["ability_id"]].replace("-", " ").title(),
                           "hidden": item["is_hidden"] == "1"}
                          for item in sorted(abilities[key], key=lambda item: int(item["slot"]))],
        })
    if seen != set(species):
        raise ValueError(f"Default forms missing for {len(set(species) - seen)} species")
    return sorted(result, key=lambda item: item["id"])


def publish(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as handle:
        pending = Path(handle.name)
        try:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        except Exception:
            handle.close()
            pending.unlink()
            raise
    try:
        os.replace(pending, path)
    finally:
        if pending.exists():
            pending.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=(ROOT / "source-revision.txt").read_text().strip(),
                        help="A full PokéAPI Git commit SHA")
    args = parser.parse_args()
    if not re.fullmatch("[0-9a-f]{40}", args.revision):
        parser.error("--revision must be a full lowercase 40-character commit SHA")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(fetch, name, args.revision) for name in TABLES}
        tables = {name: future.result() for name, future in futures.items()}
    pokemon = transform(tables)
    target = ROOT / "web" / "data" / "pokedex.json"
    publish(target, {"meta": {"revision": args.revision, "count": len(pokemon),
                               "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "scope": "One default form per species"}, "pokemon": pokemon})
    print(f"Published {len(pokemon):,} Pokémon to {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
