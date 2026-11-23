"""Cotas del MDT05 del IGN, muestreadas en los nodos de la red."""

from concurrent.futures import ThreadPoolExecutor
import numpy as np
from rasterio.io import MemoryFile
from scipy.ndimage import map_coordinates
from ciudad.fuentes import response
from ciudad.preparar import VERSION

WCS = "https://servicios.idee.es/wcs-inspire/mdt"
CELLS = [
    (x, y)
    for x in (420000, 432000, 444000, 456000)
    for y in (4460000, 4472000, 4484000, 4496000)
]


def heights(xy, cell):
    x, y = cell
    indexes = np.flatnonzero(
        (xy[:, 0] >= x)
        & (xy[:, 0] < x + 12000)
        & (xy[:, 1] >= y)
        & (xy[:, 1] < y + 12000)
    )
    if not len(indexes):
        return [], []
    query = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": "Elevacion25830_5",
        "subset": [f"x({x-10},{x+12010})", f"y({y-10},{y+12010})"],
        "format": "image/tiff",
    }
    from urllib.parse import urlencode

    with response(WCS + "?" + urlencode(query, doseq=True)) as stream, MemoryFile(
        stream.read()
    ) as dataset, dataset.open() as source:
        band = source.read(1).astype("float32")
        if source.nodata is not None:
            band[band == source.nodata] = np.nan
        columns, rows = (~source.transform) * (xy[indexes, 0], xy[indexes, 1])
        values = map_coordinates(
            band, [rows - 0.5, columns - 0.5], order=1, mode="constant", cval=np.nan
        )
    return indexes, values


if __name__ == "__main__":
    xy = np.load(VERSION / "grafo.npz")["xy"]
    z = np.full(len(xy), np.nan, dtype="float32")
    with ThreadPoolExecutor(4) as pool:
        for indexes, values in pool.map(lambda cell: heights(xy, cell), CELLS):
            if len(indexes):
                z[indexes] = values
    temporary = VERSION / "cotas.next.npy"
    np.save(temporary, z)
    temporary.replace(VERSION / "cotas.npy")
    print(f"MDT05: {np.isfinite(z).sum():,}/{len(z):,} nodos con cota.")
