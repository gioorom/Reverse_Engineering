"""Tabelle per il dimensionamento dei cavi BT.

- Portate e fattori di correzione: IEC 60364-5-52:2009, allegato B.
- Fattori k per la verifica al cortocircuito: IEC 60364-4-43, tabella 43A.
- Resistenze massime dei conduttori a 20 °C: IEC 60228, classe 2.
"""

from __future__ import annotations

from typing import Optional

from . import _tabelle_iec60364 as _t

SECTIONS = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400, 500, 630]

# temperatura massima di esercizio del conduttore [°C]
MAX_TEMPERATURE = {"pvc": 70.0, "xlpe": 90.0}

# IEC 60228, conduttori a corda rotonda (classe 2) non stagnati: resistenza massima in c.c. a 20 °C [Ω/km]
R20 = _t.R20


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


# --- portate e fattori di correzione (IEC 60364-5-52, allegato B) -------------------------

AIR_ARRANGEMENTS = tuple(sorted(_t.K_GROUP_AIR))  # B.52.17, voci 1-5
D2_SPACINGS = tuple(sorted(_t.K_GROUP_D2))  # B.52.18, cavi direttamente interrati
D1_SPACINGS = tuple(sorted({sp for _, sp in _t.K_GROUP_D1}))  # B.52.19, cavi in tubi interrati


def _insulation(insulation: str) -> str:
    ins = {"epr": "xlpe"}.get(insulation, insulation)
    if ins not in ("pvc", "xlpe"):
        raise ValueError(f"isolante non valido {insulation!r} (pvc, xlpe, epr)")
    return ins


def _lookup(table: dict, x: float, what: str) -> float:
    if x in table:
        return table[x]
    keys = sorted(table)
    if x < keys[0] or x > keys[-1]:
        raise ValueError(f"{what}: valore {x:g} fuori tabella ({keys[0]:g}–{keys[-1]:g})")
    hi = next(k for k in keys if k > x)
    lo = max(k for k in keys if k < x)
    return table[lo] + (table[hi] - table[lo]) * (x - lo) / (hi - lo)  # interpolazione lineare


def ampacity_key(material: str, insulation: str, loaded: int, method: str,
                 arrangement: Optional[str] = None) -> tuple:
    """Chiave della colonna di portata: tabelle B.52.2-B.52.5 (A1-D2) e B.52.10-B.52.13 (E, F, G)."""
    if material not in ("cu", "al"):
        raise ValueError(f"materiale non valido {material!r} (cu, al)")
    if loaded not in (2, 3):
        raise ValueError("i conduttori caricati sono 2 o 3")
    method = method.upper()
    ins = _insulation(insulation)
    if method in ("F", "G") and loaded == 3:
        default = "trefoil" if method == "F" else "horizontal"
        method = f"{method}:{arrangement or default}"
    elif arrangement is not None:
        raise ValueError(f"arrangement vale solo per i metodi F e G con 3 conduttori caricati")
    key = (material, ins, loaded, method)
    if key not in _t.AMPACITY:
        raise ValueError(f"portata non tabellata per {material} {ins} {loaded} conduttori caricati, metodo {method}")
    return key


def ampacity_table(material: str, insulation: str, loaded: int, method: str, cores: str = "multi",
                   arrangement: Optional[str] = None) -> dict[float, float]:
    return _t.AMPACITY[ampacity_key(material, insulation, loaded, method, arrangement)]


def confidence_note(key: tuple, section_mm2: float) -> Optional[str]:
    """None se il valore è confermato da almeno due fonti indipendenti, altrimenti la nota."""
    return _t.CONFIDENCE.get(key + (float(section_mm2),))


def _grouping(table: dict[int, float], circuits: int, what: str, flat_after_max: bool = False) -> float:
    counts = sorted(table)
    if circuits > counts[-1]:
        if flat_after_max:  # file singole: nessuna ulteriore riduzione oltre 9 circuiti
            return table[counts[-1]]
        raise ValueError(f"{what}: oltre {counts[-1]} circuiti non tabellato")
    n = next(c for c in counts if c >= circuits)  # numero tabellato successivo (a favore di sicurezza)
    return table[n]


def correction_factors(insulation: str, method: str, ambient_c: Optional[float], soil: Optional[float],
                       grouping: Optional[str], circuits: int, cores: str = "multi") -> dict[str, float]:
    """Fattori di correzione diversi da 1, per nome (B.52.14-B.52.19)."""
    ins = _insulation(insulation)
    method = method.upper()
    out: dict[str, float] = {}
    buried = method in ("D1", "D2")
    if ambient_c is not None and ambient_c != (20.0 if buried else 30.0):
        tbl = (_t.K_GROUND if buried else _t.K_AIR)[ins]
        out["temperatura"] = _lookup(tbl, ambient_c, "temperatura " + ("del terreno" if buried else "dell'aria"))
    if soil is not None and soil != 2.5:
        if not buried:
            raise ValueError("la resistività del terreno vale solo per i metodi D1 e D2")
        out["terreno"] = _lookup(_t.K_SOIL[method], soil, "resistività termica del terreno")
    if circuits > 1:
        if method == "D2":
            if grouping not in _t.K_GROUP_D2:
                raise ValueError(f"metodo D2: grouping tra {', '.join(D2_SPACINGS)}")
            out["raggruppamento"] = _grouping(_t.K_GROUP_D2[grouping], circuits, "B.52.18")
        elif method == "D1":
            if (cores, grouping) not in _t.K_GROUP_D1:
                raise ValueError(f"metodo D1: grouping tra {', '.join(D1_SPACINGS)}")
            out["raggruppamento"] = _grouping(_t.K_GROUP_D1[(cores, grouping)], circuits, "B.52.19")
        else:
            if grouping not in _t.K_GROUP_AIR:
                raise ValueError(f"raggruppamento in aria: grouping tra {', '.join(AIR_ARRANGEMENTS)}")
            out["raggruppamento"] = _grouping(_t.K_GROUP_AIR[grouping], circuits, "B.52.17",
                                              flat_after_max=grouping != "bunched")
    return out
