"""API privada del navegador y del panel de escenarios."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from functools import lru_cache
import csv
from collections import Counter, defaultdict, deque
from math import hypot
import os
from time import monotonic
from pathlib import Path
from typing import Literal, Optional
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ciudad.fuentes import AEMET, RAW, ROOT, response
from ciudad.motor import MAX_CHECKS, Madrid, Limits, TO_METERS, coordinates, normal
from ciudad.aforos import CAMPAIGN_SOURCE, PERMANENT_SOURCE, read_footfall
from ciudad.priorizar import SEARCH_BUDGET, compare_banks

LOCAL = ZoneInfo("Europe/Madrid")
SUMMER_PROGRAM = "https://www.madrid.es/portales/munimadrid/es/Inicio/El-Ayuntamiento/Notas-de-prensa/Matadero-Madrid-y-CentroCentro-abren-espacios-culturales-vegetales-para-refugiarse-del-calor/?vgnextchannel=6091317d3d2a7010VgnVCM100000dc0ca8c0RCRD&vgnextfmt=default&vgnextoid=f1e95a8688fee910VgnVCM100000891ecb1aRCRD"
REFUGES = (
    (
        "CentroCentro · Refugio vegetal",
        "Plaza De Cibeles 1",
        "2026-07-03",
        "2026-08-30",
        "10:00",
        "19:45",
    ),
    (
        "Matadero Madrid · Refugio de Nave Una",
        "Plaza De Legazpi 8",
        "2026-07-01",
        "2026-07-31",
        "12:00",
        "21:00",
    ),
)
SOURCE_FILES = [
    {
        "label": "Callejero de Madrid y portales",
        "url": "https://datos.madrid.es/dataset/200075-0-callejero",
        "date": "2026-10",
    },
    {
        "label": "Red peatonal, cruces y barreras",
        "url": "https://www.openstreetmap.org/copyright",
        "date": "Fecha del extracto en la versión",
    },
    {
        "label": "Ancho medio, pendiente e insolación estival",
        "url": "https://sigma.madrid.es/hosted/rest/services/GEOPORTAL/ACCESIBILIDAD_VIARIA/MapServer/layers",
        "date": "2026-11-19 (consulta)",
    },
    {
        "label": "Relieve MDT05",
        "url": "https://datos.gob.es/es/catalogo/e0dat0002-modelo-digital-del-terreno-con-paso-de-malla-de-5-metros-mdt05-de-espana1",
        "date": "2026-11-19 (consulta)",
    },
    {
        "label": "Alturas de edificios",
        "url": "https://geoportal.madrid.es/IDEAM_WBGEOPORTAL/dataset.iam?id=ALTURAS_EDIFICIOS",
        "date": "2026-07 (fichero)",
    },
    {
        "label": "Bancos municipales",
        "url": "https://datos.madrid.es/dataset/300095-0-mobiliario-bancos/downloads",
        "date": "2026 (inventario)",
    },
    {
        "label": "Centros sanitarios",
        "url": "https://datos.comunidad.madrid/dataset/centros_servicios_establecimientos_sanitarios",
        "date": "2026-11-19 (consulta)",
    },
    {
        "label": "Bibliotecas",
        "url": "https://datos.comunidad.madrid/dataset/spacm_listado_bibliotecas_servicios_lectura",
        "date": "2026-11-19 (consulta)",
    },
    {
        "label": "Centros para personas mayores (registro de atención social)",
        "url": "https://datos.comunidad.madrid/dataset/atencion_social_registro_centros",
        "date": "2026-11-23 (consulta)",
    },
    {
        "label": "Oficinas de farmacia",
        "url": "https://datos.comunidad.madrid/dataset/oficinas_farmacia",
        "date": "2026-11-23 (consulta)",
    },
    {
        "label": "Fuentes de agua potable",
        "url": "https://datos.madrid.es/dataset/300051-0-fuentes/downloads",
        "date": "2026-11-13 (inventario)",
    },
    {
        "label": "Meteorología histórica de la Comunidad",
        "url": "https://datos.comunidad.madrid/dataset/calidad_aire_datos_meteo_historico",
        "date": "2025 (observaciones)",
    },
    {
        "label": "Refugios culturales con horario publicado",
        "url": SUMMER_PROGRAM,
        "date": "2026-06-22 (programa de verano)",
    },
    {
        "label": "Recursos de Protección Civil",
        "url": "https://geoportal.madrid.es/IDEAM_WBGEOPORTAL/dataset.iam?id=RECURSOS_PROTECCION_CIVIL",
        "date": "2026-06-04 (capa de planificación)",
    },
    {
        "label": "Aforos horarios de peatones",
        "url": PERMANENT_SOURCE,
        "date": "2024-01 a 2024-06 (registros)",
    },
    {
        "label": "Campaña de aforos de peatones",
        "url": CAMPAIGN_SOURCE,
        "date": "2024-10 (campaña)",
    },
    {
        "label": "Población por sección",
        "url": "https://datos.madrid.es/dataset/200076-0-padron",
        "date": "2026-10 (padrón)",
    },
    {
        "label": "Predicción horaria para Madrid",
        "url": "https://www.aemet.es/es/eltiempo/prediccion/municipios/horas/madrid-id28079",
        "date": "Fecha de emisión en el resultado",
    },
]


class Place(BaseModel):
    lon: float = Field(ge=-4, le=-3)
    lat: float = Field(ge=40, le=41)


class Improvement(Place):
    kind: Literal["bench", "crossing", "shade"]


class Preferences(BaseModel):
    pace: float = Field(default=1, ge=0.4, le=1.7)
    rest: Optional[int] = Field(default=200, ge=30, le=1500)
    width: Optional[float] = Field(default=None, ge=0.7, le=5)
    slope: Optional[float] = Field(default=None, ge=1, le=30)
    avoidStairs: bool = True


class RouteRequest(BaseModel):
    origin: Place
    destination: Place
    departure: datetime
    preferences: Preferences = Field(default_factory=Preferences)
    scenario: Optional[Improvement] = None
    live: bool = False
    initialSinceRest: float = Field(default=0, ge=0, le=10000)


class AreaRequest(RouteRequest):
    radiusM: int = Field(default=250, ge=100, le=500)


class StudyRequest(AreaRequest):
    scenario: Improvement


class BankPlanRequest(AreaRequest):
    scenario: None = None


@asynccontextmanager
async def lifespan(app):
    app.state.city = Madrid()
    app.state.population = section_population()
    app.state.footfall = read_footfall(app.state.city)
    yield


def section_population():
    population = Counter()
    older = Counter()
    source = RAW / "padron.csv"
    if not source.is_file():
        return population, older
    columns = (
        "ESPANOLESHOMBRES",
        "ESPANOLESMUJERES",
        "EXTRANJEROSHOMBRES",
        "EXTRANJEROSMUJERES",
    )
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            try:
                section = str(int(row["COD_DIST_SECCION"])).zfill(5)
                residents = sum(int(row[col] or 0) for col in columns)
                population[section] += residents
                # La última edad se publica como «100 o +».
                age = "".join(ch for ch in row["COD_EDAD_INT"] or "" if ch.isdigit())
                if int(age or 0) >= 65:
                    older[section] += residents
            except (ValueError, TypeError):
                continue
    return population, older


app = FastAPI(title="Llegar al fresco", version="2.0", lifespan=lifespan)
front = ROOT / "web" / ".build"

# Límite sencillo de llamadas a la API por IP para una demo pública.
# Desactivado si LIMITE_PETICIONES=0. Detrás de un proxy se usa la IP que este reenvía.
RATE = int(os.environ.get("LIMITE_PETICIONES", "600"))
_calls = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if RATE and request.url.path.startswith("/api/"):
        forwarded = request.headers.get("fly-client-ip") or request.headers.get(
            "x-forwarded-for", ""
        ).split(",")[0].strip()
        client = forwarded or (request.client.host if request.client else "?")
        now = monotonic()
        window = _calls[client]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= RATE:
            return JSONResponse(
                {"detail": "Demasiadas consultas seguidas. Espera un minuto."},
                status_code=429,
            )
        window.append(now)
    return await call_next(request)


def times(request):
    timestamp = request.departure
    return (
        timestamp.replace(tzinfo=LOCAL) if timestamp.tzinfo is None else timestamp
    ).timestamp()


def limits(request):
    p = request.preferences
    return Limits(p.rest, p.width, p.slope, p.avoidStairs)


def build_trip(request):
    city = app.state.city
    try:
        trip = city.prepare_trip(
            (request.origin.lon, request.origin.lat),
            (request.destination.lon, request.destination.lat),
            request.scenario,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if trip is None:
        raise HTTPException(
            422,
            "El punto elegido está fuera de Madrid capital o a más de 60 m de la red peatonal disponible.",
        )
    return trip


@lru_cache(maxsize=3)
def forecast(_bucket):
    try:
        with response(AEMET, timeout=3, attempts=1) as info:
            xml = ET.parse(info)
    except (OSError, ET.ParseError):
        local = RAW / "aemet-madrid.xml"
        if not local.is_file():
            return None
        xml = ET.parse(local)
    issued = xml.findtext("elaborado")
    if not issued:
        return None
    values = {}
    for day in xml.findall("prediccion/dia"):
        date = day.get("fecha")
        for temperature in day.findall("temperatura"):
            hour = temperature.get("periodo")
            if hour and hour.isdigit() and int(hour) < 24 and temperature.text:
                values[date + "T" + hour.zfill(2)] = float(temperature.text)
    return issued, values


@lru_cache(maxsize=1)
def summer_reading():
    source = RAW / "calidad_aire_datos_meteo_historico.csv"
    if not source.is_file():
        return None
    with source.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file, delimiter=";"):
            keys = (
                "provincia",
                "municipio",
                "estacion",
                "magnitud",
                "ano",
                "mes",
                "dia",
                "v14",
            )
            if tuple(row[key] for key in keys) == (
                "28",
                "80",
                "3",
                "83",
                "2025",
                "7",
                "1",
                "V",
            ):
                return {
                    "temperatureC": float(row["h14"].replace(",", ".")),
                    "at": "2025-07-01",
                    "issued": None,
                    "source": "Comunidad de Madrid · estación de Majadahonda · franja h14",
                }
    return None


def air_at(epoch):
    if datetime.fromtimestamp(epoch, LOCAL).strftime("%Y-%m-%dT%H") == "2025-07-01T14":
        return summer_reading()
    if abs(datetime.now(LOCAL).timestamp() - epoch) > 4 * 86400:
        return None
    result = forecast(int(datetime.now().timestamp() // 1800))
    if not result:
        return None
    issued, values = result
    date = datetime.fromisoformat(issued).replace(tzinfo=LOCAL)
    if datetime.now(LOCAL) - date > timedelta(hours=12):
        return None
    hour = datetime.fromtimestamp(epoch, LOCAL).strftime("%Y-%m-%dT%H")
    if hour not in values:
        return None
    return {
        "temperatureC": values[hour],
        "at": hour + ":00",
        "issued": issued,
        "source": "AEMET · previsión horaria para el municipio de Madrid",
    }


def route_set(trip, request, full=True):
    p = request.preferences
    date = times(request)
    criteria = limits(request)
    if (criteria.width or criteria.slope) and max(trip.a.offset, trip.b.offset) > 3:
        raise HTTPException(
            422,
            "El acceso de un extremo está sin verificar. Marca un punto sobre la acera para aplicar límites imprescindibles de ancho o pendiente.",
        )
    styles = (
        [
            ("distance", "Más corta"),
            ("comfort", "Menos esfuerzo"),
            ("shade", "Prioriza sombra"),
        ]
        if full
        else [("comfort", "Con descansos")]
    )
    seen = set()
    routes = []
    limited = False
    for style, label in styles:
        limit = criteria.rest if style != "distance" else None
        result, paused = trip.solve(
            criteria,
            date,
            p.pace,
            style,
            limit,
            request.initialSinceRest,
            max_walk=None if style == "distance" else trip.practical_limit(),
        )
        limited |= paused
        if not result:
            continue
        signature = (
            tuple(map(tuple, result["geometry"]["coordinates"])),
            tuple(x["atM"] for x in result["rests"]),
        )
        if signature in seen:
            continue
        seen.add(signature)
        result["nearbyServices"] = list(
            trip.city.nearby_services(result["geometry"]["coordinates"])
        )
        result["label"] = label
        result["style"] = style
        result["fitsRest"] = (
            criteria.rest is None or result["maxWithoutRest"] <= criteria.rest + 0.01
        )
        routes.append(result)
    return routes, limited


@app.get("/api/info")
def info():
    city = app.state.city
    with city.db_connect() as conn:
        portals = conn.execute("SELECT count(*) FROM portals").fetchone()[0]
    return {
        "version": city.meta,
        "sources": SOURCE_FILES,
        "networkEdges": len(city.a),
        "benchConnections": sum(map(len, city.rests.values())),
        "portals": portals,
    }


@app.get("/api/addresses")
def addresses(
    q: str = Query(min_length=2, max_length=120), at: Optional[datetime] = None
):
    city = app.state.city
    results = city.search(q)
    if at is None:
        return {"results": results}
    if at.tzinfo is not None:
        at = at.astimezone(LOCAL)
    if at.weekday() == 0:
        return {"results": results}
    words = normal(q).split()
    date = at.date().isoformat()
    for index, (label, portal, first, last, open_at, close_at) in enumerate(REFUGES):
        if not (first <= date <= last and all(word in normal(label) for word in words)):
            continue
        known = city.search(portal)
        if known:
            results.insert(
                0,
                known[0]
                | {
                    "id": f"refuge:{index}",
                    "kind": "refuge",
                    "label": label,
                    "source": "Ayuntamiento de Madrid · programa de verano 2026",
                    "hours": f"Acceso al recinto. De martes a domingo, {open_at}–{close_at}.",
                    "openFrom": date + "T" + open_at,
                    "openUntil": date + "T" + close_at,
                    "url": SUMMER_PROGRAM,
                },
            )
    return {"results": results}


@app.post("/api/addresses/external")
def external(q: str = Query(min_length=3, max_length=120)):
    root = "https://www.cartociudad.es/geocoder/api/geocoder"
    try:
        candidates = jsonify_candidates(root, q)
        result = []
        for place in candidates:
            if normal(place.get("muni", "")) not in {"madrid", ""}:
                continue
            if str(place.get("id", "")) == "":
                continue
            lon, lat = place.get("lng"), place.get("lat")
            if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                continue
            if app.state.city.locate(lon, lat):
                result.append(
                    {
                        "id": "carto:" + str(place["id"]),
                        "label": place.get("address", q),
                        "kind": "address",
                        "coordinates": [lon, lat],
                        "source": "CartoCiudad · IGN",
                    }
                )
        return {"results": result[:8]}
    except (OSError, ValueError):
        raise HTTPException(
            503, "CartoCiudad no está disponible. Marca el portal en el mapa."
        )


def jsonify_candidates(root, q):
    import json

    with response(
        root + "/candidates", {"q": q + ", Madrid", "limit": 8}, timeout=5, attempts=1
    ) as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):
        return []
    for place in raw:
        if not (place.get("lng") and place.get("lat")) and place.get("id"):
            with response(
                root + "/find",
                {
                    "q": place.get("address", q),
                    "id": place["id"],
                    "type": place.get("type", "portal"),
                },
                timeout=5,
                attempts=1,
            ) as handle:
                point = json.load(handle)
            if isinstance(point, dict):
                place.update({key: point.get(key) for key in ("lng", "lat")})
    return raw


NEARBY_KINDS = {
    "salud": lambda row: row["kind"] == "health"
    and row["label"].startswith(("Centro de salud ·", "Consultorio de atención primaria ·")),
    "farmacia": lambda row: row["kind"] == "pharmacy",
    "mayores": lambda row: row["kind"] == "elderly",
    "biblioteca": lambda row: row["kind"] == "library"
    and row["source"].startswith("Comunidad de Madrid"),
}


@app.get("/api/nearby")
def nearby(
    kind: Literal["salud", "farmacia", "mayores", "biblioteca"],
    lon: float = Query(ge=-4, le=-3),
    lat: float = Query(ge=40, le=41),
    n: int = Query(default=3, ge=1, le=8),
):
    """Destinos de los registros de la Comunidad más cercanos en línea recta."""
    city = app.state.city
    x, y = TO_METERS.transform(lon, lat)
    wanted = NEARBY_KINDS[kind]
    found = []
    for k in (40, 200, 1000, len(city.pois)):
        distances, indices = city.poi_tree.query((x, y), k=min(k, len(city.pois)))
        found = [
            (d, city.pois[i])
            for d, i in zip(distances, indices)
            if wanted(city.pois[i])
        ]
        if len(found) >= n:
            break
    return {
        "results": [
            city.poi_output(row) | {"straightM": round(float(d))} for d, row in found[:n]
        ]
    }


@app.get("/api/points")
def points(w: float, s: float, e: float, n: float):
    lower = TO_METERS.transform(w, s)
    upper = TO_METERS.transform(e, n)
    x = (lower[0] + upper[0]) / 2
    y = (lower[1] + upper[1]) / 2
    radius = hypot(upper[0] - lower[0], upper[1] - lower[1]) / 2
    city = app.state.city
    if radius > 1500 or radius <= 0:
        return {"features": []}
    ids = city.poi_tree.query_ball_point((x, y), radius)
    return {
        "features": [city.poi_output(city.pois[i]) for i in ids[:700]],
        "truncated": len(ids) > 700,
    }


@app.post("/api/routes")
def routes(request: RouteRequest):
    trip = build_trip(request)
    show, limited = route_set(trip, request, not request.live)
    return {
        "routes": show,
        "limited": limited,
        "alternativeMaxM": trip.practical_limit(),
        "weather": air_at(times(request)) if not request.live else None,
        "version": app.state.city.meta,
        "scenario": request.scenario.model_dump() if request.scenario else None,
    }


def study_route(
    city, place, dest, request, scenario, enforce_rest=True, max_checks=MAX_CHECKS
):
    trip = city.prepare_trip(place, dest, scenario)
    if not trip:
        return None, False
    p = request.preferences
    criteria = limits(request)
    if (criteria.width or criteria.slope) and max(trip.a.offset, trip.b.offset) > 3:
        return None, False
    return trip.solve(
        criteria,
        times(request),
        p.pace,
        "balanced",
        p.rest if enforce_rest else None,
        max_walk=trip.practical_limit(),
        max_checks=max_checks,
    )


def sample_portals(city, x, y, r):
    with city.db_connect() as conn:
        samples = conn.execute(
            """SELECT x,y,section,district FROM portals
                                WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?
                                ORDER BY section,x,y""",
            (x - r, x + r, y - r, y + r),
        ).fetchall()
    groups = {}
    for place in samples:
        dx, dy = place["x"] - x, place["y"] - y
        if hypot(dx, dy) > r:
            continue
        key = (place["section"], int(dx // 75), int(dy // 75))
        groups.setdefault(key, place)
    selected = list(groups.values())
    if len(selected) > 16:
        selected = [
            selected[i] for i in np.linspace(0, len(selected) - 1, 16, dtype=int)
        ]
    return selected


@app.post("/api/study")
def study(request: StudyRequest):
    city = app.state.city
    build_trip(request)
    x, y = TO_METERS.transform(request.origin.lon, request.origin.lat)
    improvement_x, improvement_y = TO_METERS.transform(
        request.scenario.lon, request.scenario.lat
    )
    r = request.radiusM
    if hypot(improvement_x - x, improvement_y - y) > r:
        raise HTTPException(
            422,
            "La intervención está fuera del radio de estudio. Amplía el radio o cambia la salida.",
        )
    population, older = app.state.population
    destination = (request.destination.lon, request.destination.lat)
    rows = []
    for row in sample_portals(city, x, y, r):
        origin = tuple(coordinates((row["x"], row["y"])))
        before, limited_before = study_route(city, origin, destination, request, None)
        after, limited_after = study_route(
            city, origin, destination, request, request.scenario
        )
        metrics = lambda result: (
            None
            if result is None
            else {key: result[key] for key in ("meters", "maxWithoutRest", "sunMin")}
        )
        rows.append(
            {
                "section": row["section"],
                "district": row["district"],
                "sectionResidents": population.get(row["section"]),
                "sectionOlder": (
                    older[row["section"]] if row["section"] in population else None
                ),
                "before": metrics(before),
                "after": metrics(after),
                "limited": limited_before or limited_after,
            }
        )
    completed = [row for row in rows if not row["limited"]]
    paired = [row for row in completed if row["before"] and row["after"]]
    return {
        "rows": rows,
        "sample": len(rows),
        "radiusM": r,
        "version": city.meta,
        "completed": len(completed),
        "newPaths": sum(not row["before"] and bool(row["after"]) for row in completed),
        "lostPaths": sum(bool(row["before"]) and not row["after"] for row in completed),
        "reducedRestPaths": sum(
            row["after"]["maxWithoutRest"] < row["before"]["maxWithoutRest"]
            for row in paired
        ),
        "reducedSunPaths": sum(
            row["after"]["sunMin"] is not None
            and row["before"]["sunMin"] is not None
            and row["after"]["sunMin"] < row["before"]["sunMin"]
            for row in paired
        ),
    }


@app.post("/api/bank-plan")
def bank_plan(request: BankPlanRequest):
    if request.preferences.rest is None:
        raise HTTPException(
            422, "Fija un máximo de metros sin descanso para recomendar bancos."
        )
    build_trip(request)
    city = app.state.city
    center = TO_METERS.transform(request.origin.lon, request.origin.lat)
    destination = (request.destination.lon, request.destination.lat)

    def evaluate(origin, scenario, enforce_rest=True):
        return study_route(
            city,
            origin,
            destination,
            request,
            scenario,
            enforce_rest=enforce_rest,
            max_checks=SEARCH_BUDGET,
        )

    def improvement(dock):
        lon, lat = coordinates(dock.xy)
        return Improvement(kind="bench", lon=lon, lat=lat)

    return compare_banks(
        city,
        sample_portals(city, *center, request.radiusM),
        center,
        request.radiusM,
        datetime.fromtimestamp(times(request), LOCAL),
        request.preferences.rest,
        app.state.population,
        app.state.footfall,
        evaluate,
        improvement,
    )


if front.is_dir():
    app.mount("/", StaticFiles(directory=front, html=True), name="web")
