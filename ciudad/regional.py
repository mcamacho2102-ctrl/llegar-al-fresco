"""Destinos de los registros oficiales de la Comunidad de Madrid.

Añade al índice local los centros para personas mayores del Registro de
centros de atención social y las oficinas de farmacia del registro regional.
Se puede ejecutar sobre un ``lugares.sqlite`` ya compilado:

    .venv/bin/python -m ciudad.regional
"""

import csv
import sqlite3

import shapely

from ciudad.fuentes import RAW

VERSION = RAW / "ciudad"
SOCIAL = "atencion_social_registro_centros.csv"
PHARMACIES = "oficinas_farmacia.csv"
SOCIAL_SOURCE = "Comunidad de Madrid · Registro de centros de atención social"
PHARMACY_SOURCE = "Comunidad de Madrid · registro de oficinas de farmacia"
HEALTH_SOURCE = "Comunidad de Madrid · registro sanitario"
VIA = {
    "CALLE": "Calle", "AVDA": "Avenida", "AVENIDA": "Avenida", "PASEO": "Paseo", "PLAZA": "Plaza",
    "CTRA": "Carretera", "CMNO": "Camino", "GTA": "Glorieta", "RONDA": "Ronda", "CUSTA": "Cuesta",
    "BULEV": "Bulevar", "TRVA": "Travesía", "PSAJE": "Pasaje", "CRA": "Carrera", "CLLON": "Callejón",
    "CSTAN": "Costanilla", "PZA": "Plaza", "PS": "Paseo", "AV": "Avenida", "CL": "Calle",
}


def via(kind):
    """Tipo de vía legible a partir de la abreviatura del registro."""
    text = str(kind or "").strip()
    return VIA.get(text.upper(), text.title())


SUBTYPES = {
    "CENTROS DE DÍA": "Centro de día para mayores",
    "CENTROS RESIDENCIALES": "Residencia de mayores",
}


def number(value):
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def rows(name):
    path = RAW / name
    if not path.is_file():
        print(f"Falta {name}; ejecuta python -m ciudad.fuentes", flush=True)
        return
    with path.open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream, delimiter=";")


def title(text):
    small = {"de", "del", "la", "las", "el", "los", "y", "e", "para", "con"}
    words = str(text).strip().lower().split()
    return " ".join(
        w if i and w in small else w[:1].upper() + w[1:] for i, w in enumerate(words)
    )


def elderly_centres(boundary):
    for row in rows(SOCIAL):
        if row["sector"].strip() != "Personas mayores":
            continue
        if row["municipio_nombre"].strip().lower() != "madrid":
            continue
        x, y = number(row["direccion_coor_x"]), number(row["direccion_coor_y"])
        if not x or not y or not shapely.intersects_xy(boundary, x, y):
            continue
        kind = SUBTYPES.get(row["tipo"].strip())
        if row["subtipo"].strip() == "HOGARES Y CLUBES":
            kind = "Hogar o club de mayores"
        kind = kind or "Centro para mayores"
        street = " ".join(
            filter(
                None,
                (
                    via(row["direccion_via_tipo"]),
                    row["direccion_via_nombre"].strip(),
                    row["direccion_portal"].strip(),
                ),
            )
        )
        label = f"{title(row['denominacion'])} · {kind}"
        if street:
            label += f" · {street}"
        yield ("m" + row["numero_registro"], label, "elderly", x, y, SOCIAL_SOURCE, None)


def pharmacies(boundary):
    for row in rows(PHARMACIES):
        if row["MUNICIPIO_NOMBRE"].strip().lower() != "madrid":
            continue
        x = number(row["LOCALIZACION_COORDENADA_X"])
        y = number(row["LOCALIZACION_COORDENADA_Y"])
        if not x or not y or not shapely.intersects_xy(boundary, x, y):
            continue
        street = " ".join(
            filter(
                None,
                (
                    via(row["DIRECCION_VIAL_TIPO"]),
                    row["DIRECCION_VIAL_NOMBRE"].strip(),
                    row["DIRECCION_VIAL_NRO"].strip(),
                ),
            )
        )
        yield (
            "farm:" + row["FARMACIA_NRO_SOE"],  # «p…» es el prefijo de los portales
            f"Farmacia · {street}",
            "pharmacy",
            x,
            y,
            PHARMACY_SOURCE,
            None,
        )


def health_label(row):
    """Etiqueta de un centro del registro sanitario, con tipo de vía."""
    street = " ".join(
        part
        for part in (
            via(row["direccion_vial_tipo"]),
            row["direccion_vial_nombre"].strip(),
            row["direccion_vial_nro"].strip(),
        )
        if part
    )
    return f'{row["centro_tipo"]} · {street}'


def fix_health_labels(db):
    """Rehace la parte de dirección de los centros sanitarios ya indexados, conservando
    el nombre añadido desde OSM («Nombre — …»)."""
    labels = {}
    for row in rows("centros_servicios_establecimientos_sanitarios.csv"):
        labels.setdefault("s" + row["centro_nro_registro"], health_label(row))
    changed = 0
    for ident, label in db.execute("SELECT id,label FROM poi WHERE source=?", (HEALTH_SOURCE,)).fetchall():
        base = labels.get(ident)
        if not base:
            continue
        new = (label.split(" — ")[0] + " — " + base) if " — " in label else base
        if new != label:
            db.execute("UPDATE poi SET label=? WHERE id=?", (new, ident))
            changed += 1
    return changed


def add_regional(db, boundary):
    """Sustituye los destinos regionales en una base abierta de ``lugares``."""
    db.execute("DELETE FROM poi WHERE source IN (?,?)", (SOCIAL_SOURCE, PHARMACY_SOURCE))
    elderly = list(elderly_centres(boundary))
    farms = list(pharmacies(boundary))
    if farms:
        # El registro oficial sustituye a las farmacias cartografiadas en OSM.
        db.execute("DELETE FROM poi WHERE kind='pharmacy' AND source='OpenStreetMap'")
    db.executemany("INSERT OR REPLACE INTO poi VALUES(?,?,?,?,?,?,?)", elderly + farms)
    print(
        f"Destinos regionales: {len(elderly)} centros para mayores · {len(farms)} farmacias",
        flush=True,
    )


def main():
    boundary = shapely.from_wkb((VERSION / "limite.wkb").read_bytes())
    db = sqlite3.connect(VERSION / "lugares.sqlite")
    add_regional(db, boundary)
    print(f"Centros sanitarios con tipo de vía corregido: {fix_health_labels(db):,}", flush=True)
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
