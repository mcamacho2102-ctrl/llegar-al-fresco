"""Prueba de aceptación contra la aplicación instalada localmente."""

import json
from pathlib import Path
import sqlite3
import sys
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8768"
DB = Path(__file__).resolve().parent.parent / "datos" / "ciudad" / "lugares.sqlite"


def api(path, query=None):
    payload = json.dumps(query).encode() if query is not None else None
    with urlopen(
        Request(
            BASE + "/api/" + path, payload, headers={"Content-Type": "application/json"}
        ),
        timeout=120,
    ) as result:
        return json.load(result)


def place(label, at=None):
    filters = {"q": label}
    if at:
        filters["at"] = at
    return api("addresses?" + urlencode(filters))["results"]


def position(pair):
    return dict(zip(("lon", "lat"), pair))


def check_stairs(departure):
    origin = place("Calle de los Mancebos 3")[0]
    destination = place("Calle de Segovia 16")[0]
    request = {
        "origin": position(origin["coordinates"]),
        "destination": position(destination["coordinates"]),
        "departure": departure,
    }
    permit = api(
        "routes", request | {"preferences": {"rest": None, "avoidStairs": False}}
    )
    avoid = api(
        "routes", request | {"preferences": {"rest": None, "avoidStairs": True}}
    )
    barrier = "Escaleras cartografiadas"
    assert permit["routes"] and barrier in permit["routes"][0]["barriers"]
    assert avoid["routes"] and all(
        barrier not in route["barriers"] for route in avoid["routes"]
    )
    assert avoid["routes"][0]["meters"] > permit["routes"][0]["meters"]
    print(
        f'Escaleras: {permit["routes"][0]["meters"]} m permitiéndolas, '
        f'{avoid["routes"][0]["meters"]} m evitándolas.',
        flush=True,
    )


def check_bank_plan(request):
    query = request | {"radiusM": 500}
    plan = api("bank-plan", query)
    assert 3 <= plan["sitesTested"] <= 12
    assert 0 < plan["completed"] <= plan["sample"] <= 16
    assert plan["olderInSampleSections"] > 0
    candidates = plan["options"]
    assert len(candidates) == 3 and len({row["id"] for row in candidates}) == 3
    assert candidates[0]["newPaths"] > 0
    assert [row["newPaths"] for row in candidates] == sorted(
        (row["newPaths"] for row in candidates), reverse=True
    )
    assert any(
        row["kind"] == "permanent" and row["count"] is not None and row["days"] > 0
        for row in plan["footfall"]
    )
    assert any(
        row["kind"] == "campaign" and "133" in row["label"] for row in plan["footfall"]
    )
    assert all(
        row["footfall"] is None or row["footfall"]["kind"] == "permanent"
        for row in candidates
    )
    manual = api("study", query | {"scenario": candidates[0]["scenario"]})
    assert manual["sample"] == plan["sample"]
    if manual["completed"] == plan["completed"] == plan["sample"]:
        assert manual["newPaths"] == candidates[0]["newPaths"]
    small = api("bank-plan", request | {"radiusM": 100})
    assert small["footfall"] == []
    try:
        api("bank-plan", request | {"preferences": {"rest": None}})
    except HTTPError as error:
        assert error.code == 422
    else:
        raise AssertionError("El análisis debe exigir un límite de descanso.")
    print(
        f'Bancos: {plan["sitesTested"]} ubicaciones evaluadas, '
        f'{candidates[0]["newPaths"]} rutas compatibles adicionales en la primera '
        f'y {len(plan["footfall"])} puntos de aforo en el entorno.',
        flush=True,
    )


def main():
    info = api("info")
    assert info["version"]["districts"] == 21 and info["benchConnections"] > 50_000
    with sqlite3.connect(DB) as db:
        portal_samples = db.execute(
            "SELECT district,min(label) FROM portals GROUP BY district"
        ).fetchall()
    for district, label in portal_samples:
        assert any(
            row.get("district") == district and row["label"] == label
            for row in place(label)
        ), (district, label)
    print("21 distritos: un portal real encontrado en cada uno.", flush=True)
    assert place("Biblioteca Pedro Salinas")[0]["kind"] == "library"
    assert place("CentroCentro", "2026-07-04T14:00")[0]["kind"] == "refuge"
    assert not any(
        row["kind"] == "refuge" for row in place("CentroCentro", "2026-11-19T14:00")
    )
    assert any(
        row["kind"] == "health" for row in place("Hospital general Arturo Soria")
    )
    origin = place("Plaza Virgen de la Paloma 1")[0]
    destination = place("Biblioteca Pedro Salinas")[0]
    request = {
        "origin": position(origin["coordinates"]),
        "destination": position(destination["coordinates"]),
        "departure": "2025-07-01T14:00",
        "preferences": {"rest": 200},
    }
    start = perf_counter()
    check_stairs(request["departure"])
    before = api("routes", request)
    assert before["weather"]["temperatureC"] == 33.6
    assert any(not row["fitsRest"] and not row["rests"] for row in before["routes"])
    comfort = next(row for row in before["routes"] if row["fitsRest"])
    assert (
        comfort["coverage"]["slope"] > 60
        and comfort["rests"]
        and comfort["sunMin"] is not None
    )
    assert any(row["kind"] == "drinking_water" for row in comfort["nearbyServices"])
    scenario = {"lon": -3.7103549, "lat": 40.4096198, "kind": "bench"}
    after = api("routes", request | {"scenario": scenario})
    proposed = next(row for row in after["routes"] if row["fitsRest"])
    assert (
        proposed["maxWithoutRest"] < comfort["maxWithoutRest"]
        and proposed["meters"] < comfort["meters"]
    )
    assert any(row["simulated"] for row in proposed["rests"])
    assert before["routes"] == api("routes", request)["routes"]
    short = api("routes", request | {"preferences": {"rest": 50}})
    assert not short["limited"] and not any(row["fitsRest"] for row in short["routes"])
    with_rest = api("routes", request | {"live": True, "initialSinceRest": 10})
    assert with_rest["routes"] and with_rest["routes"][0]["fitsRest"]
    print(
        f'Ruta piloto: {comfort["meters"]} → {proposed["meters"]} m; máximo sin descanso {comfort["maxWithoutRest"]} → {proposed["maxWithoutRest"]} m.',
        flush=True,
    )
    study = api("study", request | {"scenario": scenario, "radiusM": 100})
    assert 0 < study["sample"] <= 16 and any(
        row["sectionOlder"] is not None for row in study["rows"]
    )
    assert study["newPaths"] + study["reducedRestPaths"] > 0
    shade = api(
        "study", request | {"scenario": scenario | {"kind": "shade"}, "radiusM": 100}
    )
    assert shade["sample"] == study["sample"]
    assert [row["section"] for row in shade["rows"]] == [
        row["section"] for row in study["rows"]
    ]
    print(
        f'Estudio municipal reproducible: {study["completed"]}/{study["sample"]} orígenes con cálculo concluido.',
        flush=True,
    )
    print(f"Secuencia de rutas y escenarios: {perf_counter()-start:.1f} s.", flush=True)

    check_bank_plan(request)


if __name__ == "__main__":
    main()
