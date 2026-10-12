"""Tabelle per il dimensionamento dei cavi BT.

- Portate e fattori di correzione: IEC 60364-5-52:2009, allegato B.
- Fattori k per la verifica al cortocircuito: IEC 60364-4-43, tabella 43A.
- Resistenze massime dei conduttori a 20 °C: IEC 60228, classe 2.
"""

from __future__ import annotations

from typing import Optional

SECTIONS = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400, 500, 630]

# temperatura massima di esercizio del conduttore [°C]
MAX_TEMPERATURE = {"pvc": 70.0, "xlpe": 90.0}

# IEC 60228, conduttori a corda rotonda (classe 2) non stagnati: resistenza massima in c.c. a 20 °C [Ω/km]
R20 = {
    "cu": {1.5: 12.1, 2.5: 7.41, 4: 4.61, 6: 3.08, 10: 1.83, 16: 1.15, 25: 0.727, 35: 0.524, 50: 0.387,
           70: 0.268, 95: 0.193, 120: 0.153, 150: 0.124, 185: 0.0991, 240: 0.0754, 300: 0.0601,
           400: 0.0470, 500: 0.0366, 630: 0.0283},
    "al": {10: 3.08, 16: 1.91, 25: 1.20, 35: 0.868, 50: 0.641, 70: 0.443, 95: 0.320, 120: 0.253,
           150: 0.206, 185: 0.164, 240: 0.125, 300: 0.100, 400: 0.0778, 500: 0.0605, 630: 0.0469},
}


def resistance_20c(material: str, section_mm2: float) -> float:
    try:
        return R20[material][section_mm2]
    except KeyError:
        raise ValueError(f"resistenza IEC 60228 non disponibile per {material} {section_mm2:g} mm²") from None


def next_section(s: float) -> float:
    """Sezione normalizzata uguale o immediatamente superiore."""
    return next(x for x in SECTIONS if x >= s - 1e-9)


def k_factor(material: str, insulation: str, section_mm2: Optional[float] = None) -> float:
    """k della IEC 60364-4-43, tabella 43A (conduttori di fase)."""
    if insulation == "pvc":
        if section_mm2 is not None and section_mm2 > 300:
            return {"cu": 103.0, "al": 68.0}[material]
        return {"cu": 115.0, "al": 76.0}[material]
    if insulation == "xlpe":
        return {"cu": 143.0, "al": 94.0}[material]
    raise ValueError(f"isolante non valido {insulation!r} (pvc, xlpe)")
