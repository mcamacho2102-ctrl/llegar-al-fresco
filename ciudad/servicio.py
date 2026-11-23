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
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ciudad.fuentes import AEMET, RAW, ROOT, response
from ciudad.motor import MAX_CHECKS, MAX_CONNECT, Madrid, Limits, TO_METERS, coordinates, is_primary_care, normal
from ciudad.aforos import CAMPAIGN_SOURCE, PERMANENT_SOURCE, read_footfall
from ciudad.priorizar import SEARCH_BUDGET, compare_banks
from ciudad.uso import Registro

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
    rest: Optional[int] = Field(default=200, ge=30, le=2000)
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
    # Registro anónimo para el informe municipal (ver ciudad/uso.py)
    purpose: Optional[Literal["salud", "farmacia", "mayores", "biblioteca", "direccion"]] = None
    register: bool = True


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
    with app.state.city.db_connect() as conn:
        app.state.portals = conn.execute("SELECT count(*) FROM portals").fetchone()[0]
    app.state.registro = Registro(app.state.city)
    demo = RAW / "uso" / "consultas-demo.sqlite"
    app.state.demo = Registro(app.state.city, demo) if demo.exists() else None
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


@app.exception_handler(RequestValidationError)
async def friendly_validation(request: Request, exc: RequestValidationError):
    """Traduce los errores de validación a mensajes comprensibles."""
    fields = {str(part) for error in exc.errors() for part in error.get("loc", ())}
    if fields & {"origin", "destination", "lon", "lat"}:
        message = "Ese punto está fuera de la zona que cubre la aplicación (Madrid capital)."
    elif "departure" in fields:
        message = "La fecha u hora de salida no es válida."
    elif "rest" in fields:
        message = "El límite sin descanso debe estar entre 30 m y 2 km."
    else:
        message = "Revisa los datos de la consulta."
    return JSONResponse({"detail": message, "errors": jsonable_encoder(exc.errors())}, status_code=422)
front = ROOT / "web" / ".build"

# Límite sencillo de llamadas a la API por IP para una demo pública.
# Desactivado si LIMITE_PETICIONES=0. Detrás de un proxy se usa la IP que este reenvía.
RATE = int(os.environ.get("LIMITE_PETICIONES", "600"))
_calls = defaultdict(deque)


CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://tiles.openfreemap.org",
        "font-src 'self' data: https://tiles.openfreemap.org",
        "connect-src 'self' https://tiles.openfreemap.org",
        "worker-src 'self' blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    response.headers.setdefault("Content-Security-Policy", CSP)
    return response


# Detrás de Fly.io (o con CONFIAR_PROXY=1) se usa la IP que reenvía el proxy; si no, la
# de la conexión, para que nadie pueda saltarse el límite con una cabecera falsa.
TRUST_PROXY = os.environ.get("CONFIAR_PROXY") == "1" or "FLY_APP_NAME" in os.environ
HEAVY = {"/api/bank-plan", "/api/study"}  # cálculos de varios segundos
HEAVY_RATE = int(os.environ.get("LIMITE_PETICIONES_PESADAS", "20"))
_heavy_calls = defaultdict(deque)


def client_ip(request):
    if TRUST_PROXY:
        forwarded = request.headers.get("fly-client-ip") or request.headers.get(
            "x-forwarded-for", ""
        ).split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "?"


def over_limit(calls, client, limit, now):
    window = calls[client]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        return True
    window.append(now)
    return False


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if RATE and path.startswith("/api/"):
        client = client_ip(request)
        now = monotonic()
        blocked = over_limit(_calls, client, RATE, now) or (
            path in HEAVY and over_limit(_heavy_calls, client, HEAVY_RATE, now)
        )
        if len(_calls) > 5000:  # limpieza: IPs sin actividad en el último minuto
            for table in (_calls, _heavy_calls):
                for key in [k for k, w in table.items() if not w or now - w[-1] > 60]:
                    del table[key]
        if blocked:
            return JSONResponse(
                {"detail": "Demasiadas consultas seguidas. Espera un minuto."},
                status_code=429,
            )
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
        raise HTTPException(422, unreachable_message(city, request))
    return trip


def unreachable_message(city, request):
    """Explica cuál de los dos extremos falla y por qué."""
    ends = (("La salida", request.origin), ("La llegada", request.destination))
    for name, place in ends:
        if not city.inside(place.lon, place.lat):
            return (
                f"{name} está fuera de Madrid capital. Por ahora la aplicación "
                "solo cubre el municipio de Madrid."
            )
    for name, place in ends:
        if city.locate(place.lon, place.lat) is None:
            return (
                f"{name} está a más de {MAX_CONNECT} m de cualquier calle o camino "
                "del mapa (puede ser una urbanización muy nueva o el interior de "
                "un recinto). Marca en el mapa un punto en la calle más cercana."
            )
    return "No se ha podido preparar el recorrido. Prueba con otro punto cercano."


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


STATION = ("28", "80", "3")  # Majadahonda, red regional de calidad del aire
STATION_NAME = "Majadahonda"


@lru_cache(maxsize=1)
def observed_temperatures():
    """Temperaturas horarias validadas (magnitud 83) de la red regional: histórico 2025
    y mes en curso. Clave: (AAAA-MM-DD, hora 0–23)."""
    readings = {}
    for name in ("calidad_aire_datos_meteo_historico.csv", "calidad_aire_datos_meteo_mes.csv"):
        source = RAW / name
        if not source.is_file():
            continue
        with source.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file, delimiter=";"):
                if (row["provincia"], row["municipio"].lstrip("0"), row["estacion"]) != STATION:
                    continue
                if row["magnitud"] != "83":
                    continue
                day = f'{row["ano"]}-{int(row["mes"]):02d}-{int(row["dia"]):02d}'
                following = (datetime.fromisoformat(day) + timedelta(days=1)).strftime("%Y-%m-%d")
                for hour in range(1, 25):
                    if row.get(f"v{hour:02d}") == "V":
                        # h24 es la medida que cierra el día: las 00 h del día siguiente.
                        key = (following, 0) if hour == 24 else (day, hour)
                        try:
                            readings[key] = float(row[f"h{hour:02d}"].replace(",", "."))
                        except (TypeError, ValueError):
                            continue
    return readings


def summer_reading():
    value = observed_temperatures().get(("2025-07-01", 14))
    return None if value is None else observation("2025-07-01", 14, value)


def observation(day, hour, value):
    return {
        "temperatureC": value,
        "at": f"{day}T{hour:02d}:00",
        "issued": None,
        "source": f"Comunidad de Madrid · Red de Calidad del Aire · estación de {STATION_NAME} · observado el {day} a las {hour} h",
    }


def air_at(epoch):
    moment = datetime.fromtimestamp(epoch, LOCAL)
    observed = observed_temperatures().get((moment.strftime("%Y-%m-%d"), moment.hour))
    if observed is not None and moment <= datetime.now(LOCAL):
        return observation(moment.strftime("%Y-%m-%d"), moment.hour, observed)
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
    styles = (
        [
            ("distance", "Más corta"),
            ("comfort", "Menos esfuerzo"),
            ("shade", "Prioriza sombra"),
        ]
        if full
        else [("comfort", "Con descansos")]
    )
    if full and trip.straight_m() > TOO_FAR_M:
        styles = [("distance", "Más corta")]  # a pie no es razonable: solo el camino directo
    seen = set()
    routes = []
    limited = False
    shortest_m = None
    impossible = False
    for style, label in styles:
        limit = criteria.rest if style != "distance" else None
        if style == "shade" and impossible:
            # Sombra solo cambia el coste, no qué caminos cumplen el límite: si con
            # «menos esfuerzo» no hay ninguno, tampoco lo habrá aquí.
            continue
        result, paused = trip.solve(
            criteria,
            date,
            p.pace,
            style,
            limit,
            request.initialSinceRest,
            max_walk=None if style == "distance" else trip.walk_limit(shortest_m),
        )
        limited |= paused
        if not result:
            impossible |= style == "comfort" and not paused
            continue
        if style == "distance":
            shortest_m = result["meters"]
            # Sin paradas, maxWithoutRest es la longitud entera: se informa del tramo
            # real más largo entre bancos que hay junto a este camino.
            result["maxGapM"] = round(app.state.registro.longest_gap(result), 1)
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
        if full and style == "distance" and shortest_m > TOO_FAR_WALK_M:
            break  # a pie es demasiado largo: solo el camino directo, sin más búsquedas
    if not full and not routes:
        # Navegando: si ya no hay forma de respetar el límite, se guía por el camino directo.
        result, paused = trip.solve(
            criteria._replace(rest=None), date, p.pace, "distance", None, request.initialSinceRest
        )
        limited |= paused
        if result:
            result["nearbyServices"] = list(trip.city.nearby_services(result["geometry"]["coordinates"]))
            result.update(label="Camino directo", style="distance", fitsRest=False)
            routes.append(result)
    if full and criteria.rest is not None and routes and not any(r["fitsRest"] for r in routes) \
            and trip.straight_m() <= TOO_FAR_M and (shortest_m or 0) <= TOO_FAR_WALK_M:
        closest = closest_route(trip, criteria, date, p.pace, request.initialSinceRest, routes)
        if closest:
            closest["nearbyServices"] = list(
                trip.city.nearby_services(closest["geometry"]["coordinates"])
            )
            closest["label"] = "La que menos anda sin sentarse"
            closest["style"] = "closest"
            closest["fitsRest"] = False
            routes.append(closest)
    return routes, limited


def closest_route(trip, criteria, date, pace, initial, routes, step=10, budget=40000, probes=5):
    """Cuando ninguna ruta respeta el límite, busca la que minimiza el tramo más largo
    sin banco: el menor límite L ≥ el pedido para el que existe ruta (búsqueda binaria).
    Como mucho `probes` intentos: en el servidor cada uno cuesta unos segundos."""
    low = criteria.rest
    high = min(r["maxWithoutRest"] for r in routes)
    best = None
    while high - low > step and probes > 0:
        probes -= 1
        middle = int((low + high) / 2)
        result, _ = trip.solve(
            criteria._replace(rest=middle),
            date,
            pace,
            "comfort",
            middle,
            initial,
            max_walk=trip.walk_limit(min(r["meters"] for r in routes)),
            max_checks=budget,
        )
        if result:
            best = result
            high = min(middle, result["maxWithoutRest"])
        else:
            low = middle
    if best is None or best["maxWithoutRest"] >= min(r["maxWithoutRest"] for r in routes) - 1:
        return None  # no mejora a lo que ya se muestra
    best["bestRestM"] = round(best["maxWithoutRest"])
    return best


def informe_fuente(demo):
    if demo:
        if app.state.demo is None:
            raise HTTPException(404, "No hay datos de demostración. Ejecuta python -m ciudad.uso_demo.")
        return app.state.demo
    return app.state.registro


@app.get("/api/informe")
def informe(demo: bool = False, dias: Optional[int] = Query(default=None, ge=1, le=3650)):
    data = informe_fuente(demo).report(days=dias)
    data["demo"] = demo
    data["hayDemo"] = app.state.demo is not None
    return data


@app.get("/api/informe.csv")
def informe_csv(demo: bool = False, dias: Optional[int] = Query(default=None, ge=1, le=3650)):
    from fastapi.responses import Response

    return Response(
        informe_fuente(demo).report_csv(days=dias),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=huecos-sin-banco.csv"},
    )


@app.get("/api/info")
def info():
    city = app.state.city
    return {
        "version": city.meta,
        "sources": SOURCE_FILES,
        "networkEdges": len(city.a),
        "benchConnections": sum(map(len, city.rests.values())),
        "portals": app.state.portals,
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


TOO_FAR_M = 3000  # más de 3 km en línea recta: se recomienda transporte público
TOO_FAR_WALK_M = 4000  # o más de 4 km andando (p. ej. hay que rodear una autovía o las vías)


@app.get("/api/dentro")
def dentro(lon: float = Query(ge=-180, le=180), lat: float = Query(ge=-90, le=90)):
    """¿Está el punto dentro del área que cubre la aplicación (Madrid capital)? Y, si lo
    está, ¿hay una calle o camino de la red a menos de MAX_CONNECT m para empezar?"""
    city = app.state.city
    inside = -4 <= lon <= -3 and 40 <= lat <= 41 and city.inside(lon, lat)
    out = {"dentro": inside, "red": inside and city.locate(lon, lat) is not None}
    if inside and not out["red"]:
        # Hay portales a los que el mapa peatonal no llega del todo (p. ej. naves de un
        # polígono): se propone el punto del camino más cercano si está a ≤ CALLE_CERCA_M.
        dock = city.locate(lon, lat, reach=CALLE_CERCA_M)
        if dock is not None:
            out["calle"] = {"coordinates": coordinates(dock.xy), "distanceM": round(float(dock.offset))}
    return out


CALLE_CERCA_M = 300


@app.get("/api/cerca")
def cerca(lon: float = Query(ge=-180, le=180), lat: float = Query(ge=-90, le=90)):
    """Portal del callejero más cercano a un punto marcado en el mapa (≤ 80 m)."""
    city = app.state.city
    if not city.inside(lon, lat):
        return {"label": None}
    x, y = TO_METERS.transform(lon, lat)
    reach = 80
    with city.db_connect() as conn:
        rows = conn.execute(
            "SELECT label,x,y FROM portals WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?",
            (x - reach, x + reach, y - reach, y + reach),
        ).fetchall()
    best = min(rows, key=lambda r: hypot(r["x"] - x, r["y"] - y), default=None)
    if best is None or hypot(best["x"] - x, best["y"] - y) > reach:
        return {"label": None}
    return {"label": "Junto a " + best["label"], "distanceM": round(hypot(best["x"] - x, best["y"] - y))}


NEARBY_KINDS = {
    "salud": is_primary_care,
    "farmacia": lambda row: row["kind"] == "pharmacy",
    "mayores": lambda row: row["kind"] == "elderly",
    "biblioteca": lambda row: row["kind"] == "library"
    and row["source"].startswith("Comunidad de Madrid"),
}


@app.get("/api/nearby")
def nearby(
    kind: Literal["salud", "farmacia", "mayores", "biblioteca"],
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    n: int = Query(default=3, ge=1, le=8),
):
    """Destinos de los registros de la Comunidad más cercanos andando.

    Se toman los más cercanos en línea recta a los que se puede llegar desde la red
    peatonal y se ordenan por el camino a pie más corto: una biblioteca a 700 m en
    línea recta puede quedar a 7 km andando si hay que rodear una autovía."""
    city = app.state.city
    if not city.inside(lon, lat):
        raise HTTPException(
            422,
            "Ese punto está fuera de Madrid capital. Por ahora la aplicación solo cubre el municipio de Madrid.",
        )
    x, y = TO_METERS.transform(lon, lat)
    wanted = NEARBY_KINDS[kind]
    pool = max(n, NEARBY_POOL)
    found = []
    for k in (40, 200, 1000, len(city.pois)):
        distances, indices = city.poi_tree.query((x, y), k=min(k, len(city.pois)))
        found = [(d, city.pois[i]) for d, i in zip(distances, indices) if wanted(city.pois[i])]
        if len(found) >= 3 * pool:
            break
    origin = city.locate(lon, lat)
    out = []
    for d, row in found:
        place = city.poi_output(row) | {"straightM": round(float(d))}
        if city.locate(*place["coordinates"]) is None:
            continue  # sin calle o camino cerca (p. ej. dentro de la terminal del aeropuerto)
        if origin is not None:
            place["walkM"] = walking_m((lon, lat), place["coordinates"])
        out.append(place)
        if len(out) >= pool:
            break
    out.sort(key=lambda r: (r.get("walkM") is None, r.get("walkM") or 0, r["straightM"]))
    return {"results": out[:n]}


NEARBY_POOL = 5  # candidatos que se miden andando antes de elegir los n más cercanos


def walking_m(origin, destination):
    """Longitud del camino a pie más corto, sin más condiciones (None si no se encuentra)."""
    trip = app.state.city.prepare_trip(origin, destination, None)
    if trip is None:
        return None
    result, _ = trip.solve(Limits(), datetime.now(LOCAL).timestamp(), 1.0, "distance", None, 0, max_checks=40000)
    return result["meters"] if result else None


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
    # Con más de 700 puntos, primero todo lo que no es banco (fuentes, aseos, centros…)
    # y después bancos repartidos por igual en toda la vista, sin dejar media vista vacía.
    others = [i for i in ids if city.pois[i]["kind"] != "bench"]
    benches = [i for i in ids if city.pois[i]["kind"] == "bench"]
    if len(others) > POINTS_OTHERS:
        others = spread(others, POINTS_OTHERS)
    chosen = others + spread(benches, POINTS_MAX - len(others))
    return {
        "features": [city.poi_output(city.pois[i]) for i in chosen],
        "truncated": len(chosen) < len(ids),
    }


POINTS_MAX = 700
POINTS_OTHERS = 350


def spread(items, quota):
    """Muestra uniforme (orden espacial del árbol) de hasta `quota` elementos."""
    if quota <= 0:
        return []
    if len(items) <= quota:
        return items
    step = len(items) / quota
    return [items[int(k * step)] for k in range(quota)]


@app.post("/api/routes")
def routes(request: RouteRequest):
    trip = build_trip(request)
    show, limited = route_set(trip, request, not request.live)
    relaxed = []
    p = request.preferences
    if not show and not request.live and (p.width or p.slope):
        # Ningún camino cumple el ancho o la cuesta pedidos: se muestra el mejor sin
        # esos filtros y se avisa de qué no se ha podido respetar.
        relaxed = [name for name, value in (("width", p.width), ("slope", p.slope)) if value]
        lenient = request.model_copy(
            update={"preferences": p.model_copy(update={"width": None, "slope": None})}
        )
        show, limited = route_set(trip, lenient, True)
    app.state.registro.register(request, show)
    walk_m = min((r["meters"] for r in show if r["style"] == "distance"), default=0)
    return {
        "routes": show,
        "relaxed": relaxed,
        "tooFar": trip.straight_m() > TOO_FAR_M or walk_m > TOO_FAR_WALK_M,
        "straightM": round(trip.straight_m()),
        "walkM": walk_m or None,
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
