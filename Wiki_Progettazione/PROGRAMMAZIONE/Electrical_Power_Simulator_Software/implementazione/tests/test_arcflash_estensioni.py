"""Arc flash, estensioni: metodo di Lee oltre 15 kV, corrente continua (NFPA 70E
allegato D.5), scelta della corrente franca, calcolo a più intervalli, fusibili
e avvisi sotto 240 V. Verifiche con calcoli a mano e con arcflash-calc."""

import copy
import json
import math
from pathlib import Path

import pytest

from iec60909 import calculate, load_network, network_from_dict
from iec60909.arcflash import (
    E_BOUNDARY_J_CM2,
    J_PER_CAL,
    METHOD_LEE,
    CurrentStep,
    Enclosure,
    Protection,
    arc_durations_ms,
    arc_flash,
    arc_flash_case,
    arc_flash_study,
    feeding_transformers,
    ieee_multistep_case,
    results_to_dict,
    results_to_markdown,
)
from iec60909.arcflash_dc import (
    METHOD_DOAN,
    METHOD_STOKES,
    dc_arc_flash,
    stokes_arc_current,
    stokes_arc_resistance,
)
from iec60909.coordination import trip_time_s

ESEMPI = Path(__file__).resolve().parents[1] / "esempi"
CABINA = ESEMPI / "arc_flash_cabina.json"
COORD = ESEMPI / "coordinamento_cabina.json"


def _dati(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- metodo di Lee -------------------------------------------------------------------------


def test_lee_calcolo_a_mano():
    enc = Enclosure(33.0, "VCB", 0.0, 914.4)
    r = arc_flash(enc, 10.0, Protection(time_ms=100.0))
    assert r.method == METHOD_LEE and r.reduced is None and r.factors is None
    e = 2.142e6 * 33.0 * 10.0 * 0.1 / 914.4**2  # J/cm²
    assert r.full.e_j_cm2 == pytest.approx(e, rel=1e-12)
    assert r.e_cal_cm2 == pytest.approx(e / 4.184, rel=1e-12)
    assert r.full.i_arc_ka == 10.0  # Lee: corrente d'arco = corrente franca
    assert r.afb_mm == pytest.approx(math.sqrt(2.142e6 * 33.0 * 10.0 * 0.1 / 5.0208), rel=1e-12)
    # più intervalli: energia e argomento del confine si sommano
    r2 = arc_flash(enc, None, Protection(time_ms=100.0),
                   steps=[CurrentStep(10.0, 40.0), CurrentStep(6.0)])
    k = 2.142e6 * 33.0 * (10.0 * 0.04 + 6.0 * 0.06)
    assert r2.full.e_j_cm2 == pytest.approx(k / 914.4**2, rel=1e-12)
    assert r2.afb_mm == pytest.approx(math.sqrt(k / 5.0208), rel=1e-12)


def test_lee_scelto_sulla_rete_oltre_15_kv():
    data = _dati(CABINA)
    data["arc_flash"] = [{"id": "MT", "bus": "MT", "distance_mm": 914.4, "protection": {"time_ms": 150}},
                         {"id": "QD1", "bus": "QD1", "equipment_class": "pannello_bt", "protection": {"time_ms": 20}}]
    net = network_from_dict(data)
    res = {r.location: r for r in arc_flash_study(net)}
    ibf = calculate(net).bus("MT").ikss3_ka
    assert res["MT"].method == METHOD_LEE
    assert res["MT"].e_cal_cm2 == pytest.approx(2.142e6 * 20.0 * ibf * 0.15 / 914.4**2 / 4.184, rel=1e-12)
    assert res["QD1"].method == "IEEE 1584-2018"
    md = results_to_markdown(list(res.values()))
    assert "| MT | Lee |" in md
    json.dumps(results_to_dict(list(res.values())))


# --- corrente continua ----------------------------------------------------------------------


def test_dc_doan_calcolo_a_mano():
    # 250 V, Ibf 4 kA, Iarc 2 kA, 1 s, D = 45,72 cm, all'aperto
    r = dc_arc_flash(250.0, 457.2, Protection(time_ms=1000.0), ibf_ka=4.0, enclosure_factor=1.0)
    e_cal = 0.01 * 250.0 * 2000.0 * 1.0 / 45.72**2
    assert r.method == METHOD_DOAN and r.full.i_arc_ka == pytest.approx(2.0)
    assert r.e_cal_cm2 == pytest.approx(e_cal, rel=1e-12)
    assert r.afb_mm == pytest.approx(10.0 * math.sqrt(0.01 * 250.0 * 2000.0 / 1.2), rel=1e-12)
    # arco in involucro: fattore 3 (default)
    r3 = dc_arc_flash(250.0, 457.2, Protection(time_ms=1000.0), r_system_ohm=250.0 / 4000.0)
    assert r3.ibf_ka == pytest.approx(4.0)
    assert r3.e_cal_cm2 == pytest.approx(3.0 * e_cal, rel=1e-12)
    assert r3.afb_mm == pytest.approx(math.sqrt(3.0) * r.afb_mm, rel=1e-12)


def test_dc_stokes_calcolo_a_mano():
    v, rs, g = 500.0, 0.05, 25.0
    i = stokes_arc_current(v, rs, g)
    r_arc = (20.0 + 0.534 * g) / (i * 1000.0) ** 0.88
    assert stokes_arc_resistance(i, g) == pytest.approx(r_arc)
    assert i * 1000.0 == pytest.approx(v / (rs + r_arc), rel=1e-10)  # punto fisso
    res = dc_arc_flash(v, 600.0, Protection(time_ms=200.0), r_system_ohm=rs, method="stokes", gap_mm=g,
                       enclosure_factor=1.0)
    assert res.method == METHOD_STOKES and res.full.i_arc_ka == pytest.approx(i)
    p = (i * 1000.0) ** 2 * r_arc
    e_j = p * 0.2 / (4 * math.pi * 60.0**2)
    assert res.full.e_j_cm2 == pytest.approx(e_j, rel=1e-9)
    assert res.full.steps[0]["v_arc_v"] == pytest.approx(i * 1000.0 * r_arc)
    # confine: energia 1,2 cal/cm²
    assert res.afb_mm == pytest.approx(10 * math.sqrt(p * 0.2 / (4 * math.pi * E_BOUNDARY_J_CM2)), rel=1e-9)


def test_dc_stokes_alla_massima_potenza_ritrova_doan():
    # con Rarc = Rsys la tensione d'arco è Vsys/2: E_Stokes/E_Doan = 1/(0,02·4π·4,184) = 0,951
    i_a, g = 3000.0, 20.0
    rs = stokes_arc_resistance(i_a / 1000.0, g)
    v = 2.0 * i_a * rs
    st = dc_arc_flash(v, 500.0, Protection(time_ms=100.0), r_system_ohm=rs, method="stokes", gap_mm=g)
    do = dc_arc_flash(v, 500.0, Protection(time_ms=100.0), r_system_ohm=rs, method="doan")
    assert st.full.i_arc_ka == pytest.approx(do.full.i_arc_ka, rel=1e-9)
    assert st.full.e_j_cm2 / do.full.e_j_cm2 == pytest.approx(1.0 / (0.02 * 4 * math.pi * J_PER_CAL), rel=1e-9)


def test_dc_sulla_rete_e_protezione():
    data = _dati(COORD)
    data["protective_devices"].append({"id": "F_cc", "branch": "C1", "bus": "QGBT", "kind": "fuse",
                                       "points": [[500, 10.0], [5000, 0.01]]})
    data["arc_flash"] = [
        {"id": "Batteria", "system": "dc", "vdc_v": 220, "ibf_ka": 6.0, "distance_mm": 457.2,
         "protection": {"time_ms": 500}},
        {"id": "Raddrizzatore", "system": "dc", "vdc_v": 600, "r_system_ohm": 0.06, "dc_method": "stokes",
         "equipment_class": "quadro_bt", "configuration": "VOA", "protection": {"device": "F_cc"}},
    ]
    res = {r.location: r for r in arc_flash_study(network_from_dict(data))}
    b = res["Batteria"]
    assert b.e_cal_cm2 == pytest.approx(3 * 0.01 * 220 * 3000 * 0.5 / 45.72**2, rel=1e-12)
    r = res["Raddrizzatore"]
    assert r.ibf_ka == pytest.approx(10.0)
    fuse = next(d for d in network_from_dict(data).protective_devices if d.id == "F_cc")
    assert r.full.t_arc_ms == pytest.approx(trip_time_s(fuse, r.full.i_arc_ka * 1000) * 1000)
    assert r.full.steps[0]["enclosure_factor"] == 1.0  # VOA: all'aperto
    md = results_to_markdown(list(res.values()))
    assert "| Batteria | NFPA 70E D.5.1" in md
    json.dumps(results_to_dict(list(res.values())))


@pytest.mark.parametrize("point, msg", [
    ({"system": "dc", "ibf_ka": 5.0, "distance_mm": 500}, "vdc_v"),
    ({"system": "dc", "vdc_v": 125, "distance_mm": 500}, "r_system_ohm"),
    ({"system": "dc", "vdc_v": 125, "ibf_ka": 5.0, "distance_mm": 500, "dc_method": "stokes"}, "gap_mm"),
    ({"system": "dc", "vdc_v": 125, "ibf_ka": 5.0, "distance_mm": 500, "dc_method": "boh"}, "metodo"),
    ({"system": "xx", "bus": "QD1"}, "system"),
    ({"bus": "QD1", "equipment_class": "pannello_bt", "ibf_ka": 5.0, "motor_decay_ms": 10}, "alternativo"),
    ({"bus": "QD1", "equipment_class": "pannello_bt", "vdc_v": 110}, "solo per i punti in c.c."),
])
def test_errori_dati(point, msg):
    data = _dati(CABINA)
    data["arc_flash"] = [dict({"id": "P", "protection": {"time_ms": 100}}, **point)]
    with pytest.raises(ValueError, match=msg):
        arc_flash_study(network_from_dict(data))


# --- corrente franca ------------------------------------------------------------------------


def test_scelta_della_corrente_franca():
    net = load_network(CABINA)
    sc = calculate(net)
    std = {r.location: r for r in arc_flash_study(net)}
    c1 = {r.location: r for r in arc_flash_study(net, ibf="c1")}
    for pid, bus in (("QGBT_partenze", "QGBT"), ("QD1", "QD1")):
        assert std[pid].ibf_ka == pytest.approx(sc.bus(bus).ikss3_ka)
        assert c1[pid].ibf_ka == pytest.approx(sc.bus(bus).ikss3_ka / sc.bus(bus).c)
        assert "c = 1" in c1[pid].ibf_source
    assert c1["QD1"].full.i_arc_ka < std["QD1"].full.i_arc_ka
    data = _dati(CABINA)
    data["arc_flash"][2]["ibf_ka"] = 7.5
    r = {r.location: r for r in arc_flash_study(network_from_dict(data), ibf="c1")}["QD1"]
    assert r.ibf_ka == 7.5 and r.ibf_source == "imposta nel punto"
    with pytest.raises(ValueError, match="corrente franca"):
        arc_flash_study(net, ibf="boh")


def test_riga_di_comando_ibf(capsys):
    from iec60909.arco import main

    assert main([str(CABINA), "--json", "--ibf", "c1"]) == 0
    righe = {r["id"]: r for r in json.loads(capsys.readouterr().out)}
    sc = calculate(load_network(CABINA))
    assert righe["QD1"]["ibf_ka"] == pytest.approx(sc.bus("QD1").ikss3_ka / sc.bus("QD1").c)


# --- calcolo a più intervalli ---------------------------------------------------------------


def test_consumo_della_protezione():
    p = Protection(curve="VI", pickup_ka=1.0, tms=0.1, breaker_time_ms=0.0)
    t1, t2 = p.clearing_time_ms(10.0), p.clearing_time_ms(4.0)
    d = arc_durations_ms(p, [10.0, 4.0], [CurrentStep(20.0, 50.0), CurrentStep(8.0)])
    assert d[0] == 50.0 and d[1] == pytest.approx((1 - 50.0 / t1) * t2)
    # intervento entro il primo intervallo
    assert arc_durations_ms(p, [10.0, 4.0], [CurrentStep(20.0, 500.0), CurrentStep(8.0)]) == [pytest.approx(t1)]
    # la protezione non interviene nel secondo intervallo: tempo massimo
    q = Protection(curve="VI", pickup_ka=5.0, tms=0.1)
    assert sum(arc_durations_ms(q, [10.0, 4.0], [CurrentStep(20.0, 50.0), CurrentStep(8.0)])) == 2000.0
    # un solo intervallo: come clearing_time_ms
    assert arc_durations_ms(p, [3.0], [CurrentStep(5.0)]) == [pytest.approx(p.clearing_time_ms(3.0))]


@pytest.mark.parametrize("v, gap, dist, ibfs, times", [
    (4.16, 104.0, 914.4, (20.0, 12.0, 8.0), (60.0, 120.0, 300.0)),
    (13.8, 152.0, 914.4, (15.0, 9.0), (100.0, 400.0)),
    (0.48, 32.0, 609.6, (40.0, 25.0), (30.0, 170.0)),
    (0.208, 25.0, 457.2, (10.0, 4.0), (50.0, 500.0)),
])
@pytest.mark.parametrize("reduced", [False, True])
def test_piu_intervalli_come_arcflash_calc(v, gap, dist, ibfs, times, reduced):
    pytest.importorskip("arcflash.ieee_1584.multistep")
    from arcflash.ieee_1584.calculation import Calculation
    from arcflash.ieee_1584.cubicle import Cubicle
    from arcflash.ieee_1584.multistep import multistep_E_and_AFB
    from arcflash.ieee_1584.units import kA, kV, mm, ms

    dims = (914.4, 914.4, 914.4) if v > 0.6 else (508.0, 508.0, 508.0)
    cub = Cubicle(V_oc=v * kV, EC="VCB", G=gap * mm, D=dist * mm, height=dims[0] * mm, width=dims[1] * mm,
                  depth=dims[2] * mm)
    calcs = []
    for ibf, t in zip(ibfs, times):
        c = Calculation(cub, ibf * kA, "reduced" if reduced else "full")
        c.calculate_I_arc()
        c.calculate_E_AFB(t * ms)
        calcs.append(c)
    e_ref, afb_ref = multistep_E_and_AFB(cub, calcs)
    enc = Enclosure(v, "VCB", gap, dist, *dims)
    mine = ieee_multistep_case(enc, [CurrentStep(i, t) for i, t in zip(ibfs, times)], list(times), reduced)
    assert mine.e_j_cm2 == pytest.approx(e_ref.m, rel=1e-12)
    assert mine.afb_mm == pytest.approx(afb_ref.m_as(mm), rel=1e-9)
    assert mine.e_j_cm2 == pytest.approx(sum(c.E.m for c in calcs), rel=1e-12)
    assert mine.t_arc_ms == pytest.approx(sum(times))


def test_un_intervallo_come_eq_7_10():
    enc = Enclosure(4.16, "VCB", 104, 914.4, 1143, 762, 508)
    one = ieee_multistep_case(enc, [CurrentStep(15.0)], [197.0])
    assert one.e_j_cm2 == pytest.approx(arc_flash_case(enc, 15.0, 197.0).e_j_cm2, rel=1e-15)
    # due intervalli uguali danno lo stesso risultato di uno solo lungo quanto la somma
    two = ieee_multistep_case(enc, [CurrentStep(15.0, 97.0), CurrentStep(15.0)], [97.0, 100.0])
    assert two.e_j_cm2 == pytest.approx(one.e_j_cm2, rel=1e-12)
    assert two.afb_mm == pytest.approx(one.afb_mm, rel=1e-9)


def test_decadimento_dei_motori_sulla_rete():
    data = _dati(COORD)
    data["arc_flash"][1]["motor_decay_ms"] = 10.0
    net = network_from_dict(data)
    r = {x.location: x for x in arc_flash_study(net)}["QD1"]
    nm = copy.deepcopy(net)
    nm.motors = []
    ibf_mot, ibf_nm = calculate(net).bus("QD1").ikss3_ka, calculate(nm).bus("QD1").ikss3_ka
    assert ibf_nm < ibf_mot
    # QF1 interviene in istantaneo (20 ms) con e senza motori: 10/20 + 10/20 = 1
    for c in (r.full, r.reduced):
        assert [s["ibf_ka"] for s in c.steps] == [pytest.approx(ibf_mot), pytest.approx(ibf_nm)]
        assert [s["duration_ms"] for s in c.steps] == [pytest.approx(10.0), pytest.approx(10.0)]
        assert c.e_j_cm2 == pytest.approx(sum(s["e_j_cm2"] for s in c.steps), rel=1e-12)
    enc = _enc_qd1()
    attesa = arc_flash_case(enc, ibf_mot, 10.0).e_j_cm2 + arc_flash_case(enc, ibf_nm, 10.0).e_j_cm2
    assert r.full.e_j_cm2 == pytest.approx(attesa, rel=1e-12)
    assert "motori esauriti dopo 10 ms" in r.ibf_source
    assert "Calcolo a più intervalli" in results_to_markdown([r])
    singolo = {x.location: x for x in arc_flash_study(load_network(COORD))}["QD1"]
    assert r.e_cal_cm2 < singolo.e_cal_cm2


def _enc_qd1():
    return Enclosure(0.4, "VCBB", 25.0, 457.2, 355.6, 304.8, 250.0)


def _ratio(net, dev):
    from iec60909.calc import fault_currents

    fc = fault_currents(net, "QD1")
    return abs(fc.branch_ka[(dev.branch, dev.bus)]) / abs(fc.ikss_ka)


def test_decadimento_con_tempo_fisso():
    data = _dati(CABINA)
    data["arc_flash"][2]["protection"] = {"time_ms": 100}
    data["arc_flash"][2]["motor_decay_ms"] = 30.0
    net = network_from_dict(data)
    r = {x.location: x for x in arc_flash_study(net)}["QD1"]
    nm = copy.deepcopy(net)
    nm.motors = []
    enc = _enc_qd1()
    ibf1, ibf2 = calculate(net).bus("QD1").ikss3_ka, calculate(nm).bus("QD1").ikss3_ka
    attesa = arc_flash_case(enc, ibf1, 30.0).e_j_cm2 + arc_flash_case(enc, ibf2, 70.0).e_j_cm2
    assert r.full.e_j_cm2 == pytest.approx(attesa, rel=1e-12)
    assert r.full.t_arc_ms == pytest.approx(100.0)
    singolo = {x.location: x for x in arc_flash_study(load_network(CABINA))}["QD1"]
    assert r.full.e_j_cm2 < arc_flash_case(enc, ibf1, 100.0).e_j_cm2
    assert singolo.full.steps[0]["ibf_ka"] == pytest.approx(ibf1)


def test_intervalli_imposti():
    data = _dati(CABINA)
    data["arc_flash"] = [{"id": "P", "bus": "QGBT", "equipment_class": "quadro_bt", "protection": {"time_ms": 200},
                          "steps": [{"ibf_ka": 18.0, "duration_ms": 50}, {"ibf_ka": 12.0}]}]
    r = arc_flash_study(network_from_dict(data))[0]
    enc = Enclosure(0.4, "VCB", 32.0, 609.6, 508.0, 508.0, 508.0)
    attesa = arc_flash_case(enc, 18.0, 50.0).e_j_cm2 + arc_flash_case(enc, 12.0, 150.0).e_j_cm2
    assert r.full.e_j_cm2 == pytest.approx(attesa, rel=1e-12)
    assert r.ibf_ka == 18.0
    data["arc_flash"][0]["steps"] = [{"ibf_ka": 18.0}, {"ibf_ka": 12.0}]
    with pytest.raises(ValueError, match="duration_ms"):
        arc_flash_study(network_from_dict(data))
    data["arc_flash"][0]["steps"] = [{"corrente": 18.0}]
    with pytest.raises(ValueError, match="intervalli"):
        arc_flash_study(network_from_dict(data))


# --- fusibili -------------------------------------------------------------------------------


def test_punto_protetto_da_fusibile():
    data = _dati(COORD)
    data["protective_devices"].append({"id": "FU1", "branch": "C1", "bus": "QGBT", "kind": "fuse",
                                       "points": [[400, 100.0], [1000, 1.0], [3000, 0.05], [10000, 0.004]]})
    data["arc_flash"][1]["protection"] = {"device": "FU1"}
    net = network_from_dict(data)
    r = {x.location: x for x in arc_flash_study(net)}["QD1"]
    fuse = next(d for d in net.protective_devices if d.id == "FU1")
    ratio = _ratio(net, fuse)
    assert 0.0 < ratio < 1.0  # il motore su QD1 non passa nel fusibile
    for c in (r.full, r.reduced):
        assert c.t_arc_ms == pytest.approx(trip_time_s(fuse, c.i_arc_ka * ratio * 1000.0) * 1000.0, rel=1e-12)
    assert r.reduced.t_arc_ms > r.full.t_arc_ms  # curva inversa: corrente ridotta, tempo maggiore


# --- avvisi sotto 240 V ---------------------------------------------------------------------


def _rete_208v(sr_mva):
    return {
        "name": "BT 208 V",
        "buses": [{"id": "MT", "un_kv": 20.0}, {"id": "B208", "un_kv": 0.208}, {"id": "Q2", "un_kv": 0.208}],
        "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 500}],
        "transformers": [{"id": "TRp", "hv_bus": "MT", "lv_bus": "B208", "sr_mva": sr_mva, "ur_hv_kv": 20.0,
                          "ur_lv_kv": 0.208, "ukr_percent": 4.0, "urr_percent": 1.5}],
        "lines": [{"id": "L", "from_bus": "B208", "to_bus": "Q2", "length_km": 0.01, "r1_ohm_per_km": 0.2,
                   "x1_ohm_per_km": 0.08}],
        "arc_flash": [{"id": "Q2", "bus": "Q2", "equipment_class": "pannello_bt", "protection": {"time_ms": 100}}],
    }


def test_avviso_sotto_240_v():
    net = network_from_dict(_rete_208v(0.1))
    assert feeding_transformers(net, "Q2") == [("TRp", pytest.approx(100.0))]
    r = arc_flash_study(net)[0]
    assert any("125 kVA" in w and "TRp" in w for w in r.warnings)
    assert "## Avvertenze" in results_to_markdown([r])
    r = arc_flash_study(network_from_dict(_rete_208v(0.3)))[0]
    assert not any("125 kVA" in w for w in r.warnings)
    # a 400 V nessun avviso
    assert all(not x.warnings for x in arc_flash_study(load_network(CABINA)))
