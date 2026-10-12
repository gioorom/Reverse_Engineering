"""Flusso di potenza: soluzione in forma chiusa e confronto con pandapower."""

import copy
import math
import warnings

import pytest

from iec60909 import network_from_dict
from iec60909.loadflow import run_load_flow

# Rete magliata 110/20/0,4 kV con tutti i modelli del flusso di potenza.
RETE_LF = {
    "name": "Rete di prova per il flusso di potenza",
    "f_hz": 50,
    "buses": [
        {"id": "AT", "un_kv": 110.0},
        {"id": "A", "un_kv": 20.0},
        {"id": "B", "un_kv": 20.0},
        {"id": "C", "un_kv": 20.0},
        {"id": "BT", "un_kv": 0.4},
        {"id": "MT2", "un_kv": 20.0},
        {"id": "MT3", "un_kv": 10.0},
    ],
    "external_grids": [
        {"id": "Q", "bus": "AT", "skq_max_mva": 3000, "rx_max": 0.1, "vm_pu": 1.02, "va_degree": 0.0}
    ],
    "transformers": [
        {"id": "T1", "hv_bus": "AT", "lv_bus": "A", "sr_mva": 40, "ur_hv_kv": 110,
         "ur_lv_kv": 20, "ukr_percent": 12, "urr_percent": 0.4, "vector_group": "Dyn5",
         "tap_pos": -2, "tap_step_percent": 1.25, "tap_side": "hv",
         "i0_percent": 0.05, "pfe_kw": 14.0},
        {"id": "T2", "hv_bus": "AT", "lv_bus": "A", "sr_mva": 25, "ur_hv_kv": 110,
         "ur_lv_kv": 20, "ukr_percent": 11, "urr_percent": 0.5, "vector_group": "Dyn5",
         "tap_pos": -2, "tap_step_percent": 1.25, "tap_side": "hv"},
        {"id": "T3", "hv_bus": "C", "lv_bus": "BT", "sr_mva": 1.0, "ur_hv_kv": 20,
         "ur_lv_kv": 0.42, "ukr_percent": 6, "urr_percent": 1.0, "vector_group": "Dyn11",
         "tap_pos": 1, "tap_step_percent": 2.5, "tap_side": "lv",
         "i0_percent": 0.8, "pfe_kw": 1.5},
    ],
    "transformers3w": [
        {"id": "T3W", "hv_bus": "AT", "mv_bus": "MT2", "lv_bus": "MT3",
         "ur_hv_kv": 110, "ur_mv_kv": 20, "ur_lv_kv": 10,
         "sr_hv_mv_mva": 20, "sr_hv_lv_mva": 10, "sr_mv_lv_mva": 10,
         "ukr_hv_mv_percent": 10, "ukr_hv_lv_percent": 14, "ukr_mv_lv_percent": 6,
         "urr_hv_mv_percent": 0.4, "urr_hv_lv_percent": 0.5, "urr_mv_lv_percent": 0.45,
         "vector_group": "YNynd5"},
    ],
    "lines": [
        {"id": "L_AB", "from_bus": "A", "to_bus": "B", "length_km": 5,
         "r1_ohm_per_km": 0.125, "x1_ohm_per_km": 0.112, "c_nf_per_km": 300,
         "max_i_ka": 0.4},
        {"id": "L_BC", "from_bus": "B", "to_bus": "C", "length_km": 3,
         "r1_ohm_per_km": 0.206, "x1_ohm_per_km": 0.118, "c_nf_per_km": 250,
         "max_i_ka": 0.3},
        {"id": "L_AC", "from_bus": "A", "to_bus": "C", "length_km": 8,
         "r1_ohm_per_km": 0.125, "x1_ohm_per_km": 0.112, "c_nf_per_km": 300,
         "max_i_ka": 0.4, "parallel": 2},
    ],
    "generators": [
        {"id": "G1", "bus": "B", "sr_mva": 10, "ur_kv": 20, "xd2_percent": 15,
         "cos_phi": 0.8, "p_mw": 6.0, "vm_pu": 1.01},
    ],
    "motors": [
        {"id": "M1", "bus": "C", "pr_mw": 2.0, "ur_kv": 20, "efficiency": 0.96,
         "cos_phi": 0.88, "ilr_ir": 5.5, "pole_pairs": 2, "loading": 0.8},
    ],
    "static_generators": [
        {"id": "PV", "bus": "C", "kind": "PF", "ikss_ka": 0.05, "p_mw": 1.5, "q_mvar": -0.2},
    ],
    "loads": [
        {"id": "LA", "bus": "A", "p_mw": 12.0, "q_mvar": 4.0},
        {"id": "LB", "bus": "B", "p_mw": 5.0, "q_mvar": 2.0},
        {"id": "LC", "bus": "C", "p_mw": 3.0, "q_mvar": 1.2, "count": 2},
        {"id": "LBT", "bus": "BT", "p_mw": 0.6, "q_mvar": 0.25},
        {"id": "L2", "bus": "MT2", "p_mw": 8.0, "q_mvar": 3.0},
        {"id": "L3", "bus": "MT3", "p_mw": 4.0, "q_mvar": 1.5},
    ],
    "shunts": [
        {"id": "RIF", "bus": "BT", "q_mvar": -0.15},
        {"id": "RIF2", "bus": "MT3", "q_mvar": -1.0, "p_mw": 0.002},
    ],
}

REL = 1e-6


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


# --- due nodi: soluzione in forma chiusa -----------------------------------------


def test_due_nodi_forma_chiusa():
    """Rete esterna (V1 = 1) - linea R + jX - carico P + jQ.

    |V2|⁴ + (2(R·P + X·Q) − V1²)·|V2|² + (R² + X²)(P² + Q²) = 0 (per unità).
    """
    data = {
        "buses": [{"id": "1", "un_kv": 20.0}, {"id": "2", "un_kv": 20.0}],
        "external_grids": [{"id": "Q", "bus": "1", "skq_max_mva": 500}],
        "lines": [{"id": "L", "from_bus": "1", "to_bus": "2", "length_km": 10,
                   "r1_ohm_per_km": 0.2, "x1_ohm_per_km": 0.35}],
        "loads": [{"id": "C", "bus": "2", "p_mw": 8.0, "q_mvar": 3.0}],
    }
    res = run_load_flow(network_from_dict(data))
    zb = 20.0**2 / 100.0
    r, x = 2.0 / zb, 3.5 / zb
    p, q = 0.08, 0.03
    b = 2 * (r * p + x * q) - 1.0
    v2_sq = (-b + math.sqrt(b * b - 4 * (r * r + x * x) * (p * p + q * q))) / 2
    assert res.converged
    assert res.bus("2").vm_pu == pytest.approx(math.sqrt(v2_sq), rel=1e-10)
    i2 = (p * p + q * q) / v2_sq  # |I|² in p.u.
    src = res.source("Q")
    assert src.p_mw == pytest.approx(8.0 + i2 * r * 100, rel=1e-9)
    assert src.q_mvar == pytest.approx(3.0 + i2 * x * 100, rel=1e-9)
    assert res.losses_mw == pytest.approx(i2 * r * 100, rel=1e-9)
    ln = res.branch("L")
    assert ln.i_from_ka == pytest.approx(math.sqrt(i2) * 100 / (math.sqrt(3) * 20), rel=1e-9)


# --- confronto con pandapower ----------------------------------------------------

pp_ref = pytest.importorskip("tests.pp_ref", reason="pandapower non installato")
pytest.importorskip("pandapower")


def _dang(a, b):
    """Differenza di due angoli in gradi, ridotta a (−180°, 180°]."""
    return (a - b + 180.0) % 360.0 - 180.0


def _confronta(data, **kw):
    res = run_load_flow(network_from_dict(data), **kw)
    net, ids = pp_ref.run_pf(data, enforce_q_lims=kw.get("enforce_q_lims", False),
                             calculate_voltage_angles=kw.get("phase_shift", True))
    assert res.converged
    for b in res.buses:
        ref = net.res_bus.loc[ids[b.bus]]
        assert b.vm_pu == pytest.approx(ref.vm_pu, rel=REL), b.bus
        assert _dang(b.va_degree, ref.va_degree) == pytest.approx(0.0, abs=1e-6), b.bus
    return res, net, ids


def test_pandapower_tensioni_e_angoli():
    """Angoli assoluti con gli sfasamenti dei gruppi vettoriali (Dyn5, Dyn11, YNynd5)."""
    res, _, _ = _confronta(RETE_LF)
    # nodo BT: Dyn5 (−150°) seguito da Dyn11 (−330°): circa −480° = −120°
    assert _dang(res.bus("BT").va_degree, -120.0) == pytest.approx(0.0, abs=5.0)
    assert _dang(res.bus("MT3").va_degree, -150.0) == pytest.approx(0.0, abs=10.0)


def test_pandapower_angoli_relativi():
    """phase_shift=False: angoli relativi, come calculate_voltage_angles=False."""
    res, _, _ = _confronta(RETE_LF, phase_shift=False)
    assert abs(res.bus("BT").va_degree) < 10.0
    # moduli, flussi e perdite non dipendono dagli sfasamenti (rete senza maglie sfasate)
    ass = run_load_flow(network_from_dict(RETE_LF))
    assert ass.losses_mw == pytest.approx(res.losses_mw, rel=1e-9)
    for b in res.buses:
        assert ass.bus(b.bus).vm_pu == pytest.approx(b.vm_pu, rel=1e-9)


def test_pandapower_flussi_e_sorgenti():
    res, net, ids = _confronta(RETE_LF)
    eg = net.res_ext_grid.iloc[0]
    assert res.source("Q").p_mw == pytest.approx(eg.p_mw, rel=REL)
    assert res.source("Q").q_mvar == pytest.approx(eg.q_mvar, rel=REL)
    assert res.source("G1").q_mvar == pytest.approx(net.res_gen.iloc[0].q_mvar, rel=REL)
    names = list(net.line.index)
    for k, ln in enumerate(RETE_LF["lines"]):
        r, ref = res.branch(ln["id"]), net.res_line.loc[names[k]]
        assert r.p_from_mw == pytest.approx(ref.p_from_mw, rel=REL), ln["id"]
        assert r.q_to_mvar == pytest.approx(ref.q_to_mvar, rel=REL), ln["id"]
        assert r.i_from_ka == pytest.approx(ref.i_from_ka, rel=REL), ln["id"]
        assert r.loading_percent == pytest.approx(ref.loading_percent, rel=REL), ln["id"]
    for k, t in enumerate(RETE_LF["transformers"]):
        r, ref = res.branch(t["id"]), net.res_trafo.iloc[k]
        assert r.p_from_mw == pytest.approx(ref.p_hv_mw, rel=REL), t["id"]
        assert r.q_from_mvar == pytest.approx(ref.q_hv_mvar, rel=REL), t["id"]
        assert r.p_to_mw == pytest.approx(ref.p_lv_mw, rel=REL), t["id"]
        assert r.i_to_ka == pytest.approx(ref.i_lv_ka, rel=REL), t["id"]
    ref3 = net.res_trafo3w.iloc[0]
    assert res.branch("T3W:hv").p_from_mw == pytest.approx(ref3.p_hv_mw, rel=REL)
    assert res.branch("T3W:mv").q_from_mvar == pytest.approx(ref3.q_mv_mvar, rel=REL)
    assert res.branch("T3W:lv").p_from_mw == pytest.approx(ref3.p_lv_mw, rel=REL)
    perdite = net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum() + net.res_trafo3w.pl_mw.sum()
    assert res.losses_mw == pytest.approx(perdite, rel=REL)


def test_pandapower_limiti_di_potenza_reattiva():
    data = copy.deepcopy(RETE_LF)
    data["generators"][0].update(vm_pu=1.04, q_min_mvar=-2.0, q_max_mvar=3.0)
    libero = run_load_flow(network_from_dict(data))
    assert libero.source("G1").q_mvar > 3.0  # senza limiti li supera
    res, net, _ = _confronta(data, enforce_q_lims=True)
    assert res.source("G1").q_mvar == pytest.approx(3.0, rel=1e-9)
    assert res.bus("B").vm_pu < 1.04


def test_pandapower_generatore_pq():
    data = copy.deepcopy(RETE_LF)
    data["generators"][0].update(vm_pu=None, q_mvar=1.5)
    res, net, _ = _confronta(data)
    assert res.source("G1").q_mvar == pytest.approx(1.5)


def test_generatore_come_nodo_di_saldo():
    """Senza rete esterna il primo generatore PV fa da nodo di saldo."""
    data = {
        "buses": [{"id": "1", "un_kv": 20.0}, {"id": "2", "un_kv": 20.0}],
        "lines": [{"id": "L", "from_bus": "1", "to_bus": "2", "length_km": 10,
                   "r1_ohm_per_km": 0.2, "x1_ohm_per_km": 0.35}],
        "generators": [{"id": "G", "bus": "1", "sr_mva": 20, "ur_kv": 20,
                        "xd2_percent": 15, "vm_pu": 1.03}],
        "loads": [{"id": "C", "bus": "2", "p_mw": 8.0, "q_mvar": 3.0}],
    }
    res = run_load_flow(network_from_dict(data))
    assert any("nodo di saldo" in w for w in res.warnings)
    assert res.bus("1").vm_pu == pytest.approx(1.03)
    g = res.source("G")
    assert g.p_mw == pytest.approx(8.0 + res.losses_mw, rel=1e-9)
    assert g.q_mvar == pytest.approx(3.0 + res.losses_mvar, rel=1e-9)


def test_bilancio_di_potenza():
    res = run_load_flow(network_from_dict(RETE_LF))
    gen = sum(s.p_mw for s in res.sources) + 1.5  # + generatore statico
    carichi = 12 + 5 + 6 + 0.6 + 8 + 4 + 0.8 * 2.0 / 0.96
    shunt = 0.002 * res.bus("MT3").vm_pu ** 2
    assert gen == pytest.approx(carichi + shunt + res.losses_mw, rel=1e-9)


def test_nodo_isolato():
    data = copy.deepcopy(RETE_LF)
    data["buses"].append({"id": "X", "un_kv": 20.0})
    with pytest.raises(ValueError, match="non collegati"):
        run_load_flow(network_from_dict(data))


def test_riga_di_comando(capsys):
    import json
    from pathlib import Path

    from iec60909.flusso import main

    esempio = Path(__file__).resolve().parents[1] / "esempi" / "rete_flusso_potenza.json"
    assert main([str(esempio)]) == 0
    md = capsys.readouterr().out
    assert "convergente" in md and "| T3W:hv |" in md
    assert main([str(esempio), "--json"]) == 0
    dati = json.loads(capsys.readouterr().out)
    assert dati["converged"] and len(dati["buses"]) == 7
    # il calcolo di cortocircuito sulla stessa rete resta possibile
    from iec60909 import calculate, load_network

    assert calculate(load_network(esempio)).bus("A").ikss3_ka > 0
