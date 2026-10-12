"""Energia incidente da arco elettrico (arc flash) secondo IEEE 1584-2018.

Modello empirico della norma per sistemi trifase in c.a. da 208 V a 15 kV:
1. corrente d'arco intermedia a 600, 2700 e 14 300 V (eq. 1, tabella 1) e
   corrente d'arco finale (interpolazione eq. 16–18 sopra 600 V, eq. 25 fino a
   600 V); corrente d'arco ridotta con il fattore di variazione VarCF
   (eq. 2, tabella 2);
2. fattore di correzione per le dimensioni dell'involucro CF (eq. 11–15,
   tabelle 6 e 7);
3. energia incidente intermedia e finale (eq. 3–6, tabelle 3–5,
   interpolazione eq. 19–21) e confine dell'arco (eq. 7–10, eq. 22–24),
   dove l'energia vale 1,2 cal/cm² (5,0208 J/cm²).

Il calcolo va eseguito due volte: con la corrente d'arco piena e con quella
ridotta, ciascuna con il proprio tempo di eliminazione dell'arco (che dipende
dalla protezione); si adotta il caso con energia maggiore.

Unità: tensioni in kV, correnti in kA, distanze in mm, tempi in ms, energia in
J/cm² (1 cal/cm² = 4,184 J/cm²).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .network import ArcFlashPoint, Network

J_PER_CAL = 4.184
E_BOUNDARY_J_CM2 = 1.2 * J_PER_CAL  # 1,2 cal/cm²
CONFIGURATIONS = ("VCB", "VCBB", "HCB", "VOA", "HOA")
_V_INTERMEDIATE = (0.6, 2.7, 14.3)

# Tabella 1: coefficienti della corrente d'arco intermedia (k1 … k10)
_TABLE_1 = {
    ("VCB", 0.6): (-0.04287, 1.035, -0.083, 0, 0, -4.783e-09, 1.962e-06, -0.000229, 0.003141, 1.092),
    ("VCB", 2.7): (0.0065, 1.001, -0.024, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729),
    ("VCB", 14.3): (0.005795, 1.015, -0.011, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729),
    ("VCBB", 0.6): (-0.017432, 0.98, -0.05, 0, 0, -5.767e-09, 2.524e-06, -0.00034, 0.01187, 1.013),
    ("VCBB", 2.7): (0.002823, 0.995, -0.0125, 0, -9.204e-11, 2.901e-08, -3.262e-06, 0.0001569, -0.004003, 0.9825),
    ("VCBB", 14.3): (0.014827, 1.01, -0.01, 0, -9.204e-11, 2.901e-08, -3.262e-06, 0.0001569, -0.004003, 0.9825),
    ("HCB", 0.6): (0.054922, 0.988, -0.11, 0, 0, -5.382e-09, 2.316e-06, -0.000302, 0.0091, 0.9725),
    ("HCB", 2.7): (0.001011, 1.003, -0.0249, 0, 0, 4.859e-10, -1.814e-07, -9.128e-06, -0.0007, 0.9881),
    ("HCB", 14.3): (0.008693, 0.999, -0.02, 0, -5.043e-11, 2.233e-08, -3.046e-06, 0.000116, -0.001145, 0.9839),
    ("VOA", 0.6): (0.043785, 1.04, -0.18, 0, 0, -4.783e-09, 1.962e-06, -0.000229, 0.003141, 1.092),
    ("VOA", 2.7): (-0.02395, 1.006, -0.0188, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729),
    ("VOA", 14.3): (0.005371, 1.0102, -0.029, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729),
    ("HOA", 0.6): (0.111147, 1.008, -0.24, 0, 0, -3.895e-09, 1.641e-06, -0.000197, 0.002615, 1.1),
    ("HOA", 2.7): (0.000435, 1.006, -0.038, 0, 0, 7.859e-10, -1.914e-07, -9.128e-06, -0.0007, 0.9981),
    ("HOA", 14.3): (0.000904, 0.999, -0.02, 0, 0, 7.859e-10, -1.914e-07, -9.128e-06, -0.0007, 0.9981),
}

# Tabella 2: fattore di variazione della corrente d'arco (k1 … k7, polinomio in Voc)
_TABLE_2 = {
    "VCB": (0, -0.0000014269, 0.000083137, -0.0019382, 0.022366, -0.12645, 0.30226),
    "VCBB": (1.138e-06, -6.0287e-05, 0.0012758, -0.013778, 0.080217, -0.24066, 0.33524),
    "HCB": (0, -3.097e-06, 0.00016405, -0.0033609, 0.033308, -0.16182, 0.34627),
    "VOA": (9.5606e-07, -5.1543e-05, 0.0011161, -0.01242, 0.075125, -0.23584, 0.33696),
    "HOA": (0, -3.1555e-06, 0.0001682, -0.0034607, 0.034124, -0.1599, 0.34629),
}

# Tabelle 3, 4, 5: coefficienti dell'energia incidente (k1 … k13) a 600, 2700, 14 300 V
_TABLE_E = {
    0.6: {
        "VCB": (0.753364, 0.566, 1.752636, 0, 0, -4.783e-09, 1.962e-06, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957),
        "VCBB": (3.068459, 0.26, -0.098107, 0, 0, -5.767e-09, 2.524e-06, -0.00034, 0.01187, 1.013, -0.06, -1.809, 1.19),
        "HCB": (4.073745, 0.344, -0.370259, 0, 0, -5.382e-09, 2.316e-06, -0.000302, 0.0091, 0.9725, 0, -2.03, 1.036),
        "VOA": (0.679294, 0.746, 1.222636, 0, 0, -4.783e-09, 1.962e-06, -0.000229, 0.003141, 1.092, 0, -1.598, 0.997),
        "HOA": (3.470417, 0.465, -0.261863, 0, 0, -3.895e-09, 1.641e-06, -0.000197, 0.002615, 1.1, 0, -1.99, 1.04),
    },
    2.7: {
        "VCB": (2.40021, 0.165, 0.354202, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729, 0, -1.569, 0.9778),
        "VCBB": (3.870592, 0.185, -0.736618, 0, -9.204e-11, 2.901e-08, -3.262e-06, 0.0001569, -0.004003, 0.9825, 0, -1.742, 1.09),
        "HCB": (3.486391, 0.177, -0.193101, 0, 0, 4.859e-10, -1.814e-07, -9.128e-06, -0.0007, 0.9881, 0.027, -1.723, 1.055),
        "VOA": (3.880724, 0.105, -1.906033, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729, 0, -1.515, 1.115),
        "HOA": (3.616266, 0.149, -0.761561, 0, 0, 7.859e-10, -1.914e-07, -9.128e-06, -0.0007, 0.9981, 0, -1.639, 1.078),
    },
    14.3: {
        "VCB": (3.825917, 0.11, -0.999749, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729, 0, -1.568, 0.99),
        "VCBB": (3.644309, 0.215, -0.585522, 0, -9.204e-11, 2.901e-08, -3.262e-06, 0.0001569, -0.004003, 0.9825, 0, -1.677, 1.06),
        "HCB": (3.044516, 0.125, 0.245106, 0, -5.043e-11, 2.233e-08, -3.046e-06, 0.000116, -0.001145, 0.9839, 0, -1.655, 1.084),
        "VOA": (3.405454, 0.12, -0.93245, -1.557e-12, 4.556e-10, -4.186e-08, 8.346e-07, 5.482e-05, -0.003191, 0.9729, 0, -1.534, 0.979),
        "HOA": (2.04049, 0.177, 1.005092, 0, 0, 7.859e-10, -1.914e-07, -9.128e-06, -0.0007, 0.9981, -0.05, -1.633, 1.151),
    },
}

# Tabella 7: coefficienti b1, b2, b3 del fattore CF (involucri tipici e poco profondi)
_TABLE_7 = {
    ("typical", "VCB"): (-0.000302, 0.03441, 0.4325),
    ("typical", "VCBB"): (-0.0002976, 0.032, 0.479),
    ("typical", "HCB"): (-0.0001923, 0.01935, 0.6899),
    ("shallow", "VCB"): (0.002222, -0.02556, 0.6222),
    ("shallow", "VCBB"): (-0.002778, 0.1194, -0.2778),
    ("shallow", "HCB"): (-0.0005556, 0.03722, 0.4778),
}

# Tabella 6 / eq. 11–12: costanti A e B per le dimensioni equivalenti
_TABLE_6_AB = {"VCB": (4.0, 20.0), "VCBB": (10.0, 24.0), "HCB": (10.0, 22.0)}

# Tabelle 8 e 10: valori tipici per classe di apparecchiatura
# (distanza tra le sbarre G, dimensioni dell'involucro A × L × P e distanza di lavoro D, in mm)
EQUIPMENT_CLASSES = {
    "quadro_mt_15kv": dict(gap_mm=152.0, height_mm=1143.0, width_mm=762.0, depth_mm=762.0, distance_mm=914.4),
    "ccm_mt_15kv": dict(gap_mm=152.0, height_mm=914.4, width_mm=914.4, depth_mm=914.4, distance_mm=914.4),
    "quadro_mt_5kv": dict(gap_mm=104.0, height_mm=914.4, width_mm=914.4, depth_mm=914.4, distance_mm=914.4),
    "quadro_mt_5kv_grande": dict(gap_mm=104.0, height_mm=1143.0, width_mm=762.0, depth_mm=762.0, distance_mm=914.4),
    "ccm_mt_5kv": dict(gap_mm=104.0, height_mm=660.4, width_mm=660.4, depth_mm=660.4, distance_mm=914.4),
    "quadro_bt": dict(gap_mm=32.0, height_mm=508.0, width_mm=508.0, depth_mm=508.0, distance_mm=609.6),
    "ccm_bt": dict(gap_mm=25.0, height_mm=355.6, width_mm=304.8, depth_mm=250.0, distance_mm=457.2),
    "ccm_bt_poco_profondo": dict(gap_mm=25.0, height_mm=355.6, width_mm=304.8, depth_mm=100.0, distance_mm=457.2),
    "pannello_bt": dict(gap_mm=25.0, height_mm=355.6, width_mm=304.8, depth_mm=250.0, distance_mm=457.2),
    "pannello_bt_poco_profondo": dict(gap_mm=25.0, height_mm=355.6, width_mm=304.8, depth_mm=100.0, distance_mm=457.2),
    "cassetta_di_derivazione": dict(gap_mm=13.0, height_mm=355.6, width_mm=304.8, depth_mm=250.0, distance_mm=457.2),
    "cassetta_di_derivazione_poco_profonda": dict(gap_mm=13.0, height_mm=355.6, width_mm=304.8, depth_mm=100.0, distance_mm=457.2),
}

MM_TO_IN = 0.03937  # fattore stampato nella tabella 6 della norma


@dataclass
class Enclosure:
    """Geometria del punto di lavoro (cella, quadro, cassetta)."""

    voc_kv: float  # tensione nominale (concatenata, a vuoto)
    configuration: str  # VCB, VCBB, HCB, VOA, HOA
    gap_mm: float  # distanza tra i conduttori
    distance_mm: float  # distanza di lavoro
    height_mm: float = 508.0
    width_mm: float = 508.0
    depth_mm: float = 508.0


@dataclass
class CorrectionFactors:
    var_cf: float  # fattore di variazione della corrente d'arco
    cf: float  # fattore di correzione per le dimensioni dell'involucro
    enclosure_type: Optional[str]  # "typical", "shallow" o None (all'aperto)
    width1_in: Optional[float] = None
    height1_in: Optional[float] = None
    ees_in: Optional[float] = None


@dataclass
class ArcFlashCase:
    """Risultato per una corrente d'arco (piena o ridotta) e il suo tempo d'arco."""

    reduced: bool
    i_arc_ka: float
    t_arc_ms: float
    e_j_cm2: float
    afb_mm: float
    i_arc_intermediate_ka: dict[float, float] = field(default_factory=dict)
    e_intermediate_j_cm2: dict[float, float] = field(default_factory=dict)
    afb_intermediate_mm: dict[float, float] = field(default_factory=dict)

    @property
    def e_cal_cm2(self) -> float:
        return self.e_j_cm2 / J_PER_CAL


def check_range(enc: Enclosure, ibf_ka: float) -> None:
    """Campo di validità del modello (IEEE 1584-2018, 4.2)."""
    if enc.configuration not in CONFIGURATIONS:
        raise ValueError(f"configurazione degli elettrodi non valida: {enc.configuration!r} {CONFIGURATIONS}")
    if not 0.208 <= enc.voc_kv <= 15.0:
        raise ValueError("IEEE 1584: tensione fuori dal campo 0,208–15 kV")
    if enc.voc_kv <= 0.6:
        if not 0.5 <= ibf_ka <= 106.0:
            raise ValueError("IEEE 1584: corrente di cortocircuito fuori dal campo 0,5–106 kA (≤ 600 V)")
        if not 6.35 <= enc.gap_mm <= 76.2:
            raise ValueError("IEEE 1584: distanza tra i conduttori fuori dal campo 6,35–76,2 mm (≤ 600 V)")
    else:
        if not 0.2 <= ibf_ka <= 65.0:
            raise ValueError("IEEE 1584: corrente di cortocircuito fuori dal campo 0,2–65 kA (> 600 V)")
        if not 19.05 <= enc.gap_mm <= 254.0:
            raise ValueError("IEEE 1584: distanza tra i conduttori fuori dal campo 19,05–254 mm (> 600 V)")
    if enc.distance_mm < 305.0:
        raise ValueError("IEEE 1584: distanza di lavoro inferiore a 305 mm")
    if enc.configuration in ("VCB", "VCBB", "HCB") and enc.width_mm < 4.0 * enc.gap_mm:
        raise ValueError("IEEE 1584: larghezza dell'involucro inferiore a 4 volte la distanza tra i conduttori")


def _poly(coeffs: tuple, x: float) -> float:
    """Polinomio con coefficienti dal grado massimo al termine noto."""
    out = 0.0
    for c in coeffs:
        out = out * x + c
    return out


def intermediate_arc_current(configuration: str, v_kv: float, ibf_ka: float, gap_mm: float) -> float:
    """Eq. 1: corrente d'arco media a 600, 2700 o 14 300 V."""
    k = _TABLE_1[(configuration, v_kv)]
    return 10 ** (k[0] + k[1] * math.log10(ibf_ka) + k[2] * math.log10(gap_mm)) * _poly(k[3:], ibf_ka)


def variation_factor(configuration: str, voc_kv: float) -> float:
    """Fattore di variazione della corrente d'arco VarCF (tabella 2)."""
    return _poly(_TABLE_2[configuration], voc_kv)


def correction_factors(enc: Enclosure) -> CorrectionFactors:
    """VarCF e fattore di correzione per le dimensioni dell'involucro CF (eq. 11–15)."""
    var_cf = variation_factor(enc.configuration, enc.voc_kv)
    if enc.configuration in ("VOA", "HOA"):
        return CorrectionFactors(var_cf, 1.0, None)
    shallow = enc.voc_kv < 0.6 and enc.height_mm < 508.0 and enc.width_mm < 508.0 and enc.depth_mm <= 203.2
    kind = "shallow" if shallow else "typical"
    a, b = _TABLE_6_AB[enc.configuration]

    def eq_11(dim_mm: float) -> float:
        # dimensione equivalente in pollici (eq. 11 e 12)
        return (660.4 + (dim_mm - 660.4) * (enc.voc_kv + a) / b) / 25.4

    def equivalent(dim_mm: float, is_height: bool) -> float:
        if dim_mm < 508.0:
            return 20.0 if kind == "typical" else MM_TO_IN * dim_mm
        if dim_mm <= 660.4:
            return MM_TO_IN * dim_mm
        if is_height and enc.configuration == "VCB":
            # altezza per VCB: misura reale fino a 1244,6 mm, poi 49 in
            return MM_TO_IN * dim_mm if dim_mm <= 1244.6 else 49.0
        return eq_11(min(dim_mm, 1244.6))

    w1 = equivalent(enc.width_mm, False)
    h1 = equivalent(enc.height_mm, True)
    ees = (h1 + w1) / 2.0  # eq. 13
    b1, b2, b3 = _TABLE_7[(kind, enc.configuration)]
    x = b1 * ees**2 + b2 * ees + b3
    cf = x if kind == "typical" else 1.0 / x  # eq. 14 e 15
    return CorrectionFactors(var_cf, cf, kind, w1, h1, ees)


def _energy_terms(enc: Enclosure, v_key: float, i_arc_ka: float, ibf_ka: float, cf: float,
                  i_arc_600_ka: Optional[float]) -> tuple[float, float]:
    """Esponente (senza il termine della distanza) e coefficiente k12 delle eq. 3–10."""
    k = _TABLE_E[v_key][enc.configuration]
    i_num = i_arc_ka if i_arc_600_ka is None else i_arc_600_ka
    x3 = k[2] * i_num / (_poly(k[3:10], ibf_ka) * ibf_ka)  # k4·Ibf⁷ + … + k10·Ibf
    expo = (k[0] + k[1] * math.log10(enc.gap_mm) + x3 + k[10] * math.log10(ibf_ka)
            + k[12] * math.log10(i_arc_ka) + math.log10(1.0 / cf))
    return expo, k[11]


def incident_energy(enc: Enclosure, v_key: float, i_arc_ka: float, ibf_ka: float, t_ms: float,
                    cf: float, i_arc_600_ka: Optional[float] = None) -> float:
    """Eq. 3–6: energia incidente (J/cm²) alla distanza di lavoro."""
    expo, k12 = _energy_terms(enc, v_key, i_arc_ka, ibf_ka, cf, i_arc_600_ka)
    return 12.552 / 50.0 * t_ms * 10 ** (expo + k12 * math.log10(enc.distance_mm))


def arc_flash_boundary(enc: Enclosure, v_key: float, i_arc_ka: float, ibf_ka: float, t_ms: float,
                       cf: float, i_arc_600_ka: Optional[float] = None) -> float:
    """Eq. 7–10: distanza (mm) a cui l'energia incidente vale 1,2 cal/cm²."""
    expo, k12 = _energy_terms(enc, v_key, i_arc_ka, ibf_ka, cf, i_arc_600_ka)
    return 10 ** ((expo - math.log10(20.0 / t_ms)) / -k12)


def _interpolate(voc_kv: float, x600: float, x2700: float, x14300: float) -> float:
    """Eq. 16–24: valore finale dai tre valori intermedi (Voc > 0,6 kV)."""
    x1 = (x2700 - x600) / 2.1 * (voc_kv - 2.7) + x2700
    x2 = (x14300 - x2700) / 11.6 * (voc_kv - 14.3) + x14300
    if voc_kv > 2.7:
        return x2
    return x1 * (2.7 - voc_kv) / 2.1 + x2 * (voc_kv - 0.6) / 2.1


def arc_currents(enc: Enclosure, ibf_ka: float) -> tuple[float, float, dict, dict, float]:
    """Correnti d'arco finali piena e ridotta, intermedie (piene e ridotte) e Iarc,600."""
    var_cf = variation_factor(enc.configuration, enc.voc_kv)
    red = 1.0 - 0.5 * var_cf  # eq. 2
    if enc.voc_kv > 0.6:
        full = {v: intermediate_arc_current(enc.configuration, v, ibf_ka, enc.gap_mm) for v in _V_INTERMEDIATE}
        reduced = {v: i * red for v, i in full.items()}
        i_full = _interpolate(enc.voc_kv, *(full[v] for v in _V_INTERMEDIATE))
        i_red = _interpolate(enc.voc_kv, *(reduced[v] for v in _V_INTERMEDIATE))
        return i_full, i_red, full, reduced, full[0.6]
    i600 = intermediate_arc_current(enc.configuration, 0.6, ibf_ka, enc.gap_mm)
    # eq. 25: corrente d'arco finale fino a 600 V
    i_full = 1.0 / math.sqrt((0.6 / enc.voc_kv) ** 2
                             * (1.0 / i600**2 - (0.6**2 - enc.voc_kv**2) / (0.6**2 * ibf_ka**2)))
    return i_full, i_full * red, {0.6: i600}, {0.6: i600 * red}, i600


def arc_flash_case(enc: Enclosure, ibf_ka: float, t_arc_ms: float, reduced: bool = False) -> ArcFlashCase:
    """Energia incidente e confine dell'arco per la corrente d'arco piena o ridotta.

    t_arc_ms: durata dell'arco (tempo di eliminazione della protezione per la
    corrente d'arco considerata).
    """
    check_range(enc, ibf_ka)
    cf = correction_factors(enc).cf
    i_full, i_red, inter_full, inter_red, i600 = arc_currents(enc, ibf_ka)
    i_arc = i_red if reduced else i_full
    inter = inter_red if reduced else inter_full
    if enc.voc_kv > 0.6:
        e_int = {v: incident_energy(enc, v, inter[v], ibf_ka, t_arc_ms, cf) for v in _V_INTERMEDIATE}
        afb_int = {v: arc_flash_boundary(enc, v, inter[v], ibf_ka, t_arc_ms, cf) for v in _V_INTERMEDIATE}
        e = _interpolate(enc.voc_kv, *(e_int[v] for v in _V_INTERMEDIATE))
        afb = _interpolate(enc.voc_kv, *(afb_int[v] for v in _V_INTERMEDIATE))
        return ArcFlashCase(reduced, i_arc, t_arc_ms, e, afb, inter, e_int, afb_int)
    # fino a 600 V (eq. 6 e 10): Iarc,600 della corrente piena anche nel caso ridotto
    e = incident_energy(enc, 0.6, i_arc, ibf_ka, t_arc_ms, cf, i_arc_600_ka=i600)
    afb = arc_flash_boundary(enc, 0.6, i_arc, ibf_ka, t_arc_ms, cf, i_arc_600_ka=i600)
    return ArcFlashCase(reduced, i_arc, t_arc_ms, e, afb, inter)


# --- protezione: tempo di eliminazione dell'arco ------------------------------------

# IEC 60255-151: t = TMS·k/((I/Is)^α − 1)
IEC_CURVES = {
    "SI": (0.14, 0.02),  # normalmente inversa
    "VI": (13.5, 1.0),  # molto inversa
    "EI": (80.0, 2.0),  # estremamente inversa
    "LTI": (120.0, 1.0),  # a tempo lungo
}


@dataclass
class Protection:
    """Protezione che elimina l'arco: tempo fisso oppure relè IEC 60255-151.

    Il relè vede la corrente d'arco moltiplicata per `current_ratio` (1 se tutta
    la corrente d'arco passa nel dispositivo; es. Un,BT/Un,MT per un arco sulle
    sbarre BT eliminato dalla protezione sul lato MT del trasformatore; soglie
    in kA riferite alla corrente vista dal relè); il tempo di eliminazione è il tempo del relè (soglia a tempo
    inverso e/o soglia istantanea, il minore) più il tempo di apertura
    dell'interruttore. Il tempo d'arco è limitato a max_time_ms (la norma
    suggerisce 2 s quando l'operatore può allontanarsi).
    """

    time_ms: Optional[float] = None
    curve: Optional[str] = None
    pickup_ka: Optional[float] = None
    tms: float = 1.0
    inst_pickup_ka: Optional[float] = None
    inst_time_ms: float = 0.0
    breaker_time_ms: float = 0.0
    max_time_ms: float = 2000.0
    current_ratio: float = 1.0
    # dispositivo della sezione protective_devices (impostato da arc_flash_study)
    device: Optional[object] = None

    def clearing_time_ms(self, i_arc_ka: float) -> float:
        i_ka = i_arc_ka * self.current_ratio
        if self.device is not None:
            from .coordination import trip_time_s

            t = trip_time_s(self.device, i_ka * 1000.0)
            return self.max_time_ms if t is None else min(t * 1000.0, self.max_time_ms)
        if self.time_ms is not None:
            return min(self.time_ms, self.max_time_ms)
        times = []
        if self.curve is not None:
            if self.pickup_ka is None:
                raise ValueError("protezione a tempo inverso senza soglia pickup_ka")
            k, alpha = IEC_CURVES[self.curve]
            m = i_ka / self.pickup_ka
            if m > 1.0:
                times.append(self.tms * k / (m**alpha - 1.0) * 1000.0)
        if self.inst_pickup_ka is not None and i_ka >= self.inst_pickup_ka:
            times.append(self.inst_time_ms)
        if not times:
            return self.max_time_ms  # la protezione non interviene: tempo massimo
        return min(min(times) + self.breaker_time_ms, self.max_time_ms)


@dataclass
class ArcFlashResult:
    """Risultato completo in un punto: casi con corrente piena e ridotta."""

    location: str
    voc_kv: float
    ibf_ka: float
    configuration: str
    distance_mm: float
    factors: CorrectionFactors
    full: ArcFlashCase
    reduced: ArcFlashCase

    @property
    def governing(self) -> ArcFlashCase:
        return self.full if self.full.e_j_cm2 >= self.reduced.e_j_cm2 else self.reduced

    @property
    def e_cal_cm2(self) -> float:
        return self.governing.e_cal_cm2

    @property
    def afb_mm(self) -> float:
        return max(self.full.afb_mm, self.reduced.afb_mm)

    @property
    def ppe_category(self) -> Optional[int]:
        """Categoria DPI NFPA 70E (1: 4, 2: 8, 3: 25, 4: 40 cal/cm²); None oltre 40."""
        e = self.e_cal_cm2
        for cat, limit in ((1, 4.0), (2, 8.0), (3, 25.0), (4, 40.0)):
            if e <= limit:
                return cat
        return None


def arc_flash(enc: Enclosure, ibf_ka: float, protection: Protection, location: str = "") -> ArcFlashResult:
    """Calcolo completo: corrente d'arco piena e ridotta, ognuna con il suo tempo."""
    check_range(enc, ibf_ka)
    i_full, i_red, *_ = arc_currents(enc, ibf_ka)
    full = arc_flash_case(enc, ibf_ka, protection.clearing_time_ms(i_full), reduced=False)
    reduced = arc_flash_case(enc, ibf_ka, protection.clearing_time_ms(i_red), reduced=True)
    return ArcFlashResult(location, enc.voc_kv, ibf_ka, enc.configuration, enc.distance_mm,
                          correction_factors(enc), full, reduced)


# --- studio sulla rete ----------------------------------------------------------------


def enclosure_for(point: "ArcFlashPoint", voc_kv: float) -> Enclosure:
    """Geometria del punto: valori tipici della classe di apparecchiatura e dati espliciti."""
    data = dict(height_mm=508.0, width_mm=508.0, depth_mm=508.0)
    if point.equipment_class is not None:
        if point.equipment_class not in EQUIPMENT_CLASSES:
            raise ValueError(f"{point.id}: classe di apparecchiatura sconosciuta {point.equipment_class!r} "
                             f"({sorted(EQUIPMENT_CLASSES)})")
        data.update(EQUIPMENT_CLASSES[point.equipment_class])
    for key in ("gap_mm", "distance_mm", "height_mm", "width_mm", "depth_mm"):
        if getattr(point, key) is not None:
            data[key] = getattr(point, key)
    for key in ("gap_mm", "distance_mm"):
        if key not in data:
            raise ValueError(f"{point.id}: serve {key} oppure equipment_class")
    return Enclosure(voc_kv, point.configuration, **data)


def arc_flash_study(net: "Network", case: str = "max", **sc_options) -> list[ArcFlashResult]:
    """Arc flash in tutti i punti della sezione `arc_flash` della rete.

    La corrente di cortocircuito franca Ibf è la I"k trifase della IEC 60909
    nel nodo (caso `case`, opzioni di `calculate`); Voc è la tensione nominale
    del nodo.
    """
    from .calc import calculate

    if not net.arc_flash:
        raise ValueError("la rete non contiene punti arc_flash")
    sc = calculate(net, case, **sc_options)
    out = []
    for point in net.arc_flash:
        bus = sc.bus(point.bus)
        enc = enclosure_for(point, bus.un_kv)
        prot = dict(point.protection)
        device_id = prot.pop("device", None)
        try:
            protection = Protection(**prot)
        except TypeError as exc:
            raise ValueError(f"{point.id}: dati di protezione non validi: {exc}") from None
        if device_id is not None:
            # dispositivo del coordinamento: vede la quota della corrente di guasto
            # che lo attraversa (rapporto dalle correnti nei rami del guasto trifase)
            from .calc import fault_currents
            from .coordination import validate_device

            devs = {d.id: d for d in net.protective_devices}
            if device_id not in devs:
                raise ValueError(f"{point.id}: dispositivo inesistente {device_id!r}")
            dev = devs[device_id]
            validate_device(dev)
            fc = fault_currents(net, point.bus, case, sc_options.get("zf_ohm", 0j))
            protection.device = dev
            protection.current_ratio = abs(fc.branch_ka[(dev.branch, dev.bus)]) / abs(fc.ikss_ka)
        if protection.curve is not None and protection.curve not in IEC_CURVES:
            raise ValueError(f"{point.id}: curva sconosciuta {protection.curve!r} ({sorted(IEC_CURVES)})")
        out.append(arc_flash(enc, bus.ikss3_ka, protection, location=point.id))
    return out


def results_to_dict(results: list[ArcFlashResult]) -> list[dict]:
    import dataclasses

    rows = []
    for r in results:
        rows.append({
            "id": r.location, "voc_kv": r.voc_kv, "ibf_ka": r.ibf_ka, "configuration": r.configuration,
            "distance_mm": r.distance_mm, "factors": dataclasses.asdict(r.factors),
            "full": dict(dataclasses.asdict(r.full), e_cal_cm2=r.full.e_cal_cm2),
            "reduced": dict(dataclasses.asdict(r.reduced), e_cal_cm2=r.reduced.e_cal_cm2),
            "e_cal_cm2": r.e_cal_cm2, "afb_mm": r.afb_mm, "ppe_category": r.ppe_category,
        })
    return rows


def results_to_markdown(results: list[ArcFlashResult], title: str = "") -> str:
    out = [
        f"# Arc flash IEEE 1584-2018{' — ' + title if title else ''}",
        "",
        "Energia incidente alla distanza di lavoro; per ogni punto il caso con corrente d'arco "
        "piena e quello con corrente ridotta (VarCF), ciascuno con il suo tempo d'arco.",
        "",
        "| Punto | Voc [kV] | Ibf [kA] | Conf. | D [mm] | Iarc [kA] | t [ms] | E [cal/cm²] "
        "| Iarc rid. [kA] | t rid. [ms] | E rid. [cal/cm²] | E [cal/cm²] | Confine [mm] | Cat. DPI |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        cat = "oltre 40 cal/cm²" if r.ppe_category is None else str(r.ppe_category)
        out.append(
            f"| {r.location} | {r.voc_kv:g} | {r.ibf_ka:.3f} | {r.configuration} | {r.distance_mm:.0f} "
            f"| {r.full.i_arc_ka:.3f} | {r.full.t_arc_ms:.1f} | {r.full.e_cal_cm2:.2f} "
            f"| {r.reduced.i_arc_ka:.3f} | {r.reduced.t_arc_ms:.1f} | {r.reduced.e_cal_cm2:.2f} "
            f"| **{r.e_cal_cm2:.2f}** | {r.afb_mm:.0f} | {cat} |"
        )
    out += ["", "Categoria DPI secondo NFPA 70E (1: ≤ 4, 2: ≤ 8, 3: ≤ 25, 4: ≤ 40 cal/cm²), a titolo "
            "indicativo: la scelta dei DPI spetta al responsabile della valutazione del rischio."]
    return "\n".join(out) + "\n"
