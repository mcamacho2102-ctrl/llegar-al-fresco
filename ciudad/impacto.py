"""Cifra de impacto reproducible: ¿se llega al centro de salud sin caminar más
de X metros seguidos sin un banco?

Para cada distrito se toma una muestra aleatoria (semilla fija) de portales del
callejero municipal. Desde cada portal se busca el centro de salud de atención
primaria más cercano en línea recta, según el registro de centros sanitarios de
la Comunidad de Madrid, y se calculan con el mismo motor de la aplicación:

1. la ruta más corta (sin límite de descanso), y su mayor tramo seguido sin banco;
2. la ruta que respeta el límite de metros sin descanso, si existe.

Uso:
    .venv/bin/python -m ciudad.impacto                       # 3 distritos más envejecidos + Centro
    .venv/bin/python -m ciudad.impacto --todos --n 120       # los 21 distritos
    .venv/bin/python -m ciudad.impacto --distritos Latina Usera --limite 150
"""

import argparse
import csv
import json
import random
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from scipy.spatial import cKDTree

from ciudad.fuentes import RAW, ROOT
from ciudad.motor import Limits, Madrid, coordinates, is_primary_care

OUT = ROOT / "resultados" / "impacto"
PRIMARY = ("Centro de salud ·", "Consultorio de atención primaria ·")
DEPARTURE = datetime(2025, 7, 1, 14, 0, tzinfo=ZoneInfo("Europe/Madrid")).timestamp()


def padron():
    """Residentes y residentes de 65 o más años por sección censal (padrón municipal)."""
    people, older = Counter(), Counter()
    with (RAW / "padron.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            try:
                section = str(int(row["COD_DIST_SECCION"])).zfill(5)
                n = sum(
                    int(row[c] or 0)
                    for c in (
                        "ESPANOLESHOMBRES",
                        "ESPANOLESMUJERES",
                        "EXTRANJEROSHOMBRES",
                        "EXTRANJEROSMUJERES",
                    )
                )
            except (ValueError, TypeError, KeyError):
                continue
            people[section] += n
            # La última edad se publica como «100 o +».
            if int("".join(ch for ch in row["COD_EDAD_INT"] if ch.isdigit()) or 0) >= 65:
                older[section] += n
    return people, older


def district_ageing(city, people, older):
    with city.db_connect() as conn:
        sections = dict(conn.execute("SELECT DISTINCT section, district FROM portals"))
    total, aged = Counter(), Counter()
    for section, district in sections.items():
        total[district] += people.get(section, 0)
        aged[district] += older.get(section, 0)
    return {d: aged[d] / total[d] for d in total if total[d]}


TOLERANCE_M = 20  # ida y vuelta a un banco junto a la acera


def solve(trip, rest):
    """Distancia mínima sin límite frente a distancia mínima respetando el límite."""
    shortest, short_paused = trip.solve(
        Limits(None, None, None, True), DEPARTURE, 1.0, "distance", None
    )
    rested, rest_paused = trip.solve(
        Limits(rest, None, None, True),
        DEPARTURE,
        1.0,
        "distance",
        rest,
        max_walk=trip.walk_limit(shortest["meters"] if shortest else None),
    )
    return shortest, rested, short_paused or rest_paused


def classify(shortest, rested, paused, rest):
    """cumple_ya: el límite se respeta casi sin alargar el camino (bancos de paso).
    se_arregla_con_desvio: hay que alargar el camino más de TOLERANCE_M para encontrar bancos.
    no_hay_alternativa: no existe ruta que respete el límite dentro de lo explorado."""
    if shortest is None:
        return "sin_ruta"
    if rested is None:
        return "inconcluso" if paused else "no_hay_alternativa"
    if rested["meters"] <= shortest["meters"] + TOLERANCE_M:
        return "cumple_ya"
    return "se_arregla_con_desvio"


def run(districts, n, rest, seed):
    city = Madrid()
    people, older = padron()
    ageing = district_ageing(city, people, older)
    primary = [
        row for row in city.pois if is_primary_care(row)
    ]
    tree = cKDTree([(row["x"], row["y"]) for row in primary])
    if not districts:
        ranked = sorted(ageing, key=ageing.get, reverse=True)
        districts = ranked[:3] + (["Centro"] if "Centro" not in ranked[:3] else [])
    rng = random.Random(seed)
    rows = []
    started = perf_counter()
    for district in districts:
        with city.db_connect() as conn:
            portals = conn.execute(
                "SELECT id,label,section,x,y FROM portals WHERE district=? ORDER BY id",
                (district,),
            ).fetchall()
        if not portals:
            print(f"Distrito sin portales: {district}", flush=True)
            continue
        for portal in rng.sample(portals, min(n, len(portals))):
            distance, index = tree.query((portal["x"], portal["y"]))
            target = primary[index]
            trip = city.prepare_trip(
                tuple(coordinates((portal["x"], portal["y"]))),
                tuple(coordinates((target["x"], target["y"]))),
                None,
            )
            if trip is None:
                shortest = rested = None
                paused = False
            else:
                shortest, rested, paused = solve(trip, rest)
            rows.append(
                {
                    "distrito": district,
                    "portal": portal["label"],
                    "seccion": portal["section"],
                    "residentes_seccion": people.get(portal["section"], 0),
                    "mayores65_seccion": older.get(portal["section"], 0),
                    "centro_salud": target["label"],
                    "linea_recta_m": round(distance),
                    "corta_m": shortest and round(shortest["meters"]),
                    "corta_necesita_banco": shortest and shortest["meters"] > rest,
                    "corta_sol_min": shortest and shortest.get("sunMin"),
                    "con_descansos_m": rested and round(rested["meters"]),
                    "con_descansos_max_sin_banco_m": rested
                    and round(rested["maxWithoutRest"], 1),
                    "resultado": classify(shortest, rested, paused, rest),
                }
            )
        print(f"{district}: {sum(r['distrito'] == district for r in rows)} trayectos", flush=True)
    return rows, ageing, perf_counter() - started, city.meta


def summarize(rows, ageing, rest):
    by = {}
    for district in dict.fromkeys(r["distrito"] for r in rows):
        group = [r for r in rows if r["distrito"] == district]
        evaluable = [r for r in group if r["resultado"] not in {"sin_ruta", "inconcluso"}]
        count = Counter(r["resultado"] for r in evaluable)
        weight = sum(r["mayores65_seccion"] for r in evaluable) or 1
        exceed = [r for r in evaluable if r["resultado"] != "cumple_ya"]
        fixed = [r for r in group if r["resultado"] == "se_arregla_con_desvio"]
        extra = sorted(r["con_descansos_m"] - r["corta_m"] for r in fixed)
        by[district] = {
            "pct_mayores65": round(100 * ageing.get(district, 0), 1),
            "muestra": len(group),
            "evaluables": len(evaluable),
            "pct_supera_limite": round(100 * len(exceed) / max(len(evaluable), 1), 1),
            "pct_supera_limite_ponderado_mayores": round(
                100 * sum(r["mayores65_seccion"] for r in exceed) / weight, 1
            ),
            "pct_se_arregla": round(100 * count["se_arregla_con_desvio"] / max(len(evaluable), 1), 1),
            "pct_sin_alternativa": round(100 * count["no_hay_alternativa"] / max(len(evaluable), 1), 1),
            "desvio_mediano_m": extra[len(extra) // 2] if extra else None,
            "excluidos_sin_ruta_o_inconclusos": len(group) - len(evaluable),
        }
    evaluable = [r for r in rows if r["resultado"] not in {"sin_ruta", "inconcluso"}]
    exceed = [r for r in evaluable if r["resultado"] != "cumple_ya"]
    total = {
        "muestra": len(rows),
        "evaluables": len(evaluable),
        "pct_supera_limite": round(100 * len(exceed) / max(len(evaluable), 1), 1),
        "pct_se_arregla": round(
            100 * sum(r["resultado"] == "se_arregla_con_desvio" for r in evaluable) / max(len(evaluable), 1), 1
        ),
        "pct_sin_alternativa": round(
            100 * sum(r["resultado"] == "no_hay_alternativa" for r in evaluable) / max(len(evaluable), 1), 1
        ),
    }
    return {"limite_m": rest, "total": total, "distritos": by}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--distritos", nargs="*")
    parser.add_argument("--todos", action="store_true")
    parser.add_argument("--n", type=int, default=150, help="portales por distrito")
    parser.add_argument("--limite", type=int, default=200, help="metros seguidos sin banco")
    parser.add_argument("--semilla", type=int, default=2026)
    args = parser.parse_args()
    districts = sorted(all_districts()) if args.todos else args.distritos
    rows, ageing, seconds, meta = run(districts, args.n, args.limite, args.semilla)
    summary = summarize(rows, ageing, args.limite)
    summary.update(
        {
            "semilla": args.semilla,
            "n_por_distrito": args.n,
            "salida_simulada": "2025-07-01T14:00 Europe/Madrid",
            "segundos": round(seconds),
            "version_datos": meta,
            "destino": "Centro de salud o consultorio de atención primaria más cercano en línea recta · Comunidad de Madrid, registro de centros sanitarios",
        }
    )
    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"impacto_{args.limite}m_n{args.n}_s{args.semilla}" + ("_todos" if args.todos else "")
    with (OUT / f"{stem}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / f"{stem}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.todos:
        publish(args.n, args.semilla)


def publish(n, seed, main_limit=200):
    """Resumen para la vista regional de la web: límite principal y sensibilidad."""
    found = {}
    for path in sorted(OUT.glob(f"impacto_*m_n{n}_s{seed}_todos.json")):
        data = json.loads(path.read_text())
        found[data["limite_m"]] = data
    if main_limit not in found:
        return
    web = {
        "principal": found[main_limit],
        "sensibilidad": {str(k): v["total"] for k, v in sorted(found.items())},
    }
    target = ROOT / "web" / "public" / "impacto.json"
    target.write_text(json.dumps(web, ensure_ascii=False, separators=(",", ":")))
    print(f"Publicado {target.relative_to(ROOT)}", flush=True)


def all_districts():
    conn = sqlite3.connect(f"file:{RAW / 'ciudad' / 'lugares.sqlite'}?mode=ro", uri=True)
    try:
        return [d for (d,) in conn.execute("SELECT DISTINCT district FROM portals")]
    finally:
        conn.close()


if __name__ == "__main__":
    main()
