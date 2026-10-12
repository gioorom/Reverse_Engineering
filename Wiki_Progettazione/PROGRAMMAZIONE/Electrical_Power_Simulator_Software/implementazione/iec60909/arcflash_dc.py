"""Energia incidente da arco elettrico in corrente continua (NFPA 70E, allegato D.5).

Due metodi:

1. **Massima potenza** (D.5.1, Doan 2010): la potenza dell'arco è massima
   quando la tensione d'arco vale metà della tensione del sistema, quindi
   Iarc = 0,5·Ibf e
   E = 0,01·Vsys·Iarc·Tarc/D²   [cal/cm²; Vsys in V, Iarc in A, Tarc in s, D in cm].
   Il coefficiente 0,01 ≈ 0,5/(4π·4,184) = 0,00951: metà della potenza
   Vsys·Iarc irradiata su una sfera di raggio D.
2. **Resistenza d'arco** (D.5.2, Ammerman et al. 2010 con il modello di
   Stokes e Oppenlander 1991): resistenza dell'arco
   Rarc = (20 + 0,534·G)/Iarc^0,88   [Ω; G in mm, Iarc in A],
   corrente d'arco dalla soluzione di Iarc = Vsys/(Rsys + Rarc), potenza
   Parc = Iarc²·Rarc = Varc·Iarc e energia irradiata su una sfera
   E = Parc·Tarc/(4π·D²)   [J/cm²; D in cm],
   cioè 0,019·Varc·Iarc·Tarc/D² in cal/cm². Con Varc = Vsys/2 ritrova il
   metodo della massima potenza (0,0095 contro 0,01).

Arco in involucro: le formule valgono per l'arco in aria libera; per l'arco in
una cella NFPA 70E (D.5.1, sulla base delle prove in c.a. di Wilkins) indica
che un moltiplicatore fino a 3 è prudente. Il fattore è `enclosure_factor`
(default 3 per le configurazioni in cella, 1 per VOA e HOA).

Unità dell'interfaccia: tensione in V, correnti in kA, resistenze in Ω,
distanze in mm, tempi in ms, energia in J/cm².
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from .arcflash import (
    E_BOUNDARY_J_CM2,
    J_PER_CAL,
    ArcFlashCase,
    ArcFlashResult,
    Protection,
    enclosure_for,
    protection_for,
)

if TYPE_CHECKING:
    from .network import ArcFlashPoint, Network

METHOD_DOAN = "NFPA 70E D.5.1 c.c. (Doan)"
METHOD_STOKES = "NFPA 70E D.5.2 c.c. (Stokes-Oppenlander)"
DC_METHODS = {"doan": METHOD_DOAN, "stokes": METHOD_STOKES}
DC_BOX_FACTOR = 3.0  # arco in involucro (NFPA 70E D.5.1)
DOAN_K = 0.01  # cal/cm² con V, A, s, cm


def doan_energy(vdc_v: float, i_arc_ka: float, t_ms: float, distance_mm: float, factor: float = 1.0) -> float:
    """Metodo della massima potenza: energia incidente (J/cm²) con Iarc = 0,5·Ibf."""
    e_cal = DOAN_K * vdc_v * (i_arc_ka * 1000.0) * (t_ms / 1000.0) / (distance_mm / 10.0) ** 2
    return factor * e_cal * J_PER_CAL


def doan_boundary(vdc_v: float, i_arc_ka: float, t_ms: float, factor: float = 1.0) -> float:
    """Metodo della massima potenza: distanza (mm) a cui l'energia vale 1,2 cal/cm²."""
    e_b_cal = E_BOUNDARY_J_CM2 / J_PER_CAL
    return 10.0 * math.sqrt(factor * DOAN_K * vdc_v * i_arc_ka * 1000.0 * t_ms / 1000.0 / e_b_cal)


def stokes_arc_resistance(i_arc_ka: float, gap_mm: float) -> float:
    """Resistenza dell'arco (Ω) di Stokes e Oppenlander: (20 + 0,534·G)/Iarc^0,88, Iarc in A."""
    return (20.0 + 0.534 * gap_mm) / (i_arc_ka * 1000.0) ** 0.88


def stokes_arc_current(vdc_v: float, r_system_ohm: float, gap_mm: float) -> float:
    """Corrente d'arco (kA): soluzione di Iarc = Vsys/(Rsys + Rarc(Iarc)).

    f(I) = Rsys·I + (20 + 0,534·G)·I^0,12 − Vsys è crescente, negativa per
    I → 0 e positiva per I = Vsys/Rsys: la soluzione esiste ed è unica
    (bisezione).
    """
    if vdc_v <= 0.0 or r_system_ohm <= 0.0:
        raise ValueError("c.c.: servono tensione e resistenza del sistema positive")
    a = 20.0 + 0.534 * gap_mm
    lo, hi = 0.0, vdc_v / r_system_ohm
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if r_system_ohm * mid + a * mid**0.12 - vdc_v > 0.0:
            hi = mid
        else:
            lo = mid
        if hi - lo <= 1e-13 * hi:
            break
    return 0.5 * (lo + hi) / 1000.0


def stokes_energy(i_arc_ka: float, r_arc_ohm: float, t_ms: float, distance_mm: float, factor: float = 1.0) -> float:
    """Energia incidente (J/cm²): Parc·Tarc/(4π·D²), Parc = Iarc²·Rarc."""
    p_w = (i_arc_ka * 1000.0) ** 2 * r_arc_ohm
    return factor * p_w * t_ms / 1000.0 / (4.0 * math.pi * (distance_mm / 10.0) ** 2)


def stokes_boundary(i_arc_ka: float, r_arc_ohm: float, t_ms: float, factor: float = 1.0) -> float:
    """Distanza (mm) a cui l'energia vale 1,2 cal/cm²."""
    p_w = (i_arc_ka * 1000.0) ** 2 * r_arc_ohm
    return 10.0 * math.sqrt(factor * p_w * t_ms / 1000.0 / (4.0 * math.pi * E_BOUNDARY_J_CM2))


def dc_arc_flash(vdc_v: float, distance_mm: float, protection: Protection, *, ibf_ka: Optional[float] = None,
                 r_system_ohm: Optional[float] = None, method: str = "doan", gap_mm: Optional[float] = None,
                 enclosure_factor: float = DC_BOX_FACTOR, location: str = "",
                 configuration: str = "VCB") -> ArcFlashResult:
    """Arc flash in c.c. in un punto.

    La corrente franca è `ibf_ka` oppure Vsys/Rsys; il metodo della resistenza
    d'arco usa Rsys (ricavata da Vsys/Ibf se non indicata) e la distanza tra
    i conduttori `gap_mm`. Il tempo d'arco è quello della protezione alla
    corrente d'arco.
    """
    if method not in DC_METHODS:
        raise ValueError(f"metodo c.c. non valido {method!r} ({sorted(DC_METHODS)})")
    if vdc_v is None or vdc_v <= 0.0:
        raise ValueError("c.c.: serve la tensione vdc_v > 0")
    if distance_mm is None or distance_mm <= 0.0:
        raise ValueError("c.c.: serve la distanza di lavoro")
    if enclosure_factor <= 0.0:
        raise ValueError("c.c.: il fattore per l'arco in involucro deve essere positivo")
    if ibf_ka is None and r_system_ohm is None:
        raise ValueError("c.c.: serve ibf_ka oppure r_system_ohm")
    if ibf_ka is None:
        if r_system_ohm <= 0.0:
            raise ValueError("c.c.: r_system_ohm deve essere positiva")
        ibf_ka = vdc_v / r_system_ohm / 1000.0
    if ibf_ka <= 0.0:
        raise ValueError("c.c.: ibf_ka deve essere positiva")
    if r_system_ohm is None:
        r_system_ohm = vdc_v / (ibf_ka * 1000.0)
    if method == "doan":
        i_arc = 0.5 * ibf_ka
        t = protection.clearing_time_ms(i_arc)
        e = doan_energy(vdc_v, i_arc, t, distance_mm, enclosure_factor)
        afb = doan_boundary(vdc_v, i_arc, t, enclosure_factor)
        r_arc = r_system_ohm  # alla massima potenza Rarc = Rsys
    else:
        if gap_mm is None or gap_mm <= 0.0:
            raise ValueError("c.c.: il metodo di Stokes-Oppenlander richiede gap_mm")
        i_arc = stokes_arc_current(vdc_v, r_system_ohm, gap_mm)
        r_arc = stokes_arc_resistance(i_arc, gap_mm)
        t = protection.clearing_time_ms(i_arc)
        e = stokes_energy(i_arc, r_arc, t, distance_mm, enclosure_factor)
        afb = stokes_boundary(i_arc, r_arc, t, enclosure_factor)
    row = dict(ibf_ka=ibf_ka, i_arc_ka=i_arc, duration_ms=t, e_j_cm2=e, r_system_ohm=r_system_ohm,
               r_arc_ohm=r_arc, v_arc_v=i_arc * 1000.0 * r_arc, enclosure_factor=enclosure_factor)
    case = ArcFlashCase(False, i_arc, t, e, afb, steps=[row])
    return ArcFlashResult(location, vdc_v / 1000.0, ibf_ka, configuration, distance_mm, None, case, None,
                          method=DC_METHODS[method])


def dc_point(net: "Network", point: "ArcFlashPoint") -> ArcFlashResult:
    """Punto in c.c. della sezione `arc_flash` (`system: "dc"`).

    Dati: `vdc_v`, `ibf_ka` o `r_system_ohm`, `dc_method`, distanza di lavoro
    (e `gap_mm` per Stokes-Oppenlander) espliciti o dalla classe di
    apparecchiatura, `dc_enclosure_factor` (default 3 in cella, 1 per VOA e
    HOA). Un dispositivo della sezione protective_devices vede tutta la
    corrente d'arco (rapporto 1, salvo `current_ratio` nella protezione).
    """
    if point.motor_decay_ms is not None or point.steps:
        raise ValueError(f"{point.id}: il calcolo a più intervalli non è previsto in c.c.")
    if point.vdc_v is None:
        raise ValueError(f"{point.id}: per un punto in c.c. serve vdc_v")
    enc = enclosure_for(point, point.vdc_v / 1000.0, require_gap=point.dc_method == "stokes")
    protection = protection_for(net, point)
    factor = point.dc_enclosure_factor
    if factor is None:
        factor = 1.0 if point.configuration in ("VOA", "HOA") else DC_BOX_FACTOR
    try:
        res = dc_arc_flash(point.vdc_v, enc.distance_mm, protection, ibf_ka=point.ibf_ka,
                           r_system_ohm=point.r_system_ohm, method=point.dc_method, gap_mm=enc.gap_mm or None,
                           enclosure_factor=factor, location=point.id, configuration=point.configuration)
    except ValueError as exc:
        raise ValueError(f"{point.id}: {exc}") from None
    res.ibf_source = "imposta nel punto" if point.ibf_ka is not None else "Vsys/Rsys"
    return res
