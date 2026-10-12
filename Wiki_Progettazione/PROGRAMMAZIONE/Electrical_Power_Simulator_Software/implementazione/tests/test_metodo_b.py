"""Metodo B: fattore 1,15 e deroga per R/X < 0,3 in tutti i rami."""

import copy

import pytest

from iec60909 import calculate, factors, network_from_dict

from .reti import RETE_MAGLIATA


def _rete(rx_linee):
    data = copy.deepcopy(RETE_MAGLIATA)
    for ln in data["lines"]:
        ln["r1_ohm_per_km"] = rx_linee * ln["x1_ohm_per_km"]
    return data


def _kappa_b(r, fattore):
    limite = 1.8 if r.un_kv <= 1.0 else 2.0
    z = r.z1_ohm
    return min(fattore * factors.kappa(z.real / z.imag), limite)


def test_deroga_tutti_i_rami_sotto_0_3():
    res = calculate(network_from_dict(_rete(0.2)), "max", "B")
    for r in res.buses:
        assert r.kappa == pytest.approx(_kappa_b(r, 1.0), rel=1e-12), r.bus


def test_un_ramo_sopra_0_3_mantiene_1_15():
    data = _rete(0.2)
    data["lines"][0]["r1_ohm_per_km"] = 0.35 * data["lines"][0]["x1_ohm_per_km"]
    res = calculate(network_from_dict(data), "max", "B")
    for r in res.buses:
        assert r.kappa == pytest.approx(_kappa_b(r, 1.15), rel=1e-12), r.bus


def test_motore_bt_e_rami_del_generatore_contano():
    # motore BT: R/X = 0,42 per la norma, quindi 1,15 resta
    data = _rete(0.2)
    data["motors"].append({"id": "MBT", "bus": "BT", "pr_mw": 0.1, "ur_kv": 0.4,
                           "efficiency": 0.9, "cos_phi": 0.85, "ilr_ir": 6})
    res = calculate(network_from_dict(data), "max", "B")
    assert all(r.kappa == pytest.approx(_kappa_b(r, 1.15), rel=1e-12) for r in res.buses)


def test_impedenza_di_guasto_resistiva_mantiene_1_15():
    net = network_from_dict(_rete(0.2))
    res = calculate(net, "max", "B", zf_ohm=complex(0.5, 0.0))
    for r in res.buses:
        z = r.z1_ohm + complex(0.5, 0.0)
        limite = 1.8 if r.un_kv <= 1.0 else 2.0
        assert r.kappa == pytest.approx(min(1.15 * factors.kappa(z.real / z.imag), limite), rel=1e-12)


def test_caso_minimo_usa_r_a_fine_guasto():
    # R/X = 0,25 a 20 °C diventa 0,32 a 90 °C: nel caso minimo 1,15 resta
    res = calculate(network_from_dict(_rete(0.25)), "min", "B")
    assert all(r.kappa == pytest.approx(_kappa_b(r, 1.15), rel=1e-12) for r in res.buses)
    res = calculate(network_from_dict(_rete(0.25)), "max", "B")
    assert all(r.kappa == pytest.approx(_kappa_b(r, 1.0), rel=1e-12) for r in res.buses)
