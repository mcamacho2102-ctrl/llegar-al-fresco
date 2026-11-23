#!/bin/sh
# Despliegue aislado en un servidor Linux con Docker. Se ejecuta EN el servidor:
#   sh servidor.sh [rama]
# Crea /opt/llegar-al-fresco, descarga código y datos de GitHub, construye la imagen y
# arranca un contenedor con límites estrictos que solo escucha en 127.0.0.1:8780.
set -eu
REPO="https://github.com/mcamacho2102-ctrl/llegar-al-fresco"
BASE=/opt/llegar-al-fresco
RAMA="${1:-main}"
mkdir -p "$BASE"
if [ -d "$BASE/codigo/.git" ]; then
  git -C "$BASE/codigo" fetch -q origin && git -C "$BASE/codigo" checkout -q "origin/$RAMA"
else
  git clone -q --branch "$RAMA" "$REPO" "$BASE/codigo"
fi
cd "$BASE/codigo"
[ -f datos/ciudad/grafo.npz ] || sh scripts/descargar_datos.sh
docker build -q -t llegar-al-fresco:actual . >/dev/null
# Registro de uso persistente (único directorio escribible) con el informe de demostración.
mkdir -p "$BASE/uso"
[ -f "$BASE/uso/consultas-demo.sqlite" ] || cp datos/uso/consultas-demo.sqlite "$BASE/uso/"
chown -R 10001:10001 "$BASE/uso"
docker network inspect llegar-red >/dev/null 2>&1 || docker network create llegar-red >/dev/null
docker rm -f llegar-al-fresco >/dev/null 2>&1 || true
docker run -d --name llegar-al-fresco --restart unless-stopped \
  --network llegar-red -p 127.0.0.1:8780:8080 \
  --memory 2g --memory-swap 2g --cpus 2 --pids-limit 256 \
  --read-only --tmpfs /tmp:size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  -v "$BASE/uso:/app/datos/uso" \
  -e CONFIAR_PROXY=1 \
  llegar-al-fresco:actual >/dev/null
echo "Contenedor arrancado. Esperando a que cargue la red…"
for i in $(seq 1 60); do
  curl -fsS -o /dev/null http://127.0.0.1:8780/api/info && { echo "Listo en 127.0.0.1:8780"; exit 0; }
  sleep 2
done
echo "No respondió a tiempo: docker logs llegar-al-fresco"; exit 1
