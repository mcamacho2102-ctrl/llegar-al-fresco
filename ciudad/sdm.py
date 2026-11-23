"""Exporta los destinos regionales al modelo estándar Smart Data Models · PointOfInterest.

Genera entidades NGSI-LD en formato key-values para los centros para mayores, farmacias,
centros de salud y bibliotecas de la Comunidad de Madrid que usa la aplicación, y las
valida contra el esquema oficial (dataModel.PointOfInterest). Así otro municipio u otra
plataforma (FIWARE, espacios de datos Gaia-X) pueden reutilizarlas sin traducir campos.

    .venv/bin/python -m ciudad.sdm
"""

import json
import re
import sqlite3
import unicodedata
from urllib.request import Request, urlopen

from ciudad.fuentes import RAW, ROOT
from ciudad.motor import coordinates

SCHEMA = "https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/PointOfInterest/schema.json"
CONTEXT = "https://raw.githubusercontent.com/smart-data-models/dataModel.PointOfInterest/master/context.jsonld"
OUT = ROOT / "resultados" / "smart-data-models"
KINDS = {
    "elderly": ("centro-para-mayores", "Registro de centros de atención social"),
    "pharmacy": ("farmacia", "Oficinas de farmacia"),
    "library": ("biblioteca", "Directorio de bibliotecas"),
}
SOURCES = {
    "elderly": "https://datos.comunidad.madrid/dataset/atencion_social_registro_centros",
    "pharmacy": "https://datos.comunidad.madrid/dataset/oficinas_farmacia",
    "library": "https://datos.comunidad.madrid/dataset/spacm_listado_bibliotecas_servicios_lectura",
    "health": "https://datos.comunidad.madrid/dataset/centros_servicios_establecimientos_sanitarios",
}
PRIMARY = ("Centro de salud ·", "Consultorio de atención primaria ·")


def slug(text):
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-")[:60]


def fetch_json(url):
    with urlopen(Request(url, headers={"User-Agent": "llegar-al-fresco"}), timeout=60) as r:
        return json.load(r)


def entities():
    db = sqlite3.connect(f"file:{RAW / 'ciudad' / 'lugares.sqlite'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT * FROM poi WHERE source LIKE 'Comunidad de Madrid%' AND kind IN ('elderly','pharmacy','library','health')"
    ).fetchall()
    db.close()
    for row in rows:
        kind = row["kind"]
        if kind == "health" and not row["label"].startswith(PRIMARY):
            continue
        category = "centro-de-salud" if kind == "health" else KINDS[kind][0]
        lon, lat = coordinates((row["x"], row["y"]))
        entity = {
            "id": f"urn:ngsi-ld:PointOfInterest:llegar-al-fresco:{row['id']}-{slug(row['label'])}",
            "type": "PointOfInterest",
            "name": row["label"].split(" · ")[0],
            "description": row["label"],
            "category": [category],
            "location": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "address": {"addressCountry": "ES", "addressRegion": "Comunidad de Madrid", "addressLocality": "Madrid"},
            "source": SOURCES[kind],
            "dataProvider": row["source"],
        }
        if row["hours"]:
            entity["openingHours"] = row["hours"]
        yield entity


def validate(items):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    cache = {}

    def retrieve(uri):
        if uri not in cache:
            cache[uri] = Resource.from_contents(fetch_json(uri))
        return cache[uri]

    schema = fetch_json(SCHEMA)
    validator = Draft202012Validator(schema, registry=Registry(retrieve=retrieve))
    errors = []
    for item in items:
        for error in validator.iter_errors(item):
            errors.append((item["id"], error.message))
    return errors


def main():
    items = list(entities())
    errors = validate(items)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "destinos-comunidad-madrid.pointofinterest.json"
    target.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    ld = [item | {"@context": [CONTEXT]} for item in items[:3]]
    (OUT / "ejemplo-ngsi-ld.jsonld").write_text(json.dumps(ld, ensure_ascii=False, indent=1))
    counts = {}
    for item in items:
        counts[item["category"][0]] = counts.get(item["category"][0], 0) + 1
    print(f"{len(items)} entidades PointOfInterest · {counts}")
    print(f"Validación contra el esquema oficial: {'sin errores' if not errors else f'{len(errors)} errores'}")
    for ident, message in errors[:10]:
        print(" ", ident, message)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
