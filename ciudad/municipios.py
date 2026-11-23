"""Mapa regional: dónde hace más falta «llegar al fresco» en los 179 municipios.

Solo usa datos de la Comunidad de Madrid (datos.comunidad.madrid):

- Secciones censales (geometría, se disuelven por municipio).
- Población censada por edad (2025): residentes, 65+ y 80+.
- Grado de envejecimiento (2025): % de 65 años o más.
- Centros de servicios sociales por tipo (último año): centros para mayores.
- Registro de centros sanitarios: centros de salud y consultorios de atención primaria.
- Registro de oficinas de farmacia.
- Red de calidad del aire, datos meteorológicos horarios (2025): horas ≥ 35 °C.

    .venv/bin/python -m ciudad.municipios   # escribe web/public/municipios.geojson
"""

import csv
import json
import zipfile
from collections import Counter, defaultdict
from io import BytesIO

import shapefile
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from ciudad.fuentes import RAW, ROOT

OUT = ROOT / "web" / "public" / "municipios.geojson"
TO_DEGREES = Transformer.from_crs(25830, 4326, always_xy=True)
PRIMARY = {"Centro de salud", "Consultorio de atención primaria", "Consultorio local"}
HOT = 35.0


def read(name):
    with (RAW / name).open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream, delimiter=";")


def number(value):
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def municipalities():
    with zipfile.ZipFile(RAW / "secciones_censales.zip") as archive:
        stem = next(n for n in archive.namelist() if n.lower().endswith(".shp"))[:-4]
        parts = {ext: BytesIO(archive.read(stem + "." + ext)) for ext in ("shp", "shx", "dbf")}
    reader = shapefile.Reader(shp=parts["shp"], shx=parts["shx"], dbf=parts["dbf"])
    pieces = defaultdict(list)
    for item in reader.iterShapeRecords():
        pieces[item.record["CDMUNI"]].append(shapely.make_valid(shape(item.shape.__geo_interface__)))
    return {code: shapely.union_all(geoms) for code, geoms in pieces.items()}


def latest(rows, year_key="Año"):
    year = max(r[year_key] for r in rows)
    return year, [r for r in rows if r[year_key] == year]


def population():
    rows = [
        r
        for r in read("poblacion_censada_por_edad_nacionalidad_y_sexo.csv")
        if r["Tipo territorio"] == "Municipios" and r["Nacionalidad"] == "Total" and r["Sexo"] == "Total"
    ]
    year, rows = latest(rows)
    names, total, older, oldest = {}, Counter(), Counter(), Counter()
    for r in rows:
        code = r["Código territorio"][:3]
        names[code] = r["Territorio"]
        value = number(r["Valor"]) or 0
        if r["Edad"] == "Total":
            total[code] += value
            continue
        start = int(r["Edad"].split()[1].split("-")[0])
        if start >= 65:
            older[code] += value
        if start >= 80:
            oldest[code] += value
    return year, names, total, older, oldest


def ageing():
    rows = [
        r
        for r in read("grado_envejecimiento_por_edad.csv")
        if r["Tipo territorio"] == "Municipios" and r["Edad"] == "65 años y más"
    ]
    year, rows = latest(rows)
    return year, {r["Código territorio"][:3]: number(r["Valor"]) for r in rows}


def social_centres():
    rows = [
        r
        for r in read("centros_servicios_sociales_por_tipo.csv")
        if r["Tipo territorio"] == "Municipios" and r["Tipo"] == "Personas mayores: Total"
    ]
    year, rows = latest(rows)
    return year, {r["Código territorio"][:3]: number(r["Valor"]) for r in rows}


def count_points(shapes, points):
    codes = list(shapes)
    tree = shapely.STRtree([shapes[c] for c in codes])
    result = Counter()
    for x, y in points:
        hits = tree.query(shapely.Point(x, y), predicate="within")
        if len(hits):
            result[codes[hits[0]]] += 1
    return result


def health_points():
    # El registro repite cada centro una vez por servicio ofertado.
    seen = set()
    for r in read("centros_servicios_establecimientos_sanitarios.csv"):
        if r["centro_nro_registro"] in seen:
            continue
        seen.add(r["centro_nro_registro"])
        if r["centro_tipo"].strip() in PRIMARY:
            x, y = number(r["localizacion_coordenada_x"]), number(r["localizacion_coordenada_y"])
            if x and y:
                yield x, y


def pharmacy_points():
    for r in read("oficinas_farmacia.csv"):
        x, y = number(r["LOCALIZACION_COORDENADA_X"]), number(r["LOCALIZACION_COORDENADA_Y"])
        if x and y:
            yield x, y


def heat_hours():
    """Horas ≥ 35 °C validadas en 2025 por estación de la red regional (magnitud 83)."""
    hours, valid = Counter(), Counter()
    for r in read("calidad_aire_datos_meteo_historico.csv"):
        if r["magnitud"] != "83" or r["ano"] != "2025":
            continue
        code = r["municipio"].zfill(3)
        for h in range(1, 25):
            if r[f"v{h:02d}"] != "V":
                continue
            value = number(r[f"h{h:02d}"])
            if value is None:
                continue
            valid[code] += 1
            hours[code] += value >= HOT
    return {code: (hours[code], valid[code]) for code in valid}


def percentile(values):
    known = sorted(v for v in values.values() if v is not None)
    if not known:
        return {}
    return {
        k: None if v is None else sum(x <= v for x in known) / len(known) for k, v in values.items()
    }


def main():
    shapes = municipalities()
    year_pop, names, total, older, oldest = population()
    year_age, pct65 = ageing()
    year_soc, centres = social_centres()
    health = count_points(shapes, health_points())
    farms = count_points(shapes, pharmacy_points())
    heat = heat_hours()
    centroids = {c: shapes[c].representative_point() for c in shapes}
    stations = {c: centroids[c] for c in heat if c in centroids}
    station_tree = shapely.STRtree(list(stations.values()))
    station_codes = list(stations)

    rows = {}
    for code in shapes:
        o = older.get(code, 0)
        nearest = station_codes[station_tree.nearest(centroids[code])]
        hot, valid = heat[nearest]
        rows[code] = {
            "codigo": code,
            "municipio": names.get(code, code),
            "poblacion": int(total.get(code, 0)),
            "mayores65": int(o),
            "mayores80": int(oldest.get(code, 0)),
            "pct65": pct65.get(code),
            "centrosMayores": int(centres.get(code) or 0),
            "centrosSalud": health.get(code, 0),
            "farmacias": farms.get(code, 0),
            "mayoresPorCentroSalud": round(o / health[code]) if health.get(code) else None,
            "mayoresPorCentroMayores": round(o / centres[code]) if centres.get(code) else None,
            "horas35": hot,
            "estacionCalor": names.get(nearest, nearest),
            "estacionPropia": nearest == code,
        }
    # Índice de prioridad: media de percentiles (0–1), mayor = más necesidad.
    criteria = {
        "pct65": {c: r["pct65"] for c, r in rows.items()},
        "salud": {
            c: (r["mayoresPorCentroSalud"] if r["centrosSalud"] else r["mayores65"]) for c, r in rows.items()
        },
        "mayores": {
            c: (r["mayoresPorCentroMayores"] if r["centrosMayores"] else r["mayores65"])
            for c, r in rows.items()
        },
        "calor": {c: r["horas35"] for c, r in rows.items()},
    }
    ranks = {k: percentile(v) for k, v in criteria.items()}
    for code, row in rows.items():
        parts = [ranks[k][code] for k in ranks if ranks[k].get(code) is not None]
        row["indice"] = round(100 * sum(parts) / len(parts), 1) if parts else None
    order = sorted(rows, key=lambda c: rows[c]["indice"] or 0, reverse=True)
    for position, code in enumerate(order, 1):
        rows[code]["puesto"] = position

    features = []
    for code, geom in shapes.items():
        simple = transform(
            lambda x, y, z=None: TO_DEGREES.transform(x, y), geom.simplify(40, preserve_topology=True)
        )
        geometry = json.loads(
            json.dumps(mapping(simple)), parse_float=lambda v: round(float(v), 5)
        )
        features.append({"type": "Feature", "properties": rows[code], "geometry": geometry})
    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "poblacion": year_pop,
            "envejecimiento": year_age,
            "centrosSociales": year_soc,
            "calor": f"2025 · horas validadas ≥ {HOT:.0f} °C · estación de la red regional más cercana",
            "fuente": "Comunidad de Madrid · datos.comunidad.madrid",
            "indice": "Media de percentiles: % 65+, mayores por centro de salud, mayores por centro para mayores y horas ≥ 35 °C",
        },
        "features": features,
    }
    OUT.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")))
    print(f"{OUT.name}: {len(features)} municipios · {OUT.stat().st_size / 1e6:.1f} MB", flush=True)
    for code in order[:10]:
        r = rows[code]
        print(
            f"{r['puesto']:3} {r['municipio']:28} índice {r['indice']:5} · 65+ {r['pct65']}% · "
            f"{r['mayores65']} mayores · salud {r['centrosSalud']} · c.mayores {r['centrosMayores']} · {r['horas35']} h≥35",
            flush=True,
        )


if __name__ == "__main__":
    main()
