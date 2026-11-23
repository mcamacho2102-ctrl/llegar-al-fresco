"""Descarga reproducible de las capas públicas de Madrid."""

import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "datos"
GIS = "https://sigma.madrid.es/hosted/rest/services"
AEMET = "https://www.aemet.es/xml/municipios_h/localidad_h_28079.xml"

FILES = {
    "aforos/peatones-permanentes-2024.csv": "https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas/resource/300321-0-aforos-peatones-bicicletas-csv/download/300321-0-aforos-peatones-bicicletas-csv.csv",
    "aforos/peatones-campana-octubre-2024.csv": "https://datos.madrid.es/dataset/300197-0-aforo-trafico/resource/300197-45-aforo-trafico/download/aforos_peatones_octubre_2024.csv",
    "madrid.osm.pbf": "https://download.geofabrik.de/europe/spain/madrid-latest.osm.pbf",
    "portales.csv": "https://datos.madrid.es/dataset/200075-0-callejero/resource/200075-1-callejero-csv/download/callejero_vigente_numeraciones_202610.csv",
    "bancos-original.json": "https://datos.madrid.es/dataset/300095-0-mobiliario-bancos/resource/300095-28-mobiliario-bancos/download/export_20260305_072850_json.json",
    "fuentes.csv": "https://datos.madrid.es/dataset/300051-0-fuentes/resource/300051-26-fuentes/download/300051-26-fuentes.csv",
    "padron.csv": "https://datos.madrid.es/dataset/200076-0-padron/resource/200076-2-padron-csv/download/200076_20261029_160704.csv",
    "edificios.zip": "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/CARTOGRAFIA/CARTOGRAFIA_ACTUALIZADA/ALTURAS_EDIFICIOS/ALTURAS_EDIFICIOS.ZIP",
    "centros_servicios_establecimientos_sanitarios.csv": None,
    "spacm_listado_bibliotecas_servicios_lectura.csv": None,
    "calidad_aire_datos_meteo_historico.csv": None,
    "calidad_aire_datos_meteo_mes.csv": None,
    "atencion_social_registro_centros.csv": None,
    "oficinas_farmacia.csv": None,
    "grado_envejecimiento_por_edad.csv": None,
    "poblacion_censada_por_edad_nacionalidad_y_sexo.csv": None,
    "centros_servicios_sociales_por_tipo.csv": None,
    "secciones_censales.zip": "https://datos.comunidad.madrid/dataset/2c176a23-a6cd-4c18-b5df-b32a3a3a1219/resource/b53b766c-e013-444c-b3b0-0992c4a0dbfc/download/558.zip",
}


def response(url, params=None, timeout=60, attempts=3):
    query = url + ("?" + urlencode(params) if params else "")
    for attempt in range(attempts):
        try:
            return urlopen(
                Request(
                    query, headers={"User-Agent": "LlegarAlFresco/2.0 Madrid open data"}
                ),
                timeout=timeout,
            )
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)


def jsonify(url, **params):
    for attempt in range(3):
        try:
            with response(url, params) as stream:
                result = json.load(stream)
            if "error" in result:
                raise ValueError(result["error"])
            return result
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def layer(service, n, target, fields="*"):
    path = RAW / target
    if path.exists():
        return
    url = f"{GIS}/{service}/MapServer/{n}/query"
    ids = sorted(jsonify(url, where="1=1", returnIdsOnly="true", f="json")["objectIds"])

    def batch(chunk):
        return jsonify(
            url,
            where=f"OBJECTID BETWEEN {chunk[0]} AND {chunk[-1]}",
            outFields=fields,
            returnGeometry="true",
            outSR=25830,
            maxAllowableOffset=0.5,
            f="geojson",
        )["features"]

    chunks = [ids[i : i + 1000] for i in range(0, len(ids), 1000)]
    fetched = 0
    temporary = path.with_suffix(".part")
    with gzip.open(temporary, "wt") as output, ThreadPoolExecutor(4) as pool:
        for features in pool.map(batch, chunks):
            for feature in features:
                output.write(json.dumps(feature, separators=(",", ":")) + "\n")
            fetched += len(features)
    if fetched != len(ids):
        raise RuntimeError(f"{target}: {fetched}/{len(ids)} entidades")
    temporary.replace(path)
    print(f"{target}: {fetched}", flush=True)


def file_entry(entry):
    name, url = entry
    path = RAW / name
    if path.exists() and path.stat().st_size:
        return
    if url is None:
        identifier = name.removesuffix(".csv")
        with response(
            f"https://datos.comunidad.madrid/api/3/action/package_show",
            {"id": identifier},
        ) as stream:
            resources = json.load(stream)["result"]["resources"]
        csvs = [row["url"] for row in resources if row["format"].upper() == "CSV"]
        url = next((item for item in csvs if item.endswith("/2025.csv")), csvs[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".part")
    with response(url) as stream, temp.open("wb") as out:
        while block := stream.read(1024 * 1024):
            out.write(block)
    temp.replace(path)
    print(f"{name}: {path.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(file_entry, FILES.items()))
        jobs = [
            pool.submit(
                layer, "CARTOGRAFIA/LIMITES_ADMINISTRATIVOS", 26, "distritos.jsonl.gz"
            ),
            pool.submit(
                layer, "CARTOGRAFIA/LIMITES_ADMINISTRATIVOS", 24, "secciones.jsonl.gz"
            ),
            pool.submit(
                layer,
                "GEOPORTAL/ACCESIBILIDAD_VIARIA",
                3,
                "aceras.jsonl.gz",
                "OBJECTID,ancho_ac_m,sol_ver_m,pen_m",
            ),
        ]
        for job in jobs:
            job.result()
