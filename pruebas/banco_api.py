#!/usr/bin/env python3
"""Banco de pruebas de la API (solo biblioteca estándar).

    python3 pruebas/banco_api.py [http://127.0.0.1:8768]

Cada prueba imprime OK / FALLO / AVISO con el detalle, y al final un resumen.
Ninguna consulta cuenta en el informe de uso (register=false).
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8768").rstrip("/")
RESULTS = []

SOL = (-3.7038, 40.4168)
PALOMA = None  # se rellenan buscando
GETAFE = (-3.7327, 40.3057)
BARCELONA = (2.1734, 41.3851)
BARAJAS = (-3.5776, 40.4747)
VILLAVERDE = (-3.7019, 40.3466)
EL_PARDO = (-3.7710, 40.5197)


def call(path, body=None, method=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data, {"Content-Type": "application/json"}, method=method)
    t = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
            out = json.loads(raw) if "json" in ctype else raw.decode()
            return r.status, out, time.perf_counter() - t
    except HTTPError as e:
        try:
            out = json.loads(e.read())
        except Exception:
            out = None
        return e.code, out, time.perf_counter() - t


def record(area, name, status, detail=""):
    RESULTS.append((area, name, status, detail))
    print(f"[{status:5}] {area} · {name}{' · ' + detail if detail else ''}", flush=True)


def route(origin, destination, **extra):
    body = {
        "origin": {"lon": origin[0], "lat": origin[1]},
        "destination": {"lon": destination[0], "lat": destination[1]},
        "departure": extra.pop("departure", "2026-07-01T10:00:00"),
        "register": False,
    }
    prefs = extra.pop("preferences", None)
    if prefs is not None:
        body["preferences"] = prefs
    body.update(extra)
    return call("/api/routes", body)


def search(q):
    return call("/api/addresses?" + urlencode({"q": q}))


def first(q, kind=None):
    code, data, _ = search(q)
    if code != 200 or not data["results"]:
        return None
    rows = [r for r in data["results"] if not kind or r["kind"] == kind] or data["results"]
    return tuple(rows[0]["coordinates"])


def main():
    global PALOMA
    # ---------- Disponibilidad ----------
    code, info, t = call("/api/info")
    record("Servidor", "Responde /api/info", "OK" if code == 200 else "FALLO", f"{t*1000:.0f} ms")
    code, page, t = call("/")
    record("Servidor", "Sirve la web", "OK" if code == 200 and "<div id=\"root\"" in page else "FALLO", f"{t*1000:.0f} ms")
    for asset in ("/municipios.geojson", "/impacto.json", "/manifest.webmanifest", "/sw.js"):
        code, _, _ = call(asset)
        record("Servidor", f"Recurso {asset}", "OK" if code == 200 else "FALLO", str(code))

    # ---------- Buscador ----------
    PALOMA = first("Plaza Virgen De La Paloma, 1")
    pedro = first("Biblioteca Pedro Salinas")
    record("Buscador", "Dirección del ejemplo", "OK" if PALOMA else "FALLO")
    cases = {
        "Calle Mayor 1": True,
        "calle mayor, 1": True,
        "CALLE DE ALCALÁ 100": True,
        "calle de alcala 100": True,
        "c/ toledo 46": True,
        "Avda. de América 2": True,
        "Paseo de la Castellana 100": True,
        "Gran Vía 1": True,
        "Hospital Gregorio Marañón": True,
        "Gregorio Marañón": True,
        "12 de Octubre": True,
        "centro de salud segovia": True,
        "centro de salud": True,
        "farmacia": True,
        "biblioteca": True,
        "centro de dia": True,
        "28005": False,
        "Calle Mallor 1": False,
        "': OR 1=1 --": False,
        '"*()': False,
        "🙂🙂🙂": False,
        "a" * 120: False,
    }
    for q, expected in cases.items():
        code, data, t = search(q)
        n = len(data["results"]) if code == 200 and data else 0
        label = q if len(q) < 40 else q[:20] + "…"
        if code >= 500:
            record("Buscador", f"«{label}»", "FALLO", f"error {code}")
        elif expected and n == 0:
            record("Buscador", f"«{label}»", "FALLO", "sin resultados")
        elif t > 1.0:
            record("Buscador", f"«{label}»", "AVISO", f"{n} resultados en {t:.1f} s (lento)")
        else:
            top = data["results"][0]["label"][:45] if n else "-"
            record("Buscador", f"«{label}»", "OK", f"{n} resultados · {top}")
    for q in ("", "ab"):
        code, _, _ = search(q)
        record("Buscador", f"Texto demasiado corto «{q}»", "OK" if code in (200, 422) else "FALLO", str(code))

    # ---------- Rutas básicas ----------
    code, data, t = route(PALOMA, pedro, departure="2025-07-01T14:00:00")
    if code == 200:
        styles = {r["style"]: r for r in data["routes"]}
        ok = styles.get("distance", {}).get("meters") == 238 and styles.get("comfort", {}).get("fitsRest")
        record("Rutas", "Ejemplo de la demo", "OK" if ok else "FALLO",
               f"{[(r['style'], r['meters'], round(r['maxWithoutRest'])) for r in data['routes']]} · {t:.2f} s")
        w = data.get("weather")
        record("Rutas", "Temperatura histórica 1/7/2025 14 h", "OK" if w and abs(w["temperatureC"] - 33.6) < 0.05 else "FALLO", str(w and w["temperatureC"]))
    else:
        record("Rutas", "Ejemplo de la demo", "FALLO", str(data))

    code, data, t = route(PALOMA, PALOMA)
    record("Rutas", "Mismo origen y destino", "OK" if code in (200, 422) else "FALLO",
           f"{code} · {data.get('detail') if isinstance(data, dict) and 'detail' in data else [r['meters'] for r in data['routes']] if code == 200 else ''}")

    for name, a, b in (("Barajas → Villaverde (≈17 km)", BARAJAS, VILLAVERDE), ("El Pardo → Sol", EL_PARDO, SOL)):
        code, data, t = route(a, b)
        if code == 200 and data["routes"]:
            status = "OK" if t < 10 and data.get("tooFar") else "AVISO"
            record("Rendimiento", name, status, f"{t:.1f} s · {[(r['style'], r['meters']) for r in data['routes']]}")
        else:
            record("Rendimiento", name, "AVISO", f"{code} {data.get('detail') if isinstance(data, dict) else ''} · {t:.1f} s")

    # ---------- Fuera de cobertura y validación ----------
    for name, a in (("Salida en Getafe", GETAFE), ("Salida en Barcelona", BARCELONA)):
        code, data, _ = route(a, SOL)
        detail = data.get("detail") if isinstance(data, dict) else data
        good = code == 422 and isinstance(detail, str) and "Madrid" in detail
        record("Validación", name, "OK" if good else "FALLO", f"{code} · {str(detail)[:110]}")
    code, data, _ = route((-3.7, 40.4), SOL, departure="mañana")
    record("Validación", "Fecha no válida", "OK" if code == 422 else "FALLO", str(code))
    for rest in (29, 2001):
        code, _, _ = route(PALOMA, pedro, preferences={"rest": rest})
        record("Validación", f"Límite fuera de rango ({rest} m)", "OK" if code == 422 else "FALLO", str(code))
    for rest in (30, 2000, None):
        code, data, t = route(PALOMA, pedro, preferences={"rest": rest})
        record("Rutas", f"Límite {rest} m", "OK" if code == 200 and data["routes"] else "FALLO", f"{t:.2f} s · {[r['style'] for r in data['routes']] if code == 200 else data}")

    # ---------- Opciones avanzadas ----------
    combos = [
        ("Escaleras permitidas", {"rest": 200, "avoidStairs": False}),
        ("Ancho ≥ 1,5 m", {"rest": 200, "width": 1.5}),
        ("Ancho ≥ 1,8 m + cuesta ≤ 4 %", {"rest": 200, "width": 1.8, "slope": 4}),
        ("Cuesta ≤ 6 %", {"rest": 200, "slope": 6}),
        ("Ritmo 0,4 (muy lento)", {"rest": 200, "pace": 0.4}),
        ("Ritmo 1,7", {"rest": 200, "pace": 1.7}),
    ]
    for name, prefs in combos:
        code, data, t = route(PALOMA, pedro, preferences=prefs)
        if code == 200 and data["routes"]:
            r = data["routes"][0]
            extra = f" · sin cumplir: {data['relaxed']}" if data.get("relaxed") else ""
            record("Opciones", name, "OK", f"{t:.2f} s · {[(x['style'], x['meters'], x['durationMin']) for x in data['routes']]}{extra}")
        else:
            record("Opciones", name, "FALLO", f"{code} {data}")

    # ---------- Ruta imposible → la mejor posible ----------
    a = first("Calle Del Puerto De La Cruz Verde, 14")
    b = first("centro de salud Antracita", "health")
    code, data, t = route(a, b, preferences={"rest": 100})
    styles = [r["style"] for r in data["routes"]] if code == 200 else []
    record("Rutas", "Sin ruta posible → la mejor posible", "OK" if "closest" in styles else "FALLO", f"{styles} · {t:.1f} s")

    # ---------- Cercanos ----------
    for kind in ("salud", "farmacia", "mayores", "biblioteca"):
        for name, p in (("Sol", SOL), ("Barajas", BARAJAS), ("El Pardo", EL_PARDO)):
            code, data, t = call("/api/nearby?" + urlencode({"kind": kind, "lon": p[0], "lat": p[1], "n": 3}))
            n = len(data["results"]) if code == 200 else 0
            far = data["results"][0]["straightM"] if n else None
            status = "OK" if n == 3 else "FALLO"
            if status == "OK" and far > 1500:
                status = "AVISO"
            record("Cercanos", f"{kind} desde {name}", status, f"el más cercano a {far} m · {t*1000:.0f} ms")
    code, data, _ = call("/api/nearby?kind=salud&lon=2.17&lat=41.38")
    record("Validación", "Cercanos desde Barcelona", "OK" if code == 422 and "Madrid" in str(data) else "FALLO", f"{code} · {str(data)[:90]}")
    code, data, _ = call("/api/dentro?lon=-3.70&lat=40.42")
    record("Validación", "/api/dentro en Sol", "OK" if code == 200 and data["dentro"] else "FALLO")
    code, data, _ = call("/api/dentro?lon=-3.73&lat=40.31")
    record("Validación", "/api/dentro en Getafe", "OK" if code == 200 and not data["dentro"] else "FALLO")
    code, _, _ = call("/api/nearby?kind=bar&lon=-3.7&lat=40.4")
    record("Validación", "Tipo de destino inexistente", "OK" if code == 422 else "FALLO", str(code))

    # ---------- Puntos del mapa ----------
    code, data, _ = call("/api/points?w=-3.72&s=40.41&e=-3.70&n=40.42")
    record("Mapa", "Puntos de una zona pequeña", "OK" if code == 200 and data["features"] else "FALLO", f"{len(data['features']) if code == 200 else code}")
    code, data, _ = call("/api/points?w=-3.9&s=40.3&e=-3.5&n=40.6")
    record("Mapa", "Zona demasiado grande devuelve vacío", "OK" if code == 200 and not data["features"] else "AVISO")

    # ---------- Ayuntamientos ----------
    query = {"origin": {"lon": PALOMA[0], "lat": PALOMA[1]}, "destination": {"lon": pedro[0], "lat": pedro[1]},
             "departure": "2025-07-01T14:00:00", "radiusM": 500, "register": False}
    code, data, t = call("/api/bank-plan", query)
    record("Ayuntamientos", "Buscar ubicaciones para bancos", "OK" if code == 200 and data["options"] else "FALLO", f"{t:.1f} s · {len(data['options']) if code == 200 else data}")
    code, data, t = call("/api/study", {**query, "scenario": {"kind": "bench", "lon": -3.7103549, "lat": 40.4096198}})
    record("Ayuntamientos", "Estudio de un banco", "OK" if code == 200 else "FALLO", f"{t:.1f} s · nuevas rutas {data.get('newPaths') if code == 200 else data}")
    code, data, _ = call("/api/informe?demo=true")
    record("Ayuntamientos", "Informe de demostración", "OK" if code == 200 and data["huecos"] else "FALLO", f"{data['consultas'] if code == 200 else code} consultas")
    code, data, _ = call("/api/informe?demo=true&dias=30")
    record("Ayuntamientos", "Informe filtrado por días", "OK" if code == 200 else "FALLO", f"{data.get('consultas') if code == 200 else code}")
    code, data, _ = call("/api/informe.csv?demo=true")
    record("Ayuntamientos", "CSV de huecos", "OK" if code == 200 and data.startswith("calle,") else "FALLO")

    # ---------- Concurrencia ----------
    def one(_):
        return route(PALOMA, pedro)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(16) as pool:
        out = list(pool.map(one, range(32)))
    total = time.perf_counter() - t0
    errors = [c for c, _, _ in out if c != 200]
    worst = max(t for _, _, t in out)
    record("Rendimiento", "32 rutas a la vez (16 simultáneas)", "OK" if not errors and worst < 8 else "AVISO",
           f"{len(errors)} errores · peor {worst:.1f} s · total {total:.1f} s")

    # ---------- Resumen ----------
    counts = {s: sum(1 for r in RESULTS if r[2] == s) for s in ("OK", "AVISO", "FALLO")}
    print("\nRESUMEN", counts)
    with open("pruebas/resultado_api.json", "w", encoding="utf-8") as f:
        json.dump([dict(zip(("area", "prueba", "estado", "detalle"), r)) for r in RESULTS], f, ensure_ascii=False, indent=1)
    return 1 if counts["FALLO"] else 0


if __name__ == "__main__":
    sys.exit(main())
