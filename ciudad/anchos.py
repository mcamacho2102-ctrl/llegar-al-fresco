"""Completa el ancho de acera en una red ya compilada (grafo.npz) sin recompilar OSM.

Aplica la misma regla que ciudad.preparar: si el punto medio del tramo no cae dentro
de un polígono de acera del Ayuntamiento, se usa la acera medida más cercana a menos
de 15 m. Hace copia de seguridad de grafo.npz antes de escribir.

    .venv/bin/python -m ciudad.anchos
"""

import shutil

import numpy as np

from ciudad.preparar import VERSION, nearest_sidewalk_width


def main():
    path = VERSION / "grafo.npz"
    with np.load(path) as stored:
        arrays = {key: stored[key] for key in stored.files}
    sizes = arrays["sizes"]
    known = lambda: ~np.isnan(arrays["attrs"][:, 0]) | ~np.isnan(arrays["explicit_width"])
    before = sizes[known()].sum() / sizes.sum()
    mid = (arrays["xy"][arrays["a"]] + arrays["xy"][arrays["b"]]) * 0.5
    attrs = arrays["attrs"].copy()
    filled = nearest_sidewalk_width(attrs, mid)
    arrays["attrs"] = attrs
    after = sizes[known()].sum() / sizes.sum()
    # La copia va fuera de datos/ciudad para que no entre en la imagen ni en la Release.
    backup = VERSION.parent / "respaldos" / "grafo.antes-anchos.npz"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    np.savez_compressed(path, **arrays)
    print(
        f"Ancho de acera: {filled:,} tramos completados · cobertura por longitud "
        f"{before:.1%} → {after:.1%} · copia en {backup.name}",
        flush=True,
    )


if __name__ == "__main__":
    main()
