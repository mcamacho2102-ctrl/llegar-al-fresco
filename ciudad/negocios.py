"""Negocios y lugares con nombre de OpenStreetMap para el buscador («Mercadona», «farmacia»,
«Museo del Prado»), ordenados por cercanía como en un mapa.

Construir el índice (una vez, desde datos/madrid.osm.pbf):

    .venv/bin/python -m ciudad.negocios

Escribe datos/ciudad/negocios.sqlite. Si no existe, el buscador funciona igual sin negocios.
Datos © colaboradores de OpenStreetMap (ODbL 1.0).
"""

import math
import sqlite3
from pathlib import Path

from ciudad.fuentes import ROOT
from ciudad.preparar import normal

PBF = ROOT / "datos" / "madrid.osm.pbf"
DB = ROOT / "datos" / "ciudad" / "negocios.sqlite"
LIMITE = ROOT / "datos" / "ciudad" / "limite.wkb"
PORTALES = ROOT / "datos" / "ciudad" / "lugares.sqlite"

# Lo que no se busca por su nombre o no es un sitio al que ir andando.
EXCLUIR = {
    "amenity": {"parking", "parking_entrance", "parking_space", "bicycle_parking", "motorcycle_parking",
                "bench", "waste_basket", "waste_disposal", "recycling", "vending_machine", "telephone",
                "post_box", "grit_bin", "clock", "charging_station", "bicycle_rental", "taxi",
                "hunting_stand", "loading_dock", "fuel"},
    "leisure": {"pitch", "track", "picnic_table", "slipway", "outdoor_seating", "firepit"},
    "tourism": {"information"},
}
CLAVES = ("shop", "amenity", "tourism", "leisure", "office", "healthcare", "craft")

CATEGORIA = {
    "supermarket": "Supermercado", "convenience": "Tienda de alimentación", "bakery": "Panadería",
    "butcher": "Carnicería", "greengrocer": "Frutería", "seafood": "Pescadería", "pastry": "Pastelería",
    "department_store": "Grandes almacenes", "mall": "Centro comercial", "clothes": "Ropa",
    "shoes": "Zapatería", "hairdresser": "Peluquería", "beauty": "Estética", "optician": "Óptica",
    "chemist": "Droguería", "hardware": "Ferretería", "doityourself": "Bricolaje", "florist": "Floristería",
    "books": "Librería", "stationery": "Papelería", "newsagent": "Quiosco", "kiosk": "Quiosco",
    "tobacco": "Estanco", "mobile_phone": "Telefonía", "electronics": "Electrónica",
    "furniture": "Muebles", "jewelry": "Joyería", "toys": "Juguetería", "pet": "Tienda de animales",
    "alcohol": "Bodega", "wine": "Vinoteca", "dry_cleaning": "Tintorería", "laundry": "Lavandería",
    "car_repair": "Taller", "variety_store": "Bazar", "gift": "Regalos", "sports": "Deportes",
    "pharmacy": "Farmacia", "hospital": "Hospital", "clinic": "Clínica", "doctors": "Consulta médica",
    "dentist": "Dentista", "veterinary": "Veterinario", "restaurant": "Restaurante", "cafe": "Cafetería",
    "bar": "Bar", "pub": "Bar", "fast_food": "Comida rápida", "ice_cream": "Heladería",
    "bank": "Oficina bancaria", "atm": "Cajero", "post_office": "Correos", "library": "Biblioteca",
    "school": "Colegio", "kindergarten": "Escuela infantil", "university": "Universidad",
    "college": "Centro de estudios", "place_of_worship": "Templo", "townhall": "Ayuntamiento",
    "police": "Policía", "fire_station": "Bomberos", "community_centre": "Centro cultural",
    "social_centre": "Centro social", "social_facility": "Centro social", "arts_centre": "Centro de arte",
    "theatre": "Teatro", "cinema": "Cine", "marketplace": "Mercado", "toilets": "Aseos",
    "drinking_water": "Fuente", "fountain": "Fuente", "courthouse": "Juzgado",
    "museum": "Museo", "gallery": "Galería", "hotel": "Hotel", "hostel": "Albergue",
    "guest_house": "Pensión", "apartment": "Apartamentos", "attraction": "Lugar de interés",
    "viewpoint": "Mirador", "artwork": "Obra de arte", "zoo": "Zoo", "park": "Parque", "garden": "Jardín",
    "sports_centre": "Polideportivo", "fitness_centre": "Gimnasio", "swimming_pool": "Piscina",
    "playground": "Parque infantil", "stadium": "Estadio", "dance": "Baile",
}


def categoria(tags):
    for k in CLAVES:
        v = tags.get(k)
        if v and v not in EXCLUIR.get(k, ()):
            return CATEGORIA.get(v) or (v.replace("_", " ").capitalize() if k == "shop" else "")
    return None


def construir():
    import numpy as np
    import osmium
    import shapely
    from ciudad.motor import TO_METERS

    borde = shapely.from_wkb(LIMITE.read_bytes())
    filas = []

    class Lector(osmium.SimpleHandler):
        def guardar(self, o, lon, lat):
            t = {k: v for k, v in o.tags}
            nombre = (t.get("name") or "").strip()
            if not nombre or len(nombre) > 90:
                return
            cat = categoria(t)
            if cat is None:
                return
            calle, num = t.get("addr:street"), t.get("addr:housenumber")
            dire = f"{calle}, {num}" if calle and num else (calle or "")
            filas.append((f"{o.__class__.__name__[0].lower()}{o.id}", nombre, cat, dire, lon, lat))

        def node(self, n):
            if n.location.valid() and -3.9 < n.location.lon < -3.5 and 40.3 < n.location.lat < 40.66:
                self.guardar(n, n.location.lon, n.location.lat)

        def area(self, a):
            try:
                anillo = next(iter(a.outer_rings()))
                pts = [(p.lon, p.lat) for p in anillo]
            except Exception:
                return
            lon, lat = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            if -3.9 < lon < -3.5 and 40.3 < lat < 40.66:
                self.guardar(a, lon, lat)

    Lector().apply_file(str(PBF), locations=True)
    lon = np.array([f[4] for f in filas]); lat = np.array([f[5] for f in filas])
    x, y = TO_METERS.transform(lon, lat)
    dentro = shapely.contains_xy(borde, x, y)
    # Dirección aproximada con el portal más cercano cuando OSM no la trae.
    with sqlite3.connect(PORTALES) as c:
        port = c.execute("SELECT label, x, y FROM portals").fetchall()
    celda = {}
    for etiqueta, px, py in port:
        celda.setdefault((int(px // 100), int(py // 100)), []).append((etiqueta, px, py))

    def cercano(px, py):
        mejor, d = "", 120.0
        cx, cy = int(px // 100), int(py // 100)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for etiqueta, qx, qy in celda.get((cx + i, cy + j), ()):
                    dd = math.hypot(px - qx, py - qy)
                    if dd < d:
                        mejor, d = etiqueta, dd
        return mejor

    vistos, salida = set(), []
    for f, xi, yi, ok in zip(filas, x, y, dentro):
        if not ok:
            continue
        clave = (normal(f[1]), round(xi / 25), round(yi / 25))  # nodo y área del mismo sitio
        if clave in vistos:
            continue
        vistos.add(clave)
        dire = f[3] or cercano(xi, yi)
        salida.append((f[0], f[1], f[2], dire, f[4], f[5], normal(f"{f[1]} {f[2]}")))
    DB.unlink(missing_ok=True)
    with sqlite3.connect(DB) as c:
        c.execute("CREATE TABLE negocio(id TEXT, nombre TEXT, categoria TEXT, direccion TEXT, lon REAL, lat REAL)")
        c.execute("CREATE VIRTUAL TABLE buscar USING fts5(texto)")
        for i, r in enumerate(salida, 1):
            c.execute("INSERT INTO negocio(rowid,id,nombre,categoria,direccion,lon,lat) VALUES (?,?,?,?,?,?,?)", (i, *r[:6]))
            c.execute("INSERT INTO buscar(rowid, texto) VALUES (?,?)", (i, r[6]))
    print(f"{len(salida)} negocios y lugares en {DB}")


_conn = [None]
PARTICULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "a", "al"}


def suave(texto):
    """«Calle Del Butron, 16» → «Calle del Butron, 16»."""
    w = texto.split()
    return " ".join(x.lower() if i and x.lower() in PARTICULAS else x for i, x in enumerate(w))


def buscar(q, cerca=None, limite=8):
    """Negocios cuyo nombre o categoría empieza por cada palabra buscada; los más cercanos
    primero si se da `cerca` = (lon, lat)."""
    if not DB.exists():
        return []
    palabras = [w for w in normal(q).split() if w not in {"de", "del", "la", "las", "los", "el", "y"}]
    palabras = [w for w in palabras if w.isalnum()][:8]
    if not palabras or sum(len(w) for w in palabras) < 3:
        return []
    if _conn[0] is None:
        _conn[0] = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    consulta = " ".join(f'"{w}"*' for w in palabras)
    filas = _conn[0].execute(
        """SELECT n.id, n.nombre, n.categoria, n.direccion, n.lon, n.lat FROM buscar
           JOIN negocio n ON n.rowid = buscar.rowid WHERE buscar MATCH ?
           ORDER BY bm25(buscar), length(n.nombre) LIMIT 600""",
        (consulta,),
    ).fetchall()

    def metros(lon, lat):
        k = math.cos(math.radians(lat))
        return math.hypot((lon - cerca[0]) * 111_320 * k, (lat - cerca[1]) * 110_540)

    buscado = " ".join(palabras)
    LUGARES = {"Lugar de interés", "Museo", "Parque", "Jardín", "Mirador", "Mercado", "Estadio", "Zoo",
               "Teatro", "Biblioteca", "Hospital", "Universidad", "Centro cultural", "Grandes almacenes"}

    def orden(item):
        i, r = item
        nombre = " ".join(w for w in normal(r[1]).split() if w not in {"de", "del", "la", "las", "los", "el", "y"})
        exacto = nombre == buscado
        lugar = r[2] in LUGARES
        entero = lugar and all(w in nombre.split() for w in palabras)
        if cerca:  # con punto de partida manda la distancia, salvo el lugar exacto que se busca
            return (not (exacto and lugar), metros(r[4], r[5]))
        return (not (exacto and lugar), not exacto, not entero, i)

    filas = [r for _, r in sorted(enumerate(filas), key=orden)]
    out = []
    for ident, nombre, cat, dire, lon, lat in filas[: limite * 2]:
        dire = suave(dire)
        partes = [cat] if cat else []
        if cerca:
            d = metros(lon, lat)
            partes.append(f"a {round(d / 10) * 10:.0f} m" if d < 1000 else f"a {d / 1000:.1f} km".replace(".", ","))
        partes.append("OpenStreetMap")
        out.append({
            "id": "osm:" + ident,
            "label": f"{nombre} · {dire}" if dire else nombre,
            "kind": "address",
            "coordinates": [lon, lat],
            "source": " · ".join(partes),
        })
    return out[: limite * 2]


if __name__ == "__main__":
    construir()
