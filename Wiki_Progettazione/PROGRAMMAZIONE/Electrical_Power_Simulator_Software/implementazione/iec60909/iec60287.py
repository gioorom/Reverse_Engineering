"""Portata dei cavi unipolari MT/AT in regime permanente (IEC 60287-1-1, IEC 60287-2-1).

Equazione della portata con fattore di carico 100 % (IEC 60287-1-1, 1.4.1.1):

    I = √{ [Δθ − Wd·(0,5·T1 + n·(T2 + T3 + T4))] /
           [R·T1 + n·R·(1 + λ1)·T2 + n·R·(1 + λ1 + λ2)·(T3 + T4)] }

con n = 1 (cavi unipolari), R resistenza in c.a. alla temperatura massima del
conduttore, Wd perdite dielettriche, λ1 rapporto tra le perdite nello schermo e
quelle nel conduttore, T1…T4 resistenze termiche (isolante, guaina interna,
guaina esterna, ambiente). Le perdite nello schermo dipendono dalla sua
temperatura, che si ricava iterando.

Unità SI interne: m, Ω/m, W/m, K·m/W.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# IEC 60287-1-1 tabella 1: resistività a 20 °C [Ω·m] e coefficiente di temperatura [1/K]
RHO_20 = {"cu": 1.7241e-8, "al": 2.8264e-8, "lead": 21.4e-8, "steel": 13.8e-8, "bronze": 3.5e-8}
ALPHA_20 = {"cu": 3.93e-3, "al": 4.03e-3, "lead": 4.0e-3, "steel": 4.5e-3, "bronze": 3.0e-3}
MU0_2PI = 2e-7  # μ0/2π [H/m]


@dataclass
class CableConstruction:
    """Cavo unipolare con isolante estruso. Diametri in mm."""

    conductor_material: str = "cu"
    area_mm2: float = 240.0
    conductor_diameter_mm: float = 18.4
    r20_ohm_per_km: Optional[float] = None  # default: IEC 60228 non disponibile qui -> obbligatorio
    ks: float = 1.0
    kp: float = 1.0
    insulation_thickness_mm: float = 8.0  # isolante + strati semiconduttori (t1)
    insulation_eps: float = 2.5
    insulation_tan_delta: float = 0.004
    insulation_rho_t: float = 3.5  # K·m/W
    screen_material: str = "cu"
    screen_area_mm2: float = 25.0
    screen_mean_diameter_mm: float = 37.0
    screen_kind: str = "wires"  # "wires" | "tape" | "sheath"
    screen_thickness_mm: Optional[float] = None  # per tubi/guaine (perdite per correnti parassite)
    bedding_thickness_mm: float = 0.0  # tra schermo e armatura (T2)
    bedding_rho_t: float = 6.0
    oversheath_thickness_mm: float = 3.0
    oversheath_rho_t: float = 3.5
    outer_diameter_mm: float = 45.0
    max_temperature_c: float = 90.0
    # fattori per gli schermi a fili (IEC 60287-2-1:2023): T1 e T3 moltiplicati
    t1_factor: float = 1.0
    t3_factor: float = 1.0


@dataclass
class Installation:
    """Tre cavi unipolari di un circuito trifase."""

    kind: str = "buried"  # "buried" (direttamente interrati)
    formation: str = "trefoil"  # "trefoil" | "flat"
    depth_m: float = 1.0  # profondità dell'asse (del cavo più profondo per il trifoglio: centro del gruppo)
    spacing_mm: Optional[float] = None  # interasse; None = a contatto
    soil_temperature_c: float = 20.0
    soil_rho_t: float = 1.0
    bonding: str = "both_ends"  # "both_ends" | "single_point" | "cross_bonded"
    frequency_hz: float = 50.0
    u0_kv: float = 12.0
    # altri circuiti uguali e ugualmente caricati: posizioni (x, y) [m] dei loro cavi
    other_cables_m: list = field(default_factory=list)


@dataclass
class RatingResult:
    current_a: float
    r_ac_ohm_per_m: float
    ys: float
    yp: float
    wc_w_per_m: float
    wd_w_per_m: float
    lambda1: float
    lambda1_circ: float
    lambda1_eddy: float
    t1: float
    t2: float
    t3: float
    t4: float
    screen_temperature_c: float
    iterations: int
    notes: list[str] = field(default_factory=list)


def _y(x2: float) -> float:
    """x⁴/(192 + 0,8·x⁴), valido per x ≤ 2,8 (IEC 60287-1-1, 2.1.2)."""
    x4 = x2 * x2
    return x4 / (192.0 + 0.8 * x4)


def ac_resistance(c: CableConstruction, inst: Installation, theta_c: float) -> tuple[float, float, float]:
    """R in c.a. [Ω/m], ys, yp (tre cavi unipolari)."""
    if c.r20_ohm_per_km is None:
        raise ValueError("serve r20_ohm_per_km (resistenza in c.c. a 20 °C, IEC 60228)")
    r0 = c.r20_ohm_per_km / 1000.0
    r1 = r0 * (1.0 + ALPHA_20[c.conductor_material] * (theta_c - 20.0))
    f = inst.frequency_hz
    xs2 = 8.0 * math.pi * f / r1 * 1e-7 * c.ks
    xp2 = 8.0 * math.pi * f / r1 * 1e-7 * c.kp
    if math.sqrt(xs2) > 2.8:
        raise ValueError("effetto pelle: xs > 2,8 fuori dal campo della formula")
    ys = _y(xs2)
    s = _spacing_m(c, inst)
    dc = c.conductor_diameter_mm / 1000.0
    if inst.formation == "flat":
        s = s * math.sqrt(2.0)  # s = √(s1·s2) con s2 = 2·s1 (IEC 60287-1-1, 2.1.4)
    fp = _y(xp2)
    yp = fp * (dc / s) ** 2 * (0.312 * (dc / s) ** 2 + 1.18 / (fp + 0.27))
    return r1 * (1.0 + ys + yp), ys, yp


def _spacing_m(c: CableConstruction, inst: Installation) -> float:
    return (inst.spacing_mm if inst.spacing_mm is not None else c.outer_diameter_mm) / 1000.0


def dielectric_loss(c: CableConstruction, inst: Installation) -> float:
    """Wd = ω·C·U0²·tanδ, C = ε/(18·ln(Di/dc))·10⁻⁹ F/m."""
    dc = c.conductor_diameter_mm
    di = dc + 2.0 * c.insulation_thickness_mm
    cap = c.insulation_eps / (18.0 * math.log(di / dc)) * 1e-9
    return 2.0 * math.pi * inst.frequency_hz * cap * (inst.u0_kv * 1e3) ** 2 * c.insulation_tan_delta


def screen_resistance(c: CableConstruction, theta_s: float) -> float:
    rho = RHO_20[c.screen_material]
    rs0 = rho / (c.screen_area_mm2 * 1e-6)
    return rs0 * (1.0 + ALPHA_20[c.screen_material] * (theta_s - 20.0))


def screen_loss_factor(c: CableConstruction, inst: Installation, r_ac: float, theta_s: float) -> tuple[float, float]:
    """λ1' (correnti di circolazione) e λ1'' (correnti parassite) per tre cavi unipolari."""
    rs = screen_resistance(c, theta_s)
    s = _spacing_m(c, inst)
    d = c.screen_mean_diameter_mm / 1000.0
    omega = 2.0 * math.pi * inst.frequency_hz
    lam_circ = 0.0
    if inst.bonding == "both_ends":
        if inst.formation == "trefoil":
            x = 2.0 * omega * 1e-7 * math.log(2.0 * s / d)
        else:  # in piano, con trasposizione regolare (IEC 60287-1-1, 2.3.1 b)
            x = 2.0 * omega * 1e-7 * math.log(2.0 * 2.0 ** (1.0 / 3.0) * s / d)
        lam_circ = rs / r_ac / (1.0 + (rs / x) ** 2)
    elif inst.bonding not in ("single_point", "cross_bonded"):
        raise ValueError(f"collegamento degli schermi non valido {inst.bonding!r}")
    # correnti parassite: trascurate per schermi a fili o nastri collegati alle due estremità
    # (IEC 60287-1-1, 2.3.1); per gli altri casi vedi eddy_loss_factor
    lam_eddy = 0.0
    return lam_circ, lam_eddy


def t1_single_core(c: CableConstruction) -> float:
    dc = c.conductor_diameter_mm
    return c.insulation_rho_t / (2.0 * math.pi) * math.log(1.0 + 2.0 * c.insulation_thickness_mm / dc) * c.t1_factor


def t2_bedding(c: CableConstruction) -> float:
    if c.bedding_thickness_mm <= 0:
        return 0.0
    d = c.screen_mean_diameter_mm  # diametro sotto lo strato (approssimato con quello medio dello schermo)
    return c.bedding_rho_t / (2.0 * math.pi) * math.log(1.0 + 2.0 * c.bedding_thickness_mm / d)


def t3_oversheath(c: CableConstruction) -> float:
    da = c.outer_diameter_mm - 2.0 * c.oversheath_thickness_mm
    return c.oversheath_rho_t / (2.0 * math.pi) * math.log(1.0 + 2.0 * c.oversheath_thickness_mm / da) * c.t3_factor


def t4_buried(c: CableConstruction, inst: Installation) -> float:
    """T4 per tre cavi unipolari direttamente interrati, ugualmente caricati
    (IEC 60287-2-1, 2.2.3): cavo più caldo, con il metodo delle immagini."""
    de = c.outer_diameter_mm / 1000.0
    rho = inst.soil_rho_t
    L = inst.depth_m
    if inst.formation == "trefoil" and inst.spacing_mm is None and not inst.other_cables_m:
        u = 2.0 * L / de
        return 1.5 * rho / math.pi * (math.log(2.0 * u) - 0.630)  # trifoglio a contatto
    s = _spacing_m(c, inst)
    if inst.formation == "trefoil":
        # vertici di un triangolo equilatero di lato s; L = profondità del centro del gruppo
        h = s * math.sqrt(3.0) / 2.0
        pos = [(0.0, L - 2 * h / 3), (-s / 2, L + h / 3), (s / 2, L + h / 3)]
    else:
        pos = [(-s, L), (0.0, L), (s, L)]
    pos += [tuple(p) for p in inst.other_cables_m]
    best = 0.0
    for i, (xi, yi) in enumerate(pos):
        u = 2.0 * yi / de
        t = math.log(u + math.sqrt(u * u - 1.0))
        for k, (xk, yk) in enumerate(pos):
            if k == i:
                continue
            d_direct = math.hypot(xi - xk, yi - yk)
            d_image = math.hypot(xi - xk, yi + yk)
            t += math.log(d_image / d_direct)
        best = max(best, rho / (2.0 * math.pi) * t)
    return best


def rating(c: CableConstruction, inst: Installation, max_iter: int = 50, tol: float = 1e-9) -> RatingResult:
    """Portata [A] di un circuito di tre cavi unipolari."""
    if inst.kind != "buried":
        raise ValueError(f"posa non supportata {inst.kind!r}")
    theta = c.max_temperature_c
    dtheta = theta - inst.soil_temperature_c
    r, ys, yp = ac_resistance(c, inst, theta)
    wd = dielectric_loss(c, inst)
    t1, t2, t3 = t1_single_core(c), t2_bedding(c), t3_oversheath(c)
    t4 = t4_buried(c, inst)
    theta_s = theta - 10.0
    i = 0.0
    lam_c = lam_e = 0.0
    for it in range(1, max_iter + 1):
        lam_c, lam_e = screen_loss_factor(c, inst, r, theta_s)
        lam1 = lam_c + lam_e
        num = dtheta - wd * (0.5 * t1 + t2 + t3 + t4)
        den = r * t1 + r * (1 + lam1) * t2 + r * (1 + lam1) * (t3 + t4)
        if num <= 0:
            raise ValueError("le perdite dielettriche da sole superano il salto termico ammesso")
        i = math.sqrt(num / den)
        new_theta_s = theta - (i * i * r + 0.5 * wd) * t1
        if abs(new_theta_s - theta_s) < tol:
            theta_s = new_theta_s
            break
        theta_s = new_theta_s
    return RatingResult(i, r, ys, yp, i * i * r, wd, lam_c + lam_e, lam_c, lam_e, t1, t2, t3, t4, theta_s, it)


def rating_of(cr) -> tuple[CableConstruction, RatingResult]:
    """Portata di una voce di cable_ratings."""
    try:
        c = CableConstruction(**cr.cable)
        inst = Installation(**cr.installation)
    except TypeError as e:
        raise ValueError(f"{cr.id}: {e}") from None
    return c, rating(c, inst)
