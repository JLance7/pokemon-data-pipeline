# Pokédex Studio

Pokédex Studio is a local Pokémon data pipeline and browser dashboard. The included snapshot contains **1,025 species across nine generations**, with one default form per species.

## Open the dashboard

Install Python 3.8 or later. On Windows, double-click **Run-Pokedex.bat**. To start the server from a terminal instead:

```powershell
python serve.py --open
```

The dashboard runs at `http://127.0.0.1:8765/`. Press Ctrl+C in the terminal to stop it. Use `--port 8766` if the default port is occupied.

Search by name or National Dex number. Filter by type and generation, sort by base stat total, and select a species to see its stats, measurements, abilities, and direct evolutions. The type distribution chart updates as you filter. A dual-type species counts once for each of its types.

The dashboard reads `mimic.db` when available and falls back to the included snapshot otherwise. Both work offline. The selected Pokémon's sprite loads from the PokéAPI sprite repository when internet access is available.

## Refresh from the live API

Double-click **Refresh-Pokedex.bat**, or run:

```powershell
python mimic_etl.py
```

The ETL checks PokéAPI's species list, fetches the species and default-form records for new entries, transforms them into dashboard rows, and loads them into `mimic.db` in one SQLite transaction. The CSV snapshot seeds the database on the first run. Known species stay cached between runs. Reload the dashboard after refreshing.

To refresh an existing species, pass its National Dex number or API slug:

```powershell
python mimic_etl.py --pokemon 25
python mimic_etl.py --pokemon pikachu
```

Use `python mimic_etl.py --seed-only` to build the database from the included snapshot offline. The `pokemon` table contains one row per species, with JSON text columns for types, stats, and abilities. The `metadata` table records the seed and the last live API check.

## Rebuild the CSV seed

```powershell
python pipeline.py
```

The pipeline downloads eight PokéAPI CSV tables from the commit in `source-revision.txt`. It joins species, English names, default Pokémon forms, types, stats, and abilities. It converts height and weight to meters and kilograms, checks coverage and stat completeness, and atomically publishes `web/data/pokedex.json`. If the download or validation fails, the existing snapshot remains available.

To import a different revision, pass its full commit SHA to `python pipeline.py --revision`. The snapshot stores the actual source commit and import timestamp. If you already have `mimic.db`, run the ETL afterward to add missing rows from the rebuilt seed. Existing rows are preserved, including any live API updates.

The default form can differ from a regional, Mega, or other alternate form. Generation refers to the species' introduction. Stats reflect the source snapshot and can differ from individual game releases.

The dashboard uses plain HTML, CSS, and JavaScript. The import and local server use Python's standard library. [PokéAPI documentation](https://pokeapi.co/docs/v2) · [CSV source](https://github.com/PokeAPI/pokeapi/tree/master/data/v2/csv) · [Sprite source](https://github.com/PokeAPI/sprites)
