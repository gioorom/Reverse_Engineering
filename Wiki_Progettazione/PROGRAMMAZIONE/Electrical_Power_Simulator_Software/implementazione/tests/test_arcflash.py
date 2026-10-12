"""Arc flash IEEE 1584-2018: esempi svolti dell'allegato D, confronto con
arcflash-calc (implementazione open source indipendente) e studio sulla rete."""

import copy
import itertools
import json
from pathlib import Path

import pytest

from iec60909 import calculate, load_network, network_from_dict
from iec60909.arcflash import (
    CONFIGURATIONS,
    Enclosure,
    Protection,
    arc_flash,
    arc_flash_case,
    arc_flash_study,
    correction_factors,
)

ESEMPIO = Path(__file__).resolve().parents[1] / "esempi" / "arc_flash_cabina.json"


# --- allegato D.1: sistema a 4,16 kV ---------------------------------------------

D1 = Enclosure(4.16, "VCB", gap_mm=104, distance_mm=914.4, height_mm=1143, width_mm=762, depth_mm=508)


def test_allegato_d1_corrente_piena():
    c = arc_flash_case(D1, 15.0, 197.0)
    assert [round(c.i_arc_intermediate_ka[v], 3) for v in (0.6, 2.7, 14.3)] == [11.117, 12.816, 14.116]
    assert round(c.i_arc_ka, 3) == 12.979  # D.17
    f = correction_factors(D1)
    assert (round(f.width1_in, 3), round(f.height1_in, 3), round(f.ees_in, 3)) == (27.632, 45.0, 36.316)
    assert round(f.cf, 3) == 1.284  # D.22
    assert [round(c.e_intermediate_j_cm2[v], 3) for v in (0.6, 2.7, 14.3)] == [8.652, 11.977, 13.367]
    assert round(c.e_j_cm2, 3) == 12.152  # D.32
    assert [round(c.afb_intermediate_mm[v]) for v in (0.6, 2.7, 14.3)] == [1285, 1591, 1707]
    assert round(c.afb_mm) == 1606  # D.42


def test_allegato_d1_corrente_ridotta():
    f = correction_factors(D1)
    assert round(f.var_cf, 3) == 0.047 and round(1 - 0.5 * f.var_cf, 3) == 0.977  # D.43, D.44
    c = arc_flash_case(D1, 15.0, 223.0, reduced=True)
    assert [round(c.i_arc_intermediate_ka[v], 3) for v in (0.6, 2.7, 14.3)] == [10.856, 12.515, 13.786]
    assert round(c.i_arc_ka, 3) == 12.675  # D.51
    assert [round(c.e_intermediate_j_cm2[v], 3) for v in (0.6, 2.7, 14.3)] == [8.980, 13.018, 15.602]
    assert round(c.e_j_cm2, 3) == 13.343  # D.62
    assert [round(c.afb_intermediate_mm[v]) for v in (0.6, 2.7, 14.3)] == [1316, 1678, 1884]
    assert round(c.afb_mm) == 1704  # D.72


# --- allegato D.2: sistema a 480 V ------------------------------------------------

D2 = Enclosure(0.48, "VCB", gap_mm=32, distance_mm=609.6, height_mm=610, width_mm=610, depth_mm=254)


def test_allegato_d2():
    c = arc_flash_case(D2, 45.0, 61.3)
    assert round(c.i_arc_intermediate_ka[0.6], 3) == 32.449  # D.82
    assert round(c.i_arc_ka, 3) == 28.793  # D.84
    f = correction_factors(D2)
    assert round(f.ees_in, 3) == 24.016 and round(f.cf, 3) == 1.085  # D.88, D.89
    assert round(c.e_j_cm2, 3) == 11.585  # D.91
    assert round(c.afb_mm) == 1029  # D.95
    assert round(f.var_cf, 3) == 0.247  # D.96
    r = arc_flash_case(D2, 45.0, 319.0, reduced=True)
    assert round(r.i_arc_ka, 3) == 25.244  # D.99
    assert round(r.e_j_cm2, 3) == 53.156  # D.103
    assert round(r.afb_mm) == 2669  # D.106


def test_caso_determinante_e_categoria():
    # nell'esempio D.2 la corrente ridotta fa intervenire la protezione più tardi
    prot = Protection(time_ms=None, curve="EI", pickup_ka=5.0, tms=0.3, inst_pickup_ka=27.0,
                      inst_time_ms=30.0, breaker_time_ms=31.3)
    res = arc_flash(D2, 45.0, prot)
    assert res.full.t_arc_ms == pytest.approx(61.3)
    assert res.reduced.t_arc_ms > res.full.t_arc_ms
    assert res.governing is res.reduced
    assert res.e_cal_cm2 == pytest.approx(res.reduced.e_j_cm2 / 4.184)
    assert res.afb_mm == pytest.approx(max(res.full.afb_mm, res.reduced.afb_mm))


# --- confronto con arcflash-calc ---------------------------------------------------

VOLTAGGI = [0.208, 0.24, 0.4, 0.48, 0.6, 0.69, 1.0, 2.4, 2.7, 4.16, 6.6, 13.8, 15.0]
INVOLUCRI = [  # altezza, larghezza, profondità [mm]
    (508.0, 508.0, 508.0),
    (355.6, 304.8, 150.0),  # poco profondo (BT)
    (1143.0, 762.0, 762.0),
    (1500.0, 1400.0, 900.0),  # oltre 1244,6 mm
    (600.0, 900.0, 600.0),
]


def _casi():
    for ec, v, dims in itertools.product(CONFIGURATIONS, VOLTAGGI, INVOLUCRI):
        lv = v <= 0.6
        gap = 25.0 if lv else 104.0
        if dims[1] < 4 * gap:
            continue
        for ibf in ((2.0, 20.0, 80.0) if lv else (1.0, 10.0, 40.0)):
            yield ec, v, dims, gap, ibf


@pytest.mark.parametrize("ec, v, dims, gap, ibf", list(_casi()))
def test_come_arcflash_calc(ec, v, dims, gap, ibf):
    ref = pytest.importorskip("arcflash.ieee_1584.calculation")
    from arcflash.ieee_1584.cubicle import Cubicle
    from arcflash.ieee_1584.units import kA, kV, mm, ms

    dist = 610.0 if v <= 0.6 else 914.4
    cub = Cubicle(V_oc=v * kV, EC=ec, G=gap * mm, D=dist * mm,
                  height=dims[0] * mm, width=dims[1] * mm, depth=dims[2] * mm)
    enc = Enclosure(v, ec, gap, dist, *dims)
    assert correction_factors(enc).cf == pytest.approx(cub.CF.m, rel=1e-12)
    for reduced, t in ((False, 100.0), (True, 350.0)):
        calc = ref.Calculation(cub, ibf * kA, "reduced" if reduced else "full")
        calc.calculate_I_arc()
        calc.calculate_E_AFB(t * ms)
        mine = arc_flash_case(enc, ibf, t, reduced=reduced)
        assert mine.i_arc_ka == pytest.approx(calc.I_arc.m_as(kA), rel=1e-12)
        assert mine.e_j_cm2 == pytest.approx(calc.E.m, rel=1e-12)
        assert mine.afb_mm == pytest.approx(calc.AFB.m_as(mm), rel=1e-9)


# --- protezioni ---------------------------------------------------------------------


@pytest.mark.parametrize("curve, k, alpha", [("SI", 0.14, 0.02), ("VI", 13.5, 1.0),
                                              ("EI", 80.0, 2.0), ("LTI", 120.0, 1.0)])
def test_curve_iec_60255(curve, k, alpha):
    p = Protection(curve=curve, pickup_ka=1.0, tms=0.2, breaker_time_ms=50.0)
    assert p.clearing_time_ms(20.0) == pytest.approx(0.2 * k / (20.0**alpha - 1) * 1000 + 50.0)


def test_soglia_istantanea_rapporto_e_tempo_massimo():
    p = Protection(curve="VI", pickup_ka=0.5, tms=0.1, inst_pickup_ka=4.0, inst_time_ms=20.0,
                   breaker_time_ms=40.0)
    assert p.clearing_time_ms(5.0) == pytest.approx(60.0)  # istantanea
    assert p.clearing_time_ms(3.0) == pytest.approx(0.1 * 13.5 / 5.0 * 1000 + 40.0)
    # relè lato MT: vede la corrente d'arco BT ridotta del rapporto di trasformazione
    pm = Protection(curve="VI", pickup_ka=0.5, tms=0.1, current_ratio=0.02)
    assert pm.clearing_time_ms(100.0) == pytest.approx(0.1 * 13.5 / 3.0 * 1000)
    # sotto soglia: tempo massimo (2 s)
    assert Protection(curve="SI", pickup_ka=10.0).clearing_time_ms(5.0) == 2000.0
    assert Protection(time_ms=3000.0).clearing_time_ms(1.0) == 2000.0


# --- campo di validità --------------------------------------------------------------


@pytest.mark.parametrize("enc, ibf, msg", [
    (Enclosure(20.0, "VCB", 104, 914.4, 1143, 762, 762), 10.0, "tensione"),
    (Enclosure(0.4, "VCB", 32, 610), 120.0, "0,5–106 kA"),
    (Enclosure(4.16, "VCB", 104, 914.4, 1143, 762, 762), 70.0, "0,2–65 kA"),
    (Enclosure(0.4, "VCB", 100, 610), 20.0, "distanza tra i conduttori"),
    (Enclosure(0.4, "VCB", 32, 200), 20.0, "305 mm"),
    (Enclosure(0.4, "XYZ", 32, 610), 20.0, "configurazione"),
    (Enclosure(4.16, "VCB", 152, 914.4, 1143, 500, 762), 10.0, "4 volte"),
])
def test_fuori_campo(enc, ibf, msg):
    with pytest.raises(ValueError, match=msg):
        arc_flash_case(enc, ibf, 100.0)


# --- studio sulla rete ----------------------------------------------------------------


def test_studio_sulla_rete():
    net = load_network(ESEMPIO)
    res = {r.location: r for r in arc_flash_study(net)}
    sc = calculate(net)
    assert res["QGBT_partenze"].ibf_ka == pytest.approx(sc.bus("QGBT").ikss3_ka)
    assert res["QD1"].ibf_ka == pytest.approx(sc.bus("QD1").ikss3_ka)
    # valori tipici della classe di apparecchiatura (tabelle 8 e 10)
    assert res["QD1"].distance_mm == pytest.approx(457.2)
    assert res["QGBT_partenze"].full.t_arc_ms == pytest.approx(30.0)  # istantanea + 30 ms
    # stesso calcolo diretto
    enc = Enclosure(0.4, "VCB", 32.0, 609.6, 508.0, 508.0, 508.0)
    diretto = arc_flash(enc, sc.bus("QGBT").ikss3_ka, Protection(time_ms=30.0))
    assert res["QGBT_partenze"].e_cal_cm2 == pytest.approx(diretto.e_cal_cm2, rel=1e-12)


def test_dati_espliciti_e_errori():
    data = json.loads(ESEMPIO.read_text(encoding="utf-8"))
    data["arc_flash"] = [{"id": "P", "bus": "QD1", "equipment_class": "pannello_bt",
                          "distance_mm": 600.0, "protection": {"time_ms": 100}}]
    r = arc_flash_study(network_from_dict(data))[0]
    assert r.distance_mm == 600.0
    bad = copy.deepcopy(data)
    bad["arc_flash"][0]["equipment_class"] = "boh"
    with pytest.raises(ValueError, match="classe di apparecchiatura"):
        arc_flash_study(network_from_dict(bad))
    bad = copy.deepcopy(data)
    bad["arc_flash"][0]["protection"] = {"tempo": 1}
    with pytest.raises(ValueError, match="protezione"):
        arc_flash_study(network_from_dict(bad))
    bad = copy.deepcopy(data)
    del bad["arc_flash"][0]["equipment_class"]
    with pytest.raises(ValueError, match="gap_mm"):
        arc_flash_study(network_from_dict(bad))


def test_riga_di_comando(capsys):
    from iec60909.arco import main

    assert main([str(ESEMPIO)]) == 0
    assert "| QD1 |" in capsys.readouterr().out
    assert main([str(ESEMPIO), "--json"]) == 0
    righe = json.loads(capsys.readouterr().out)
    assert {r["id"] for r in righe} == {"QGBT_arrivo", "QGBT_partenze", "QD1"}
