"""Registro anónimo de consultas e informe para ayuntamientos.

De cada ruta consultada se guarda solo lo necesario para planificar mobiliario:
tipo de destino, límite sin descanso elegido, longitudes (camino directo, ruta con
descansos), si hubo que dar un rodeo o no existía alternativa y **dónde están los
tramos del camino directo sin banco** («huecos»). No se guarda la dirección de salida,
ni la IP, ni coordenadas del origen. El informe solo muestra huecos que se repiten en
un mínimo de consultas (k-anonimato).

Se desactiva con la variable de entorno USO_REGISTRO=0.
"""

import csv
import io
import math
import os
import sqlite3
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from statistics import median

import numpy as np
import shapely
from shapely import LineString, STRtree

from ciudad.fuentes import RAW
from ciudad.motor import TO_METERS, coordinates

BENCH_REACH_M = 10  # banco utilizable si está a 10 m o menos del camino
GRID_M = 60  # agrupación de huecos para el informe
MIN_COUNT = 3  # huecos con menos consultas no se muestran
LONG_GAP_M = 800  # más largo: zona sin bancos, no un banco estratégico
LOCAL = ZoneInfo("Europe/Madrid")

SCHEMA = """
CREATE TABLE IF NOT EXISTS consultas(
  id INTEGER PRIMARY KEY,
  dia TEXT, hora INTEGER,
  destino_tipo TEXT,
  limite_m INTEGER,
  corta_m REAL, con_descansos_m REAL, rodeo_m REAL,
  resultado TEXT
);
CREATE TABLE IF NOT EXISTS huecos(
  consulta INTEGER REFERENCES consultas(id),
  x REAL, y REAL, largo_m REAL, calle TEXT
);
CREATE INDEX IF NOT EXISTS huecos_xy ON huecos(x, y);
"""


MERGE_M = 150


def merge_nearby(items, by_id):
    """Une puntos de la misma calle a menos de MERGE_M metros (celdas contiguas),
    contando cada consulta una sola vez."""
    items = sorted(items, key=lambda r: len(r["_q"]), reverse=True)
    merged = []
    for item in items:
        x, y = TO_METERS.transform(*item["coordinates"])
        for group in merged:
            if group["calle"] == item["calle"] and math.dist((x, y), group["_xy"]) <= MERGE_M:
                group["_q"] |= item["_q"]
                break
        else:
            merged.append(item | {"_xy": (x, y)})
    for group in merged:
        queries = group.pop("_q")
        group.pop("_xy")
        group["consultas"] = len(queries)
        group["sinAlternativa"] = sum(by_id[q]["resultado"] == "sin_alternativa" for q in queries)
        group["rodeoTotalM"] = round(
            sum(by_id[q]["rodeo_m"] or 0 for q in queries if by_id[q]["resultado"] == "rodeo")
        )
        group["destinos"] = dict(Counter(by_id[q]["destino_tipo"] for q in queries))
    return merged


class Registro:
    def __init__(self, city, path=None):
        self.city = city
        self.path = path or RAW / "uso" / "consultas.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self.connect() as db:
            db.executescript(SCHEMA)
        # Solo los bancos enlazados a la red peatonal (los mismos que usa el motor),
        # no los que están tras un muro o en un recinto cerrado.
        linked = {rest.xy for rests in city.rests.values() for rest in rests}
        self.bench_points = shapely.points(sorted(linked))
        self.bench_tree = STRtree(self.bench_points)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    # --- cálculo de huecos -------------------------------------------------
    def gaps(self, route, limit):
        """Tramos del camino directo más largos que el límite sin un banco a mano."""
        xy = np.array([TO_METERS.transform(*p) for p in route["geometry"]["coordinates"]])
        if len(xy) < 2:
            return []
        line = LineString(xy)
        near = self.bench_tree.query(line, predicate="dwithin", distance=BENCH_REACH_M)
        stops = sorted({round(line.project(self.bench_points[i]), 1) for i in near})
        cuts = [0.0, *stops, line.length]
        found = []
        for start, end in zip(cuts, cuts[1:]):
            length = end - start
            if length <= limit:
                continue
            # Bancos que harían falta para cumplir el límite, repartidos por igual.
            needed = math.ceil(length / limit) - 1
            for k in range(1, needed + 1):
                spot = line.interpolate(start + k * length / (needed + 1))
                found.append((spot.x, spot.y, length, self.street(spot)))
        return found

    def street(self, point):
        """Nombre de la calle con nombre más cercana (a 60 m o menos)."""
        candidates = self.city.segment_tree.query(point, predicate="dwithin", distance=60)
        best = ""
        best_distance = float("inf")
        for edge in candidates:
            try:
                name = self.city.names[int(self.city.name[int(edge)])]
            except (IndexError, KeyError):
                continue
            if not name:
                continue
            distance = self.city.segments[int(edge)].distance(point)
            if distance < best_distance:
                best, best_distance = name, distance
        return best

    # --- registro ----------------------------------------------------------
    def classify(self, shortest, rested, limit):
        if limit is None or shortest is None:
            return "sin_limite"
        if rested is None:
            return "sin_alternativa"
        if rested["meters"] <= shortest["meters"] + 20:
            return "cumple"
        return "rodeo"

    def save(self, when, destination_kind, limit, shortest, rested):
        if limit is None or shortest is None:
            return
        result = self.classify(shortest, rested, limit)
        gaps = self.gaps(shortest, limit) if result != "cumple" else []
        with self.lock, self.connect() as db:
            cursor = db.execute(
                "INSERT INTO consultas(dia,hora,destino_tipo,limite_m,corta_m,con_descansos_m,rodeo_m,resultado)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    when.strftime("%Y-%m-%d"),
                    when.hour,
                    destination_kind or "direccion",
                    int(limit),
                    shortest["meters"],
                    rested["meters"] if rested else None,
                    (rested["meters"] - shortest["meters"]) if rested else None,
                    result,
                ),
            )
            db.executemany(
                "INSERT INTO huecos VALUES(?,?,?,?,?)",
                [(cursor.lastrowid, round(x, 1), round(y, 1), round(length, 1), street) for x, y, length, street in gaps],
            )

    def register(self, request, routes):
        if (
            os.environ.get("USO_REGISTRO", "1") == "0"
            or request.live
            or not request.register
            or request.scenario is not None  # simulaciones de mejoras: no es demanda real
        ):
            return
        limit = request.preferences.rest
        shortest = next((r for r in routes if r["style"] == "distance"), None)
        fitting = [r for r in routes if r["fitsRest"]]
        rested = min(fitting, key=lambda r: r["meters"]) if fitting else None
        try:
            self.save(datetime.now(LOCAL), request.purpose, limit, shortest, rested)
        except (sqlite3.Error, ValueError):
            pass  # el registro nunca debe impedir calcular una ruta

    # --- informe -----------------------------------------------------------
    def report(self, days=None, min_count=MIN_COUNT, limit_rows=25):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            where, args = "", []
            if days:
                where = "WHERE dia >= ?"
                args = [(datetime.now(LOCAL) - timedelta(days=days)).strftime("%Y-%m-%d")]
            rows = db.execute(f"SELECT * FROM consultas {where}", args).fetchall()
            gaps = db.execute(
                f"SELECT huecos.* FROM huecos JOIN consultas ON consultas.id = huecos.consulta {where}",
                args,
            ).fetchall()
        total = len(rows)
        results = Counter(row["resultado"] for row in rows)
        detours = [row["rodeo_m"] for row in rows if row["resultado"] == "rodeo"]
        by_id = {row["id"]: row for row in rows}
        cells = defaultdict(list)
        zones = defaultdict(list)
        for g in gaps:
            if g["largo_m"] > LONG_GAP_M:
                if g["calle"]:  # sin nombre no se puede situar como zona
                    zones[g["calle"]].append(g)
            else:
                cells[(int(g["x"] // GRID_M), int(g["y"] // GRID_M))].append(g)
        zone_list = []
        for street, items in zones.items():
            queries = {g["consulta"] for g in items}
            if len(queries) < min_count:
                continue
            zone_list.append(
                {
                    "calle": street,
                    "consultas": len(queries),
                    "coordinates": coordinates(
                        (float(np.mean([g["x"] for g in items])), float(np.mean([g["y"] for g in items])))
                    ),
                    "huecoMedianoM": round(median(g["largo_m"] for g in items)),
                }
            )
        zone_list.sort(key=lambda z: z["consultas"], reverse=True)
        ranked = []
        for items in cells.values():
            queries = {g["consulta"] for g in items}
            if len(queries) < min_count:
                continue
            x = float(np.mean([g["x"] for g in items]))
            y = float(np.mean([g["y"] for g in items]))
            detour = sum(by_id[q]["rodeo_m"] or 0 for q in queries if by_id[q]["resultado"] == "rodeo")
            blocked = sum(by_id[q]["resultado"] == "sin_alternativa" for q in queries)
            street = Counter(g["calle"] for g in items if g["calle"]).most_common(1)
            ranked.append(
                {
                    "coordinates": coordinates((x, y)),
                    "calle": street[0][0] if street else "",
                    "consultas": len(queries),
                    "sinAlternativa": blocked,
                    "rodeoTotalM": round(detour),
                    "huecoMedianoM": round(median(g["largo_m"] for g in items)),
                    "destinos": dict(Counter(by_id[q]["destino_tipo"] for q in queries)),
                    "_q": set(queries),
                }
            )
        ranked = merge_nearby(ranked, by_id)
        ranked.sort(key=lambda r: (r["consultas"], r["rodeoTotalM"]), reverse=True)
        days_seen = sorted({row["dia"] for row in rows})
        return {
            "consultas": total,
            "periodo": [days_seen[0], days_seen[-1]] if days_seen else None,
            "cumplen": results["cumple"],
            "conRodeo": results["rodeo"],
            "sinAlternativa": results["sin_alternativa"],
            "rodeoTotalM": round(sum(detours)),
            "rodeoMedianoM": round(median(detours)) if detours else None,
            "limites": dict(sorted(Counter(row["limite_m"] for row in rows).items())),
            "destinos": dict(Counter(row["destino_tipo"] for row in rows).most_common()),
            "horas": dict(sorted(Counter(row["hora"] for row in rows).items())),
            "huecos": ranked[:limit_rows],
            "zonasSinBancos": zone_list[:10],
            "huecoLargoM": LONG_GAP_M,
            "huecosOcultos": sum(1 for items in cells.values() if len({g["consulta"] for g in items}) < min_count),
            "minimoConsultas": min_count,
        }

    def report_csv(self, **kwargs):
        data = self.report(limit_rows=500, **kwargs)
        out = io.StringIO()
        out.write("\ufeff")  # BOM: Excel en español detecta UTF-8 (tildes)
        writer = csv.writer(out, delimiter=";")
        writer.writerow(["calle", "lat", "lon", "consultas", "sin_alternativa", "rodeo_total_m", "hueco_mediano_m"])
        for h in data["huecos"]:
            lon, lat = h["coordinates"]
            writer.writerow([h["calle"], round(lat, 6), round(lon, 6), h["consultas"], h["sinAlternativa"], h["rodeoTotalM"], h["huecoMedianoM"]])
        return out.getvalue()
