#!/usr/bin/env python3
"""Aplica la paleta «Invernadero de Atocha» (propuesta #14) a la interfaz.

Sustituye cada color antiguo por el token de la paleta según su función. Los colores
con significado propio en el mapa (agua, aseos, aforos, posición) se mantienen.
Idempotente: se puede ejecutar más de una vez.

    python3 scripts/paleta.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "web/src/style.css",
    ROOT / "web/src/index.tsx",
    ROOT / "web/src/Map.tsx",
    ROOT / "web/src/Region.tsx",
    ROOT / "web/src/Informe.tsx",
    ROOT / "web/src/Sencillo.tsx",
    ROOT / "web/src/BankPlan.tsx",
    ROOT / "web/index.html",
    ROOT / "web/public/manifest.webmanifest",
]

INK = "#0b3b30"
MUTED = "#466960"
PRIMARY = "#0e5242"
ACCENT = "#1e7e5f"
HEAT = "#b8592a"
HEAT_DARK = "#8e4320"
WARN = "#cf8b23"
BG = "#f2f6f3"
SURFACE_SOFT = "#f7faf8"
TINT = "#e2efe8"
BORDER = "#cce0d5"
BORDER_STRONG = "#b4cfc2"
MAP_BG = "#e6efea"
WARM_BG = "#fbf0e6"
WARM_SOFT = "#fffaf4"
WARM_BORDER = "#e5be9e"

MAP = {
    # textos oscuros
    "#193e34": INK, "#173f36": INK, "#144b3b": INK, "#2e5f4c": INK, "#34584c": INK,
    # textos secundarios
    "#4d6a5e": MUTED, "#3c5d51": MUTED, "#49665b": MUTED, "#42665b": MUTED, "#476c5c": MUTED,
    "#356957": MUTED, "#5c7469": MUTED, "#526c60": MUTED, "#456459": MUTED, "#5b7468": MUTED,
    "#5d5a45": "#6b5a48",
    # verdes de acción
    "#1f6b52": PRIMARY, "#225b49": PRIMARY, "#157256": PRIMARY, "#17664f": PRIMARY,
    "#12694e": PRIMARY, "#20664f": PRIMARY, "#1d614c": PRIMARY, "#23644e": PRIMARY,
    "#205842": PRIMARY,
    "#208563": ACCENT, "#2d765f": ACCENT, "#2d8a4e": ACCENT, "#2f8f3a": ACCENT,
    # fondos claros y tintes
    "#f4f6ef": BG, "#f5f7ed": BG, "#f6f9f4": SURFACE_SOFT, "#fafcf8": SURFACE_SOFT,
    "#fbfdf9": SURFACE_SOFT, "#f4f8f1": SURFACE_SOFT, "#f3faee": SURFACE_SOFT,
    "#e3f1e6": TINT, "#e7f2e2": TINT, "#eef4ec": TINT, "#eaf1e8": TINT, "#edf5e5": TINT,
    "#edf5e3": TINT, "#edf4e9": TINT, "#edf4df": TINT, "#e3ece4": TINT,
    "#e4ece3": MAP_BG, "#dbe6dd": MAP_BG,
    # bordes
    "#cbdacf": BORDER, "#d6e2d8": BORDER, "#cddbd0": BORDER, "#d5e0d7": BORDER,
    "#ceded2": BORDER, "#ccdad0": BORDER, "#ccdacf": BORDER, "#e0e9df": BORDER,
    "#d8e3d9": BORDER, "#d8e1d7": BORDER,
    "#b9cdbf": BORDER_STRONG, "#bfd1c6": BORDER_STRONG, "#bed2c5": BORDER_STRONG,
    "#afc1b5": BORDER_STRONG, "#a8c1b1": BORDER_STRONG, "#a6bdae": BORDER_STRONG,
    "#9fb5aa": "#9cb8ab",
    # cálidos
    "#fff5d7": WARM_BG, "#fff0e7": WARM_BG, "#f2e8dd": WARM_BG, "#fffdf5": WARM_SOFT,
    "#e2c36d": WARM_BORDER, "#cd9e38": WARM_BORDER,
    # calor, avisos y semáforo
    "#d18a1c": WARN, "#bc7824": WARN, "#ab6814": "#a86d16",
    "#b94c1d": HEAT, "#cf6a33": HEAT, "#c56a1f": "#c2711f",
    "#9d3b1f": HEAT_DARK, "#9e3b1f": HEAT_DARK, "#9d532b": HEAT_DARK, "#803221": HEAT_DARK,
    "#875028": HEAT_DARK, "#754526": HEAT_DARK, "#6a4b2a": "#6b4a2e",
    # rampa del mapa regional (de claro a calor)
    "#f3efe0": "#f5ede4", "#f1d39a": "#ebcbaa", "#e7a25a": "#dda071",
}


def main():
    pattern = re.compile(r"#[0-9a-fA-F]{6}\b")
    for path in FILES:
        if not path.exists():
            continue
        text = path.read_text()
        new = pattern.sub(lambda m: MAP.get(m.group(0).lower(), m.group(0)), text)
        if new != text:
            path.write_text(new)
            print("paleta aplicada:", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
