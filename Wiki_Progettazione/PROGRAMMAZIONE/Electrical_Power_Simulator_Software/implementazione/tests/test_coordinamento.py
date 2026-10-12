"""Coordinamento delle protezioni: curve dei dispositivi, correnti nei rami,
selettività, sensibilità, correnti di carico, collegamento con l'arc flash."""

import copy
import json
import math
from pathlib import Path

import pytest

from iec60909 import calculate, network_from_dict
from iec60909.arcflash import arc_flash_study, arc_currents, enclosure_for
from iec60909.calc import fault_currents
from iec60909.coordination import coordination_study, tcc_svg, trip_time_s, validate_device
from iec60909.network import ProtectiveDevice

ESEMPIO = Path(__file__).resolve().parents[1] / "esempi" / "coordinamento_cabina.json"


def _dati():
    return json.loads(ESEMPIO.read_text(encoding="utf-8"))


def _dev(**kw):
    base = dict(id="D", branch="C1", bus="QGBT")
    base.update(kw)
    return ProtectiveDevice(**base)


# --- curve dei dispositivi -----------------------------------------------------------


@pytest.mark.parametrize("curve, a, p, b", [
    ("IEC_SI", 0.14, 0.02, 0.0), ("IEC_VI", 13.5, 1.0, 0.0), ("IEC_EI", 80.0, 2.0, 0.0),
    ("IEC_LTI", 120.0, 1.0, 0.0), ("IEEE_MI", 0.0515, 0.02, 0.114), ("IEEE_VI", 19.61, 2.0, 0.491),
    ("IEEE_EI", 28.2, 2.0, 0.1217),
])
def test_curve_relè(curve, a, p, b):
    d = _dev(kind="relay", curve=curve, pickup_a=100.0, tms=0.3, breaker_time_s=0.05)
    assert trip_time_s(d, 500.0) == pytest.approx(0.3 * (a / (5.0**p - 1) + b) + 0.05)
    assert trip_time_s(d, 100.0) is None  # alla soglia non interviene


def test_relè_soglie_a_tempo_definito():
    d = _dev(kind="relay", curve="IEC_SI", pickup_a=100.0, tms=0.1,
             stages=[{"pickup_a": 800.0, "time_s": 0.2}, {"pickup_a": 3000.0, "time_s": 0.03}])
    assert trip_time_s(d, 1000.0) == pytest.approx(min(0.1 * 0.14 / (10**0.02 - 1), 0.2))
    assert trip_time_s(d, 5000.0) == pytest.approx(0.03)
    solo_soglia = _dev(kind="relay", stages=[{"pickup_a": 500.0, "time_s": 0.4}])
    assert trip_time_s(solo_soglia, 400.0) is None
    assert trip_time_s(solo_soglia, 600.0) == pytest.approx(0.4)


def test_interruttore_lsi():
    d = _dev(kind="breaker", in_a=400.0, ir=0.8, tr_s=10.0, isd=5.0, tsd_s=0.2, ii=12.0, ti_s=0.03)
    ir = 320.0
    assert trip_time_s(d, 1.0 * ir) is None  # sotto 1,05·Ir
    assert trip_time_s(d, 3.0 * ir) == pytest.approx(10.0 * 36.0 / 9.0)  # L, I²t costante
    assert trip_time_s(d, 6.0 * ir) == pytest.approx(0.2)  # S a tempo definito
    assert trip_time_s(d, 13.0 * 400.0) == pytest.approx(0.03)  # I
    # S a I²t costante fino a 10·Ir
    d2 = _dev(kind="breaker", in_a=400.0, ir=0.8, tr_s=10.0, isd=5.0, tsd_s=0.2, i2t_sd=True)
    assert trip_time_s(d2, 6.0 * ir) == pytest.approx(0.2 * (10.0 / 6.0) ** 2)
    assert trip_time_s(d2, 20.0 * ir) == pytest.approx(0.2)
    # la zona L non scende sotto l'istantaneo alle correnti molto alte
    d3 = _dev(kind="breaker", in_a=160.0, tr_s=6.0, ii=10.0, ti_s=0.02)
    assert trip_time_s(d3, 1e6) == pytest.approx(0.02)


def test_fusibile_log_log():
    d = _dev(kind="fuse", points=[[100.0, 100.0], [1000.0, 0.1], [10000.0, 0.01]])
    assert trip_time_s(d, 90.0) is None
    assert trip_time_s(d, 100.0 * 10**0.5) == pytest.approx(10 ** (2 - 1.5))
    assert trip_time_s(d, 3162.27766) == pytest.approx(10**-1.5, rel=1e-6)
    assert trip_time_s(d, 1e6) == pytest.approx(0.01)


@pytest.mark.parametrize("kw, msg", [
    (dict(kind="relay"), "curva o almeno una soglia"),
    (dict(kind="relay", curve="XX", pickup_a=1.0), "curva sconosciuta"),
    (dict(kind="relay", curve="IEC_SI"), "pickup_a"),
    (dict(kind="relay", stages=[{"pickup_a": 1.0}]), "time_s"),
    (dict(kind="breaker"), "in_a"),
    (dict(kind="breaker", in_a=100.0, isd=2.0), "tsd_s"),
    (dict(kind="fuse", points=[[1.0, 1.0]]), "due punti"),
    (dict(kind="fuse", points=[[1.0, 1.0], [10.0, 5.0]]), "decrescere"),
    (dict(kind="altro"), "tipo"),
    (dict(kind="fuse", points=[[1.0, 2.0], [2.0, 1.0]], protects="x"), "protects"),
])
def test_dati_non_validi(kw, msg):
    with pytest.raises(ValueError, match=msg):
        validate_device(_dev(**kw))


# --- correnti nei rami ------------------------------------------------------------------


def test_correnti_nei_rami_radiale():
    """Senza motori la corrente nel cavo è la corrente di guasto; lato MT del
    trasformatore la stessa corrente riportata a 20 kV."""
    data = _dati()
    data["motors"] = []
    net = network_from_dict(data)
    fc = fault_currents(net, "QD1")
    assert abs(fc.ikss_ka) == pytest.approx(calculate(net).bus("QD1").ikss3_ka, rel=1e-12)
    assert fc.branch_ka[("C1", "QGBT")] == pytest.approx(fc.ikss_ka, rel=1e-9)
    assert fc.branch_ka[("C1", "QD1")] == pytest.approx(-fc.ikss_ka, rel=1e-9)
    assert fc.branch_ka[("TR1", "MT")] == pytest.approx(fc.ikss_ka * 0.4 / 20.0, rel=1e-9)


def test_correnti_nei_rami_bilancio_con_motore():
    """Nodo guasto: corrente dal cavo + contributo del motore = I"k."""
    net = network_from_dict(_dati())
    fc = fault_currents(net, "QD1")
    from iec60909.calc import _Builder

    b = _Builder(net, "max", [])
    zm = b.motor_z(net.motors[0], 1) * b.zbase("QD1")
    i_mot = 1.05 * 0.4 / math.sqrt(3) / zm  # il motore è ai morsetti del guasto
    assert -fc.branch_ka[("C1", "QD1")] + i_mot == pytest.approx(fc.ikss_ka, rel=1e-9)


# --- studio --------------------------------------------------------------------------------


def test_esempio_coordinato():
    res = coordination_study(network_from_dict(_dati()))
    assert res.issues == []
    f = res.fault("QD1", "max")
    ordine = sorted((o for o in f.operations if o.order is not None), key=lambda o: o.order)
    assert [o.device for o in ordine] == ["QF1", "QF_gen", "R_MT"]
    r_mt = next(o for o in f.operations if o.device == "R_MT")
    assert r_mt.time_s == pytest.approx(0.55 * 13.5 / (r_mt.current_a / 40.0 - 1.0) + 0.06)
    p = f.pairs[1]
    assert (p.primary, p.backup, p.required_s) == ("QF_gen", "R_MT", 0.3)
    assert p.margin_s == pytest.approx(r_mt.time_s - 0.3)
    # guasto sulle sbarre QGBT: la partenza QF1 non è nel verso protetto (contributo del motore)
    g = res.fault("QGBT", "max")
    assert next(o for o in g.operations if o.device == "QF1").order is None
    assert next(o for o in g.operations if o.device == "QF_gen").order == 0
    # caso minimo: corrente bifase
    sc = calculate(network_from_dict(_dati()), "min").bus("QD1")
    assert res.fault("QD1", "min").ik_ka == pytest.approx(sc.ikss2_ka)
    assert set(res.load_currents_a) == {"R_MT", "QF_gen", "QF1"}


def test_non_selettivo_al_punto_di_guasto():
    data = _dati()
    data["protective_devices"][0]["tms"] = 0.05
    res = coordination_study(network_from_dict(data))
    assert any("QF_gen–R_MT non selettivi, margine" in i for i in res.issues)


def test_non_selettivo_a_corrente_ridotta():
    """Tarature iniziali dell'esempio: selettive alle correnti di guasto ma non
    tra 1,4 e 3,8 kA (curva del relè MT sotto lo sganciatore L)."""
    data = _dati()
    data["protective_devices"][0]["pickup_a"] = 25.0
    data["protective_devices"][1]["isd"] = 4.0
    res = coordination_study(network_from_dict(data))
    f = res.fault("QD1", "max")
    p = next(p for p in f.pairs if p.backup == "R_MT")
    assert p.margin_s > 0.3  # al punto di guasto è selettivo
    assert not p.ok and p.worst_margin_s < 0
    assert 1000 < p.worst_current_a < 4000
    assert any("correnti inferiori a quella di guasto" in i for i in res.issues)


def test_sensibilità():
    data = _dati()
    data["protective_devices"][2].update(ii=None, tr_s=None, isd=100.0, tsd_s=0.1)
    res = coordination_study(network_from_dict(data), fault_buses=["QD1"])
    assert any("principale QF1 non interviene" in i for i in res.issues)


def test_intervento_con_la_corrente_di_carico():
    data = _dati()
    data["protective_devices"][2]["ir"] = 0.5  # Ir = 80 A < corrente del motore
    res = coordination_study(network_from_dict(data))
    assert any(i.startswith("QF1: interviene con la corrente di carico") for i in res.issues)
    res = coordination_study(network_from_dict(data), check_load=False)
    assert not any("corrente di carico" in i for i in res.issues)


def test_errori_di_configurazione():
    data = _dati()
    data["protective_devices"][0]["branch"] = "XX"
    with pytest.raises(ValueError, match="ramo inesistente"):
        coordination_study(network_from_dict(data))
    data = _dati()
    data["protective_devices"][0]["bus"] = "QD1"
    with pytest.raises(ValueError, match="non è un estremo"):
        coordination_study(network_from_dict(data))
    data = _dati()
    data["protective_devices"] = []
    with pytest.raises(ValueError, match="protective_devices"):
        coordination_study(network_from_dict(data))


# --- arc flash con i dispositivi --------------------------------------------------------------


def test_arc_flash_con_dispositivo():
    net = network_from_dict(_dati())
    res = {r.location: r for r in arc_flash_study(net)}
    # sbarre QGBT: interviene il corto ritardo dell'interruttore generale (0,3 s)
    assert res["QGBT_sbarre"].full.t_arc_ms == pytest.approx(300.0)
    assert res["QD1"].full.t_arc_ms == pytest.approx(20.0)
    # la corrente vista dal dispositivo è la sua quota della corrente di guasto
    point = net.arc_flash[0]
    ibf = calculate(net).bus("QGBT").ikss3_ka
    i_arc = arc_currents(enclosure_for(point, 0.4), ibf)[0]
    fc = fault_currents(net, "QGBT")
    share = abs(fc.branch_ka[("TR1", "QGBT")]) / abs(fc.ikss_ka)
    assert share < 1.0  # il motore contribuisce al guasto senza passare dall'interruttore
    dev = next(d for d in net.protective_devices if d.id == "QF_gen")
    assert res["QGBT_sbarre"].full.t_arc_ms == pytest.approx(trip_time_s(dev, i_arc * share * 1000) * 1000)


def test_arc_flash_dispositivo_inesistente():
    data = _dati()
    data["arc_flash"][0]["protection"] = {"device": "nessuno"}
    with pytest.raises(ValueError, match="dispositivo inesistente"):
        arc_flash_study(network_from_dict(data))


# --- uscita --------------------------------------------------------------------------------


def test_curve_svg():
    net = network_from_dict(_dati())
    svg = tcc_svg(net, ["QF1", "QF_gen", "R_MT"], 0.4, {"I\"k": 13.4}, "prova")
    assert svg.startswith("<svg") and svg.count("<polyline") == 3 and "1k" in svg


def test_riga_di_comando(tmp_path, capsys):
    from iec60909.coordinamento import main

    assert main([str(ESEMPIO), "--svg", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Sequenza di intervento" in out and "| QF_gen | R_MT |" in out
    assert {p.name for p in tmp_path.iterdir()} == {"tcc_QGBT.svg", "tcc_QD1.svg"}
    assert main([str(ESEMPIO), "--json", "--nodi", "QD1"]) == 0
    dati = json.loads(capsys.readouterr().out)
    assert {f["bus"] for f in dati["faults"]} == {"QD1"} and dati["issues"] == []
    data = _dati()
    data["protective_devices"][0]["tms"] = 0.05
    rete = tmp_path / "rete.json"
    rete.write_text(json.dumps(data), encoding="utf-8")
    assert main([str(rete)]) == 1  # problemi di coordinamento: codice di uscita 1
    capsys.readouterr()


def test_copia_non_modifica_esempio():
    a = _dati()
    b = copy.deepcopy(a)
    coordination_study(network_from_dict(a))
    assert a == b
