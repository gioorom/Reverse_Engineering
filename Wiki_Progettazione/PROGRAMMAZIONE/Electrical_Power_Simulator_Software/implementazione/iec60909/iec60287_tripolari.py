"""Portata di un cavo tripolare con schermo separato su ogni anima (tipo SL), con o senza
armatura a fili (IEC 60287-1-1, IEC 60287-2-1, con le indicazioni della CIGRE TB 880).

Rispetto ai cavi unipolari:

- n = 3 nell'equazione della portata;
- le anime sono a contatto, quindi l'interasse è il diametro dell'anima;
- la cordatura delle anime (passo `core_lay_length_mm`) allunga le anime: per metro di cavo
  aumentano capacità, resistenza e reattanza degli schermi e si riduce T1 (CIGRE TB 880, GP23,
  fattore √(1 + (π·1,29·D_anima/L)²));
- l'armatura magnetica (acciaio) moltiplica per 1,5 le perdite per effetto pelle e di
  prossimità (GP25) e quelle per correnti di circolazione negli schermi (GP38);
- perdite nell'armatura magnetica a fili (IEC 60287-1-1, 5.4.3.3.1, tipo SL):
  λ2 = 1,23·(RA/R)·(2c/dA)²·1/[(2,77·RA·10⁶/ω)² + 1]·(1 − R·λ1'/Rs), con RA la resistenza in
  c.a. dell'armatura (GP34) e c la distanza tra l'asse dell'anima e quello del cavo (GP33);
  armatura non magnetica (acciaio inossidabile): λ2 = 0 (GP36);
- T2 = T2'/(3·f) + ρ·G/(6π): guaina sull'anima più riempitivi e letto con il fattore
  geometrico G (GP45);
- T4 di un cavo isolato, con il mutuo riscaldamento di altri cavi uguali.
"""

from __future__ import annotations

import math

from .iec60287 import (
    ALPHA_20,
    DUCT_CONSTANTS,
    MAGNETIC_ARMOUR,
    NON_MAGNETIC_ARMOUR,
    RHO_20,
    CableConstruction,
    Installation,
    RatingResult,
    _f_reduction,
    _r0,
    _t4_air,
    _y,
    skin_factor,
    t1_insulation,
)


def _geometric_factor_g(x: float) -> float:
    """Fattore geometrico G dei riempitivi e del letto sotto l'armatura (CIGRE TB 880, GP45),
    con x = spessore del letto / diametro dell'anima, valido per 0 ≤ x ≤ 0,15."""
    if not 0.0 <= x <= 0.15:
        raise ValueError(f"fattore geometrico G: x = {x:.4f} fuori dal campo 0–0,15")
    if x <= 0.03:
        return 2 * math.pi * (0.00022619 + 2.11429 * x - 20.4762 * x * x)
    return 2 * math.pi * (0.0142108 + 1.17533 * x - 4.49737 * x * x + 10.6352 * x**3)


def armour_ac_resistance(c: CableConstruction, theta_a: float) -> float:
    """RA [Ω/m]: fili in parallelo, lunghezza effettiva dei fili e rapporto c.a./c.c. che passa
    da 1,2 (fili da 2 mm) a 1,4 (fili da 5 mm), lineare (CIGRE TB 880, GP34)."""
    if c.armour_wires <= 0 or c.armour_wire_diameter_mm <= 0:
        raise ValueError("armatura: servono armour_wires e armour_wire_diameter_mm")
    area = c.armour_wires * math.pi * (c.armour_wire_diameter_mm * 1e-3) ** 2 / 4.0
    lay = 1.0
    if c.armour_lay_length_mm:
        lay = math.sqrt(1 + (math.pi * c.diameters_mm()["armour_mean"] / c.armour_lay_length_mm) ** 2)
    k = c.armour_ac_factor
    if k is None:
        k = 0.2 / 3.0 * (c.armour_wire_diameter_mm - 2.0) + 1.2
    ra20 = k * RHO_20["steel"] / area * lay
    return ra20 * (1.0 + ALPHA_20["steel"] * (theta_a - 20.0))


def _validate(c: CableConstruction, inst: Installation) -> None:
    if c.armour_material and c.armour_material not in MAGNETIC_ARMOUR | NON_MAGNETIC_ARMOUR:
        raise ValueError(f"armatura non valida {c.armour_material!r} "
                         f"({', '.join(sorted(MAGNETIC_ARMOUR | NON_MAGNETIC_ARMOUR))})")
    if inst.kind not in ("buried", "ducts", "air"):
        raise ValueError(f"posa non supportata {inst.kind!r} (buried, ducts, air)")
    if inst.bonding not in ("both_ends", "single_point"):
        raise ValueError("tripolari: schermi collegati alle due estremità (both_ends) o a una (single_point)")


def _t4_buried_single(inst: Installation, de_m: float, depth: float) -> float:
    """T4 di un cavo (o tubo) interrato con il mutuo riscaldamento degli altri (immagini)."""
    u = 2.0 * depth / de_m
    t = math.log(u + math.sqrt(u * u - 1.0))
    for xk, yk in inst.other_cables_m:
        t += math.log(math.hypot(xk, depth + yk) / math.hypot(xk, depth - yk))
    return inst.soil_rho_t / (2.0 * math.pi) * t


def rating_three_core(c: CableConstruction, inst: Installation, max_iter: int = 500,
                      tol: float = 1e-11) -> RatingResult:
    """Portata [A] di un cavo tripolare (n = 3)."""
    _validate(c, inst)
    n = 3
    d = c.diameters_mm()
    f = c.layup_factor
    mag = c.magnetic_armour
    k_mag = 1.5 if mag else 1.0
    notes: list[str] = []
    omega = 2.0 * math.pi * inst.frequency_hz
    theta = c.max_temperature_c
    # conduttore: anime a contatto, interasse = diametro dell'anima
    s = d["core"] / 1000.0
    dc = c.conductor_diameter_mm / 1000.0
    r1 = _r0(c) * (1.0 + ALPHA_20[c.conductor_material] * (theta - 20.0))
    xs2 = 8.0 * math.pi * inst.frequency_hz / r1 * 1e-7 * c.ks
    xp2 = 8.0 * math.pi * inst.frequency_hz / r1 * 1e-7 * c.kp
    ys = skin_factor(xs2)
    fp = _y(xp2)
    yp = fp * (dc / s) ** 2 * (0.312 * (dc / s) ** 2 + 1.18 / (fp + 0.27))
    r = r1 * (1.0 + k_mag * (ys + yp))
    # perdite dielettriche per anima (capacità per metro di cavo)
    cap = c.insulation_eps / (18.0 * math.log(d["insulation"] / d["conductor_screen"])) * 1e-9 * f
    wd = omega * cap * (inst.u0_kv * 1e3) ** 2 * c.insulation_tan_delta
    # schermo
    dm = d["screen_mean"] / 1000.0
    x = 2.0 * omega * 1e-7 * math.log(2.0 * s / dm) * f
    if c.screen_area_mm2 is not None:
        area_s = c.screen_area_mm2 * 1e-6
    elif c.screen_kind == "sheath":
        area_s = math.pi * d["screen_mean"] * c.screen_thickness_mm * 1e-6
    else:
        raise ValueError("per uno schermo a fili o a nastro serve screen_area_mm2")
    rs0 = RHO_20[c.screen_material] / area_s * c.screen_lay_factor * f
    eddy = inst.bonding == "single_point" or inst.eddy_both_ends
    if eddy and c.screen_kind != "sheath":
        notes.append("perdite parassite trascurate per lo schermo a fili o a nastro")
        eddy = False
    # resistenze termiche
    t1 = t1_insulation(c, None) / f
    t2_core = c.core_sheath_rho_t / (2.0 * math.pi) * math.log(d["core"] / d["screen"]) if c.core_sheath_mm else 0.0
    xg = (d["under_armour"] - d["fillers"]) / 2.0 / d["core"]
    t2 = t2_core / (n * f) + c.filler_rho_t * _geometric_factor_g(xg) / (6.0 * math.pi)
    t3 = c.oversheath_rho_t / (2.0 * math.pi) * math.log(d["outer"] / d["under_oversheath"])
    de = d["outer"]
    if inst.kind == "buried":
        t4_fixed = _t4_buried_single(inst, de / 1000.0, inst.depth_m)
    elif inst.kind == "ducts":
        if inst.duct_inner_mm is None or inst.duct_outer_mm is None:
            raise ValueError("per la posa in tubo servono duct_inner_mm e duct_outer_mm")
        if inst.duct_inner_mm <= de:
            raise ValueError("il diametro interno del tubo è minore del cavo")
        uc, vc, yc = DUCT_CONSTANTS[inst.duct_type]
        t4_fixed = (inst.duct_rho_t / (2.0 * math.pi) * math.log(inst.duct_outer_mm / inst.duct_inner_mm)
                    + _t4_buried_single(inst, inst.duct_outer_mm / 1000.0, inst.depth_m))
    else:
        if None in (inst.air_z, inst.air_e, inst.air_g):
            from .iec60287 import AIR_ARRANGEMENTS

            key = inst.air_arrangement or "single"
            if key not in AIR_ARRANGEMENTS:
                raise ValueError(f"air_arrangement tra {', '.join(AIR_ARRANGEMENTS)}")
            z, e, g = AIR_ARRANGEMENTS[key]
            inst = Installation(**{**inst.__dict__, "air_z": z, "air_e": e, "air_g": g})
        t4_fixed = 0.0
    ambient = inst.air_temperature_c if inst.kind == "air" else inst.soil_temperature_c
    dtheta = theta - ambient
    c_dist = (d["fillers"] - d["core"]) / 2.0 / 1000.0  # asse anima - asse cavo (GP33)
    da = d["armour_mean"] / 1000.0

    theta_s, theta_a, theta_m = theta - 10.0, theta - 20.0, 70.0
    i = lam_c = lam_e = lam2 = t4 = t4_air = 0.0
    for it in range(1, max_iter + 1):
        rs = rs0 * (1.0 + ALPHA_20[c.screen_material] * (theta_s - 20.0))
        lam_c = k_mag * rs / r / (1.0 + (rs / x) ** 2) if inst.bonding == "both_ends" else 0.0
        lam_e = 0.0
        if eddy:  # IEC 60287-1-1 2.3.6.1, trifoglio
            ts = c.screen_thickness_mm
            ds = d["screen"]
            rho_s = RHO_20[c.screen_material] * (1.0 + ALPHA_20[c.screen_material] * (theta_s - 20.0))
            beta1 = math.sqrt(4.0 * math.pi * omega / (1e7 * rho_s))
            m = omega / rs * 1e-7
            gs = 1.0 + (ts / ds) ** 1.74 * (beta1 * ds * 1e-3 - 1.6)
            rr = dm / (2.0 * s)
            lam0 = 3.0 * (m * m / (1.0 + m * m)) * rr**2
            d1 = (1.14 * m**2.45 + 0.33) * rr ** (0.92 * m + 1.66)  # anche per m ≤ 0,1, come CIGRE
            lam_e = rs / r * (gs * lam0 * (1.0 + d1) + (beta1 * ts) ** 4 / 12e12)
            if inst.bonding == "both_ends":
                lam_e *= _f_reduction(rs / x, rs / x)
        lam1 = lam_c + lam_e
        lam2 = 0.0
        if mag:
            ra = armour_ac_resistance(c, theta_a)
            reduction = max(0.0, 1.0 - r * lam_c / rs)  # λ1' già comprensivo del fattore 1,5 (GP37)
            lam2 = (1.23 * ra / r * (2.0 * c_dist / da) ** 2
                    / ((2.77 * ra * 1e6 / omega) ** 2 + 1.0) * reduction)
        if inst.kind == "air":
            t4 = _t4_air(c, inst, lam1, t1, t2, t3, wd, dtheta, n=n, lam2=lam2)
        elif inst.kind == "ducts":
            t4_air = uc / (1.0 + 0.1 * (vc + yc * theta_m) * de)
            t4 = t4_air + t4_fixed
        else:
            t4 = t4_fixed
        num = dtheta - wd * (0.5 * t1 + n * (t2 + t3 + t4))
        if num <= 0:
            raise ValueError("le perdite dielettriche da sole superano il salto termico ammesso")
        den = r * t1 + n * r * (1 + lam1) * t2 + n * r * (1 + lam1 + lam2) * (t3 + t4)
        i = math.sqrt(num / den)
        wc = i * i * r
        new_s = theta - (wc + 0.5 * wd) * t1
        new_a = new_s - (wc * (1 + lam1) + wd) * n * t2
        w_tot = n * (wc * (1 + lam1 + lam2) + wd)
        new_m = ambient + w_tot * t4 - 0.5 * t4_air * w_tot
        done = max(abs(new_s - theta_s), abs(new_a - theta_a), abs(new_m - theta_m)) < tol
        theta_s, theta_a, theta_m = new_s, new_a, new_m
        if done:
            break
    else:
        raise ValueError("calcolo della portata non convergente")
    if c.armour_material in NON_MAGNETIC_ARMOUR:
        notes.append("armatura non magnetica: perdite nell'armatura trascurate (CIGRE TB 880, GP36)")
    return RatingResult(i, r, ys, yp, i * i * r, wd, lam_c + lam_e, lam_c, lam_e, t1, t2, t3, t4, theta_s, it,
                        notes, 0, [i], lam2, theta_a if c.armour_material else None, f)
