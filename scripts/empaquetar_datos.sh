#!/bin/sh
# Empaqueta los datos que necesita el servidor para publicarlos como GitHub Release.
set -eu
cd "$(dirname "$0")/.."
VERSION="${1:-v1.0-datamad}"
OUT="llegar-al-fresco-datos-$VERSION.tar.gz"
tar --exclude='*.antes-anchos.npz' -czf "$OUT" \
  datos/ciudad \
  datos/padron.csv datos/fuentes.csv datos/aemet-madrid.xml \
  datos/calidad_aire_datos_meteo_historico.csv datos/calidad_aire_datos_meteo_mes.csv \
  datos/aforos \
  datos/uso/consultas-demo.sqlite
if command -v sha256sum >/dev/null 2>&1; then sha256sum "$OUT" > "$OUT.sha256"; else shasum -a 256 "$OUT" > "$OUT.sha256"; fi
ls -lh "$OUT"
