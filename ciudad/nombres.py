"""Pone nombre a los centros sanitarios del registro regional usando OpenStreetMap.

El registro de centros sanitarios de la Comunidad de Madrid trae tipo y dirección, pero
no el nombre («Centro de salud · de Segovia 4»). OpenStreetMap sí tiene el nombre de
muchos hospitales y centros de salud, a menudo dibujados como edificio (área). Este paso:

1. Lee de OSM los centros sanitarios con nombre (nodos y áreas, centroide de las áreas).
2. A cada centro del registro le añade el nombre del elemento OSM más cercano a ≤ 80 m
   del mismo tipo general (hospital con hospital; centro de salud con clínica/centro).
3. Añade como destino los hospitales de OSM que no estén ya en el índice.

    .venv/bin/python -m ciudad.nombres
"""

import sqlite3

import osmium
import shapely
from scipy.spatial import cKDTree

from ciudad.fuentes import RAW
from ciudad.preparar import TO_METERS, VERSION

MATCH_M = 80
HOSPITAL = "hospital"
PRIMARY = "primary"


def classify(tags):
    amenity = tags.get("amenity")
    healthcare = tags.get("healthcare")
    if amenity == "hospital" or healthcare == "hospital":
        return HOSPITAL
    if amenity in {"clinic", "doctors"} or healthcare in {"centre", "clinic", "doctor"}:
        return PRIMARY
    return None


class Health(osmium.SimpleHandler):
    def __init__(self, boundary):
        super().__init__()
        self.boundary = boundary
        self.items = []

    def keep(self, tags, lon, lat):
        kind = classify(tags)
        name = tags.get("name")
        if not kind or not name:
            return
        x, y = TO_METERS.transform(lon, lat)
        if shapely.intersects_xy(self.boundary, x, y):
            self.items.append((kind, name.strip(), x, y))

    def node(self, n):
        if n.location.valid():
            self.keep(n.tags, n.location.lon, n.location.lat)

    def area(self, a):
        try:
            rings = [[(p.lon, p.lat) for p in ring] for ring in a.outer_rings()]
        except osmium.InvalidLocationError:
            return
        if not rings or len(rings[0]) < 3:
            return
        centroid = shapely.Polygon(rings[0]).centroid
        self.keep(a.tags, centroid.x, centroid.y)


def main():
    boundary = shapely.from_wkb((VERSION / "limite.wkb").read_bytes())
    handler = Health(boundary)
    handler.apply_file(str(RAW / "madrid.osm.pbf"), locations=True)
    osm = handler.items
    print(f"OSM: {len(osm):,} centros sanitarios con nombre en Madrid capital", flush=True)
    db = sqlite3.connect(VERSION / "lugares.sqlite")
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id,label,x,y FROM poi WHERE kind='health' AND source LIKE 'Comunidad de Madrid%'"
    ).fetchall()
    named = 0
    rules = (
        # (prefijo en el registro, tipo OSM, distancia máxima, el nombre OSM debe contener)
        (("Hospital",), HOSPITAL, 200, None),
        (("Centro de salud ·", "Consultorio de atención primaria ·"), PRIMARY, MATCH_M, ("salud", "consultorio")),
    )
    for prefixes, kind, reach, must in rules:
        subset = [
            item for item in osm
            if item[0] == kind and (must is None or any(w in item[1].lower() for w in must))
        ]
        if not subset:
            continue
        tree = cKDTree([(x, y) for _, _, x, y in subset])
        for row in rows:
            base = row["label"]
            if not base.startswith(prefixes) or " — " in base:
                continue
            distance, index = tree.query((row["x"], row["y"]))
            if distance <= reach:
                db.execute("UPDATE poi SET label=? WHERE id=?", (f"{subset[index][1]} — {base}", row["id"]))
                named += 1
    # Hospitales de OSM que aún no están en el índice como destino
    added = 0
    existing = db.execute("SELECT x,y FROM poi WHERE kind IN ('health','hospital')").fetchall()
    tree = cKDTree([(r["x"], r["y"]) for r in existing]) if existing else None
    for kind, name, x, y in osm:
        if kind != HOSPITAL:
            continue
        if db.execute("SELECT 1 FROM poi WHERE label LIKE ? LIMIT 1", (name + "%",)).fetchone():
            continue  # ya está en el índice con ese nombre
        if tree is not None and tree.query((x, y))[0] <= MATCH_M:
            continue  # ya hay un centro registrado en ese mismo sitio
        db.execute(
            "INSERT OR IGNORE INTO poi VALUES(?,?,?,?,?,?,?)",
            (f"oh{round(x)}_{round(y)}", name, "hospital", x, y, "OpenStreetMap", None),
        )
        added += 1
    db.commit()
    db.close()
    print(f"Centros del registro con nombre: {named:,} · hospitales añadidos desde OSM: {added}", flush=True)


if __name__ == "__main__":
    main()
