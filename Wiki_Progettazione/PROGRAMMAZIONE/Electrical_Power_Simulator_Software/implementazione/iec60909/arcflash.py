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

Estensioni:
- oltre 15 kV il calcolo usa il metodo di Lee (IEEE 1584-2002 eq. 8–9,
  richiamato dalla 2018 per le tensioni fuori dal campo del modello), con
  corrente d'arco uguale alla corrente franca;
- calcolo a più intervalli con correnti franche diverse (es. contributo dei
  motori che si esaurisce): somma delle energie, tempo di eliminazione dal
  consumo della protezione Σ Δt_k/t(I_k) = 1;
- corrente continua (NFPA 70E, allegato D.5) in `iec60909.arcflash_dc`.

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
    # intervalli del calcolo: corrente franca, corrente d'arco, durata, energia
    steps: list[dict] = field(default_factory=list)

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

    def operate_ms(self, i_arc_ka: float, current_ratio: Optional[float] = None) -> Optional[float]:
        """Tempo di eliminazione (ms) senza il limite max_time_ms; None se la protezione non interviene.

        current_ratio: quota della corrente d'arco vista dalla protezione (default
        quella della protezione; nel calcolo a più intervalli può cambiare).
        """
        ratio = self.current_ratio if current_ratio is None else current_ratio
        i_ka = i_arc_ka * ratio
        if self.device is not None:
            from .coordination import trip_time_s

            t = trip_time_s(self.device, i_ka * 1000.0)
            return None if t is None else t * 1000.0
        if self.time_ms is not None:
            return self.time_ms
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
            return None
        return min(times) + self.breaker_time_ms

    def clearing_time_ms(self, i_arc_ka: float, current_ratio: Optional[float] = None) -> float:
        t = self.operate_ms(i_arc_ka, current_ratio)
        return self.max_time_ms if t is None else min(t, self.max_time_ms)  # non interviene: tempo massimo


# --- metodo di Lee (tensioni oltre 15 kV) ---------------------------------------------------

METHOD_IEEE = "IEEE 1584-2018"
METHOD_LEE = "Lee"
# IEEE 1584-2002 eq. 8–9 (richiamate dalla 2018 oltre il campo del modello) e NFPA 70E D.2:
# E [J/cm²] = 2,142·10⁶·V[kV]·Ibf[kA]·t[s]/D[mm]²; in cal/cm² il coefficiente è 5,12·10⁵
LEE_K = 2.142e6


def lee_energy(v_kv: float, ibf_ka: float, t_ms: float, distance_mm: float) -> float:
    """Metodo di Lee: energia incidente (J/cm²); l'arco ha la corrente franca Ibf."""
    return LEE_K * v_kv * ibf_ka * t_ms / 1000.0 / distance_mm**2


def lee_boundary(v_kv: float, ibf_ka: float, t_ms: float) -> float:
    """Metodo di Lee: confine dell'arco (mm), D_B = √(2,142·10⁶·V·Ibf·t/E_B)."""
    return math.sqrt(LEE_K * v_kv * ibf_ka * t_ms / 1000.0 / E_BOUNDARY_J_CM2)


# --- calcolo a più intervalli (corrente variabile durante l'arco) -----------------------------


@dataclass
class CurrentStep:
    """Intervallo con corrente franca costante.

    duration_ms: durata dell'intervallo (l'ultimo dura comunque fino
    all'eliminazione dell'arco); current_ratio: quota della corrente d'arco
    vista dalla protezione nell'intervallo (default quella della protezione).
    """

    ibf_ka: float
    duration_ms: Optional[float] = None
    current_ratio: Optional[float] = None


def _check_steps(steps: list[CurrentStep]) -> None:
    if not steps:
        raise ValueError("servono uno o più intervalli di corrente")
    for k, s in enumerate(steps):
        if s.ibf_ka is None or s.ibf_ka <= 0.0:
            raise ValueError("ogni intervallo richiede ibf_ka > 0")
        if k < len(steps) - 1 and (s.duration_ms is None or s.duration_ms <= 0.0):
            raise ValueError("ogni intervallo tranne l'ultimo richiede duration_ms > 0")


def arc_durations_ms(protection: Protection, i_arc_ka: list[float], steps: list[CurrentStep]) -> list[float]:
    """Durata dell'arco (ms) in ciascun intervallo, con la corrente variabile.

    In ogni intervallo la protezione consuma la frazione Δt_k/t(I_k) del proprio
    tempo di intervento alla corrente dell'intervallo; l'arco è eliminato quando
    Σ Δt_k/t(I_k) = 1. Negli intervalli in cui la protezione non interviene non
    c'è consumo. La durata totale è limitata a max_time_ms; l'elenco restituito
    termina all'intervallo in cui l'arco si estingue. Con un solo intervallo il
    risultato coincide con clearing_time_ms.
    """
    out: list[float] = []
    used = 0.0
    elapsed = 0.0
    for k, (step, i_arc) in enumerate(zip(steps, i_arc_ka)):
        dur = math.inf if k == len(steps) - 1 else step.duration_ms
        t_op = protection.operate_ms(i_arc, step.current_ratio)
        done = False
        if t_op is not None:
            need = (1.0 - used) * t_op
            if need <= dur:
                dur, done = need, True
            else:
                used += dur / t_op
        if elapsed + dur >= protection.max_time_ms:
            out.append(protection.max_time_ms - elapsed)
            break
        out.append(dur)
        elapsed += dur
        if done:
            break
    return out


def afb_from_energy(enc: Enclosure, v_key: float, e_j_cm2: float) -> float:
    """Confine dall'energia alla distanza di lavoro.

    Nelle eq. 3–6 l'energia dipende dalla distanza solo con il fattore D^k12,
    quindi D_B = D·(E_B/E)^(1/k12): coincide con le eq. 7–10 per un intervallo
    e vale anche per la somma delle energie di più intervalli.
    """
    k12 = _TABLE_E[v_key][enc.configuration][11]
    return enc.distance_mm * (E_BOUNDARY_J_CM2 / e_j_cm2) ** (1.0 / k12)


def ieee_multistep_case(enc: Enclosure, steps: list[CurrentStep], durations_ms: list[float],
                        reduced: bool = False) -> ArcFlashCase:
    """IEEE 1584 con più intervalli: somma delle energie (intermedie sopra 600 V).

    Sopra 600 V si sommano le energie intermedie a 600, 2700 e 14 300 V, si
    ricavano i confini intermedi dalle somme e poi si interpola (come
    arcflash-calc, multistep.py); fino a 600 V si somma l'energia finale.
    """
    parts = [(s, d, arc_flash_case(enc, s.ibf_ka, d, reduced)) for s, d in zip(steps, durations_ms) if d > 0.0]
    if not parts:
        raise ValueError("tempo d'arco nullo")
    rows = [dict(ibf_ka=s.ibf_ka, i_arc_ka=c.i_arc_ka, duration_ms=d, e_j_cm2=c.e_j_cm2) for s, d, c in parts]
    if len(durations_ms) == 1:
        c = parts[0][2]
        c.steps = rows
        return c
    if enc.voc_kv > 0.6:
        e_int = {v: sum(c.e_intermediate_j_cm2[v] for *_, c in parts) for v in _V_INTERMEDIATE}
        afb_int = {v: afb_from_energy(enc, v, e_int[v]) for v in _V_INTERMEDIATE}
        e = _interpolate(enc.voc_kv, *(e_int[v] for v in _V_INTERMEDIATE))
        afb = _interpolate(enc.voc_kv, *(afb_int[v] for v in _V_INTERMEDIATE))
    else:
        e_int, afb_int = {}, {}
        e = sum(c.e_j_cm2 for *_, c in parts)
        afb = afb_from_energy(enc, 0.6, e)
    first = arc_currents(enc, steps[0].ibf_ka)
    i_arc = first[1] if reduced else first[0]
    inter = first[3] if reduced else first[2]
    return ArcFlashCase(reduced, i_arc, sum(durations_ms), e, afb, inter, e_int, afb_int, rows)


def lee_case(v_kv: float, distance_mm: float, steps: list[CurrentStep], durations_ms: list[float]) -> ArcFlashCase:
    """Metodo di Lee, anche a più intervalli (energia e argomento del confine sono lineari in Ibf·t)."""
    rows = [dict(ibf_ka=s.ibf_ka, i_arc_ka=s.ibf_ka, duration_ms=d, e_j_cm2=lee_energy(v_kv, s.ibf_ka, d, distance_mm))
            for s, d in zip(steps, durations_ms)]
    ibf_t = sum(s.ibf_ka * d for s, d in zip(steps, durations_ms))
    e = sum(r["e_j_cm2"] for r in rows)
    afb = math.sqrt(LEE_K * v_kv * ibf_t / 1000.0 / E_BOUNDARY_J_CM2)
    return ArcFlashCase(False, steps[0].ibf_ka, sum(durations_ms), e, afb, steps=rows)


@dataclass
class ArcFlashResult:
    """Risultato completo in un punto.

    IEEE 1584: casi con corrente piena e ridotta; Lee e c.c.: un solo caso
    (`reduced` e `factors` sono None).
    """

    location: str
    voc_kv: float
    ibf_ka: float
    configuration: str
    distance_mm: float
    factors: Optional[CorrectionFactors]
    full: ArcFlashCase
    reduced: Optional[ArcFlashCase]
    method: str = METHOD_IEEE
    ibf_source: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def governing(self) -> ArcFlashCase:
        if self.reduced is None:
            return self.full
        return self.full if self.full.e_j_cm2 >= self.reduced.e_j_cm2 else self.reduced

    @property
    def e_cal_cm2(self) -> float:
        return self.governing.e_cal_cm2

    @property
    def afb_mm(self) -> float:
        if self.reduced is None:
            return self.full.afb_mm
        return max(self.full.afb_mm, self.reduced.afb_mm)

    @property
    def ppe_category(self) -> Optional[int]:
        """Categoria DPI NFPA 70E (1: 4, 2: 8, 3: 25, 4: 40 cal/cm²); None oltre 40."""
        e = self.e_cal_cm2
        for cat, limit in ((1, 4.0), (2, 8.0), (3, 25.0), (4, 40.0)):
            if e <= limit:
                return cat
        return None


def arc_flash(enc: Enclosure, ibf_ka: Optional[float], protection: Protection, location: str = "",
              steps: Optional[list[CurrentStep]] = None) -> ArcFlashResult:
    """Calcolo completo in c.a. con scelta automatica del metodo.

    Voc fino a 15 kV: IEEE 1584-2018, corrente d'arco piena e ridotta, ognuna
    con il suo tempo. Voc oltre 15 kV: metodo di Lee (corrente d'arco = Ibf).
    steps: intervalli con corrente franca diversa (calcolo a più intervalli);
    se assenti un solo intervallo con ibf_ka.
    """
    steps = [CurrentStep(ibf_ka)] if steps is None else list(steps)
    _check_steps(steps)
    if enc.voc_kv > 15.0:
        if enc.distance_mm <= 0.0:
            raise ValueError("Lee: distanza di lavoro non valida")
        durations = arc_durations_ms(protection, [s.ibf_ka for s in steps], steps)
        case = lee_case(enc.voc_kv, enc.distance_mm, steps[:len(durations)], durations)
        return ArcFlashResult(location, enc.voc_kv, steps[0].ibf_ka, enc.configuration, enc.distance_mm,
                              None, case, None, method=METHOD_LEE)
    for s in steps:
        check_range(enc, s.ibf_ka)
    currents = [arc_currents(enc, s.ibf_ka) for s in steps]
    cases = []
    for reduced in (False, True):
        i_arc = [c[1] if reduced else c[0] for c in currents]
        durations = arc_durations_ms(protection, i_arc, steps)
        cases.append(ieee_multistep_case(enc, steps[:len(durations)], durations, reduced))
    return ArcFlashResult(location, enc.voc_kv, steps[0].ibf_ka, enc.configuration, enc.distance_mm,
                          correction_factors(enc), cases[0], cases[1])


# --- studio sulla rete ----------------------------------------------------------------


def enclosure_for(point: "ArcFlashPoint", voc_kv: float, require_gap: bool = True) -> Enclosure:
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
    if not require_gap:
        data.setdefault("gap_mm", 0.0)
    for key in ("gap_mm", "distance_mm"):
        if key not in data:
            raise ValueError(f"{point.id}: serve {key} oppure equipment_class")
    return Enclosure(voc_kv, point.configuration, **data)


def protection_for(net: "Network", point: "ArcFlashPoint") -> Protection:
    """Protezione del punto dalla sezione `protection` (tempo, relè o dispositivo)."""
    prot = dict(point.protection)
    device_id = prot.pop("device", None)
    try:
        protection = Protection(**prot)
    except TypeError as exc:
        raise ValueError(f"{point.id}: dati di protezione non validi: {exc}") from None
    if protection.curve is not None and protection.curve not in IEC_CURVES:
        raise ValueError(f"{point.id}: curva sconosciuta {protection.curve!r} ({sorted(IEC_CURVES)})")
    if device_id is not None:
        from .coordination import validate_device

        devs = {d.id: d for d in net.protective_devices}
        if device_id not in devs:
            raise ValueError(f"{point.id}: dispositivo inesistente {device_id!r}")
        validate_device(devs[device_id])
        protection.device = devs[device_id]
    return protection


# Corrente franca Ibf dei punti in c.a. (il valore `ibf_ka` del punto ha sempre la precedenza)
IBF_SOURCES = {
    "iec60909": 'I"k trifase IEC 60909 (con il fattore di tensione c)',
    "c1": 'I"k trifase IEC 60909 riscalata a c = 1 (I"k/c)',
}
LV_SUSTAIN_KV = 0.24  # sotto 240 V l'arco può non autosostenersi
LV_SUSTAIN_KVA = 125.0
LV_SUSTAIN_KA = 2.0


def feeding_transformers(net: "Network", bus_id: str) -> list[tuple[str, float]]:
    """Trasformatori che alimentano il nodo: (id, potenza in kVA).

    Sono i trasformatori con un lato secondario (BT, o MT/BT per i tre
    avvolgimenti) sui nodi collegati a `bus_id` da sole linee, cioè sullo
    stesso livello di tensione: il trasformatore sul nodo o a monte nella rete
    radiale.
    """
    adj: dict[str, set[str]] = {b.id: set() for b in net.buses}
    for ln in net.lines:
        adj[ln.from_bus].add(ln.to_bus)
        adj[ln.to_bus].add(ln.from_bus)
    seen = {bus_id}
    stack = [bus_id]
    while stack:
        for nxt in adj[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    out = [(t.id, t.sr_mva * t.parallel * 1000.0) for t in net.transformers if t.lv_bus in seen]
    for t3 in net.transformers3w:
        if t3.lv_bus in seen:
            out.append((t3.id, t3.sr_hv_lv_mva * 1000.0))
        elif t3.mv_bus in seen:
            out.append((t3.id, t3.sr_hv_mv_mva * 1000.0))
    return out


def low_voltage_warnings(net: "Network", point: "ArcFlashPoint", voc_kv: float, ibf_ka: float) -> list[str]:
    """Avvisi per i punti sotto 240 V in cui l'arco potrebbe non autosostenersi."""
    if voc_kv >= LV_SUSTAIN_KV:
        return []
    out = []
    trs = feeding_transformers(net, point.bus)
    kva = sum(p for _, p in trs)
    if trs and kva < LV_SUSTAIN_KVA:
        names = ", ".join(t for t, _ in trs)
        out.append(f"{point.id}: Voc = {voc_kv * 1000:.0f} V < 240 V alimentato da trasformatori ({names}) per "
                   f"{kva:.0f} kVA in totale, meno di 125 kVA: l'arco potrebbe non autosostenersi "
                   "(IEEE 1584); il risultato è cautelativo")
    if ibf_ka < LV_SUSTAIN_KA:
        out.append(f"{point.id}: Voc = {voc_kv * 1000:.0f} V < 240 V e Ibf = {ibf_ka:.3f} kA < 2 kA: "
                   "arco sostenuto poco probabile (IEEE 1584-2018); il risultato è cautelativo")
    return out


def arc_flash_study(net: "Network", case: str = "max", ibf: str = "iec60909", **sc_options) -> list[ArcFlashResult]:
    """Arc flash in tutti i punti della sezione `arc_flash` della rete.

    Punti in c.a.: Voc è la tensione nominale del nodo e Ibf, salvo il valore
    `ibf_ka` del punto, la I"k trifase della IEC 60909 nel nodo (caso `case`,
    opzioni di `calculate`) con `ibf="iec60909"`, oppure la stessa corrente
    riscalata a c = 1 con `ibf="c1"`. Con `motor_decay_ms` il calcolo ha due
    intervalli: con i motori fino a quel tempo, poi con la I"k ricalcolata
    sulla rete senza motori; `steps` impone gli intervalli.
    Punti in c.c. (`system: "dc"`): vedi `iec60909.arcflash_dc`.
    """
    from .calc import calculate, fault_currents

    if not net.arc_flash:
        raise ValueError("la rete non contiene punti arc_flash")
    if ibf not in IBF_SOURCES:
        raise ValueError(f"origine della corrente franca non valida {ibf!r} ({sorted(IBF_SOURCES)})")
    for point in net.arc_flash:
        if point.system not in ("ac", "dc"):
            raise ValueError(f"{point.id}: system deve essere 'ac' o 'dc'")
    sc = calculate(net, case, **sc_options) if any(p.system == "ac" for p in net.arc_flash) else None
    cache: dict[str, object] = {}

    def without_motors():
        # rete senza motori: Ibf dopo l'esaurimento del loro contributo
        if "net" not in cache:
            import copy

            nm = copy.copy(net)
            nm.motors = []
            cache["net"] = nm
            cache["sc"] = calculate(nm, case, **sc_options)
        return cache["net"], cache["sc"]

    def ratio(network: "Network", point: "ArcFlashPoint", dev) -> float:
        # quota della corrente di guasto che attraversa il dispositivo (guasto trifase)
        fc = fault_currents(network, point.bus, case, sc_options.get("zf_ohm", 0j))
        return abs(fc.branch_ka[(dev.branch, dev.bus)]) / abs(fc.ikss_ka)

    out = []
    for point in net.arc_flash:
        if point.system == "dc":
            from .arcflash_dc import dc_point

            out.append(dc_point(net, point))
            continue
        if point.vdc_v is not None or point.r_system_ohm is not None:
            raise ValueError(f"{point.id}: vdc_v e r_system_ohm valgono solo per i punti in c.c.")
        if point.ibf_ka is not None and (point.motor_decay_ms is not None or point.steps):
            raise ValueError(f"{point.id}: ibf_ka è alternativo a motor_decay_ms e steps")
        if point.motor_decay_ms is not None and point.steps:
            raise ValueError(f"{point.id}: motor_decay_ms e steps sono alternativi")
        bus = sc.bus(point.bus)
        protection = protection_for(net, point)
        dev = protection.device
        if dev is not None:
            protection.current_ratio = ratio(net, point, dev)
        scale = 1.0 / bus.c if ibf == "c1" else 1.0
        source = IBF_SOURCES[ibf]
        if point.steps:
            try:
                steps = [CurrentStep(**s) for s in point.steps]
            except TypeError as exc:
                raise ValueError(f"{point.id}: intervalli non validi: {exc}") from None
            source = "intervalli imposti nel punto"
        elif point.ibf_ka is not None:
            steps = [CurrentStep(point.ibf_ka)]
            source = "imposta nel punto"
        elif point.motor_decay_ms is not None:
            if point.motor_decay_ms <= 0.0:
                raise ValueError(f"{point.id}: motor_decay_ms deve essere positivo")
            nm, sc_nm = without_motors()
            steps = [CurrentStep(float(bus.ikss3_ka) * scale, point.motor_decay_ms),
                     CurrentStep(float(sc_nm.bus(point.bus).ikss3_ka) * scale, None,
                                 ratio(nm, point, dev) if dev is not None else None)]
            source += f"; motori esauriti dopo {point.motor_decay_ms:g} ms"
        else:
            steps = [CurrentStep(float(bus.ikss3_ka) * scale)]
        enc = enclosure_for(point, bus.un_kv, require_gap=bus.un_kv <= 15.0)
        try:
            res = arc_flash(enc, None, protection, location=point.id, steps=steps)
        except ValueError as exc:
            raise ValueError(f"{point.id}: {exc}") from None
        res.ibf_source = source
        res.warnings += low_voltage_warnings(net, point, bus.un_kv, steps[0].ibf_ka)
        out.append(res)
    return out


def results_to_dict(results: list[ArcFlashResult]) -> list[dict]:
    import dataclasses

    def case(c: Optional[ArcFlashCase]) -> Optional[dict]:
        return None if c is None else dict(dataclasses.asdict(c), e_cal_cm2=c.e_cal_cm2)

    rows = []
    for r in results:
        rows.append({
            "id": r.location, "method": r.method, "voc_kv": r.voc_kv, "ibf_ka": r.ibf_ka,
            "ibf_source": r.ibf_source, "configuration": r.configuration, "distance_mm": r.distance_mm,
            "factors": None if r.factors is None else dataclasses.asdict(r.factors),
            "full": case(r.full), "reduced": case(r.reduced),
            "e_cal_cm2": r.e_cal_cm2, "afb_mm": r.afb_mm, "ppe_category": r.ppe_category,
            "warnings": r.warnings,
        })
    return rows


def results_to_markdown(results: list[ArcFlashResult], title: str = "") -> str:
    out = [
        f"# Arc flash{' — ' + title if title else ''}",
        "",
        "Energia incidente alla distanza di lavoro. IEEE 1584-2018 (0,208–15 kV): caso con corrente "
        "d'arco piena e caso con corrente ridotta (VarCF), ciascuno con il suo tempo d'arco. Lee (oltre "
        "15 kV) e corrente continua (NFPA 70E, allegato D.5): un solo caso.",
        "",
        "| Punto | Metodo | Voc [kV] | Ibf [kA] | Conf. | D [mm] | Iarc [kA] | t [ms] | E [cal/cm²] "
        "| Iarc rid. [kA] | t rid. [ms] | E rid. [cal/cm²] | E [cal/cm²] | Confine [mm] | Cat. DPI |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        cat = "oltre 40 cal/cm²" if r.ppe_category is None else str(r.ppe_category)
        red = ("| — | — | — " if r.reduced is None else
               f"| {r.reduced.i_arc_ka:.3f} | {r.reduced.t_arc_ms:.1f} | {r.reduced.e_cal_cm2:.2f} ")
        out.append(
            f"| {r.location} | {r.method} | {r.voc_kv:g} | {r.ibf_ka:.3f} | {r.configuration} | {r.distance_mm:.0f} "
            f"| {r.full.i_arc_ka:.3f} | {r.full.t_arc_ms:.1f} | {r.full.e_cal_cm2:.2f} "
            + red + f"| **{r.e_cal_cm2:.2f}** | {r.afb_mm:.0f} | {cat} |"
        )
    multi = [r for r in results if any(len(c.steps) > 1 for c in (r.full, r.reduced) if c is not None)]
    if multi:
        out += ["", "## Calcolo a più intervalli", "",
                "| Punto | Caso | Ibf [kA] | Iarc [kA] | Durata [ms] | E [cal/cm²] |", "|---|---|---|---|---|---|"]
        for r in multi:
            for name, c in (("piena", r.full), ("ridotta", r.reduced)):
                if c is None:
                    continue
                for s in c.steps:
                    out.append(f"| {r.location} | {name} | {s['ibf_ka']:.3f} | {s['i_arc_ka']:.3f} "
                               f"| {s['duration_ms']:.1f} | {s['e_j_cm2'] / J_PER_CAL:.2f} |")
    warnings = [w for r in results for w in r.warnings]
    if warnings:
        out += ["", "## Avvertenze", ""] + [f"- {w}" for w in warnings]
    out += ["", "Categoria DPI secondo NFPA 70E (1: ≤ 4, 2: ≤ 8, 3: ≤ 25, 4: ≤ 40 cal/cm²), a titolo "
            "indicativo: la scelta dei DPI spetta al responsabile della valutazione del rischio."]
    return "\n".join(out) + "\n"
