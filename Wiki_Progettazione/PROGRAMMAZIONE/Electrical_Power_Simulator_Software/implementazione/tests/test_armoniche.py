"""Armoniche: calcoli a mano, risonanza, filtri, cancellazione a 12 impulsi,
armoniche omopolari, limiti e confronto con OpenDSS."""

import cmath
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from iec60909 import network_from_dict
from iec60909.harmonics import (
    SPECTRA,
    design_single_tuned_filter,
    filter_impedance_pu,
    frequency_scan,
    harmonic_analysis,
    ieee519_current_limits,
    ieee519_voltage_limits,
    sequence_of,
)
from iec60909.network import HarmonicFilter

ESEMPI = Path(__file__).resolve().parents[1] / "esempi"
DATI = Path(__file__).resolve().parent / "dati"


def _nodo_singolo(**extra):
    """Rete esterna 0,4 kV (Sk = 20 MVA, R/X = 0,1), condensatori 0,2 Mvar, convertitore
    che assorbe 0,1 MW a cosφ = 1 con spettro a 6 impulsi."""
    data = {
        "name": "Nodo singolo", "f_hz": 50,
        "buses": [{"id": "B", "un_kv": 0.4}],
        "external_grids": [{"id": "Q", "bus": "B", "skq_max_mva": 20, "rx_max": 0.1}],
        "shunts": [{"id": "C", "bus": "B", "q_mvar": -0.2}],
        "loads": [{"id": "L", "bus": "B", "p_mw": 0.1, "q_mvar": 0.0}],
        "harmonic_sources": [{"id": "S", "bus": "B", "element": "L", "spectrum": "6_impulsi"}],
    }
    data.update(extra)
    return data


# --- elementi di base ---------------------------------------------------------------------


def test_sequenze_e_spettri():
    assert [sequence_of(h) for h in (2, 3, 4, 5, 7, 9, 11, 13)] == [2, 0, 1, 2, 1, 0, 2, 1]
    assert sorted(SPECTRA["6_impulsi"])[:4] == [5, 7, 11, 13]
    assert SPECTRA["6_impulsi"][7][0] == pytest.approx(100 / 7)
    assert sorted(SPECTRA["12_impulsi"])[:4] == [11, 13, 23, 25]


def test_tensione_armonica_a_mano():
    """V_h = I_h·(Zq(h) ∥ Zc(h) ∥ Z_carico(h)), I_h = I1/h, θ_h = h·θ1."""
    res = harmonic_analysis(network_from_dict(_nodo_singolo()), include_loads=False)
    zb = 0.4**2 / 100
    zq = 0.4**2 / 20 / zb
    xq = zq / math.sqrt(1.01)
    v1 = res.buses[0].v1_pu  # tensione fondamentale dal flusso di potenza
    i1 = 0.1 / 100 / v1  # p.u., cosφ = 1
    for h in (5, 7, 11, 13):
        y = 1 / complex(0.1 * xq, xq * h) + 1j * 0.002 * h
        assert res.bus("B").vh_percent[h] == pytest.approx(i1 / h / abs(y) * 100, rel=1e-9), h


def test_carichi_r_l_in_parallelo():
    """Con i carichi: ammettenza aggiuntiva P − jQ/h (potenza a tensione nominale)."""
    data = _nodo_singolo()
    data["loads"].append({"id": "R", "bus": "B", "p_mw": 0.3, "q_mvar": 0.1})
    res = harmonic_analysis(network_from_dict(data))
    zb = 0.4**2 / 100
    xq = 0.4**2 / 20 / zb / math.sqrt(1.01)
    i1 = 0.001 / res.buses[0].v1_pu
    h = 5
    y = 1 / complex(0.1 * xq, xq * h) + 1j * 0.002 * h + complex(0.001, 0) + complex(0.003, -0.001 / h)
    assert res.bus("B").vh_percent[h] == pytest.approx(i1 / h / abs(y) * 100, rel=1e-9)


def test_risonanza_parallelo():
    """Senza resistenze la risonanza è a h = √(Sk/Qc)."""
    data = _nodo_singolo()
    data["external_grids"][0]["rx_max"] = 0.0
    scan = frequency_scan(network_from_dict(data), "B", h_max=20, step=0.001, include_loads=False)
    assert len(scan.resonances) == 1
    assert scan.resonances[0][0] == pytest.approx(math.sqrt(20 / 0.2), abs=0.002)
    # impedenza alla fondamentale ≈ quella della rete in parallelo ai condensatori
    zb = 0.4**2 / 100
    x = 0.4**2 / 20
    assert scan.z_ohm[0] == pytest.approx(abs(1 / (1 / (1j * x) + 1j * 0.002 / zb)), rel=1e-9)


# --- filtri -----------------------------------------------------------------------------------


def test_filtro_accordato():
    hf = HarmonicFilter("F", "B", q_mvar=0.15, tuned_order=4.7, quality=40)
    z = filter_impedance_pu(hf, 4.7)
    xl = 100 / 0.15 * 4.7**2 / (4.7**2 - 1) / 4.7**2
    assert z.imag == pytest.approx(0.0, abs=1e-9)
    assert z.real == pytest.approx(4.7 * xl / 40, rel=1e-12)
    # potenza reattiva alla fondamentale: Q = U²/|X|
    assert -filter_impedance_pu(hf, 1.0).imag == pytest.approx(100 / 0.15, rel=1e-12)
    comp = design_single_tuned_filter(0.15, 4.7, 0.4, 40)
    assert comp["xc_ohm"] - comp["xl_ohm"] == pytest.approx(0.4**2 / 0.15, rel=1e-12)
    assert 1 / (2 * math.pi * math.sqrt(comp["l_mh"] * 1e-3 * comp["c_uf"] * 1e-6)) == \
        pytest.approx(4.7 * 50, rel=1e-9)


def test_filtro_riduce_la_quinta_e_rifasa():
    base = harmonic_analysis(network_from_dict(_nodo_singolo()))
    data = _nodo_singolo(harmonic_filters=[{"id": "F", "bus": "B", "q_mvar": 0.15, "tuned_order": 4.7}])
    con = harmonic_analysis(network_from_dict(data))
    assert con.bus("B").vh_percent[5] < 0.5 * base.bus("B").vh_percent[5]
    # alla fondamentale il filtro eroga la sua potenza reattiva (0,15 Mvar a 1 p.u.)
    from iec60909.loadflow import run_load_flow

    q0 = run_load_flow(network_from_dict(_nodo_singolo())).source("Q").q_mvar
    q1 = run_load_flow(network_from_dict(data)).source("Q").q_mvar
    y1 = 1 / filter_impedance_pu(HarmonicFilter("F", "B", 0.15, 4.7), 1.0)
    assert q0 - q1 == pytest.approx(y1.imag * 100, rel=1e-9)  # 0,15 Mvar meno l'effetto di R
    assert q0 - q1 == pytest.approx(0.15, rel=1e-4)


# --- trasformatori: 12 impulsi e armoniche omopolari ------------------------------------------


def _due_convertitori(gruppo2: str, spettro="6_impulsi"):
    return network_from_dict({
        "name": "Due convertitori", "f_hz": 50,
        "buses": [{"id": "MT", "un_kv": 20.0}, {"id": "A", "un_kv": 0.69}, {"id": "B", "un_kv": 0.69}],
        "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 300, "rx_max": 0.1, "x0x1": 1.0}],
        "transformers": [
            {"id": "T1", "hv_bus": "MT", "lv_bus": "A", "sr_mva": 2, "ur_hv_kv": 20, "ur_lv_kv": 0.69,
             "ukr_percent": 6, "urr_percent": 1, "vector_group": "YNyn0"},
            {"id": "T2", "hv_bus": "MT", "lv_bus": "B", "sr_mva": 2, "ur_hv_kv": 20, "ur_lv_kv": 0.69,
             "ukr_percent": 6, "urr_percent": 1, "vector_group": gruppo2},
        ],
        "loads": [{"id": "LA", "bus": "A", "p_mw": 1.0, "q_mvar": 0.0},
                  {"id": "LB", "bus": "B", "p_mw": 1.0, "q_mvar": 0.0}],
        "harmonic_sources": [{"id": "SA", "bus": "A", "element": "LA", "spectrum": spettro},
                             {"id": "SB", "bus": "B", "element": "LB", "spectrum": spettro}],
    })


def test_dodici_impulsi():
    """Yy0 + Dy11: alla MT 5ª e 7ª si annullano (sfasamento ±30° per sequenza e 5·30°/7·30°
    delle correnti), 11ª e 13ª si sommano."""
    res = harmonic_analysis(_due_convertitori("Dyn11"), include_loads=False)
    mt = res.bus("MT").vh_percent
    stesso = harmonic_analysis(_due_convertitori("YNyn0"), include_loads=False).bus("MT").vh_percent
    assert mt[5] < 1e-9 and mt[7] < 1e-9 and mt[17] < 1e-9 and mt[19] < 1e-9
    assert mt[11] == pytest.approx(stesso[11], rel=1e-9)
    assert mt[13] == pytest.approx(stesso[13], rel=1e-9)
    # nei secondari le correnti restano quelle di ogni convertitore
    assert res.branch("T2", "B").ih_a[5] == pytest.approx(res.branch("T1", "A").ih_a[5], rel=1e-9)


def test_armoniche_omopolari_bloccate_dal_triangolo():
    """3ª armonica (omopolare) lato BT di un Dyn: nessuna tensione lato MT; con YNyn passa."""
    spettro = {"3": [30.0, 0.0]}
    dyn = harmonic_analysis(_due_convertitori("Dyn11", spettro), include_loads=False)
    assert dyn.bus("B").vh_percent[3] > 0.1
    assert dyn.branch("T2", "MT").ih_a[3] == pytest.approx(0.0, abs=1e-9)
    assert dyn.branch("T1", "MT").ih_a[3] > 1.0  # YNyn0 con neutro di rete a terra


# --- limiti --------------------------------------------------------------------------------------


def test_limiti_tensione_e_corrente():
    assert ieee519_voltage_limits(0.4) == (5.0, 8.0)
    assert ieee519_voltage_limits(20) == (3.0, 5.0)
    assert ieee519_voltage_limits(132) == (1.5, 2.5)
    assert ieee519_voltage_limits(220) == (1.0, 1.5)
    bands, tdd = ieee519_current_limits(30.0)
    assert tdd == 8.0 and bands[0] == (3, 10, 7.0)
    assert ieee519_current_limits(2000.0)[1] == 20.0


def test_verifica_dei_limiti_e_punto_di_consegna():
    net = network_from_dict(json.loads((ESEMPI / "armoniche_cabina.json").read_text(encoding="utf-8")))
    en = harmonic_analysis(net)
    assert any(v.startswith("V7 ") for v in en.bus("BT").limit_violations)  # risonanza vicino alla 7ª
    assert en.bus("MT").limit_violations == []
    ie = harmonic_analysis(net, limits="ieee519", pcc_bus="MT", pcc_branch="TR", il_a=30.0)
    assert ie.pcc["isc_il"] == pytest.approx(ie.pcc["isc_a"] / 30.0)
    br = ie.branch("TR", "MT")
    tdd = math.sqrt(sum(x**2 for x in br.ih_a.values())) / 30.0 * 100
    assert ie.pcc["tdd_percent"] == pytest.approx(tdd)
    # THD e fattore K del ramo
    assert br.thd_percent == pytest.approx(math.sqrt(sum(x**2 for x in br.ih_a.values())) / br.i1_a * 100)
    num = br.i1_a**2 + sum((h * x) ** 2 for h, x in br.ih_a.items())
    assert br.k_factor == pytest.approx(num / br.rms_a**2)


def test_errori():
    data = _nodo_singolo()
    data["harmonic_sources"][0]["spectrum"] = "boh"
    with pytest.raises(ValueError, match="spettro sconosciuto"):
        harmonic_analysis(network_from_dict(data))
    data = _nodo_singolo()
    data["harmonic_sources"][0]["element"] = "X"
    with pytest.raises(ValueError, match="elemento inesistente"):
        harmonic_analysis(network_from_dict(data))
    data = _nodo_singolo(harmonic_sources=[])
    with pytest.raises(ValueError, match="harmonic_sources"):
        harmonic_analysis(network_from_dict(data))


# --- OpenDSS ---------------------------------------------------------------------------------------


def test_come_opendss():
    """Riferimento: OpenDSS (DSS C-API 0.14.5), cabina con trasformatore Dyn11, due sorgenti
    (6 impulsi e spettro con angoli), rifasamento e cavo (strumenti/confronto_opendss_armoniche.py).
    Rete esterna alla stessa tensione fondamentale di OpenDSS (fem a 1 p.u. dietro Zq)."""
    ref = json.loads((DATI / "armoniche_opendss.json").read_text(encoding="utf-8"))
    res = harmonic_analysis(network_from_dict(ref["rete"]))
    for bus, valori in ref["vh_percent"].items():
        for h, v in valori.items():
            assert res.bus(bus).vh_percent[int(h)] == pytest.approx(v, rel=1e-4), (bus, h)


def test_riga_di_comando(tmp_path, capsys):
    from iec60909.armoniche import main

    svg = tmp_path / "scan.svg"
    rete = str(ESEMPI / "armoniche_cabina.json")
    assert main([rete, "--scansione", "BT", "--svg", str(svg)]) == 1  # limiti superati
    out = capsys.readouterr().out
    assert "risonanze" in out and "| BT |" in out
    assert svg.read_text(encoding="utf-8").startswith("<svg")
    data = json.loads(Path(rete).read_text(encoding="utf-8"))
    data["harmonic_filters"] = [{"id": "F5", "bus": "BT", "q_mvar": 0.1, "tuned_order": 4.7, "quality": 40},
                                {"id": "F7", "bus": "BT", "q_mvar": 0.1, "tuned_order": 6.7, "quality": 40}]
    data["shunts"] = []
    f = tmp_path / "filtri.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    main([str(f), "--json"])
    dati = {b["bus"]: b for b in json.loads(capsys.readouterr().out)["buses"]}
    # con i filtri di 5ª e 7ª le sbarre BT rientrano nei limiti (in fondo al cavo resta
    # la 19ª poco sopra l'1,5 %)
    assert dati["BT"]["limit_violations"] == []
    assert dati["BT"]["vh_percent"]["7"] < 2.0
