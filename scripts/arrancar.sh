#!/bin/sh
# Plan B: arranca la aplicación completa en este ordenador (http://localhost:8768).
set -eu
cd "$(dirname "$0")/.."
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt; }
[ -d web/.build ] || { npm --prefix web ci && npm --prefix web run build; }
[ -f datos/ciudad/grafo.npz ] || { echo "Faltan los datos: ejecuta scripts/descargar_datos.sh usuario/repositorio"; exit 1; }
[ -d ../entrega/pitch ] && echo "Presentación: http://localhost:8768/pitch/"
( sleep 25 && open http://localhost:8768/ 2>/dev/null || true ) &
exec .venv/bin/python -m uvicorn ciudad.servicio:app --host 127.0.0.1 --port 8768 --no-access-log
