"""Banco de pruebas exhaustivo (bombardeo multi-actor) contra Llegar al fresco.

Simula el uso real y adversarial de todos los interesados:
  1. Personas mayores y familias (búsquedas reales, accesibilidad, GPS en vivo, horarios)
  2. Ayuntamientos y técnicos (simulación de bancos/rebajes/sombra, study, bank-plan, latencia)
  3. Comunidad de Madrid (179 municipios, impacto, /api/points, SDM, trazabilidad)
  4. Jurado DATAMAD 2026 (seguridad, FTS5 edge cases, MCP completo, concurrencia, coherencia)

Uso:
    .venv/bin/python -m ciudad.banco_pruebas [http://127.0.0.1:8768]
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8768"
ROOT = Path(__file__).resolve().parents[1]

RESULTS = []


def record(group, name, status, detail, ms=None):
    RESULTS.append({"group": group, "name": name, "status": status, "detail": detail, "ms": ms})
    icon = {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL"}[status]
    t = f" ({ms:.0f} ms)" if ms is not None else ""
    print(f"[{icon:4}] [{group}] {name}{t}: {detail}", flush=True)


def http(path, payload=None, query=None, method=None, headers=None, timeout=120):
    url = BASE + path + ("?" + urlencode(query) if query else "")
    if isinstance(payload, dict) and "origin" in payload:
        payload = {**payload, "register": False}  # las pruebas no cuentan en el informe de uso
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = Request(url, data, headers=hdrs, method=method or ("POST" if payload is not None else "GET"))
    t0 = perf_counter()
    try:
        with urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            dt = (perf_counter() - t0) * 1000
            try:
                return r.status, json.loads(body), dict(r.headers), dt
            except ValueError:
                return r.status, body, dict(r.headers), dt
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        dt = (perf_counter() - t0) * 1000
        try:
            return e.code, json.loads(body), dict(e.headers), dt
        except ValueError:
            return e.code, body, dict(e.headers), dt


def get_place(q, at=None):
    params = {"q": q}
    if at:
        params["at"] = at
    code, data, _, dt = http("/api/addresses", query=params)
    return code, data, dt


def test_seniors_and_families():
    G = "MAYORES"
    # 1. Búsquedas realistas de mayores y familias
    queries = [
        ("Centro de salud genérico", "Centro de Salud", lambda r: r and r[0]["source"].startswith("Comunidad")),
        ("Hospital famoso (La Paz)", "Hospital La Paz", lambda r: any(x["kind"] in {"hospital", "health", "clinic"} for x in r)),
        ("Hospital 12 de Octubre", "Hospital 12 de Octubre", lambda r: any(x["kind"] in {"hospital", "health", "clinic"} for x in r)),
        ("Centro de día", "centro de dia", lambda r: any(x["kind"] == "elderly" for x in r)),
        ("Farmacia con calle", "farmacia toledo", lambda r: any(x["kind"] == "pharmacy" for x in r)),
        ("Biblioteca Pedro Salinas", "Biblioteca Pedro Salinas", lambda r: r and r[0]["kind"] == "library"),
        ("Abreviatura c/ + sin tildes", "c/ alcala 50", lambda r: any(x["kind"] == "address" for x in r)),
        ("Abreviatura avda + CP", "avda albufera 100 28038", lambda r: any(x["kind"] == "address" for x in r)),
        ("Parque famoso (Retiro)", "Parque del Retiro", lambda r: len(r) > 0),
        ("Plaza famosa (Puerta del Sol)", "Puerta del Sol 1", lambda r: len(r) > 0),
        ("Refugio en fecha demo (1/7/2025)", "CentroCentro", lambda r: any(x["kind"] == "refuge" for x in r)),
    ]
    for label, q, check in queries:
        at = "2025-07-01T14:00" if "2025" in label else None
        code, data, dt = get_place(q, at=at)
        res = data.get("results", []) if isinstance(data, dict) else []
        ok = code == 200 and check(res)
        top = f"{res[0]['label']} ({res[0].get('source', res[0].get('district'))})" if res else "0 resultados"
        record(G, f"Búsqueda: {label}", "PASS" if ok else "FAIL", f"HTTP {code}, {len(res)} res -> top: {top}", dt)

    # Check ID collisions in address search
    _, d_farm, _ = get_place("calle alcala")
    ids = [x["id"] for x in d_farm.get("results", [])]
    record(G, "Unicidad IDs en resultados búsqueda", "PASS" if len(ids) == len(set(ids)) else "FAIL", f"{len(ids)} resultados, {len(set(ids))} IDs únicos")

    # Check elderly label formatting (missing via_tipo like '· de Martínez...')
    _, d_eld, _ = get_place("centro de dia")
    bad_labels = [x["label"] for x in d_eld.get("results", []) if " · de " in x["label"]]
    record(G, "Formato dirección centros de mayores", "PASS" if not bad_labels else "FAIL",
           "Sin etiquetas cortadas" if not bad_labels else f"{len(bad_labels)} con tipo de vía ausente: {bad_labels[0]}")

    # 2. Filtros de accesibilidad en la ruta de ejemplo
    o = get_place("Plaza Virgen de la Paloma 1")[1]["results"][0]["coordinates"]
    d = get_place("Biblioteca Pedro Salinas")[1]["results"][0]["coordinates"]
    base_req = {
        "origin": {"lon": o[0], "lat": o[1]},
        "destination": {"lon": d[0], "lat": d[1]},
        "departure": "2025-07-01T14:00",
        "preferences": {"rest": 200, "pace": 0.65, "avoidStairs": True},
    }
    code, res, _, dt = http("/api/routes", base_req)
    record(G, "Ruta demo ritmo tranquilo (0.65 m/s)", "PASS" if code == 200 and any(r["fitsRest"] for r in res["routes"]) else "FAIL",
           f"HTTP {code}, {len(res.get('routes', []))} rutas, temp={res.get('weather')}", dt)

    # Strict width & slope
    for pname, prefs in [
        ("Ancho imprescindible 1.2 m (en demo)", {"rest": 200, "width": 1.2}),
        ("Pendiente máxima 8% (en demo)", {"rest": 200, "slope": 8}),
        ("Pendiente máxima 6% (sin descanso)", {"rest": None, "slope": 6}),
    ]:
        code, res, _, dt = http("/api/routes", base_req | {"preferences": prefs})
        ok = code == 200 and len(res.get("routes", [])) > 0
        detail = res.get("detail") if code != 200 else f"{len(res['routes'])} rutas"
        record(G, f"Filtro estricto: {pname}", "PASS" if ok else "FAIL", f"HTTP {code}: {detail}", dt)

    # 3. Live navigation rerouting edge cases
    for carried in (10, 150, 195, 210):
        code, res, _, dt = http("/api/routes", base_req | {"live": True, "initialSinceRest": carried, "preferences": {"rest": 200}})
        found = code == 200 and len(res.get("routes", [])) > 0
        status = "PASS" if found else ("WARN" if carried >= 195 else "FAIL")
        record(G, f"Recálculo GPS en vivo (andados={carried} m / límite 200 m)", status,
               f"HTTP {code}, {len(res.get('routes', []))} rutas (si 0, el usuario queda sin guía en calle)", dt)

    # 4. Same origin & destination
    code, res, _, dt = http("/api/routes", base_req | {"destination": base_req["origin"]})
    record(G, "Origen == Destino", "PASS" if code == 200 and res.get("routes") else "WARN",
           f"HTTP {code}, rutas={len(res.get('routes', []))}, metros={res['routes'][0]['meters'] if code==200 and res.get('routes') else 'N/A'}", dt)

    # 5. Historical weather on OTHER summer 2025 dates
    for dt_str in ("2025-07-01T14:00", "2025-07-01T16:00", "2025-07-15T14:00", "2025-08-10T13:00"):
        code, res, _, dt = http("/api/routes", base_req | {"departure": dt_str})
        w = res.get("weather") if isinstance(res, dict) else None
        record(G, f"Temperatura histórica ({dt_str})", "PASS" if w else "WARN",
               f"{w['temperatureC']} °C ({w['source']})" if w else "Sin dato pese a existir histórico 2025 en disco", dt)

    # 6. Nighttime (no sun) & winter sun
    for label, dt_str in [("Noche (02:00)", "2025-07-01T02:00"), ("Invierno (21/12 13:00)", "2025-12-21T13:00")]:
        code, res, _, dt = http("/api/routes", base_req | {"departure": dt_str})
        ok = code == 200 and res.get("routes")
        sun = res["routes"][0]["sunMin"] if ok else None
        record(G, f"Cálculo solar {label}", "PASS" if ok and (label.startswith("Inv") or sun == 0) else "FAIL",
               f"HTTP {code}, sunMin={sun}", dt)

    # 7. Outside Madrid (Móstoles) & inside Casa de Campo far from network
    for label, lon, lat in [("Fuera de Madrid (Móstoles)", -3.8649, 40.3223), ("Lago/monte Casa de Campo", -3.7600, 40.4250)]:
        code, res, _, dt = http("/api/routes", base_req | {"origin": {"lon": lon, "lat": lat}})
        record(G, f"Punto extremo: {label}", "PASS" if code == 422 else "WARN",
               f"HTTP {code}: {res.get('detail') if isinstance(res, dict) else res}", dt)

    # 8. Long urban trip across districts (3+ km)
    o_long = get_place("Calle de Alcala 200")[1]["results"][0]["coordinates"]
    d_long = get_place("Plaza Mayor 1")[1]["results"][0]["coordinates"]
    code, res, _, dt = http("/api/routes", {
        "origin": {"lon": o_long[0], "lat": o_long[1]},
        "destination": {"lon": d_long[0], "lat": d_long[1]},
        "departure": "2025-07-01T14:00",
        "preferences": {"rest": 200},
    })
    record(G, "Trayecto largo (Alcalá 200 → Plaza Mayor, ~3.7 km)",
           "PASS" if code == 200 and dt < 5000 else "WARN",
           f"HTTP {code}, {len(res.get('routes', []))} rutas, limited={res.get('limited')}, metros={[r['meters'] for r in res.get('routes', [])]}", dt)


def test_municipal_councils():
    G = "AYUNTAMIENTO"
    # Test 4 diverse neighborhoods for study + bank-plan
    zones = [
        ("Centro (Demo)", "Plaza Virgen de la Paloma 1", "Biblioteca Pedro Salinas"),
        ("Latina (alta vulnerabilidad)", "Calle de Illescas 50", "Centro de salud Calle de los Yebenes"),
        ("Salamanca (ensanche)", "Calle de Goya 50", "Calle de Velazquez 80"),
        ("Usera (sur)", "Calle de Marcelo Usera 60", "Calle de Dolores Barranco 30"),
    ]
    for zname, oq, dq in zones:
        ores = get_place(oq)[1]["results"]
        dres = get_place(dq)[1]["results"]
        if not ores or not dres:
            record(G, f"Bank-plan {zname}", "WARN", f"No se encontró origen/destino ({oq} -> {dq})")
            continue
        o, d = ores[0]["coordinates"], dres[0]["coordinates"]
        req = {
            "origin": {"lon": o[0], "lat": o[1]},
            "destination": {"lon": d[0], "lat": d[1]},
            "departure": "2025-07-01T14:00",
            "preferences": {"rest": 200, "avoidStairs": True},
            "radiusM": 500,
        }
        code, plan, _, dt = http("/api/bank-plan", req)
        if code != 200:
            record(G, f"Bank-plan {zname}", "FAIL", f"HTTP {code}: {plan}", dt)
            continue
        opts = plan.get("options", [])
        unk_w = sum(1 for x in opts if x.get("widthM") is None)
        unk_f = sum(1 for x in opts if x.get("footfall") is None)
        zero_med = sum(1 for x in opts if x.get("reducedGaps", 0) > 0 and x.get("medianReductionM") == 0)
        lost = sum(x.get("lostPaths", 0) for x in opts)
        status = "WARN" if (dt > 8000 or zero_med > 0 or lost > 0) else "PASS"
        record(G, f"Bank-plan {zname}", status,
               f"{plan['sitesTested']} sitios, {plan['completed']}/{plan['sample']} portales, "
               f"top newPaths={[x['newPaths'] for x in opts]}, lost={lost}, "
               f"median=0 con mejoras={zero_med}, ancho_desc={unk_w}/{len(opts)}, aforo_desc={unk_f}/{len(opts)}", dt)

        # Test study with scenario outside radius -> should 422 cleanly
        if zname.startswith("Centro"):
            bad_study = req | {"radiusM": 100, "scenario": {"kind": "bench", "lon": -3.7038, "lat": 40.4168}}
            sc, sd, _, sdt = http("/api/study", bad_study)
            record(G, "Study: intervención fuera de radio (422 esperado)", "PASS" if sc == 422 else "FAIL",
                   f"HTTP {sc}: {sd.get('detail') if isinstance(sd, dict) else sd}", sdt)

            # Test crossing intervention away from any crossing -> should 422 cleanly
            bad_cross = req | {"scenario": {"kind": "crossing", "lon": o[0], "lat": o[1]}}
            cc, cd, _, cdt = http("/api/routes", bad_cross)
            record(G, "Escenario rebaje lejos de paso de peatones (422 esperado)", "PASS" if cc == 422 else "WARN",
                   f"HTTP {cc}: {cd.get('detail') if isinstance(cd, dict) else cd}", cdt)

            # Test shade intervention at night vs day
            shade_day = req | {"scenario": {"kind": "shade", "lon": -3.7103549, "lat": 40.4096198}}
            sc2, sd2, _, sdt2 = http("/api/study", shade_day)
            record(G, "Study: intervención de sombra (14:00 verano)", "PASS" if sc2 == 200 else "FAIL",
                   f"HTTP {sc2}, reducedSun={sd2.get('reducedSunPaths')}, lostPaths={sd2.get('lostPaths')}", sdt2)


def test_regional_and_open_data():
    G = "COMUNIDAD"
    # 1. /api/points truncation in 4 areas
    boxes = [
        ("Puerta de Toledo (demo)", (-3.718, 40.402, -3.704, 40.412)),
        ("Sol / Centro", (-3.711, 40.411, -3.696, 40.422)),
        ("Chamberí", (-3.709, 40.428, -3.695, 40.438)),
        ("Barajas", (-3.588, 40.467, -3.572, 40.479)),
    ]
    for bname, (w, s, e, n) in boxes:
        code, data, _, dt = http("/api/points", query={"w": w, "s": s, "e": e, "n": n})
        feats = data.get("features", [])
        kinds = Counter(f["kind"] for f in feats)
        non_bench = sum(v for k, v in kinds.items() if k != "bench")
        record(G, f"/api/points mapa ({bname})", "PASS" if non_bench > 0 else "FAIL",
               f"total={len(feats)}, truncated={data.get('truncated')}, non_bench={non_bench}, tipos={dict(kinds)}", dt)

    # 2. /municipios.geojson integrity
    code, geo, _, dt = http("/municipios.geojson")
    feats = geo.get("features", []) if isinstance(geo, dict) else []
    props = [f["properties"] for f in feats]
    zero_health = [p["municipio"] for p in props if p.get("centrosSalud") == 0]
    zero_elderly = [p["municipio"] for p in props if p.get("centrosMayores") == 0]
    null_idx = [p["municipio"] for p in props if p.get("indice") is None]
    record(G, "/municipios.geojson 179 municipios", "PASS" if code == 200 and len(feats) == 179 and not null_idx else "FAIL",
           f"HTTP {code}, n={len(feats)}, null_indice={len(null_idx)}, 0_salud={len(zero_health)} ({zero_health}), 0_mayores={len(zero_elderly)}", dt)

    # 3. /impacto.json mathematical consistency
    code, imp, _, dt = http("/impacto.json")
    if code == 200 and isinstance(imp, dict):
        tot = imp["principal"]["total"]
        diff = abs((tot["pct_se_arregla"] + tot["pct_sin_alternativa"]) - tot["pct_supera_limite"])
        record(G, "/impacto.json coherencia aritmética", "PASS" if diff <= 0.2 else "FAIL",
               f"supera={tot['pct_supera_limite']}%, arregla={tot['pct_se_arregla']}%, sin_alt={tot['pct_sin_alternativa']}% (diff={diff:.2f})", dt)
    else:
        record(G, "/impacto.json", "FAIL", f"HTTP {code}", dt)

    # 4. Smart Data Models quality
    sdm_path = ROOT / "resultados/smart-data-models/destinos-comunidad-madrid.pointofinterest.json"
    sdm = json.loads(sdm_path.read_text())
    dup_names = Counter(x["name"] for x in sdm).most_common(3)
    uniq_ids = len({x["id"] for x in sdm})
    record(G, "Smart Data Models unicidad y nombres",
           "WARN" if dup_names[0][1] > 10 else "PASS",
           f"{len(sdm)} entidades, {uniq_ids} IDs únicos, nombres repetidos={dup_names}")


def test_jury_security_and_mcp():
    G = "JURADO"
    # 1. Adversarial search queries (SQLi / FTS5 syntax errors / XSS / huge input)
    bad_queries = [
        ("FTS5 comillas/operadores", '"calle" OR NOT () ^ *'),
        ("SQL injection", "toledo' OR '1'='1' --"),
        ("XSS payload", "<script>alert(1)</script>"),
        ("Solo símbolos", "!!!???..."),
        ("Emojis", "🌳🪑 Madrid"),
        ("Query 1 char (422 esperado)", "a"),
        ("Query 200 chars (422 esperado)", "a" * 200),
    ]
    for label, q in bad_queries:
        code, data, dt = get_place(q)
        expect_422 = "422" in label
        ok = (code == 422) if expect_422 else (code in (200, 422))
        record(G, f"Seguridad buscador: {label}", "PASS" if ok else "FAIL",
               f"HTTP {code}: {str(data)[:110]}", dt)

    # 2. HTTP security headers check on /
    code, _, hdrs, dt = http("/")
    lower = {k.lower(): v for k, v in hdrs.items()}
    missing = [h for h in ("x-content-type-options", "x-frame-options", "content-security-policy") if h not in lower]
    record(G, "Cabeceras seguridad HTTP en /", "WARN" if missing else "PASS",
           f"HTTP {code}, ausentes: {', '.join(missing) or 'ninguna'}", dt)

    # 3. Invalid JSON / wrong types / out-of-range coordinates
    for label, body in [
        ("Coordenadas fuera de rango (lat=99)", {"origin": {"lon": -3.7, "lat": 99}, "destination": {"lon": -3.7, "lat": 40.4}, "departure": "2025-07-01T14:00"}),
        ("Rest límite = 5m (<30)", {"origin": {"lon": -3.71, "lat": 40.41}, "destination": {"lon": -3.70, "lat": 40.41}, "departure": "2025-07-01T14:00", "preferences": {"rest": 5}}),
        ("Pace = 0 (división por cero)", {"origin": {"lon": -3.71, "lat": 40.41}, "destination": {"lon": -3.70, "lat": 40.41}, "departure": "2025-07-01T14:00", "preferences": {"pace": 0}}),
        ("Fecha inválida", {"origin": {"lon": -3.71, "lat": 40.41}, "destination": {"lon": -3.70, "lat": 40.41}, "departure": "no-es-fecha"}),
    ]:
        code, data, _, dt = http("/api/routes", body)
        record(G, f"Validación Pydantic: {label}", "PASS" if code == 422 else "FAIL", f"HTTP {code}", dt)

    # 4. Concurrency burst: 8 simultaneous /api/routes requests
    o = get_place("Plaza Virgen de la Paloma 1")[1]["results"][0]["coordinates"]
    d = get_place("Biblioteca Pedro Salinas")[1]["results"][0]["coordinates"]
    req = {
        "origin": {"lon": o[0], "lat": o[1]},
        "destination": {"lon": d[0], "lat": d[1]},
        "departure": "2025-07-01T14:00",
        "preferences": {"rest": 200},
    }
    t0 = perf_counter()
    with ThreadPoolExecutor(8) as pool:
        outcomes = list(pool.map(lambda _: http("/api/routes", req), range(8)))
    total_ms = (perf_counter() - t0) * 1000
    codes = Counter(c for c, _, _, _ in outcomes)
    max_ms = max(dt for _, _, _, dt in outcomes)
    record(G, "Concurrencia: 8 peticiones simultáneas /api/routes",
           "PASS" if codes == {200: 8} and total_ms < 5000 else "WARN",
           f"codes={dict(codes)}, total={total_ms:.0f} ms, max={max_ms:.0f} ms", total_ms)

    # 5. Full MCP server test (including bancos_prioritarios + invalid args + unknown place)
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mcp/servidor.py")],
        env={**__import__("os").environ, "LLEGAR_SIN_REGISTRO": "1"},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    cid = 0

    def rpc(method, params=None):
        nonlocal cid
        cid += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": cid, "method": method, "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "bench", "version": "1"}})
    mcp_cases = [
        ("buscar_lugar", {"texto": "farmacia toledo"}, False),
        ("ruta_con_descansos", {"origen": "Plaza Virgen de la Paloma 1", "destino": "Biblioteca Pedro Salinas", "max_sin_descanso": 200, "salida": "2025-07-01T14:00:00"}, False),
        ("bancos_prioritarios", {"origen": "Plaza Virgen de la Paloma 1", "destino": "Biblioteca Pedro Salinas", "max_sin_descanso": 200, "radio_m": 500}, False),
        ("municipios_prioritarios", {"n": 5, "indicador": "indice"}, False),
        ("impacto_madrid", {}, False),
        ("ruta_con_descansos (lugar inexistente)", {"origen": "Calle Inventada XYZ 9999", "destino": "Biblioteca Pedro Salinas"}, True),
        ("municipios_prioritarios (indicador inválido)", {"indicador": "inventado"}, True),
    ]
    for label, args, expect_err in mcp_cases:
        tool = label.split(" ")[0]
        t0 = perf_counter()
        r = rpc("tools/call", {"name": tool, "arguments": args})["result"]
        dt = (perf_counter() - t0) * 1000
        ok = (r["isError"] == expect_err)
        snippet = r["content"][0]["text"][:100].replace("\n", " ")
        record(G, f"MCP: {label}", "PASS" if ok else "FAIL", f"isError={r['isError']} -> {snippet}", dt)
    proc.stdin.close()
    proc.wait(timeout=10)


def main():
    print(f"=== BANCO DE PRUEBAS MULTI-ACTOR contra {BASE} ===\n", flush=True)
    test_seniors_and_families()
    test_municipal_councils()
    test_regional_and_open_data()
    test_jury_security_and_mcp()
    counts = Counter(r["status"] for r in RESULTS)
    print("\n=== RESUMEN ===", flush=True)
    print(f"Total: {len(RESULTS)} pruebas · PASS={counts['PASS']} · WARN={counts['WARN']} · FAIL={counts['FAIL']}", flush=True)


if __name__ == "__main__":
    main()
