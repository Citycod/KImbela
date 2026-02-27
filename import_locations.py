import argparse
import json
from pathlib import Path

from runserver import app
from extensions import db
from models import Country, State, City
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "static" / "assets" / "js"


def load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def chunked(items, size=5000):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main(replace: bool):
    countries_path = DATA_DIR / "countries.json"
    states_path = DATA_DIR / "states.json"
    cities_path = DATA_DIR / "cities.json"

    if not countries_path.exists() or not states_path.exists() or not cities_path.exists():
        raise SystemExit("Missing JSON files in static/assets/js")

    with app.app_context():
        if replace:
            db.session.execute(
                text(
                    "TRUNCATE TABLE cities, states, countries RESTART IDENTITY CASCADE"
                )
            )
            db.session.commit()

        if Country.query.first() is None:
            countries = load_json(countries_path)
            mappings = [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "iso2": c.get("iso2"),
                    "iso3": c.get("iso3"),
                }
                for c in countries
            ]
            for batch in chunked(mappings):
                db.session.bulk_insert_mappings(Country, batch)
                db.session.commit()
            print(f"Imported {len(mappings)} countries")
        else:
            print("Countries already present, skipping")

        if State.query.first() is None:
            states = load_json(states_path)
            mappings = [
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "country_id": s.get("country_id"),
                }
                for s in states
            ]
            for batch in chunked(mappings):
                db.session.bulk_insert_mappings(State, batch)
                db.session.commit()
            print(f"Imported {len(mappings)} states")
        else:
            print("States already present, skipping")

        if City.query.first() is None:
            cities = load_json(cities_path)
            mappings = [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "state_id": c.get("state_id"),
                    "country_id": c.get("country_id"),
                }
                for c in cities
            ]
            for batch in chunked(mappings):
                db.session.bulk_insert_mappings(City, batch)
                db.session.commit()
            print(f"Imported {len(mappings)} cities")
        else:
            print("Cities already present, skipping")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="Replace existing data")
    args = parser.parse_args()
    main(args.replace)
