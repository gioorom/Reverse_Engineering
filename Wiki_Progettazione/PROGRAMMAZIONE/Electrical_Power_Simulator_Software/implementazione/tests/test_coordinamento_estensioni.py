"""Coordinamento delle protezioni, estensioni: correnti nei rami per i guasti
dissimmetrici (reti di sequenza e gruppi vettoriali), protezioni di terra,
relè direzionali, corrente di interruzione, bande di tolleranza, selettività
energetica, convertitori pieni e guasti interni ai gruppi di generazione."""

import copy
import json
import math
from pathlib import Path

import pytest

from iec60909 import calculate, factors, network_from_dict
from iec60909.calc import _Builder, fault_currents
from iec60909.coordination import coordination_study, tcc_svg, trip_time_s, validate_device
from iec60909.network import Bus, ExternalGrid, Line, Network, ProtectiveDevice, StaticGenerator

from .reti import RETE_GRUPPO_GENERAZIONE, RETE_MAGLIATA, RETE_TRE_AVVOLGIMENTI

ESEMPIO = Path(__file__).resolve().parents[1] / "esempi" / "coordinamento_cabina.json"
SQ3 = math.sqrt(3.0)


def _cabina(motori=True):
    data = json.loads(ESEMPIO.read_text(encoding="utf-8"))
    if not motori:
        data["motors"] = []
    return data


def _kcl(fc, bus):
    """Somma delle correnti di fase che dagli elementi del nodo vanno verso il nodo."""
    tot = [0j, 0j, 0j]
    for (_, b), ph in fc.branch_phase_ka.items():
        if b == bus:
            tot = [t - p for t, p in zip(tot, ph)]
    return tot


def _riferimento(r, tipo):
    return {"3ph": r.ikss3_ka, "2ph": r.ikss2_ka, "1ph": r.ikss1_ka,
            "2ph_e": max(r.ikss2e_l2_ka, r.ikss2e_l3_ka)}[tipo]


# --- correnti nei rami: coerenza con calculate ---------------------------------------------


@pytest.mark.parametrize("dati, senza_sorgenti", [
    (RETE_MAGLIATA, ["A", "BT"]),
    (RETE_TRE_AVVOLGIMENTI, ["MT", "MT2", "TER"]),
    (_cabina(), ["QGBT"]),
])
@pytest.mark.parametrize("caso", ["max", "min"])
@pytest.mark.parametrize("tipo", ["3ph", "2ph", "1ph", "2ph_e"])
def test_correnti_coerenti_con_calculate(dati, senza_sorgenti, caso, tipo):
    """La corrente nel punto di guasto è quella di calculate; nei nodi senza
    sorgenti la somma delle correnti di fase dei rami (sequenze diretta,
    inversa e zero, con gli sfasamenti dei gruppi vettoriali) è uguale alla
    corrente di guasto in tutte e tre le fasi."""
    net = network_from_dict(copy.deepcopy(dati))
    sc = calculate(net, caso)
    for bus in net.buses:
        fc = fault_currents(net, bus.id, caso, fault_type=tipo)
        assert abs(fc.ikss_ka) == pytest.approx(_riferimento(sc.bus(bus.id), tipo), rel=1e-9, abs=1e-12)
        if bus.id in senza_sorgenti:
            for somma, i_f in zip(_kcl(fc, bus.id), fc.fault_phase_ka):
                assert abs(somma - i_f) <= 1e-9 * max(abs(fc.ikss_ka), 1.0)


def test_fasi_nel_punto_di_guasto():
    net = network_from_dict(_cabina())
    fc = fault_currents(net, "QD1", fault_type="1ph")
    ia, ib, ic = fc.fault_phase_ka
    assert abs(ib) < 1e-12 and abs(ic) < 1e-12 and ia == pytest.approx(3 * fc.fault_seq_ka[0])
    fc = fault_currents(net, "QD1", fault_type="2ph")
    ia, ib, ic = fc.fault_phase_ka
    assert abs(ia) < 1e-12 and ib == pytest.approx(-ic)


def test_dyn_monofase_lato_bt():
    """Verifica nota: guasto monofase sul lato BT di un Dyn, lato MT con
    corrente su due fasi di modulo I_BT·(Un_BT/Un_MT)/√3 e niente sulla terza;
    nessuna corrente residua lato MT (avvolgimento a triangolo)."""
    for gruppo in ("Dyn11", "Dyn5", "Dyn"):
        data = _cabina(motori=False)
        data["transformers"][0]["vector_group"] = gruppo
        net = network_from_dict(data)
        fc = fault_currents(net, "QGBT", fault_type="1ph")
        i_bt = abs(fc.ikss_ka)
        assert i_bt == pytest.approx(calculate(net).bus("QGBT").ikss1_ka, rel=1e-12)
        mt = sorted(abs(i) for i in fc.branch_phase_ka[("TR1", "MT")])
        assert mt[0] < 1e-12
        assert mt[1] == pytest.approx(i_bt * 0.4 / 20.0 / SQ3, rel=1e-9)
        assert mt[2] == pytest.approx(i_bt * 0.4 / 20.0 / SQ3, rel=1e-9)
        assert fc.residual_ka("TR1", "MT") < 1e-12
        assert fc.residual_ka("TR1", "QGBT") == pytest.approx(i_bt, rel=1e-9)
    # gruppo senza numero orario: si assume 11
    dyn = fault_currents(network_from_dict(_cabina(False)), "QGBT", fault_type="1ph")
    data = _cabina(False)
    data["transformers"][0]["vector_group"] = "Dyn11"
    dyn11 = fault_currents(network_from_dict(data), "QGBT", fault_type="1ph")
    assert dyn.branch_phase_ka[("TR1", "MT")] == pytest.approx(dyn11.branch_phase_ka[("TR1", "MT")])
    assert dyn11.bus_shift_deg["MT"] == pytest.approx(330.0)


def test_dyn_bifase_lato_bt():
    """Guasto bifase lato BT di un Dy: lato MT una fase porta (2/√3)·I"k2·n,
    cioè la corrente del guasto trifase riportata, le altre due la metà."""
    net = network_from_dict(_cabina(motori=False))
    fc = fault_currents(net, "QGBT", fault_type="2ph")
    mt = sorted(abs(i) for i in fc.branch_phase_ka[("TR1", "MT")])
    i_k2 = abs(fc.ikss_ka)
    assert mt[2] == pytest.approx(2 / SQ3 * i_k2 * 0.02, rel=1e-9)
    assert mt[0] == pytest.approx(mt[2] / 2, rel=1e-9) and mt[1] == pytest.approx(mt[2] / 2, rel=1e-9)


def _rete_ynyn(gruppo):
    return network_from_dict({
        "buses": [{"id": "AT", "un_kv": 132.0}, {"id": "MT", "un_kv": 20.0}],
        "external_grids": [{"id": "Q", "bus": "AT", "skq_max_mva": 5000, "x0x1": 1.0}],
        "transformers": [{"id": "T", "hv_bus": "AT", "lv_bus": "MT", "sr_mva": 40, "ur_hv_kv": 132,
                          "ur_lv_kv": 20, "ukr_percent": 12, "urr_percent": 0.4, "vector_group": gruppo}],
    })


@pytest.mark.parametrize("gruppo, segno", [("YNyn0", 1.0), ("YNyn6", -1.0)])
def test_ynyn_omopolare_attraverso_il_trasformatore(gruppo, segno):
    """YNyn: la sequenza zero passa il trasformatore; con il guasto monofase
    lato MT il lato AT porta la sola fase guasta, riportata con il rapporto
    (invertita con il gruppo 6)."""
    fc = fault_currents(_rete_ynyn(gruppo), "MT", fault_type="1ph")
    ia, ib, ic = fc.branch_phase_ka[("T", "AT")]
    assert ia == pytest.approx(segno * fc.ikss_ka * 20.0 / 132.0, rel=1e-9)
    assert abs(ib) < 1e-9 and abs(ic) < 1e-9
    assert fc.residual_ka("T", "AT") == pytest.approx(abs(fc.ikss_ka) * 20 / 132, rel=1e-9)


def _rete_ynd():
    """Rete MT 20 kV con neutro a terra, trasformatore YNd che alimenta il
    guasto in sequenza zero, linea verso MT2."""
    return network_from_dict({
        "buses": [{"id": "MT", "un_kv": 20.0}, {"id": "MT2", "un_kv": 20.0}, {"id": "BT", "un_kv": 0.4}],
        "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 500, "rx_max": 0.1,
                            "x0x1": 1.0, "r0x0": 0.1}],
        "transformers": [{"id": "TN", "hv_bus": "MT", "lv_bus": "BT", "sr_mva": 2.0, "ur_hv_kv": 20.0,
                          "ur_lv_kv": 0.4, "ukr_percent": 6.0, "urr_percent": 1.0,
                          "uk0_percent": 5.0, "ur0_percent": 0.8, "vector_group": "YNd11"}],
        "lines": [{"id": "L", "from_bus": "MT", "to_bus": "MT2", "length_km": 2.0,
                   "r1_ohm_per_km": 0.2, "x1_ohm_per_km": 0.12, "r0_ohm_per_km": 0.6,
                   "x0_ohm_per_km": 0.4}],
    })


def test_ynd_derivazione_omopolare():
    """La corrente omopolare del guasto in MT2 si divide in MT tra la rete e il
    trasformatore YNd in proporzione inversa alle impedenze omopolari
    (calcolo a mano)."""
    net = _rete_ynd()
    fc = fault_currents(net, "MT2", fault_type="1ph")
    zq = 1.1 * 20.0**2 / 500.0
    xq = zq / math.sqrt(1.01)
    z0q = complex(0.1 * xq, xq)
    zr = 20.0**2 / 2.0
    kt = factors.transformer_kt(factors.voltage_factor(0.4, "max", 6), math.sqrt(6.0**2 - 1.0**2) / 100.0)
    z0t = kt * complex(0.008 * zr, math.sqrt(0.05**2 - 0.008**2) * zr)
    i0 = fc.fault_seq_ka[0]
    # il trasformatore eroga verso il nodo: corrente dal nodo verso il trasformatore negativa
    assert fc.branch_seq_ka[("TN", "MT")][0] == pytest.approx(-i0 * z0q / (z0q + z0t), rel=1e-9)
    assert fc.branch_seq_ka[("L", "MT")][0] == pytest.approx(i0, rel=1e-9)
    assert fc.residual_ka("TN", "BT") == 0.0  # lato triangolo
    # derivazione: corrente omopolare = ΔV0 del nodo / Z0 del trasformatore
    dv0 = fc.bus_dv_seq_kv["MT"][0]
    assert fc.branch_seq_ka[("TN", "MT")][0] == pytest.approx(dv0 / z0t, rel=1e-9)


# --- protezioni di terra --------------------------------------------------------------------


def _con_terra(data):
    data["protective_devices"] += [
        {"id": "G1", "branch": "C1", "bus": "QGBT", "kind": "relay", "measure": "residual",
         "stages": [{"pickup_a": 100, "time_s": 0.1}]},
        {"id": "G_gen", "branch": "TR1", "bus": "QGBT", "kind": "relay", "measure": "residual",
         "protects": "bus", "stages": [{"pickup_a": 200, "time_s": 0.5}]},
    ]
    return data


def test_studio_con_guasti_monofase_e_relè_di_terra():
    net = network_from_dict(_con_terra(_cabina()))
    res = coordination_study(net)
    assert res.issues == []
    sc_max, sc_min = calculate(net, "max"), calculate(net, "min")
    assert {f.level for f in res.faults if f.bus == "MT"} == {"max", "min"}  # rete MT senza terra
    assert {f.level for f in res.faults if f.bus == "QD1"} == {"max", "min", "max_1ph", "min_1ph"}
    assert res.fault("QD1", "max_1ph").ik_ka == pytest.approx(sc_max.bus("QD1").ikss1_ka)
    assert res.fault("QD1", "min_1ph").ik_ka == pytest.approx(sc_min.bus("QD1").ikss1_ka)
    # trifase: i relè di terra non vedono corrente
    f3 = res.fault("QD1", "max")
    for d in ("G1", "G_gen"):
        op = next(o for o in f3.operations if o.device == d)
        assert op.current_a < 1e-6 and op.order is None and op.time_s is None
    # monofase: catena QF1+G1 (stesso interruttore), QF_gen+G_gen, R_MT
    f1 = res.fault("QD1", "max_1ph")
    ordine = {o.device: o.order for o in f1.operations}
    assert ordine == {"QF1": 0, "G1": 0, "QF_gen": 1, "G_gen": 1, "R_MT": 2}
    g1 = next(o for o in f1.operations if o.device == "G1")
    assert g1.current_a == pytest.approx(f1.ik_ka * 1000.0, rel=1e-9)  # 3I0 = I"k1
    p = f1.pairs[0]
    assert (p.primary, p.backup) == ("QF1", "QF_gen")  # i più rapidi di ogni posizione
    # i relè misurano la corrente di fase maggiore e la residua dei loro rami
    fc = fault_currents(net, "QD1", fault_type="1ph")
    r_mt = next(o for o in f1.operations if o.device == "R_MT")
    g_gen = next(o for o in f1.operations if o.device == "G_gen")
    assert r_mt.current_a == pytest.approx(fc.phase_ka("TR1", "MT") * 1000.0, rel=1e-12)
    assert g_gen.current_a == pytest.approx(fc.residual_ka("TR1", "QGBT") * 1000.0, rel=1e-12)
    # relè di terra principale troppo lento rispetto alla riserva di terra
    data = _con_terra(_cabina())
    data["protective_devices"][3]["stages"] = [{"pickup_a": 100, "time_s": 0.45}]
    data["protective_devices"][2]["ii"] = None  # QF1 senza istantaneo: interviene G1
    data["protective_devices"][2]["isd"] = 10.0
    data["protective_devices"][2]["tsd_s"] = 0.5
    res = coordination_study(network_from_dict(data), fault_buses=["QD1"])
    assert any("guasto QD1 (max_1ph): G1–" in i and "non selettivi" in i for i in res.issues)


def test_relè_di_terra_su_trasformatore_di_messa_a_terra():
    """Rete MT con neutro isolato e trasformatore zig-zag di messa a terra:
    tutta la corrente del guasto monofase passa dal suo neutro."""
    data = {
        "buses": [{"id": "MT", "un_kv": 20.0}, {"id": "MT2", "un_kv": 20.0}],
        "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 500}],
        "earthing_transformers": [{"id": "ZZ", "bus": "MT", "z0_ohm": [1.0, 12.0], "zn_ohm": [20.0, 0.0]}],
        "lines": [{"id": "L", "from_bus": "MT", "to_bus": "MT2", "length_km": 2.0, "r1_ohm_per_km": 0.2,
                   "x1_ohm_per_km": 0.12, "r0_ohm_per_km": 0.6, "x0_ohm_per_km": 0.4}],
        "protective_devices": [
            {"id": "RL", "branch": "L", "bus": "MT", "kind": "relay", "measure": "residual",
             "curve": "IEC_SI", "pickup_a": 20, "tms": 0.05},
            {"id": "RZZ", "branch": "ZZ", "bus": "MT", "kind": "relay", "measure": "residual",
             "protects": "bus", "stages": [{"pickup_a": 30, "time_s": 1.5}]},
        ],
    }
    net = network_from_dict(data)
    fc = fault_currents(net, "MT2", fault_type="1ph")
    assert fc.residual_ka("ZZ", "MT") == pytest.approx(calculate(net).bus("MT2").ikss1_ka, rel=1e-9)
    res = coordination_study(net, fault_buses=["MT2"])
    f = res.fault("MT2", "max_1ph")
    assert [(p.primary, p.backup) for p in f.pairs] == [("RL", "RZZ")]
    assert f.pairs[0].ok and res.issues == []


# --- relè direzionali ----------------------------------------------------------------------


def _due_linee(direzionale):
    """Due linee in parallelo da MT verso B; guasto in M a metà della prima."""
    lin = dict(r1_ohm_per_km=0.2, x1_ohm_per_km=0.12, r0_ohm_per_km=0.6, x0_ohm_per_km=0.4)
    return network_from_dict({
        "buses": [{"id": "MT", "un_kv": 20.0}, {"id": "M", "un_kv": 20.0}, {"id": "B", "un_kv": 20.0}],
        "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 500, "x0x1": 1.0}],
        "lines": [{"id": "L1a", "from_bus": "MT", "to_bus": "M", "length_km": 2.0, **lin},
                  {"id": "L1b", "from_bus": "M", "to_bus": "B", "length_km": 2.0, **lin},
                  {"id": "L2", "from_bus": "MT", "to_bus": "B", "length_km": 4.0, **lin}],
        "protective_devices": [
            {"id": "R1", "branch": "L1b", "bus": "B", "kind": "relay", "directional": direzionale,
             "stages": [{"pickup_a": 200, "time_s": 0.1}]},
            {"id": "R2", "branch": "L2", "bus": "B", "kind": "relay", "directional": direzionale,
             "stages": [{"pickup_a": 200, "time_s": 0.1}]},
            {"id": "RT", "branch": "L2", "bus": "B", "kind": "relay", "directional": direzionale,
             "measure": "residual", "stages": [{"pickup_a": 50, "time_s": 0.1}]},
        ],
    })


@pytest.mark.parametrize("livello", ["max", "max_1ph"])
def test_relè_direzionale(livello):
    """Guasto sulla linea 1: all'estremo B la corrente entra in L1b (verso
    protetto) ed esce da L2 (verso opposto). Il direzionale su L2 non
    interviene; senza direzionalità interverrebbe insieme a R1."""
    res = coordination_study(_due_linee(True), fault_buses=["M"])
    ops = {o.device: o for o in res.fault("M", livello).operations}
    assert ops["R1"].forward and ops["R1"].time_s == pytest.approx(0.1)
    assert not ops["R2"].forward and ops["R2"].time_s is None
    assert ops["R2"].current_a > 200  # la corrente c'è, ma nel verso opposto
    if livello == "max_1ph":
        assert ops["RT"].current_a > 50 and ops["RT"].time_s is None
    nd = {o.device: o for o in coordination_study(_due_linee(False), fault_buses=["M"]).fault("M", livello).operations}
    assert nd["R2"].time_s == pytest.approx(0.1) and not nd["R2"].forward
    # guasto in B (fuori dalle linee viste da B): nessun direzionale interviene
    ops_b = {o.device: o for o in coordination_study(_due_linee(True), fault_buses=["B"]).fault("B").operations}
    assert ops_b["R1"].time_s is None and ops_b["R2"].time_s is None


def test_direzionale_con_corrente_di_carico():
    """Il direzionale non interviene con la corrente di carico nel verso opposto."""
    data = _cabina()
    data["protective_devices"][1].update(kind="relay", curve=None, stages=[{"pickup_a": 300, "time_s": 1.0}],
                                         directional=True, protects="branch")
    res = coordination_study(network_from_dict(data), fault_buses=["QD1"])
    assert not any(i.startswith("QF_gen: interviene con la corrente di carico") for i in res.issues)
    data["protective_devices"][1]["directional"] = False
    res = coordination_study(network_from_dict(data), fault_buses=["QD1"])
    assert any(i.startswith("QF_gen: interviene con la corrente di carico") for i in res.issues)


# --- corrente di interruzione ---------------------------------------------------------------


def test_corrente_di_interruzione_nei_rami():
    """Con Ib decadono solo i contributi che passano dal motore: con il guasto
    franco nel nodo la tensione del nodo è nulla e la corrente del ramo verso
    la rete non cambia; la somma è la Ib di calculate."""
    net = network_from_dict(_cabina())
    sc = calculate(net, tmin_s=0.05)
    for bus, ramo_rete, ramo_motore in (("QD1", ("C1", "QD1"), None), ("QGBT", ("TR1", "QGBT"), ("C1", "QGBT"))):
        a = fault_currents(net, bus)
        b = fault_currents(net, bus, breaking=True, tmin_s=0.05)
        assert abs(b.ikss_ka) == pytest.approx(sc.bus(bus).ib_ka, rel=1e-9)
        assert abs(b.ikss_ka) < abs(a.ikss_ka)
        assert b.branch_ka[ramo_rete] == pytest.approx(a.branch_ka[ramo_rete], rel=1e-9)
        if ramo_motore:
            assert abs(b.branch_ka[ramo_motore]) < 0.5 * abs(a.branch_ka[ramo_motore])
            assert abs(sum(-v for (_, n), v in b.branch_ka.items() if n == bus) - b.ikss_ka) < 1e-9
    # guasti dissimmetrici: Ib = I"k
    assert fault_currents(net, "QD1", fault_type="1ph", breaking=True).ikss_ka == pytest.approx(
        fault_currents(net, "QD1", fault_type="1ph").ikss_ka)


def test_studio_con_corrente_di_interruzione():
    net = network_from_dict(_cabina())
    res = coordination_study(net, current_basis="ib", tmin_s=0.05)
    assert res.fault("QGBT", "max").ik_ka == pytest.approx(calculate(net, tmin_s=0.05).bus("QGBT").ib_ka)
    assert res.fault("QGBT", "min").ik_ka == pytest.approx(calculate(net, "min").bus("QGBT").ikss2_ka)
    # QF1 vede meno corrente del motore che decade: interviene più tardi
    qf1 = {lv: next(o for o in coordination_study(net, ["QGBT"], current_basis=lv).fault("QGBT").operations
                    if o.device == "QF1") for lv in ("ik", "ib")}
    assert qf1["ib"].current_a < qf1["ik"].current_a and qf1["ib"].time_s > qf1["ik"].time_s
    with pytest.raises(ValueError, match="current_basis"):
        coordination_study(net, current_basis="x")


# --- bande di tolleranza --------------------------------------------------------------------


def test_bande_di_tolleranza_a_mano():
    d = ProtectiveDevice("R", "C1", "QGBT", "relay", curve="IEC_SI", pickup_a=100.0, tms=0.1,
                         current_tolerance_percent=10.0, time_tolerance_percent=5.0, time_tolerance_s=0.03)

    def nom(i):
        return 0.1 * 0.14 / ((i / 100.0) ** 0.02 - 1.0)

    t_min = nom(500.0 / 0.9)
    t_max = nom(500.0 / 1.1)
    assert trip_time_s(d, 500.0, "min") == pytest.approx(t_min - max(0.05 * t_min, 0.03))
    assert trip_time_s(d, 500.0, "max") == pytest.approx(t_max + max(0.05 * t_max, 0.03))
    assert trip_time_s(d, 500.0) == pytest.approx(nom(500.0))
    # soglia: tra 0,9 e 1,1 volte il pickup interviene solo il limite inferiore della banda
    assert trip_time_s(d, 105.0, "max") is None and trip_time_s(d, 105.0, "min") is not None
    with pytest.raises(ValueError, match="banda"):
        trip_time_s(d, 500.0, "x")


def test_selettività_con_le_bande():
    """QF1 (0,02 s) e QF_gen con corto ritardo 0,13 s: margine 0,11 s ≥ 0,1 s
    con le curve nominali, 0,07 s con ±20 ms sui tempi."""
    data = _cabina()
    data["protective_devices"][1]["tsd_s"] = 0.13
    res = coordination_study(network_from_dict(data), fault_buses=["QD1"], earth_faults=False)
    assert res.fault("QD1").pairs[0].ok
    for k in (1, 2):
        data["protective_devices"][k]["time_tolerance_s"] = 0.02
    res = coordination_study(network_from_dict(data), fault_buses=["QD1"], earth_faults=False)
    p = res.fault("QD1").pairs[0]
    assert (p.primary, p.backup, p.t_primary_max_s, p.t_backup_min_s) == ("QF1", "QF_gen", 0.04, 0.11)
    assert p.margin_s == pytest.approx(0.07) and not p.ok
    assert any("QF1–QF_gen non selettivi, margine 0.070 s" in i for i in res.issues)
    svg = tcc_svg(network_from_dict(data), ["QF1", "QF_gen", "R_MT"], 0.4)
    assert svg.count("<polyline") == 7 and svg.count('class="banda"') == 4


# --- selettività energetica -----------------------------------------------------------------


def _istantaneo_a_monte(limite=None):
    data = _cabina()
    data["protective_devices"][1].update(ii=8.0, ti_s=0.02)  # istantaneo: curve sovrapposte con QF1
    if limite is not None:
        data["protective_devices"][1]["selectivity_limits"] = {"QF1": limite}
    return data


def test_selettività_energetica():
    res = coordination_study(network_from_dict(_istantaneo_a_monte()), fault_buses=["QD1"])
    assert any("QF1–QF_gen non selettivi" in i for i in res.issues)
    i_qf1 = next(o for o in res.fault("QD1").operations if o.device == "QF1").current_a
    # tabella del costruttore: Is oltre la corrente di guasto, la coppia è selettiva
    res = coordination_study(network_from_dict(_istantaneo_a_monte(15.0)), fault_buses=["QD1"])
    assert res.issues == []
    p = res.fault("QD1").pairs[0]
    assert (p.primary, p.backup, p.selectivity_limit_ka, p.ok) == ("QF1", "QF_gen", 15.0, True)
    assert p.worst_current_a is None  # nessun controllo delle curve sotto Is
    # Is inferiore alla corrente nel principale: non selettivi
    res = coordination_study(network_from_dict(_istantaneo_a_monte(10.0)), fault_buses=["QD1"])
    assert i_qf1 > 10_000
    assert any(f"corrente {i_qf1 / 1000:.2f} kA in QF1 oltre il limite di selettività Is = 10 kA" in i
               for i in res.issues)
    # con il guasto monofase (corrente minore di Is) torna selettiva
    assert res.fault("QD1", "max_1ph").pairs[0].ok
    data = _istantaneo_a_monte()
    data["protective_devices"][1]["selectivity_limits"] = {"QX": 5.0}
    with pytest.raises(ValueError, match="dispositivo inesistente"):
        coordination_study(network_from_dict(data))


# --- convertitori pieni e gruppi di generazione ---------------------------------------------


def _rete_pf(case_pf=True):
    gens = [StaticGenerator("PV", "B", "PF", ikss_ka=0.4)] if case_pf else []
    return Network(
        buses=[Bus("A", 20.0), Bus("B", 20.0)],
        external_grids=[ExternalGrid("Q", "A", skq_max_mva=300.0, rx_max=0.1)],
        lines=[Line("L", "A", "B", 5.0, 0.2, 0.35, 0.6, 1.05)],
        static_generators=gens,
    )


@pytest.mark.parametrize("tipo", ["3ph", "2ph"])
def test_convertitore_pieno_nelle_correnti(tipo):
    """Il convertitore in B porta nella linea la sua corrente I"k_PF = 0,4 kA
    (B non ha altri elementi) e la corrente di guasto è quella di calculate."""
    net = _rete_pf()
    sc = calculate(net)
    fa = fault_currents(net, "A", fault_type=tipo)
    assert abs(fa.ikss_ka) == pytest.approx(_riferimento(sc.bus("A"), tipo), rel=1e-12)
    if tipo == "3ph":
        assert abs(fa.branch_ka[("L", "B")]) == pytest.approx(0.4, rel=1e-12)
    fb = fault_currents(net, "B", fault_type=tipo)
    assert abs(fb.ikss_ka) == pytest.approx(_riferimento(sc.bus("B"), tipo), rel=1e-12)
    if tipo == "3ph":
        # contributo della rete dalla linea + convertitore nel nodo guasto = I"k3
        assert abs(fb.ikss_ka + fb.branch_ka[("L", "B")]) == pytest.approx(0.4, rel=1e-12)
        assert abs(fb.branch_ka[("L", "B")]) == pytest.approx(
            calculate(_rete_pf(False)).bus("B").ikss3_ka, rel=1e-12)
    # caso minimo: convertitori esclusi
    assert abs(fault_currents(net, "A", "min").branch_ka[("L", "B")]) < 1e-12


def test_guasto_interno_al_gruppo():
    """Nodo del generatore: fattori K_G,S e K_T,S come in calculate; la corrente
    dal trasformatore più quella del generatore dà I"k."""
    net = network_from_dict(copy.deepcopy(RETE_GRUPPO_GENERAZIONE))
    sc = calculate(net)
    fc = fault_currents(net, "GEN")
    assert fc.inside_unit == "G"
    assert abs(fc.ikss_ka) == pytest.approx(sc.bus("GEN").ikss3_ka, rel=1e-12)
    b = _Builder(net, "max", [], "G")
    zg = b.generator_z(net.generators[0], 1) * b.zbase("GEN")
    i_g = b.c_case("GEN") * 10.5 / SQ3 / zg
    assert -fc.branch_ka[("TG", "GEN")] + i_g == pytest.approx(fc.ikss_ka, rel=1e-9)
    fuori = fault_currents(net, "AT2")
    assert fuori.inside_unit is None
    assert abs(fuori.ikss_ka) == pytest.approx(sc.bus("AT2").ikss3_ka, rel=1e-12)


# --- validazione e riga di comando -----------------------------------------------------------


@pytest.mark.parametrize("kw, msg", [
    (dict(kind="relay", stages=[{"pickup_a": 1.0, "time_s": 1.0}], measure="x"), "measure"),
    (dict(kind="fuse", points=[[1.0, 2.0], [2.0, 1.0]], measure="residual"), "fusibile"),
    (dict(kind="fuse", points=[[1.0, 2.0], [2.0, 1.0]], directional=True), "fusibile"),
    (dict(kind="breaker", in_a=100.0, current_tolerance_percent=120.0), "tolleranze"),
    (dict(kind="breaker", in_a=100.0, time_tolerance_s=-1.0), "time_tolerance_s"),
    (dict(kind="breaker", in_a=100.0, selectivity_limits={"X": 0}), "selectivity_limits"),
])
def test_dati_non_validi(kw, msg):
    with pytest.raises(ValueError, match=msg):
        validate_device(ProtectiveDevice(id="D", branch="C1", bus="QGBT", **kw))


def test_fault_currents_tipo_non_valido():
    with pytest.raises(ValueError, match="tipo di guasto"):
        fault_currents(network_from_dict(_cabina()), "QD1", fault_type="xx")


def test_riga_di_comando(tmp_path, capsys):
    from iec60909.coordinamento import main

    rete = tmp_path / "rete.json"
    rete.write_text(json.dumps(_con_terra(_cabina())), encoding="utf-8")
    assert main([str(rete), "--svg", str(tmp_path), "--ib", "--tmin", "0.05"]) == 0
    out = capsys.readouterr().out
    assert "correnti di interruzione Ib" in out and "I\"k1 max" in out and "| G1 | principale | 3I0 |" in out
    svg = (tmp_path / "tcc_QD1.svg").read_text(encoding="utf-8")
    assert "G1 (3I0)" in svg and "I\"k1 min" in svg
    assert main([str(rete), "--no-terra", "--json"]) == 0
    dati = json.loads(capsys.readouterr().out)
    assert {f["level"] for f in dati["faults"]} == {"max", "min"}
