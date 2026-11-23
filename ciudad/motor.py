"""Grafo peatonal dirigido, descansos y evaluación de recorridos."""

from collections import defaultdict
import csv
from functools import lru_cache
from heapq import heappop, heappush
import itertools
import json
import math
from datetime import datetime, timezone
import sqlite3
from typing import NamedTuple, Optional

import numpy as np
import pvlib
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely import LineString, Point, STRtree

from ciudad.fuentes import RAW
from ciudad.preparar import VERSION, normal, number

TO_METERS = Transformer.from_crs(4326, 25830, always_xy=True)
TO_DEGREES = Transformer.from_crs(25830, 4326, always_xy=True)
MAX_CONNECT = 60
BENCH_CONNECT = 10
MAX_CHECKS = 220000


def finite(value):
    return float(value) if np.isfinite(value) else None


def coordinates(point):
    return list(TO_DEGREES.transform(*point))


class Arc(NamedTuple):
    to: int
    edge: int
    length: float
    direction: int


class Dock(NamedTuple):
    edge: int
    ratio: float
    offset: float
    xy: tuple


class Rest(NamedTuple):
    key: str
    label: str
    xy: tuple
    offset: float
    simulated: bool = False


class Limits(NamedTuple):
    rest: Optional[float] = None
    width: Optional[float] = None
    slope: Optional[float] = None
    stairs: bool = True


@lru_cache(maxsize=512)
def sun_vector(epoch_quarter):
    instant = datetime.fromtimestamp(epoch_quarter * 900 + 450, tz=timezone.utc)
    position = pvlib.solarposition.get_solarposition(instant, 40.4168, -3.7038).iloc[0]
    return (float(position["elevation"]), math.radians(float(position["azimuth"])))


class Madrid:
    def __init__(self):
        arrays = np.load(VERSION / "grafo.npz")
        for key in arrays.files:
            setattr(self, key, arrays[key])
        elevation_file = VERSION / "cotas.npy"
        heights = (
            np.load(elevation_file)
            if elevation_file.exists()
            else np.full(len(self.xy), np.nan)
        )
        estimated = (heights[self.b] - heights[self.a]) / self.sizes * 100
        estimated[
            (self.flags & 16 != 0) | (self.sizes < 4) | (np.abs(estimated) > 40)
        ] = np.nan
        self.grade = np.where(np.isfinite(self.incline), self.incline, estimated)
        self.meta = json.loads((VERSION / "version.json").read_text())
        self.names = json.loads((VERSION / "calles.json").read_text())
        self.boundary = shapely.from_wkb((VERSION / "limite.wkb").read_bytes())
        shapely.prepare(self.boundary)
        self.segments = shapely.linestrings(
            np.stack([self.xy[self.a], self.xy[self.b]], axis=1)
        )
        self.segment_tree = STRtree(self.segments)
        self.restable = np.flatnonzero(
            (self.flags & 32 != 0) & (self.flags & (1 | 2 | 128) == 0)
        )
        self.rest_tree = STRtree(self.segments[self.restable])
        self.docks = defaultdict(list)
        self.rests = defaultdict(list)
        self.points = {}
        self.db = VERSION / "lugares.sqlite"
        self.next_node = len(self.xy)
        self.adjacency = [[] for _ in self.xy]
        self.pois, self.poi_tree = self.read_pois()
        self.places_index = [
            (row, normal(row["label"]))
            for row in self.pois
            if row["kind"]
            in {"library", "health", "clinic", "hospital", "refuge", "elderly", "pharmacy"}
        ]
        self.water_and_toilets = [
            row for row in self.pois if row["kind"] in {"drinking_water", "toilets"}
        ]
        self.water_and_toilet_points = shapely.points(
            [(row["x"], row["y"]) for row in self.water_and_toilets]
        )
        self.service_tree = STRtree(self.water_and_toilet_points)
        self.bind_benches()
        for edge in range(len(self.a)):
            self.connect(edge, self.docks.get(edge, ()))
        self.shadow_raster = np.load(VERSION / "obstaculos.npy", mmap_mode="r")
        self.shadow_meta = json.loads((VERSION / "obstaculos.json").read_text())
        print(
            f"Red preparada · {len(self.a):,} tramos · {sum(map(len,self.rests.values())):,} descansos asociados",
            flush=True,
        )

    def db_connect(self):
        conn = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def read_pois(self):
        with self.db_connect() as conn:
            pois = list(conn.execute("SELECT * FROM poi"))
        sources = RAW / "fuentes.csv"
        if sources.exists():
            with sources.open(encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file, delimiter=";"):
                    if row["ESTADO"] != "OPERATIVO":
                        continue
                    x, y = number(row["COORD_GIS_X"]), number(row["COORD_GIS_Y"])
                    if x and y and shapely.intersects_xy(self.boundary, x, y):
                        street = " ".join(
                            filter(None, (row["NOM_VIA"], row["NUM_VIA"]))
                        )
                        pois.append(
                            {
                                "id": "f" + row["ID"],
                                "label": "Fuente de beber"
                                + (" · " + street if street else ""),
                                "kind": "drinking_water",
                                "x": x,
                                "y": y,
                                "source": "Ayuntamiento de Madrid · inventario 2026",
                                "hours": None,
                            }
                        )
        return pois, cKDTree([(row["x"], row["y"]) for row in pois])

    def nearby_services(self, path):
        route = LineString([TO_METERS.transform(*xy) for xy in path])
        nearby = self.service_tree.query(route, predicate="dwithin", distance=40)
        result = []
        for i in sorted(
            nearby, key=lambda i: route.distance(self.water_and_toilet_points[i])
        ):
            point = self.water_and_toilet_points[i]
            if any(other.distance(point) < 12 for other in result):
                continue
            result.append(point)
            yield self.poi_output(self.water_and_toilets[i]) | {
                "offsetM": round(route.distance(point))
            }
            if len(result) >= 5:
                break

    def point(self, node, extra=None):
        if extra and node in extra:
            return extra[node]
        if node in self.points:
            return self.points[node]
        return self.xy[node]

    def project(self, edge, xy):
        a, b = self.xy[self.a[edge]], self.xy[self.b[edge]]
        vector = b - a
        ratio = float(np.clip(((xy - a) @ vector) / (vector @ vector), 0, 1))
        fitted = a + ratio * vector
        return Dock(int(edge), ratio, float(np.linalg.norm(fitted - xy)), tuple(fitted))

    def locate(self, lon, lat, bench=False):
        xy = np.array(TO_METERS.transform(lon, lat))
        if not shapely.intersects_xy(self.boundary, *xy):
            return None
        point = Point(xy)
        distance = BENCH_CONNECT if bench else MAX_CONNECT
        tree = self.rest_tree if bench else self.segment_tree
        result = tree.query(point, predicate="dwithin", distance=distance)
        candidates = []
        for idx in result:
            edge = int(self.restable[idx]) if bench else int(idx)
            if self.flags[edge] & (128 | 1):
                continue
            dock = self.project(edge, xy)
            penalty = 0 if self.flags[edge] & 8 else 6
            candidates.append((dock.offset + penalty, edge, dock))
        return min(candidates)[2] if candidates else None

    def bind_benches(self):
        benches = [row for row in self.pois if row["kind"] == "bench"]
        xy = np.array([(row["x"], row["y"]) for row in benches])
        indices, distances = self.rest_tree.query_nearest(
            shapely.points(xy),
            max_distance=BENCH_CONNECT,
            all_matches=False,
            return_distance=True,
        )
        for (poi_idx, idx), distance in zip(indices.T, distances):
            bench = benches[poi_idx]
            edge = int(self.restable[idx])
            dock = self.project(edge, xy[poi_idx])
            node = self.next_node
            self.next_node += 1
            self.points[node] = dock.xy
            self.adjacency.append([])
            self.docks[edge].append((dock.ratio, node))
            self.rests[node].append(
                Rest(bench["id"], bench["label"], tuple(xy[poi_idx]), float(distance))
            )

    def chain(self, edge, extra):
        return sorted(
            [
                (0.0, int(self.a[edge])),
                *self.docks.get(edge, ()),
                *extra,
                (1.0, int(self.b[edge])),
            ]
        )

    def make_arcs(self, edge, chain, into):
        for (left, source), (right, target) in zip(chain, chain[1:]):
            length = (right - left) * float(self.sizes[edge])
            if self.direction[edge] >= 0:
                into(source, Arc(target, edge, length, 1))
            if self.direction[edge] <= 0:
                into(target, Arc(source, edge, length, -1))

    def connect(self, edge, existing):
        if not existing:
            chain = [(0.0, int(self.a[edge])), (1.0, int(self.b[edge]))]
        else:
            chain = self.chain(edge, ())
        self.make_arcs(edge, chain, lambda node, arc: self.adjacency[node].append(arc))

    def prepare_trip(self, origin, destination, scenario):
        a = self.locate(*origin)
        b = self.locate(*destination)
        if a is None or b is None:
            return None
        changes = defaultdict(list)
        x = self.next_node
        changes[a.edge].append((a.ratio, x))
        changes[b.edge].append((b.ratio, x + 1))
        points = {x: a.xy, x + 1: b.xy}
        rest = {}
        improved = {}
        if scenario:
            point = (scenario.lon, scenario.lat)
            location = self.locate(*point, bench=scenario.kind == "bench")
            if location is None:
                raise ValueError(
                    "No hay un tramo peatonal adecuado cerca de la intervención."
                )
            if scenario.kind == "bench":
                points[x + 2] = location.xy
                changes[location.edge].append((location.ratio, x + 2))
                rest[x + 2] = [
                    Rest(
                        "sim",
                        "Banco propuesto",
                        TO_METERS.transform(*point),
                        location.offset,
                        True,
                    )
                ]
            elif scenario.kind == "crossing":
                p = Point(*TO_METERS.transform(*point))
                indices = self.segment_tree.query(p, predicate="dwithin", distance=20)
                options = [
                    self.project(int(edge), np.array(p.coords[0]))
                    for edge in indices
                    if self.flags[edge] & 2
                ]
                if not options:
                    raise ValueError(
                        "Selecciona un paso de peatones cartografiado para simular un rebaje."
                    )
                improved[min(options, key=lambda d: d.offset).edge] = "crossing"
            else:
                improved[location.edge] = "shade"
        edges = defaultdict(list)
        for edge, extra in changes.items():
            self.make_arcs(
                edge, self.chain(edge, extra), lambda node, arc: edges[node].append(arc)
            )
        return Trip(
            self,
            x,
            x + 1,
            a,
            b,
            points,
            edges,
            set(changes),
            rest,
            improved,
            origin,
            destination,
        )

    @lru_cache(maxsize=500000)
    def exposure(self, edge, slot):
        elevation, azimuth = sun_vector(slot)
        if elevation <= 0:
            return 0.0
        a, b = self.xy[self.a[edge]], self.xy[self.b[edge]]
        samples = a + (b - a) * np.array([0.2, 0.5, 0.8])[:, None]
        steps = np.arange(4, 244, 4)
        grid = self.shadow_meta
        east = samples[:, 0, None] + math.sin(azimuth) * steps
        north = samples[:, 1, None] + math.cos(azimuth) * steps
        cols = np.floor((east - grid["x"]) / grid["cell"]).astype(int)
        rows = np.floor((grid["y"] - north) / grid["cell"]).astype(int)
        valid = (
            (rows >= 0)
            & (cols >= 0)
            & (rows < self.shadow_raster.shape[0])
            & (cols < self.shadow_raster.shape[1])
        )
        if not valid.all():
            return None
        obstruction = self.shadow_raster[rows, cols]
        shaded = np.any(
            obstruction > np.tan(np.radians(elevation)) * steps + 1.6, axis=1
        )
        return float(np.mean(~shaded))

    def poi_output(self, row):
        return {
            "id": row["id"],
            "label": row["label"],
            "kind": row["kind"],
            "coordinates": coordinates((row["x"], row["y"])),
            "source": row["source"],
            "hours": row["hours"],
        }

    def search(self, query):
        aliases = {
            "c": "calle",
            "av": "avenida",
            "avda": "avenida",
            "pza": "plaza",
            "pso": "paseo",
            "gta": "glorieta",
        }
        ignore = {"de", "del", "la", "las", "el", "los", "madrid"}
        words = [
            aliases.get(t, t)
            for t in normal(query).split()
            if t not in ignore
            and not (len(t) == 5 and t.startswith("28") and t.isdigit())
        ][:12]
        terms = [t for t in words if t.isalnum()]
        if not terms:
            return []
        if len(terms) > 1 and terms[-1].isdigit() and len(terms[-1]) > 1:
            terms[-1] = str(int(terms[-1]))
        exact_number = any(t.isdigit() for t in terms)
        match = " ".join(f'"{t}"' if t.isdigit() else f'"{t}"*' for t in terms)
        with self.db_connect() as conn:
            rows = conn.execute(
                """SELECT id,label,district,x,y FROM search JOIN portals ON portals.id=search.rowid
                                WHERE search MATCH ? ORDER BY bm25(search), length(label) LIMIT 12""",
                (match,),
            ).fetchall()
        places = (
            [
                row
                for _, row in sorted(
                    (
                        (-sum(t in label.split() for t in terms), row)
                        for row, label in self.places_index
                        if all(t in label for t in terms)
                    ),
                    key=lambda item: item[0],
                )
            ][:5]
            if not exact_number
            else []
        )
        if exact_number:
            requested = next(t for t in reversed(terms) if t.isdigit())
            rows = [
                r
                for r in rows
                if requested in normal(r["label"].partition(",")[2]).split()
            ]
        return [self.poi_output(row) for row in places] + [
            {
                "id": "p" + str(r["id"]),
                "label": r["label"],
                "district": r["district"],
                "kind": "address",
                "coordinates": coordinates((r["x"], r["y"])),
                "source": "Callejero municipal de Madrid · octubre 2026",
            }
            for r in rows
        ]


class Trip:
    def __init__(
        self,
        city,
        start,
        end,
        a,
        b,
        points,
        edges,
        replaced,
        rests,
        improved,
        origin,
        destination,
    ):
        self.city = city
        self.start = start
        self.end = end
        self.a = a
        self.b = b
        self.extra = points
        self.edges = edges
        self.replaced = replaced
        self.rests = rests
        self.improved = improved
        self.origin = origin
        self.destination = destination

    def edges_at(self, node):
        if node < len(self.city.adjacency):
            yield from (
                arc
                for arc in self.city.adjacency[node]
                if arc.edge not in self.replaced
            )
        yield from self.edges.get(node, ())

    def check(self, arc, limits):
        c = self.city
        edge = arc.edge
        flags = int(c.flags[edge])
        explicit = finite(c.explicit_width[edge])
        slope = finite(c.incline[edge])
        if flags & 128 and self.improved.get(edge) != "crossing":
            return False
        if limits.stairs and flags & 1:
            return False
        if limits.width is not None and (explicit is None or explicit < limits.width):
            return False
        if limits.slope is not None and (slope is None or abs(slope) > limits.slope):
            return False
        return True

    def practical_limit(self):
        return max(
            400,
            math.ceil(
                2 * math.dist(self.a.xy, self.b.xy)
                + self.a.offset
                + self.b.offset
                + 200
            ),
        )

    def solve(
        self,
        limits,
        depart,
        speed,
        style="distance",
        rest_limit=None,
        initial_since_rest=0,
        max_walk=None,
        max_checks=MAX_CHECKS,
    ):
        c = self.city
        target = np.array(self.b.xy)
        labels = []
        best = defaultdict(list)
        queue = []
        ids = itertools.count()
        if rest_limit is not None and self.a.offset + initial_since_rest > rest_limit:
            return None, False

        def submit(node, cost, walked, since, parent, action):
            slot = (
                int((depart + walked / speed) // 900)
                if style in {"shade", "balanced"}
                else 0
            )
            key = (node, slot)
            point = c.point(node, self.extra)
            estimate = math.hypot(point[0] - target[0], point[1] - target[1])
            if max_walk is not None and walked + estimate + self.b.offset > max_walk:
                return
            prior = best[key]
            resource = since if rest_limit is not None else 0
            if any(
                labels[i][1] <= cost + 1e-6
                and labels[i][3] <= resource + 1e-6
                and (max_walk is None or labels[i][2] <= walked + 1e-6)
                for i in prior
            ):
                return
            identifier = next(ids)
            labels.append((node, cost, walked, resource, parent, action, key))
            best[key] = [
                i
                for i in prior
                if not (
                    cost <= labels[i][1] + 1e-6
                    and resource <= labels[i][3] + 1e-6
                    and (max_walk is None or walked <= labels[i][2] + 1e-6)
                )
            ] + [identifier]
            heappush(queue, (cost + estimate, identifier))

        submit(
            self.start,
            self.a.offset,
            self.a.offset,
            self.a.offset + initial_since_rest,
            None,
            None,
        )
        checks = 0
        while queue:
            _, i = heappop(queue)
            node, cost, walked, since, _, _, key = labels[i]
            if i not in best[key]:
                continue
            if node == self.end and (
                rest_limit is None or since + self.b.offset <= rest_limit
            ):
                items = []
                while labels[i][4] is not None:
                    items.append(labels[i][5])
                    i = labels[i][4]
                return (
                    self.describe(items[::-1], depart, speed, initial_since_rest),
                    False,
                )
            checks += 1
            if checks > max_checks:
                return None, True
            for arc in self.edges_at(node):
                if rest_limit is not None and since + arc.length > rest_limit + 1e-6:
                    continue
                if not self.check(arc, limits):
                    continue
                multiplier = 1.0
                if style in {"comfort", "balanced"}:
                    slope = finite(c.grade[arc.edge])
                    slope = (
                        abs(slope)
                        if slope is not None
                        else finite(c.attrs[arc.edge, 1])
                    )
                    width = finite(c.explicit_width[arc.edge])
                    width = width if width is not None else finite(c.attrs[arc.edge, 0])
                    multiplier += min(slope / 8, 2) if slope is not None else 0.25
                    multiplier += max(0, 1.8 - width) if width is not None else 0.3
                    multiplier += 0.45 if c.flags[arc.edge] & 4 else 0
                if style in {"shade", "balanced"}:
                    exp = (
                        0.0
                        if self.improved.get(arc.edge) == "shade"
                        else c.exposure(
                            arc.edge,
                            int((depart + (walked + arc.length / 2) / speed) // 900),
                        )
                    )
                    multiplier += 1.1 * (exp if exp is not None else 0.8)
                submit(
                    arc.to,
                    cost + arc.length * multiplier,
                    walked + arc.length,
                    since + arc.length,
                    i,
                    (node, arc),
                )
            if rest_limit is not None:
                for rest in (*c.rests.get(node, ()), *self.rests.get(node, ())):
                    if since + rest.offset <= rest_limit and rest.offset + 1e-6 < since:
                        submit(
                            node,
                            cost + 2 * rest.offset,
                            walked + 2 * rest.offset,
                            rest.offset,
                            i,
                            (node, rest),
                        )
        return None, False

    def describe(self, items, depart, speed, initial_since_rest):
        c = self.city
        path = [list(self.origin), coordinates(self.a.xy)]
        walked = self.a.offset
        since = walked + initial_since_rest
        largest = 0.0
        rests, steps, segments = [], [], []
        exposure = shade_known = width_known = slope_known = ascent = descent = (
            direction_known
        ) = 0.0
        widths = []
        slopes = []
        barriers = []
        crossing_count = 0
        sun_now = sun_max = 0.0
        previous_vector = None
        for node, item in items:
            if isinstance(item, Rest):
                p = coordinates(item.xy)
                path.extend([p, coordinates(c.point(node, self.extra))])
                walked += item.offset
                since += item.offset
                largest = max(largest, since)
                rests.append(
                    {
                        "label": item.label,
                        "coordinates": p,
                        "atM": round(walked),
                        "fromRestM": round(since),
                        "simulated": item.simulated,
                    }
                )
                steps.append(
                    {
                        "action": "rest",
                        "label": item.label,
                        "distanceM": round(item.offset * 2),
                        "atM": round(walked),
                        "coordinates": p,
                    }
                )
                walked += item.offset
                since = item.offset
                continue
            edge = item.edge
            name = c.names[c.name[edge]] or "Tramo peatonal"
            xy = coordinates(c.point(item.to, self.extra))
            path.append(xy)
            flags = int(c.flags[edge])
            if flags & 2:
                crossing_count += 1
            width = finite(c.explicit_width[edge])
            if width is None:
                width = finite(c.attrs[edge, 0])
            if width is not None:
                widths.append(width)
                width_known += item.length
            signed = finite(c.grade[edge])
            slope = abs(signed) if signed is not None else finite(c.attrs[edge, 1])
            if slope is not None:
                slopes.append(slope)
                slope_known += item.length
            if signed is not None:
                rise = signed * item.direction * item.length / 100
                ascent += max(0, rise)
                descent += max(0, -rise)
                direction_known += item.length
            exp = (
                0.0
                if self.improved.get(edge) == "shade"
                else c.exposure(
                    edge, int((depart + (walked + item.length / 2) / speed) // 900)
                )
            )
            if item.length > 0.01:
                segments.append(
                    {
                        "coordinates": [path[-2], xy],
                        "widthM": round(width, 2) if width is not None else None,
                        "slopePct": round(slope, 1) if slope is not None else None,
                        "sun": round(exp, 2) if exp is not None else None,
                    }
                )
            if exp is not None:
                exposure += exp * item.length
                shade_known += item.length
                if exp > 0:
                    sun_now += exp * item.length
                    sun_max = max(sun_max, sun_now)
                if exp < 1:
                    sun_now = 0
            else:
                sun_now = 0.0
            if flags & 1:
                barriers.append("Escaleras cartografiadas")
            if flags & 4:
                barriers.append("Firme irregular cartografiado")
            if not flags & 8:
                barriers.append("Lado de la calle sin verificar en parte del recorrido")
            action = "cross" if flags & 2 else "walk"
            vector = np.subtract(
                c.point(item.to, self.extra), c.point(node, self.extra)
            )
            turn = None
            if previous_vector is not None and item.length >= 2 and action == "walk":
                u, v = previous_vector, vector
                angle = math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u @ v))
                if 42 <= abs(angle) <= 145:
                    turn = "left" if angle > 0 else "right"
            if item.length >= 2:
                previous_vector = vector
            if (
                steps
                and steps[-1]["action"] == action == "walk"
                and steps[-1]["label"] == name
                and turn is None
            ):
                steps[-1]["distanceM"] += item.length
            else:
                steps.append(
                    {
                        "action": action,
                        "label": name,
                        "distanceM": item.length,
                        "atM": round(walked),
                        "coordinates": coordinates(c.point(node, self.extra)),
                        "turn": turn,
                    }
                )
            walked += item.length
            since += item.length
        path.append(list(self.destination))
        distance = walked + self.b.offset
        longest = max(largest, since + self.b.offset)
        for step in steps:
            step["distanceM"] = round(step["distanceM"])
        return {
            "geometry": {"type": "LineString", "coordinates": path},
            "segments": segments,
            "meters": round(distance),
            "durationMin": round(distance / speed / 60, 1),
            "maxWithoutRest": round(longest, 1),
            "rests": rests,
            "steps": steps,
            "widthM": round(min(widths), 2) if widths else None,
            "slopePct": round(max(slopes), 1) if slopes else None,
            "upM": round(ascent, 1) if direction_known else None,
            "downM": round(descent, 1) if direction_known else None,
            "sunMin": round(exposure / speed / 60, 1) if shade_known else None,
            "sunStretchMin": round(sun_max / speed / 60, 1) if shade_known else None,
            "crossings": crossing_count,
            "coverage": {
                "width": round(width_known / max(distance, 1) * 100),
                "slope": round(slope_known / max(distance, 1) * 100),
                "elevation": round(direction_known / max(distance, 1) * 100),
                "sun": round(shade_known / max(distance, 1) * 100),
            },
            "barriers": sorted(set(barriers)),
            "connectionsM": [round(self.a.offset, 1), round(self.b.offset, 1)],
        }
