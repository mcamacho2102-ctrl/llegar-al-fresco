#!/bin/sh
# Descarga y descomprime los datos compilados publicados en la Release del repositorio.
# Uso: scripts/descargar_datos.sh [usuario/repositorio] [versión]
set -eu
cd "$(dirname "$0")/.."
REPO="${1:-${LLEGAR_REPO:?Indica usuario/repositorio}}"
VERSION="${2:-v1.0-datamad}"
FILE="llegar-al-fresco-datos-$VERSION.tar.gz"
URL="https://github.com/$REPO/releases/download/$VERSION/$FILE"
curl -fL "$URL" -o "$FILE"
curl -fL "$URL.sha256" -o "$FILE.sha256" && shasum -a 256 -c "$FILE.sha256"
tar -xzf "$FILE"
rm -f "$FILE" "$FILE.sha256"
echo "Datos listos en datos/"
