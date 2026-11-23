"""Compila una versión local y reproducible de la red de Madrid capital."""

import csv
import gzip
import json
import re
import sqlite3
import unicodedata
import time
from datetime import datetime, timezone

import numpy as np
import osmium
import shapefile
import shapely
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import shape
from shapely.strtree import STRtree

from ciudad.fuentes import RAW
from ciudad.regional import add_regional, health_label

VERSION = RAW / "ciudad"
TO_METERS = Transformer.from_crs(4326, 25830, always_xy=True)
TO_DEGREES = Transformer.from_crs(25830, 4326, always_xy=True)
CROSSFIELDS = ("highway", "kerb", "crossing", "barrier")
HIGHWAYS = {
    "footway",
    "pedestrian",
    "path",
    "steps",
    "living_street",
    "residential",
    "service",
    "unclassified",
    "tertiary",
    "secondary",
    "primary",
    "tertiary_link",
    "secondary_link",
    "primary_link",
    "track",
    "cycleway",
}
NO_FOOT = {"no", "private", "customers", "permit"}
UNEVEN = {
    "gravel",
    "fine_gravel",
    "unpaved",
    "ground",
    "dirt",
    "sand",
    "grass",
    "cobblestone",
}


def normal(value):
    plain = unicodedata.normalize("NFKD", str(value).lower())
    return " ".join(
        re.findall(
            r"[a-z0-9]+", "".join(c for c in plain if not unicodedata.combining(c))
        )
    )


def csv_rows(name, encoding):
    with (RAW / name).open(encoding=encoding, newline="") as stream:
        yield from csv.reader(stream, delimiter=";")


def features(name):
    with gzip.open(RAW / name, "rt") as stream:
        for line in stream:
            feature = json.loads(line)
            if feature["geometry"]:
                yield feature


def number(value):
    try:
        return float(str(value).replace(",", ".").rstrip("%").strip())
    except (TypeError, ValueError):
        return None


class Streets(osmium.SimpleHandler):
    def __init__(self, boundary):
        super().__init__()
        self.boundary = boundary.buffer(50)
        shapely.prepare(self.boundary)
        self.raw_nodes = {}
        self.tags = {}
        self.raw_edges = []
        self.places = []
        self.trees = []

    def node(self, node):
        if not node.location.valid():
            return
        tags = node.tags
        if any(tags.get(key) for key in CROSSFIELDS):
            self.tags[node.id] = {key: tags.get(key) for key in CROSSFIELDS}
        amenity = tags.get("amenity")
        tree = tags.get("natural") == "tree"
        if (
            amenity
            in {
                "toilets",
                "drinking_water",
                "library",
                "clinic",
                "hospital",
                "pharmacy",
                "community_centre",
            }
            or tree
        ):
            x, y = TO_METERS.transform(node.location.lon, node.location.lat)
            if not shapely.intersects_xy(self.boundary, x, y):
                return
            if tree:
                height = number(tags.get("height"))
                diameter = number(tags.get("diameter_crown"))
                if height and diameter and 1 < height < 45 and 0.5 < diameter < 25:
                    self.trees.append((x, y, height, diameter))
            elif tags.get("access") not in NO_FOOT:
                self.places.append((node.id, x, y, amenity, tags.get("name")))

    def way(self, way):
        tags = way.tags
        kind = tags.get("highway")
        if (
            kind not in HIGHWAYS
            or tags.get("foot") in NO_FOOT
            or tags.get("area") == "yes"
            or (
                tags.get("access") in NO_FOOT
                and tags.get("foot") not in {"yes", "designated"}
            )
            or (kind == "cycleway" and tags.get("foot") not in {"yes", "designated"})
        ):
            return
        nodes = list(way.nodes)
        for a, b in zip(nodes, nodes[1:]):
            if not a.location.valid() or not b.location.valid() or a.ref == b.ref:
                continue
            pa = self.raw_nodes.get(a.ref) or TO_METERS.transform(
                a.location.lon, a.location.lat
            )
            pb = self.raw_nodes.get(b.ref) or TO_METERS.transform(
                b.location.lon, b.location.lat
            )
            midpoint = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            if not shapely.intersects_xy(self.boundary, *midpoint):
                continue
            footway = tags.get("footway")
            both_sides = tags.get("sidewalk") in {
                "both",
                "left",
                "right",
                "yes",
                "separate",
            }
            path = kind in {"footway", "pedestrian", "path", "steps", "living_street"}
            flags = (1 if kind == "steps" else 0) | (
                2 if footway == "crossing" or tags.get("crossing") else 0
            )
            flags |= (4 if tags.get("surface") in UNEVEN else 0) | (8 if path else 0)
            flags |= 16 if tags.get("bridge") or tags.get("tunnel") else 0
            flags |= 32 if path and kind != "steps" else 0
            if tags.get("sidewalk") in {"no", "none"}:
                flags |= 64
            direction = {"yes": 1, "1": 1, "-1": -1}.get(tags.get("oneway:foot"), 0)
            self.raw_nodes[a.ref] = pa
            self.raw_nodes[b.ref] = pb
            self.raw_edges.append(
                (
                    a.ref,
                    b.ref,
                    tags.get("name") or "",
                    flags,
                    number(tags.get("width")) if path else None,
                    direction,
                    number(tags.get("incline")),
                    both_sides,
                )
            )


def acera_attributes(points, usable):
    rows = list(features("aceras.jsonl.gz"))
    polygons = [shapely.make_valid(shape(row["geometry"])) for row in rows]
    tree = STRtree(polygons)
    matches = tree.query(shapely.points(points), predicate="within")
    attrs = np.full((len(points), 3), np.nan, dtype=np.float32)
    for row_id, polygon_id in zip(*matches):
        if not usable[row_id]:
            continue
        properties = rows[polygon_id]["properties"]
        for col, name in enumerate(("ancho_ac_m", "pen_m", "sol_ver_m")):
            value = number(properties.get(name))
            if value is not None and value >= 0:
                current = attrs[row_id, col]
                attrs[row_id, col] = (
                    value
                    if np.isnan(current)
                    else (min(current, value) if col == 0 else max(current, value))
                )
    nearest_sidewalk_width(attrs, points, rows, tree)
    return attrs


NEAREST_SIDEWALK_M = 15


def nearest_sidewalk_width(attrs, points, rows=None, tree=None):
    """Completa el ancho de los tramos sin acera propia con la acera municipal más
    cercana a menos de NEAREST_SIDEWALK_M metros. En OSM muchas calles se dibujan por
    el eje de la calzada, así que su punto medio no cae dentro del polígono de acera
    aunque esta exista y esté medida. Devuelve cuántos tramos se completan."""
    if rows is None:
        rows = [row for row in features("aceras.jsonl.gz")]
    if tree is None:
        tree = STRtree([shapely.make_valid(shape(row["geometry"])) for row in rows])
    missing = np.flatnonzero(np.isnan(attrs[:, 0]))
    if not len(missing):
        return 0
    (point_index, polygon_index), _ = tree.query_nearest(
        shapely.points(points[missing]),
        max_distance=NEAREST_SIDEWALK_M,
        return_distance=True,
        all_matches=False,
    )
    filled = 0
    for i, polygon in zip(point_index, polygon_index):
        value = number(rows[polygon]["properties"].get("ancho_ac_m"))
        if value is not None and value > 0 and np.isnan(attrs[missing[i], 0]):
            attrs[missing[i], 0] = value
            filled += 1
    return filled


def graph(boundary):
    handler = Streets(boundary)
    header = osmium.io.Reader(str(RAW / "madrid.osm.pbf"))
    osm_date = header.header().get("osmosis_replication_timestamp")
    header.close()
    handler.apply_file(str(RAW / "madrid.osm.pbf"), locations=True)
    node_ids = {identifier: i for i, identifier in enumerate(handler.raw_nodes)}
    xy = np.array(list(handler.raw_nodes.values()))
    edges = []
    names = {}
    for (
        source,
        target,
        name,
        flags,
        width,
        direction,
        incline,
        both,
    ) in handler.raw_edges:
        if source not in node_ids or target not in node_ids:
            continue
        a, b = node_ids[source], node_ids[target]
        if np.linalg.norm(xy[a] - xy[b]) < 0.03:
            continue
        for node in (source, target):
            tags = handler.tags.get(node, {})
            if flags & 2 and (
                tags.get("kerb") in {"raised", "rolled"}
                or tags.get("barrier") in {"stile", "turnstile"}
            ):
                flags |= 128
        edges.append(
            (a, b, names.setdefault(name, len(names)), flags, width, direction, incline)
        )
    a, b, name, flags, width, direction, incline = map(np.array, zip(*edges))
    sizes = np.linalg.norm(xy[a] - xy[b], axis=1)
    print(f"OSM: {len(xy):,} nodos · {len(a):,} tramos", flush=True)
    mid = (xy[a] + xy[b]) * 0.5
    for _ in range(180):
        if (RAW / "aceras.jsonl.gz").exists():
            break
        time.sleep(2)
    attrs = acera_attributes(mid, flags & 8 != 0)
    width = np.array(
        [x if x is not None and x > 0 else np.nan for x in width], dtype=np.float32
    )
    incline = np.array(
        [x if x is not None and abs(x) <= 70 else np.nan for x in incline],
        dtype=np.float32,
    )
    attrs[(flags & 16 != 0), 1] = np.nan
    np.savez_compressed(
        VERSION / "grafo.npz",
        xy=xy,
        a=a.astype("int32"),
        b=b.astype("int32"),
        name=name.astype("int32"),
        flags=flags.astype("uint8"),
        sizes=sizes.astype("float32"),
        explicit_width=width,
        direction=direction.astype("int8"),
        incline=incline,
        attrs=attrs,
    )
    (VERSION / "calles.json").write_text(json.dumps(list(names), ensure_ascii=False))
    print(
        f"Cruce con aceras: {np.count_nonzero(~np.isnan(attrs[:,0])):,} tramos",
        flush=True,
    )
    return handler, osm_date


def save_geometry(boundary, handler):
    reader = shapefile.Reader(str(RAW / "edificios.zip"), encoding="utf-8")
    minx, miny, maxx, maxy = boundary.bounds
    cell = 4
    origin = from_origin(minx - 250, maxy + 250, cell, cell)
    cols, rows = (
        int((maxx - minx + 500) / cell) + 1,
        int((maxy - miny + 500) / cell) + 1,
    )

    def obstacles():
        for item in reader.iterShapeRecords(fields=["ALTURA", "Z_HUELLA"]):
            height = item.record[0]
            if height and 0 < height < 250:
                yield item.shape.__geo_interface__, max(1, round(height))
        for x, y, height, diameter in handler.trees:
            yield shapely.Point(x, y).buffer(diameter / 2).__geo_interface__, round(
                height
            )

    raster = rasterize(
        obstacles(), out_shape=(rows, cols), transform=origin, fill=0, dtype="uint8"
    )
    np.save(VERSION / "obstaculos.npy", raster)
    (VERSION / "obstaculos.json").write_text(
        json.dumps(
            {
                "x": origin.c,
                "y": origin.f,
                "cell": cell,
                "areas": len(reader),
                "trees": len(handler.trees),
            }
        )
    )
    print(
        f"Alturas: {len(reader):,} polígonos · {len(handler.trees):,} copas con dimensiones OSM",
        flush=True,
    )


def add_places(handler, boundary):
    destination = VERSION / "lugares.next.sqlite"
    if destination.exists():
        destination.unlink()
    db = sqlite3.connect(destination)
    db.executescript(
        """
        CREATE TABLE portals(id INTEGER PRIMARY KEY, label TEXT, district TEXT, section TEXT, x REAL, y REAL);
        CREATE VIRTUAL TABLE search USING fts5(text);
        CREATE TABLE poi(id TEXT PRIMARY KEY, label TEXT, kind TEXT, x REAL, y REAL, source TEXT, hours TEXT);
        CREATE INDEX poi_kind ON poi(kind);
    """
    )
    portals = []
    for row in csv_rows("portales.csv", "cp1252"):
        if len(row) < 19 or not row[0].isdigit():
            continue
        portal = re.sub(r"\b0+(?=[0-9])", "", row[15].partition(",")[2].strip())
        if not portal or not row[16].isdigit() or not row[17].isdigit():
            continue
        street = " ".join(part.strip() for part in row[2:5] if part.strip())
        label = f"{street.title()}, {portal.upper()}"
        district = row[7].strip().title()
        section = row[6] + row[10].zfill(3)
        if len(row[10]) == 5:
            section = row[10]
        portals.append(
            (
                len(portals) + 1,
                label,
                district,
                section,
                int(row[16]) / 100,
                int(row[17]) / 100,
            )
        )
    db.executemany("INSERT INTO portals VALUES(?,?,?,?,?,?)", portals)
    db.executemany(
        "INSERT INTO search(rowid,text) VALUES(?,?)",
        ((i, normal(label + " " + district)) for i, label, district, *_ in portals),
    )
    banks = json.loads((RAW / "bancos-original.json").read_text())
    for bank in banks:
        x, y = number(bank.get("COORD_GIS_X")), number(bank.get("COORD_GIS_Y"))
        if bank["ESTADO"] != "OPERATIVO" or not x or not y:
            continue
        label = (
            " ".join(
                str(bank.get(key) or "") for key in ("TIPO_VIA", "NOM_VIA", "NUM_VIA")
            )
            .strip()
            .title()
        )
        db.execute(
            "INSERT OR IGNORE INTO poi VALUES(?,?,?,?,?,?,?)",
            (
                "b" + str(bank["ID"]),
                label or "Banco municipal",
                "bench",
                x,
                y,
                "Ayuntamiento de Madrid · inventario 2026",
                None,
            ),
        )
    for identifier, x, y, kind, name in handler.places:
        label = (
            name
            or {
                "toilets": "Aseo",
                "drinking_water": "Fuente para beber",
                "library": "Biblioteca",
                "clinic": "Centro sanitario",
                "hospital": "Hospital",
                "pharmacy": "Farmacia",
                "community_centre": "Centro comunitario",
            }[kind]
        )
        db.execute(
            "INSERT INTO poi VALUES(?,?,?,?,?,?,?)",
            ("o" + str(identifier), label, kind, x, y, "OpenStreetMap", None),
        )
    health_source = "Comunidad de Madrid · registro sanitario"
    with (RAW / "centros_servicios_establecimientos_sanitarios.csv").open(
        encoding="utf-8-sig", newline=""
    ) as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row["municipio_nombre"] != "Madrid":
                continue
            x, y = number(row["localizacion_coordenada_x"]), number(
                row["localizacion_coordenada_y"]
            )
            if not x or not y:
                continue
            label = health_label(row)
            db.execute(
                "INSERT OR IGNORE INTO poi VALUES(?,?,?,?,?,?,?)",
                (
                    "s" + row["centro_nro_registro"],
                    label,
                    "health",
                    x,
                    y,
                    health_source,
                    None,
                ),
            )
    osm_libs = [
        (name, x, y)
        for _, x, y, kind, name in handler.places
        if kind == "library" and name
    ]
    with (RAW / "spacm_listado_bibliotecas_servicios_lectura.csv").open(
        encoding="cp1252", newline=""
    ) as f:
        for i, row in enumerate(csv.DictReader(f, delimiter=";")):
            if normal(row["localidad"]) != "madrid":
                continue
            label = row["nombre_biblioteca"]
            phrase = normal(row["direccion"]).replace(",", " ")
            tokens = [
                word
                for word in phrase.split()
                if word
                not in {
                    "c",
                    "s",
                    "n",
                    "calle",
                    "de",
                    "del",
                    "la",
                    "el",
                    "av",
                    "avda",
                    "avenida",
                }
            ]
            terms = [word for word in tokens if len(word) > 1 or word.isnumeric()][:8]
            match = (
                db.execute(
                    "SELECT x,y FROM search JOIN portals ON portals.id=search.rowid WHERE search MATCH ? LIMIT 2",
                    (" ".join(terms),),
                ).fetchall()
                if terms
                else []
            )
            xy = (
                match[0]
                if len(match) == 1 and any(ch.isdigit() for ch in phrase)
                else None
            )
            if not xy:
                choices = [
                    (x, y) for name, x, y in osm_libs if normal(name) == normal(label)
                ]
                xy = choices[0] if len(choices) == 1 else None
            if xy:
                db.execute(
                    "INSERT INTO poi VALUES(?,?,?,?,?,?,?)",
                    (
                        f"l{i}",
                        label,
                        "library",
                        *xy,
                        "Comunidad de Madrid · directorio de bibliotecas",
                        row["horario"],
                    ),
                )
    add_regional(db, boundary)
    db.commit()
    print(
        f"Índice: {len(portals):,} portales · {db.execute('SELECT count(*) FROM poi').fetchone()[0]:,} puntos",
        flush=True,
    )
    db.close()
    destination.replace(VERSION / "lugares.sqlite")


def main():
    VERSION.mkdir(exist_ok=True)
    districts = list(features("distritos.jsonl.gz"))
    boundary = shapely.union_all(
        [shapely.make_valid(shape(row["geometry"])) for row in districts]
    )
    (VERSION / "limite.wkb").write_bytes(boundary.wkb)
    handler, osm_date = graph(boundary)
    add_places(handler, boundary)
    save_geometry(boundary, handler)
    (VERSION / "version.json").write_text(
        json.dumps(
            {
                "built": datetime.now(timezone.utc).isoformat(),
                "osm": osm_date,
                "banks": "2026",
                "addresses": "2026-10",
                "districts": len(districts),
            }
        )
    )


if __name__ == "__main__":
    main()
