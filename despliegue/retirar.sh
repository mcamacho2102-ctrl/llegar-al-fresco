#!/bin/sh
# Retira por completo la demo del servidor (contenedor, imagen, red y ficheros).
# El bloque de Caddy se quita a mano restaurando la copia Caddyfile.antes-llegar-al-fresco.
set -eu
docker rm -f llegar-al-fresco >/dev/null 2>&1 || true
docker image rm llegar-al-fresco:actual >/dev/null 2>&1 || true
docker network rm llegar-red >/dev/null 2>&1 || true
rm -rf /opt/llegar-al-fresco
echo "Retirado. Restaura /etc/caddy/Caddyfile desde la copia y recarga Caddy."
