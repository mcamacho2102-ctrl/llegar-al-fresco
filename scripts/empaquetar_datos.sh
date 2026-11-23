#!/bin/sh
# Empaqueta los datos que necesita el servidor para publicarlos como GitHub Release.
set -eu
cd "$(dirname "$0")/.."
VERSION="${1:-v1.0-datamad}"
OUT="llegar-al-fresco-datos-$VERSION.tar.gz"
tar -czf "$OUT" \
  datos/ciudad \
  datos/padron.csv datos/fuentes.csv datos/aemet-madrid.xml \
  datos/calidad_aire_datos_meteo_historico.csv datos/aforos
shasum -a 256 "$OUT" > "$OUT.sha256"
ls -lh "$OUT"
