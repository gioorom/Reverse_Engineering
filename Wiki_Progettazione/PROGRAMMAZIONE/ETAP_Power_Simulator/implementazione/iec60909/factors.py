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
