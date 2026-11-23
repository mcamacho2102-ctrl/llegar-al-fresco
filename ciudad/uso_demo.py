"""Genera un informe de demostración simulando consultas reales.

Mientras no haya usuarios, el informe para ayuntamientos se rellena con consultas
simuladas: portales aleatorios de los 21 distritos (semilla fija) hacia el destino más
cercano de cada tipo (centro de salud, farmacia, centro de mayores o biblioteca de los
registros de la Comunidad), con límites sin descanso variados y fechas del verano de
2025. Se guarda aparte (datos/uso/consultas-demo.sqlite) y la web lo marca como
simulación.

    .venv/bin/python -m ciudad.uso_demo --n 150
"""

import argparse
import random
from datetime import datetime, timedelta

from scipy.spatial import cKDTree

from ciudad.fuentes import RAW
from ciudad.impacto import DEPARTURE, all_districts
from ciudad.motor import Limits, Madrid, coordinates, is_primary_care
from ciudad.uso import LOCAL, Registro

KINDS = [  # (tipo, peso, filtro)
    ("salud", 0.5, is_primary_care),
    ("farmacia", 0.25, lambda r: r["kind"] == "pharmacy"),
    ("mayores", 0.15, lambda r: r["kind"] == "elderly"),
    ("biblioteca", 0.10, lambda r: r["kind"] == "library" and r["source"].startswith("Comunidad de Madrid")),
]
LIMITS = [(100, 0.15), (150, 0.25), (200, 0.35), (300, 0.2), (500, 0.05)]
HOURS = [9, 10, 10, 11, 11, 12, 12, 13, 17, 18, 18, 19, 20]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--semilla", type=int, default=2026)
    args = parser.parse_args()
    city = Madrid()
    path = RAW / "uso" / "consultas-demo.sqlite"
    if path.exists():
        path.unlink()
    registro = Registro(city, path)
    rng = random.Random(args.semilla)
    targets = {}
    for kind, _, wanted in KINDS:
        rows = [r for r in city.pois if wanted(r)]
        targets[kind] = (rows, cKDTree([(r["x"], r["y"]) for r in rows]))
    start = datetime(2025, 6, 1, tzinfo=LOCAL)
    saved = 0
    for district in sorted(all_districts()):
        with city.db_connect() as conn:
            portals = conn.execute(
                "SELECT x,y FROM portals WHERE district=? ORDER BY id", (district,)
            ).fetchall()
        for portal in rng.sample(portals, min(args.n, len(portals))):
            kind = rng.choices([k[0] for k in KINDS], [k[1] for k in KINDS])[0]
            limit = rng.choices([l[0] for l in LIMITS], [l[1] for l in LIMITS])[0]
            rows, tree = targets[kind]
            _, index = tree.query((portal["x"], portal["y"]))
            target = rows[index]
            trip = city.prepare_trip(
                tuple(coordinates((portal["x"], portal["y"]))),
                tuple(coordinates((target["x"], target["y"]))),
                None,
            )
            if trip is None:
                continue
            shortest, _ = trip.solve(Limits(None, None, None, True), DEPARTURE, 1.0, "distance", None)
            if shortest is None:
                continue
            rested, _ = trip.solve(
                Limits(limit, None, None, True), DEPARTURE, 1.0, "distance", limit,
                max_walk=trip.walk_limit(shortest["meters"]),
            )
            when = start + timedelta(days=rng.randrange(92), hours=rng.choice(HOURS), minutes=rng.randrange(60))
            registro.save(when, kind, limit, shortest, rested)
            saved += 1
        print(f"{district}: {saved} consultas simuladas", flush=True)
    data = registro.report()
    print(
        f"Informe de demostración: {data['consultas']} consultas · {data['conRodeo']} con rodeo · "
        f"{data['sinAlternativa']} sin alternativa · {len(data['huecos'])} huecos repetidos",
        flush=True,
    )


if __name__ == "__main__":
    main()
