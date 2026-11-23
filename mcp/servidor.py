#!/usr/bin/env python3
"""Servidor MCP de «Llegar al fresco» (stdio, solo biblioteca estándar de Python 3.9+).

Permite que un asistente de IA (Claude Desktop, VS Code, Cursor…) responda preguntas
como «¿Cómo llega mi madre de Calle de Toledo 46 a su centro de salud sin caminar más
de 150 m sin sentarse?» usando la API de la aplicación y datos abiertos verificables.

Herramientas:
  buscar_lugar(texto)                                   direcciones y destinos regionales
  ruta_con_descansos(origen, destino, max_sin_descanso) ruta corta frente a ruta con bancos
  bancos_prioritarios(origen, destino, ...)             dónde poner un banco nuevo
  municipios_prioritarios(n, indicador)                 clasificación de los 179 municipios
  impacto_madrid()                                      cifra de impacto por distrito

Configuración (claude_desktop_config.json):
  {"mcpServers": {"llegar-al-fresco": {
      "command": "python3",
      "args": ["/ruta/llegar-al-fresco/mcp/servidor.py"],
      "env": {"LLEGAR_URL": "https://…"}}}}

Prueba sin cliente:  python3 mcp/probar.py
"""

import json
import os
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = os.environ.get("LLEGAR_URL", "http://127.0.0.1:8768").rstrip("/")
PROTOCOL = "2025-06-18"
TIMEOUT = 120


def call(path, payload=None, query=None):
    url = BASE + path + ("?" + urlencode(query) if query else "")
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data,
        headers={"Content-Type": "application/json", "User-Agent": "llegar-al-fresco-mcp"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="ignore")
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        raise ValueError(f"La aplicación respondió {error.code}: {detail}") from None
    except URLError as error:
        raise ValueError(f"No se puede conectar con {BASE}: {error.reason}") from None


def place(text):
    """Primer resultado del buscador para un texto o «lat,lon»."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) == 2:
        try:
            lat, lon = float(parts[0]), float(parts[1])
            return {"label": text, "lon": lon, "lat": lat}
        except ValueError:
            pass
    found = call("/api/addresses", query={"q": text})["results"]
    if not found:
        raise ValueError(f"No encuentro «{text}» en Madrid capital. Prueba con calle y número.")
    best = found[0]
    lon, lat = best["coordinates"]
    return {"label": best["label"], "lon": lon, "lat": lat, "source": best.get("source")}


def buscar_lugar(texto: str):
    results = call("/api/addresses", query={"q": texto})["results"][:8]
    return [
        {
            "nombre": r["label"],
            "tipo": r["kind"],
            "fuente": r.get("source") or r.get("district"),
            "lat": r["coordinates"][1],
            "lon": r["coordinates"][0],
        }
        for r in results
    ]


def request_body(origin, destination, rest, departure):
    return {
        "origin": {"lon": origin["lon"], "lat": origin["lat"]},
        "destination": {"lon": destination["lon"], "lat": destination["lat"]},
        "departure": departure or datetime.now().strftime("%Y-%m-%dT%H:%M:00"),
        "preferences": {"rest": rest, "avoidStairs": True, "pace": 1},
    }


def ruta_con_descansos(origen: str, destino: str, max_sin_descanso: int = 200, salida: str = ""):
    a, b = place(origen), place(destino)
    data = call("/api/routes", request_body(a, b, max_sin_descanso, salida or None))
    routes = []
    for r in data["routes"]:
        routes.append(
            {
                "opcion": r["label"],
                "metros": r["meters"],
                "minutos": r["durationMin"],
                "tramo_mas_largo_sin_banco_m": r["maxWithoutRest"],
                "respeta_el_limite": r["fitsRest"],
                "minutos_al_sol": r.get("sunMin"),
                "pendiente_max_pct": r.get("slopePct"),
                "paradas": [
                    {"banco": s["label"], "a_los_m": s["atM"]}
                    for s in r["rests"]
                    if s.get("action", "rest") == "rest"
                ],
                "fuentes_y_aseos_cerca": [s["label"] for s in r.get("nearbyServices", [])][:4],
            }
        )
    weather = data.get("weather")
    return {
        "origen": a["label"],
        "destino": b["label"],
        "limite_sin_descanso_m": max_sin_descanso,
        "rutas": routes,
        "tiempo": weather,
        "nota": "Bancos municipales operativos del inventario 2026; sombra modelada con edificios y arbolado de OSM. Comprobar sobre el terreno.",
    }


def bancos_prioritarios(origen: str, destino: str, max_sin_descanso: int = 200, radio_m: int = 500):
    a, b = place(origen), place(destino)
    body = request_body(a, b, max_sin_descanso, None) | {"radiusM": radio_m}
    data = call("/api/bank-plan", body)
    return {
        "zona": f"{radio_m} m alrededor de {a['label']}",
        "destino": b["label"],
        "portales_muestreados": data["sample"],
        "ubicaciones_evaluadas": data["sitesTested"],
        "mejores_ubicaciones": [
            {
                "calle": o["label"],
                "lat": o["scenario"]["lat"],
                "lon": o["scenario"]["lon"],
                "rutas_nuevas_que_respetan_el_limite": o["newPaths"],
                "mayores_65_en_secciones_beneficiadas": o.get("olderInNewSections"),
                "fraccion_al_sol": o.get("sunFraction"),
            }
            for o in data["options"]
        ],
    }


def municipios_prioritarios(n: int = 10, indicador: str = "indice"):
    data = call("/municipios.geojson")
    rows = [f["properties"] for f in data["features"]]
    keys = {"indice", "pct65", "mayoresPorCentroSalud", "horas35", "mayores65"}
    if indicador not in keys:
        raise ValueError(f"Indicador no válido. Usa uno de: {', '.join(sorted(keys))}")
    rows.sort(key=lambda r: r.get(indicador) or 0, reverse=True)
    fields = (
        "municipio", "puesto", "indice", "pct65", "mayores65", "centrosSalud",
        "mayoresPorCentroSalud", "centrosMayores", "farmacias", "horas35",
    )
    return {
        "metodo": data["metadata"],
        "municipios": [{k: r.get(k) for k in fields} for r in rows[: max(1, min(n, 179))]],
    }


def impacto_madrid():
    return call("/impacto.json")


TOOLS = {
    "buscar_lugar": (
        buscar_lugar,
        "Busca direcciones de Madrid capital y destinos de los registros de la Comunidad de Madrid "
        "(centros de salud, centros de día y residencias, farmacias, bibliotecas).",
        {"texto": {"type": "string", "description": "Calle y número, o nombre del centro"}},
        ["texto"],
    ),
    "ruta_con_descansos": (
        ruta_con_descansos,
        "Calcula a pie la ruta más corta y la que nunca supera X metros seguidos sin un banco "
        "municipal, con sombra, pendiente, paradas y fuentes cercanas. Origen y destino pueden ser "
        "direcciones, nombres de centros o «lat,lon».",
        {
            "origen": {"type": "string"},
            "destino": {"type": "string"},
            "max_sin_descanso": {"type": "integer", "minimum": 30, "maximum": 2000, "default": 200},
            "salida": {"type": "string", "description": "Fecha y hora local ISO, p. ej. 2025-07-01T14:00:00"},
        },
        ["origen", "destino"],
    ),
    "bancos_prioritarios": (
        bancos_prioritarios,
        "Para planificación municipal: propone dónde instalar un banco nuevo en torno a un origen "
        "para que más portales lleguen a un destino respetando el límite sin descanso.",
        {
            "origen": {"type": "string"},
            "destino": {"type": "string"},
            "max_sin_descanso": {"type": "integer", "default": 200},
            "radio_m": {"type": "integer", "minimum": 100, "maximum": 500, "default": 500},
        },
        ["origen", "destino"],
    ),
    "municipios_prioritarios": (
        municipios_prioritarios,
        "Clasifica los 179 municipios de la Comunidad de Madrid por envejecimiento, mayores por "
        "centro de salud, centros para mayores y horas de calor (≥35 °C), solo con datos regionales.",
        {
            "n": {"type": "integer", "default": 10},
            "indicador": {
                "type": "string",
                "enum": ["indice", "pct65", "mayoresPorCentroSalud", "horas35", "mayores65"],
                "default": "indice",
            },
        },
        [],
    ),
    "impacto_madrid": (
        impacto_madrid,
        "Devuelve la cifra de impacto por distrito: % de trayectos al centro de salud que superan "
        "200 m sin banco, cuántos se arreglan con un rodeo y la sensibilidad a 150 y 300 m.",
        {},
        [],
    ),
}


def tool_list():
    return [
        {
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
        }
        for name, (_, description, props, required) in TOOLS.items()
    ]


def handle(message):
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None  # notificación
    if method == "initialize":
        result = {
            "protocolVersion": message.get("params", {}).get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "llegar-al-fresco", "version": "1.0"},
            "instructions": "Rutas a pie con descansos y sombra en Madrid capital y prioridades regionales. Cita siempre la fuente de los datos.",
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        params = message.get("params", {})
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": f"Herramienta desconocida: {name}"}}
        try:
            output = TOOLS[name][0](**args)
            result = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, indent=1)}], "isError": False}
        except (ValueError, TypeError, KeyError) as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Método no soportado: {method}"}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        reply = handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
