"""Fattori di tensione e fattori di calcolo della IEC 60909-0:2016."""

from __future__ import annotations

import math

LV_LIMIT_KV = 1.0


def voltage_factor(un_kv: float, case: str, lv_tolerance_percent: int = 6) -> float:
    """Fattore di tensione c (IEC 60909-0, tabella 1).

    Bassa tensione (100 V - 1 kV): cmax = 1,05 / cmin = 0,95 per sistemi con
    tolleranza +6 %, cmax = 1,10 / cmin = 0,90 per tolleranza +10 %.
    Media e alta tensione (> 1 kV): cmax = 1,10, cmin = 1,00.
    """
    if case not in ("max", "min"):
        raise ValueError(f"caso non valido: {case!r} (usa 'max' o 'min')")
    if un_kv <= LV_LIMIT_KV:
        if lv_tolerance_percent == 6:
            return 1.05 if case == "max" else 0.95
        if lv_tolerance_percent == 10:
            return 1.10 if case == "max" else 0.90
        raise ValueError("la tolleranza BT deve essere 6 o 10 (%)")
    return 1.10 if case == "max" else 1.00


def kappa(r_over_x: float) -> float:
    """Fattore di picco κ = 1,02 + 0,98·e^(-3R/X)."""
    return 1.02 + 0.98 * math.exp(-3.0 * r_over_x)


def thermal_m(kappa_value: float, f_hz: float, tk_s: float) -> float:
    """Fattore m dell'effetto termico della componente continua."""
    if kappa_value <= 1.0:
        return 0.0
    ln = math.log(kappa_value - 1.0)
    if abs(ln) < 1e-12:
        return 2.0  # limite per κ → 2 (componente continua senza smorzamento)
    return (math.exp(4.0 * f_hz * tk_s * ln) - 1.0) / (2.0 * f_hz * tk_s * ln)


def transformer_kt(c_max: float, x_t_pu: float) -> float:
    """Fattore di correzione K_T dei trasformatori a due avvolgimenti.

    K_T = 0,95 · cmax / (1 + 0,6 · x_T), con x_T reattanza relativa
    (riferita alla potenza nominale del trasformatore).
    """
    return 0.95 * c_max / (1.0 + 0.6 * x_t_pu)


def generator_kg(un_kv: float, ur_kv: float, c_max: float, xd2_pu: float, cos_phi: float) -> float:
    """Fattore di correzione K_G dei generatori sincroni collegati direttamente."""
    sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi**2))
    return (un_kv / ur_kv) * c_max / (1.0 + xd2_pu * sin_phi)


def generator_rx(ur_kv: float, sr_mva: float) -> float:
    """Rapporto fittizio R_Gf/X"d dei generatori."""
    if ur_kv <= LV_LIMIT_KV:
        return 0.15
    return 0.05 if sr_mva >= 100.0 else 0.07


def motor_rx(ur_kv: float, pr_mw: float, pole_pairs: int | None) -> float:
    """Rapporto R_M/X_M dei motori asincroni."""
    if ur_kv <= LV_LIMIT_KV:
        return 0.42
    if pole_pairs is None:
        raise ValueError("per i motori MT serve il numero di coppie polari")
    return 0.10 if pr_mw / pole_pairs >= 1.0 else 0.15


# Tempi minimi di interruzione tabellati per μ e q; per valori intermedi si
# interpola linearmente, fuori dall'intervallo si usa il valore estremo.
_T_MIN = (0.02, 0.05, 0.10, 0.25)
T_MIN_IB = _T_MIN[0]
_MU = ((0.84, 0.26, 0.26), (0.71, 0.51, 0.30), (0.62, 0.72, 0.32), (0.56, 0.94, 0.38))
_Q = ((1.03, 0.12), (0.79, 0.12), (0.57, 0.12), (0.26, 0.10))


def _interpolate(values: list[float], tmin_s: float) -> float:
    if tmin_s <= _T_MIN[0]:
        return values[0]
    if tmin_s >= _T_MIN[-1]:
        return values[-1]
    for k in range(len(_T_MIN) - 1):
        t0, t1 = _T_MIN[k], _T_MIN[k + 1]
        if t0 <= tmin_s <= t1:
            return values[k] + (values[k + 1] - values[k]) * (tmin_s - t0) / (t1 - t0)
    raise AssertionError("intervallo non trovato")


def decay_mu(ikg_over_irg: float, tmin_s: float) -> float:
    """Fattore μ di decadimento della corrente simmetrica di generatori e motori.

    μ = a + b·e^(−c·I"kG/IrG) per tmin = 0,02 / 0,05 / 0,10 / ≥ 0,25 s;
    μ = 1 se I"kG/IrG ≤ 2; μ ≤ 1.
    """
    if ikg_over_irg <= 2.0:
        return 1.0
    values = [min(1.0, a + b * math.exp(-c * ikg_over_irg)) for a, b, c in _MU]
    return min(1.0, _interpolate(values, tmin_s))


def decay_q(mw_per_pole_pair: float, tmin_s: float) -> float:
    """Fattore q dei motori asincroni, m = PrM/p in MW per coppia polare; q ≤ 1."""
    if mw_per_pole_pair <= 0.0:
        raise ValueError("PrM/p deve essere positivo")
    # ogni curva tabellata è limitata a 0 ≤ q ≤ 1 prima dell'interpolazione
    values = [max(0.0, min(1.0, a + b * math.log(mw_per_pole_pair))) for a, b in _Q]
    return _interpolate(values, tmin_s)


def generator_lambda(
    ikg_over_irg: float,
    xd_sat_pu: float,
    xd2_pu: float,
    cos_phi: float,
    ufmax_ratio: float,
    c: float,
) -> tuple[float, float]:
    """Fattori λmax e λmin per la corrente permanente di un generatore.

    Modello analitico da cui derivano le curve della norma: corrente permanente
    E/(xd_sat + x_e), con x_e reattanza esterna (in p.u. del generatore)
    ricavata dalla corrente iniziale, I"kG/IrG = c/(x"d + x_e), con x"d
    l'impedenza subtransitoria corretta (K_G) in p.u. del generatore.
    λmax: eccitazione massima Ufmax/Ufr volte quella nominale a carico nominale
    (E = Ufmax/Ufr · |1 + j·xd_sat·(cosφ − j·sinφ)|); λmin: eccitazione
    costante a vuoto (E = 1).
    """
    sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi**2))
    x_ext = max(0.0, c / ikg_over_irg - xd2_pu)
    e_rated = math.hypot(1.0 + xd_sat_pu * sin_phi, xd_sat_pu * cos_phi)
    lam_max = ufmax_ratio * e_rated / (xd_sat_pu + x_ext)
    lam_min = 1.0 / (xd_sat_pu + x_ext)
    # la corrente permanente non supera quella iniziale
    return min(lam_max, ikg_over_irg), min(lam_min, ikg_over_irg)


def power_station_factors(
    *,
    un_q_kv: float,
    ur_g_kv: float,
    ur_t_hv_kv: float,
    ur_t_lv_kv: float,
    c_max_q: float,
    c_max_g: float,
    xd2_pu: float,
    xt_pu: float,
    cos_phi: float,
    oltc: bool,
    pg: float = 0.0,
    pt: float = 0.0,
) -> tuple[float, float, float]:
    """Fattori dei gruppi di generazione (generatore + trasformatore dedicato).

    Restituisce (K_esterno, K_G_interno, K_T_interno):
    - guasti fuori dal gruppo: Z_S = K·(t_r²·Z_G + Z_THV), con
      K_S = (UnQ²/UrG²)·(UrTLV²/UrTHV²)·cmax/(1 + |x"d − x_T|·sinφ) (variatore
      sotto carico) oppure
      K_SO = UnQ/(UrG·(1 + pG))·(UrTLV/UrTHV)·(1 − pT)·cmax/(1 + x"d·sinφ);
    - guasti tra generatore e trasformatore: K_G,S = cmax/(1 + x"d·sinφ) e
      K_T,S = cmax/(1 − x_T·sinφ), divisi per (1 + pG) senza variatore.
    """
    sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi**2))
    if oltc:
        k_out = (un_q_kv**2 / ur_g_kv**2) * (ur_t_lv_kv**2 / ur_t_hv_kv**2) * c_max_q / (
            1.0 + abs(xd2_pu - xt_pu) * sin_phi
        )
        scale = 1.0
    else:
        k_out = (un_q_kv / (ur_g_kv * (1.0 + pg))) * (ur_t_lv_kv / ur_t_hv_kv) * (1.0 - pt) * c_max_q / (
            1.0 + xd2_pu * sin_phi
        )
        scale = 1.0 / (1.0 + pg)
    k_g_in = scale * c_max_g / (1.0 + xd2_pu * sin_phi)
    k_t_in = scale * c_max_g / (1.0 - xt_pu * sin_phi)
    return k_out, k_g_in, k_t_in


def dc_frequency_ratio(f_times_t: float) -> float:
    """Rapporto fc/f della frequenza equivalente per la componente continua.

    f·t < 1 → 0,27; < 2,5 → 0,15; < 5 → 0,092; altrimenti 0,055.
    """
    if f_times_t < 1.0:
        return 0.27
    if f_times_t < 2.5:
        return 0.15
    if f_times_t < 5.0:
        return 0.092
    return 0.055


def dc_component(ikss: float, f_hz: float, t_s: float, r_over_x: float) -> float:
    """Componente continua i_DC = √2·I"k·e^(−2π·f·t·R/X)."""
    return math.sqrt(2.0) * ikss * math.exp(-2.0 * math.pi * f_hz * t_s * r_over_x)
