# Imagen de la demo pública: FastAPI y la web compilada en el mismo origen.
# Los datos compilados no están en Git: descárgalos antes con scripts/descargar_datos.sh
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ciudad/ ciudad/
COPY datos/ datos/
COPY --from=web /web/.build web/.build
EXPOSE 8080
CMD ["uvicorn", "ciudad.servicio:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--proxy-headers"]
