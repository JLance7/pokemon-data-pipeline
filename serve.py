"""Serve the dashboard locally without exposing files outside the web folder."""

import argparse
import json
import sqlite3
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import webbrowser

from mimic_etl import DATABASE, read_database


class PokedexHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path != "/data/pokedex.json" or not DATABASE.exists():
            return super().do_GET()
        try:
            body = json.dumps(read_database(), ensure_ascii=False).encode("utf-8")
        except (OSError, sqlite3.Error, ValueError, KeyError) as error:
            self.log_error("Could not read mimic.db: %s", error)
            self.send_error(500, "Could not read the Pokédex database.")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the dashboard in your browser.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "web"
    handler = partial(PokedexHandler, directory=str(root))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"Pokédex Studio is running at {url}. Press Ctrl+C to stop.", flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
