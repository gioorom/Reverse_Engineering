"""Portata dei cavi unipolari MT/AT in regime permanente (IEC 60287-1-1, IEC 60287-2-1).

Equazione della portata con fattore di carico 100 % (IEC 60287-1-1, 1.4.1.1):

    I = √{ [Δθ − Wd·(0,5·T1 + n·(T2 + T3 + T4))] /
           [R·T1 + n·R·(1 + λ1)·T2 + n·R·(1 + λ1 + λ2)·(T3 + T4)] }

con n = 1 (cavi unipolari), R resistenza in c.a. alla temperatura massima del
conduttore, Wd perdite dielettriche, λ1 = λ1' + λ1'' perdite nello schermo
(correnti di circolazione e parassite) riferite a quelle nel conduttore,
T1…T4 resistenze termiche (isolante, letto, guaina esterna, ambiente).
Le perdite nello schermo dipendono dalla sua temperatura e, nei tubi, T4'
dalla temperatura media dell'aria nel tubo: si itera fino a convergenza.

Unità SI interne: m, Ω/m, W/m, K·m/W; i dati sono in mm e Ω/km.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# IEC 60287-1-1 tabella 1: resistività a 20 °C [Ω·m] e coefficiente di temperatura [1/K]
RHO_20 = {"cu": 1.7241e-8, "al": 2.84e-8, "lead": 21.4e-8, "steel": 13.8e-8, "bronze": 3.5e-8}
ALPHA_20 = {"cu": 3.93e-3, "al": 4.03e-3, "lead": 4.0e-3, "steel": 4.5e-3, "bronze": 3.0e-3}
# IEC 60287-2-1 tabella 4: costanti U, V, Y per T4' (aria tra cavo e tubo)
DUCT_CONSTANTS = {"plastic": (1.87, 0.312, 0.0037)}


@dataclass
class CableConstruction:
    """Cavo unipolare con isolante estruso, descritto per strati (spessori in mm)."""

    conductor_material: str = "cu"
    area_mm2: float = 240.0
    conductor_diameter_mm: float = 18.4
    r20_ohm_per_km: Optional[float] = None  # default: IEC 60228 classe 2
    ks: float = 1.0  # IEC 60287-1-1 tabella 2 (corda rotonda, isolante estruso: 1 e 1)
    kp: float = 1.0
    conductor_screen_mm: float = 0.0
    insulation_mm: float = 5.5
    insulation_screen_mm: float = 0.0
    under_screen_mm: float = 0.0  # nastri tra semiconduttore esterno e schermo (parte di T1)
    under_screen_rho_t: float = 6.0
    insulation_eps: float = 2.5  # IEC 60287-1-1 tabella 3, XLPE
    insulation_tan_delta: float = 0.004  # XLPE fino a 18/30 kV (0,001 oltre)
    insulation_rho_t: float = 3.5  # K·m/W
    semicon_rho_t: Optional[float] = None  # strati semiconduttori (default: come l'isolante)
    screen_kind: str = "wires"  # "wires" (fili), "tape" (nastro), "sheath" (guaina tubolare)
    screen_material: str = "cu"
    screen_area_mm2: Optional[float] = None  # fili/nastro; per la guaina π·d·t
    screen_thickness_mm: float = 0.5  # spessore dello strato (diametro dei fili)
    screen_lay_factor: float = 1.0  # lunghezza effettiva dei fili per metro di cavo (cordatura)
    bedding_mm: float = 0.0
    bedding_rho_t: float = 6.0
    oversheath_mm: float = 3.0
    oversheath_rho_t: float = 3.5
    max_temperature_c: float = 90.0
    # fattori su T1 e T3 (None: automatici per il trifoglio interrato a contatto, IEC 60287-2-1
    # 4.2.4.3: T3 × 1,6; con schermo a fili e U0 ≤ 35 kV anche T1 × 1,07, edizione 2023)
    t1_factor: Optional[float] = None
    t3_factor: Optional[float] = None

    def diameters_mm(self) -> dict[str, float]:
        dc = self.conductor_diameter_mm
        d1 = dc + 2 * self.conductor_screen_mm
        di = d1 + 2 * self.insulation_mm
        d3 = di + 2 * self.insulation_screen_mm + 2 * self.under_screen_mm
        ds = d3 + 2 * self.screen_thickness_mm
        da = ds + 2 * self.bedding_mm
        de = da + 2 * self.oversheath_mm
        return {"conductor": dc, "conductor_screen": d1, "insulation": di, "insulation_screen": d3,
                "screen_mean": d3 + self.screen_thickness_mm, "screen": ds, "under_oversheath": da, "outer": de}


@dataclass
class Installation:
    """Circuito trifase di tre cavi unipolari."""

    kind: str = "buried"  # "buried" (interrati) | "ducts" (in tubi interrati) | "air" (in aria, all'ombra)
    formation: str = "trefoil"  # "trefoil" | "flat"
    transposed: bool = False  # formazione in piano con trasposizione regolare delle fasi
    depth_m: float = 1.0  # profondità dell'asse (trifoglio: baricentro del gruppo)
    spacing_mm: Optional[float] = None  # interasse; None = a contatto (cavi o tubi)
    soil_temperature_c: float = 20.0
    soil_rho_t: float = 1.0
    bonding: str = "both_ends"  # "both_ends" | "single_point" | "cross_bonded"
    eddy_both_ends: bool = False  # perdite parassite anche con schermi collegati alle due estremità
    frequency_hz: float = 50.0
    u0_kv: float = 12.0
    duct_inner_mm: Optional[float] = None
    duct_outer_mm: Optional[float] = None
    duct_type: str = "plastic"
    duct_rho_t: float = 3.5
    other_cables_m: list = field(default_factory=list)  # altri cavi uguali e ugualmente caricati: (x, y)
    # posa in aria (IEC 60287-2-1, 4.2.1): temperatura dell'aria e coefficienti Z, E, g della
    # tabella 2 per la disposizione; canaletta chiusa non riempita: perimetro utile p [m]
    air_temperature_c: float = 30.0
    air_z: Optional[float] = None
    air_e: Optional[float] = None
    air_g: Optional[float] = None
    trough_perimeter_m: Optional[float] = None


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
    cable: int = 0  # cavo che limita la portata (in piano: 0 esterno in ritardo, 1 centrale, 2 esterno in anticipo)
    currents_a: list = field(default_factory=list)  # portata di ciascun cavo


def _y(x2: float) -> float:
    """x⁴/(192 + 0,8·x⁴), valido per x ≤ 2,8 (IEC 60287-1-1, 2.1.2)."""
    x4 = x2 * x2
    return x4 / (192.0 + 0.8 * x4)


def _r0(c: CableConstruction) -> float:
    if c.r20_ohm_per_km is not None:
        return c.r20_ohm_per_km / 1000.0
    from .cable_tables import resistance_20c

    return resistance_20c(c.conductor_material, c.area_mm2) / 1000.0


def _axis_spacing_m(c: CableConstruction, inst: Installation) -> float:
    if inst.spacing_mm is not None:
        return inst.spacing_mm / 1000.0
    if inst.kind == "ducts":
        return inst.duct_outer_mm / 1000.0
    return c.diameters_mm()["outer"] / 1000.0


def ac_resistance(c: CableConstruction, inst: Installation, theta_c: float) -> tuple[float, float, float]:
    """R in c.a. [Ω/m], ys, yp per tre cavi unipolari (IEC 60287-1-1, 2.1)."""
    r1 = _r0(c) * (1.0 + ALPHA_20[c.conductor_material] * (theta_c - 20.0))
    f = inst.frequency_hz
    xs2 = 8.0 * math.pi * f / r1 * 1e-7 * c.ks
    xp2 = 8.0 * math.pi * f / r1 * 1e-7 * c.kp
    if xs2 > 2.8**2:
        raise ValueError("effetto pelle: xs > 2,8 fuori dal campo della formula")
    ys = _y(xs2)
    s = _axis_spacing_m(c, inst)
    if inst.formation == "flat":
        s = s * math.sqrt(2.0)  # s = √(s1·s2), s2 = 2·s1 (IEC 60287-1-1, 2.1.4)
    dc = c.conductor_diameter_mm / 1000.0
    fp = _y(xp2)
    yp = fp * (dc / s) ** 2 * (0.312 * (dc / s) ** 2 + 1.18 / (fp + 0.27))
    return r1 * (1.0 + ys + yp), ys, yp


def dielectric_loss(c: CableConstruction, inst: Installation) -> float:
    """Wd = ω·C·U0²·tanδ con C = ε/(18·ln(Di/dc))·10⁻⁹ F/m, dc sul semiconduttore interno."""
    d = c.diameters_mm()
    cap = c.insulation_eps / (18.0 * math.log(d["insulation"] / d["conductor_screen"])) * 1e-9
    return 2.0 * math.pi * inst.frequency_hz * cap * (inst.u0_kv * 1e3) ** 2 * c.insulation_tan_delta


def _screen_area_m2(c: CableConstruction) -> float:
    if c.screen_area_mm2 is not None:
        return c.screen_area_mm2 * 1e-6
    if c.screen_kind != "sheath":
        raise ValueError("per uno schermo a fili o a nastro serve screen_area_mm2")
    return math.pi * c.diameters_mm()["screen_mean"] * c.screen_thickness_mm * 1e-6


def screen_resistance(c: CableConstruction, theta_s: float) -> float:
    rs0 = RHO_20[c.screen_material] / _screen_area_m2(c) * c.screen_lay_factor
    return rs0 * (1.0 + ALPHA_20[c.screen_material] * (theta_s - 20.0))


def _f_reduction(m: float, n: float) -> float:
    """Riduzione delle perdite parassite per effetto delle correnti di circolazione (2.3.5)."""
    return (4 * m**2 * n**2 + (m + n) ** 2) / (4 * (m**2 + 1) * (n**2 + 1))


def screen_loss_factors(c: CableConstruction, inst: Installation, r_ac: float,
                        theta_s: list[float]) -> tuple[list[float], list[float], list[str]]:
    """λ1' (circolazione) e λ1'' (parassite) dei tre cavi (IEC 60287-1-1, 2.3).

    In piano: indice 0 cavo esterno con la fase in ritardo, 1 centrale, 2 esterno con la
    fase in anticipo; a trifoglio i tre cavi sono equivalenti."""
    notes: list[str] = []
    rs = [screen_resistance(c, t) for t in theta_s]
    s = _axis_spacing_m(c, inst)
    d = c.diameters_mm()["screen_mean"] / 1000.0
    omega = 2.0 * math.pi * inst.frequency_hz
    if inst.formation not in ("trefoil", "flat"):
        raise ValueError(f"formazione non valida {inst.formation!r} (trefoil, flat)")
    x = 2.0 * omega * 1e-7 * math.log(2.0 * s / d)  # reattanza dello schermo per due cavi adiacenti
    xm = 2.0 * omega * 1e-7 * math.log(2.0)  # mutua, cavo esterno-altri due (in piano)
    p_, q_ = x + xm, x - xm / 3.0
    if inst.bonding == "both_ends":
        eddy = inst.eddy_both_ends
        if inst.formation == "trefoil":
            lam_circ = [r / r_ac / (1.0 + (r / x) ** 2) for r in rs]
        elif inst.transposed:  # 2.3.2
            x1 = 2.0 * omega * 1e-7 * math.log(2.0 * 2.0 ** (1.0 / 3.0) * s / d)
            lam_circ = [r / r_ac / (1.0 + (r / x1) ** 2) for r in rs]
        else:  # 2.3.3: senza trasposizione, diverso per ogni cavo
            def outer(r: float, sign: float) -> float:
                return r / r_ac * (0.75 * p_**2 / (r**2 + p_**2) + 0.25 * q_**2 / (r**2 + q_**2)
                                   + sign * 2 * r * p_ * q_ * xm / (math.sqrt(3) * (r**2 + p_**2) * (r**2 + q_**2)))
            lam_circ = [outer(rs[0], 1.0), rs[1] / r_ac * q_**2 / (rs[1] ** 2 + q_**2), outer(rs[2], -1.0)]
    elif inst.bonding in ("single_point", "cross_bonded"):
        lam_circ = [0.0, 0.0, 0.0]  # cross-bonding: sezioni maggiori considerate bilanciate
        eddy = True
    else:
        raise ValueError(f"collegamento degli schermi non valido {inst.bonding!r}")
    lam_eddy = [0.0, 0.0, 0.0]
    if eddy and c.screen_kind != "sheath":
        notes.append("perdite parassite trascurate per lo schermo a fili o a nastro")
    elif eddy:  # 2.3.6.1
        ts = c.screen_thickness_mm
        ds = c.diameters_mm()["screen"]
        r_ = d / (2.0 * s)
        for k, r in enumerate(rs):
            rho_s = RHO_20[c.screen_material] * (1.0 + ALPHA_20[c.screen_material] * (theta_s[k] - 20.0))
            beta1 = math.sqrt(4.0 * math.pi * omega / (1e7 * rho_s))  # [1/m]
            m = omega / r * 1e-7
            gs = 1.0 + (ts / ds) ** 1.74 * (beta1 * ds * 1e-3 - 1.6)
            if inst.formation == "trefoil":
                lam0 = 3.0 * (m * m / (1.0 + m * m)) * r_**2
                d1, d2 = (1.14 * m**2.45 + 0.33) * r_ ** (0.92 * m + 1.66), 0.0
            elif k == 1:  # centrale
                lam0 = 6.0 * (m * m / (1.0 + m * m)) * r_**2
                d1, d2 = 0.86 * m**3.08 * r_ ** (1.4 * m + 0.7), 0.0
            elif k == 2:  # esterno, fase in anticipo
                lam0 = 1.5 * (m * m / (1.0 + m * m)) * r_**2
                d1, d2 = 4.7 * m**0.7 * r_ ** (0.16 * m + 2), 21 * m**3.3 * r_ ** (1.47 * m + 5.06)
            else:  # esterno, fase in ritardo
                lam0 = 1.5 * (m * m / (1.0 + m * m)) * r_**2
                d1 = -(0.74 * (m + 2) * m**0.5 / (2 + (m - 0.3) ** 2)) * r_ ** (m + 1)
                d2 = 0.92 * m**3.7 * r_ ** (m + 2)
            le = r / r_ac * (gs * lam0 * (1.0 + d1 + d2) + (beta1 * ts) ** 4 / 12e12)
            if inst.bonding == "both_ends":
                if inst.formation == "trefoil" or inst.transposed:
                    mm = nn = r / x
                else:
                    mm, nn = r / p_, r / q_
                le *= _f_reduction(mm, nn)
            lam_eddy[k] = le
    return lam_circ, lam_eddy, notes


def _trefoil_touching_buried(inst: Installation) -> bool:
    return inst.kind == "buried" and inst.formation == "trefoil" and inst.spacing_mm is None


def t1_insulation(c: CableConstruction, inst: Optional[Installation] = None) -> float:
    """T1 per strati: semiconduttore interno, isolante, semiconduttore esterno, nastri sotto lo
    schermo (IEC 60287-2-1, 4.1.2.1)."""
    rho_sc = c.semicon_rho_t if c.semicon_rho_t is not None else c.insulation_rho_t
    d = c.diameters_mm()
    d_is = d["insulation"] + 2 * c.insulation_screen_mm
    t = 0.0
    for rho, thick, under in ((rho_sc, c.conductor_screen_mm, d["conductor"]),
                              (c.insulation_rho_t, c.insulation_mm, d["conductor_screen"]),
                              (rho_sc, c.insulation_screen_mm, d["insulation"]),
                              (c.under_screen_rho_t, c.under_screen_mm, d_is)):
        if thick > 0:
            t += rho / (2.0 * math.pi) * math.log(1.0 + 2.0 * thick / under)
    factor = c.t1_factor
    if factor is None:
        wires = inst is not None and _trefoil_touching_buried(inst) and c.screen_kind == "wires" and inst.u0_kv <= 35
        factor = 1.07 if wires else 1.0
    return t * factor


def t2_bedding(c: CableConstruction) -> float:
    if c.bedding_mm <= 0:
        return 0.0
    d = c.diameters_mm()
    return c.bedding_rho_t / (2.0 * math.pi) * math.log(1.0 + 2.0 * c.bedding_mm / d["screen"])


def t3_oversheath(c: CableConstruction, inst: Installation) -> float:
    d = c.diameters_mm()
    t3 = c.oversheath_rho_t / (2.0 * math.pi) * math.log(1.0 + 2.0 * c.oversheath_mm / d["under_oversheath"])
    factor = c.t3_factor
    if factor is None:
        factor = 1.6 if _trefoil_touching_buried(inst) else 1.0
    return t3 * factor


def _positions(inst: Installation, s: float) -> list[tuple[float, float]]:
    L = inst.depth_m
    if inst.formation == "trefoil":
        h = s * math.sqrt(3.0) / 2.0  # triangolo equilatero di lato s, baricentro a profondità L
        pos = [(0.0, L - 2 * h / 3), (-s / 2, L + h / 3), (s / 2, L + h / 3)]
    else:
        pos = [(-s, L), (0.0, L), (s, L)]
    return pos + [tuple(p) for p in inst.other_cables_m]


def _t4_images(inst: Installation, diameter_m: float, s: float) -> list[float]:
    """T4 di ciascun cavo (o tubo) di un gruppo ugualmente caricato, metodo delle immagini
    (IEC 60287-2-1, 4.2.3.2); i primi tre sono il circuito considerato."""
    pos = _positions(inst, s)
    out = []
    for i, (xi, yi) in enumerate(pos[:3]):
        u = 2.0 * yi / diameter_m
        t = math.log(u + math.sqrt(u * u - 1.0))
        for k, (xk, yk) in enumerate(pos):
            if k != i:
                t += math.log(math.hypot(xi - xk, yi + yk) / math.hypot(xi - xk, yi - yk))
        out.append(inst.soil_rho_t / (2.0 * math.pi) * t)
    return out


def t4_external(c: CableConstruction, inst: Installation) -> list[float]:
    """T4 dei tre cavi direttamente interrati o T4''' dei loro tubi."""
    alone = inst.formation == "trefoil" and inst.spacing_mm is None and not inst.other_cables_m
    if inst.kind == "buried":
        de = c.diameters_mm()["outer"] / 1000.0
        if alone:
            u = 2.0 * inst.depth_m / de
            return [1.5 * inst.soil_rho_t / math.pi * (math.log(2.0 * u) - 0.630)] * 3  # 4.2.4.3.2
        return _t4_images(inst, de, _axis_spacing_m(c, inst))
    d0 = inst.duct_outer_mm / 1000.0
    if alone:
        u = 2.0 * inst.depth_m / d0  # tubi a trifoglio a contatto
        return [inst.soil_rho_t / (2.0 * math.pi) * (math.log(2.0 * u) + 2.0 * math.log(u))] * 3
    return _t4_images(inst, d0, _axis_spacing_m(c, inst))


def _t4_air(c: CableConstruction, inst: Installation, lam1: float, t1: float, t2: float, t3: float,
            wd: float, dtheta: float) -> float:
    """T4 in aria, all'ombra (IEC 60287-2-1, 4.2.1): h = Z/De^g + E, iterazione su (Δθs)^(1/4)."""
    de = c.diameters_mm()["outer"] / 1000.0
    h = inst.air_z / de**inst.air_g + inst.air_e
    ka = math.pi * de * h / (1.0 + lam1) * (t1 + t2 * (1.0 + lam1) + t3 * (1.0 + lam1))
    dtheta_d = wd * (1.0 / (1.0 + lam1) - 0.5) * t1
    x = 2.0
    for _ in range(100):
        new = ((dtheta + dtheta_d) / (1.0 + ka * x)) ** 0.25
        if abs(new - x) < 1e-13:
            x = new
            break
        x = new
    return 1.0 / (math.pi * de * h * x)


def rating(c: CableConstruction, inst: Installation, max_iter: int = 500, tol: float = 1e-11) -> RatingResult:
    """Portata [A] di un circuito di tre cavi unipolari: la minore tra quelle dei tre cavi."""
    if inst.kind not in ("buried", "ducts", "air"):
        raise ValueError(f"posa non supportata {inst.kind!r} (buried, ducts, air)")
    if inst.kind == "ducts" and (inst.duct_inner_mm is None or inst.duct_outer_mm is None):
        raise ValueError("per la posa in tubo servono duct_inner_mm e duct_outer_mm")
    if inst.kind == "air" and None in (inst.air_z, inst.air_e, inst.air_g):
        raise ValueError("per la posa in aria servono air_z, air_e, air_g (IEC 60287-2-1, tabella 2)")
    theta = c.max_temperature_c
    ambient = inst.air_temperature_c if inst.kind == "air" else inst.soil_temperature_c
    r, ys, yp = ac_resistance(c, inst, theta)
    wd = dielectric_loss(c, inst)
    t1, t2, t3 = t1_insulation(c, inst), t2_bedding(c), t3_oversheath(c, inst)
    de = c.diameters_mm()["outer"]
    t4_ext = t4_external(c, inst) if inst.kind != "air" else [0.0] * 3
    t4_duct = 0.0
    if inst.kind == "ducts":
        if inst.duct_inner_mm <= de:
            raise ValueError("il diametro interno del tubo è minore del cavo")
        t4_duct = inst.duct_rho_t / (2.0 * math.pi) * math.log(inst.duct_outer_mm / inst.duct_inner_mm)
        uc, vc, yc = DUCT_CONSTANTS[inst.duct_type]
    theta_s = [theta - 10.0] * 3
    theta_m = [70.0] * 3  # temperatura media dell'aria nel tubo, prima stima
    dtheta_tr = 0.0  # riscaldamento dell'aria in una canaletta chiusa
    currents = [0.0] * 3
    t4 = [0.0] * 3
    notes: list[str] = []
    for it in range(1, max_iter + 1):
        lam_c, lam_e, notes = screen_loss_factors(c, inst, r, theta_s)
        t4_air = [0.0] * 3
        dtheta = theta - ambient - dtheta_tr
        for k in range(3):
            lam1 = lam_c[k] + lam_e[k]
            if inst.kind == "air":
                t4[k] = _t4_air(c, inst, lam1, t1, t2, t3, wd, dtheta)
            else:
                if inst.kind == "ducts":
                    t4_air[k] = uc / (1.0 + 0.1 * (vc + yc * theta_m[k]) * de)
                t4[k] = t4_air[k] + t4_duct + t4_ext[k]
            num = dtheta - wd * (0.5 * t1 + t2 + t3 + t4[k])
            if num <= 0:
                raise ValueError("le perdite dielettriche da sole superano il salto termico ammesso")
            den = r * t1 + r * (1 + lam1) * t2 + r * (1 + lam1) * (t3 + t4[k])
            currents[k] = math.sqrt(num / den)
        new_s, new_m = [], []
        for k in range(3):
            wc = currents[k] ** 2 * r
            w = wc * (1 + lam_c[k] + lam_e[k]) + wd
            new_s.append(theta - (wc + 0.5 * wd) * t1)
            new_m.append(ambient + w * t4[k] - 0.5 * t4_air[k] * w)
        new_tr = 0.0
        if inst.trough_perimeter_m:
            i_min = min(currents)  # le tre fasi portano la stessa corrente
            w_tot = sum(i_min**2 * r * (1 + lam_c[k] + lam_e[k]) + wd for k in range(3))
            new_tr = w_tot / (3.0 * inst.trough_perimeter_m)
        old = theta_s + theta_m + [dtheta_tr]
        done = max(abs(a - b) for a, b in zip(new_s + new_m + [new_tr], old)) < tol
        theta_s, theta_m, dtheta_tr = new_s, new_m, new_tr
        if done:
            break
    else:
        raise ValueError("calcolo della portata non convergente")
    k = min(range(3), key=lambda q: currents[q])
    lam_c, lam_e, notes = screen_loss_factors(c, inst, r, theta_s)
    if inst.trough_perimeter_m:
        notes.append(f"aria nella canaletta più calda di {dtheta_tr:.2f} K")
    return RatingResult(currents[k], r, ys, yp, currents[k] ** 2 * r, wd, lam_c[k] + lam_e[k], lam_c[k], lam_e[k],
                        t1, t2, t3, t4[k], theta_s[k], it, notes, k, list(currents))


def rating_of(cr) -> tuple[CableConstruction, RatingResult]:
    """Portata di una voce di cable_ratings."""
    try:
        c = CableConstruction(**cr.cable)
        inst = Installation(**cr.installation)
    except TypeError as e:
        raise ValueError(f"{cr.id}: {e}") from None
    return c, rating(c, inst)
