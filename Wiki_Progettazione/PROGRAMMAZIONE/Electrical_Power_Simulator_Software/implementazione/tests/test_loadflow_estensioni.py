"""Flusso di potenza: estensioni del modello.

- sfasamenti dei gruppi vettoriali (due e tre avvolgimenti);
- trasformatori a tre avvolgimenti con presa e magnetizzazione;
- regolazione automatica delle prese (variatore sotto carico);
- regolazione remota della tensione dei generatori;
- saldo distribuito;
- carichi dipendenti dalla tensione (ZIP).
Confronti con pandapower 3.5.6 (tolleranza 1e-6) e con soluzioni a mano.
"""

import cmath
import copy
import math
import warnings

import pytest

from iec60909 import calculate, network_from_dict
from iec60909.loadflow import clock_numbers, run_load_flow
from tests.test_loadflow import RETE_LF

pp = pytest.importorskip("pandapower")
pp_ref = pytest.importorskip("tests.pp_ref", reason="pandapower non installato")

TOL = 1e-6


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _dang(a, b):
    """Differenza di due angoli in gradi, ridotta a (−180°, 180°]."""
    return (a - b + 180.0) % 360.0 - 180.0


def _confronta(data, lf=None, pf=None, controllo=None):
    """Risolve con iec60909 e con pandapower; restituisce i risultati e gli scarti massimi."""
    res = run_load_flow(network_from_dict(data), tol_mva=1e-10, **(lf or {}))
    net, ids = pp_ref.to_pandapower(data)
    if controllo is not None:
        controllo(net)
    pp.runpp(net, trafo_model="pi", calculate_voltage_angles=True, tolerance_mva=1e-10,
             init="dc", **(pf or {}))
    assert res.converged
    dvm = max(abs(res.bus(b).vm_pu - net.res_bus.at[i, "vm_pu"]) for b, i in ids.items())
    dva = max(abs(_dang(res.bus(b).va_degree, net.res_bus.at[i, "va_degree"])) for b, i in ids.items())
    assert dvm < TOL, dvm
    assert dva < TOL, dva
    eg = net.res_ext_grid
    for k, q in enumerate(data.get("external_grids", [])):
        assert res.source(q["id"]).p_mw == pytest.approx(eg.p_mw.iloc[k], abs=TOL)
        assert res.source(q["id"]).q_mvar == pytest.approx(eg.q_mvar.iloc[k], abs=TOL)
    return res, net, ids


# --- sfasamenti dei gruppi vettoriali ---------------------------------------------


@pytest.mark.parametrize("gruppo, k", [("Dyn", 0), ("Dyn5", 5), ("Dyn11", 11), ("YNd1", 1),
                                       ("Yzn11", 11), ("YNyn6", 6)])
def test_numero_orario_due_avvolgimenti(gruppo, k):
    assert clock_numbers(gruppo, 2) == [k]


def test_numero_orario_tre_avvolgimenti():
    assert clock_numbers("YNyn0d5", 3) == [0, 5]
    assert clock_numbers("YNd11d1", 3) == [11, 1]
    assert clock_numbers("YNynd", 3) == [0, 0]
    with pytest.raises(ValueError):
        clock_numbers("Dyn13", 2)
    with pytest.raises(ValueError):
        clock_numbers("Dyn5", 3)


@pytest.mark.parametrize("k", range(12))
def test_sfasamento_a_vuoto(k):
    """Trasformatore a vuoto senza magnetizzazione: U_BT = U_AT·e^(−j·k·30°)/N.

    La tensione dell'avvolgimento BT è in ritardo di k·30° (convenzione IEC
    60076-1); con phase_shift=False l'angolo resta nullo.
    """
    data = {
        "buses": [{"id": "AT", "un_kv": 20.0}, {"id": "BT", "un_kv": 0.4}],
        "external_grids": [{"id": "Q", "bus": "AT", "skq_max_mva": 500, "vm_pu": 1.0,
                            "va_degree": 10.0}],
        "transformers": [{"id": "T", "hv_bus": "AT", "lv_bus": "BT", "sr_mva": 0.63,
                          "ur_hv_kv": 20.0, "ur_lv_kv": 0.42, "ukr_percent": 6.0,
                          "urr_percent": 1.0, "vector_group": f"Dyn{k}"}],
    }
    res = run_load_flow(network_from_dict(data), tol_mva=1e-12)
    assert res.bus("BT").vm_pu == pytest.approx(0.42 / 0.4, rel=1e-12)
    assert _dang(res.bus("BT").va_degree, 10.0 - 30.0 * k) == pytest.approx(0.0, abs=1e-9)
    rel = run_load_flow(network_from_dict(data), phase_shift=False)
    assert rel.bus("BT").va_degree == pytest.approx(10.0, abs=1e-9)


def test_sfasamento_maglia_tra_trasformatori():
    """Maglia chiusa a 20 kV tra due trasformatori Dyn5 e YNd5 (stesso sfasamento).

    Il circuito a π con rapporto complesso (ammettenze non simmetriche) deve
    dare in maglia gli stessi flussi di pandapower.
    """
    data = {
        "buses": [{"id": "AT", "un_kv": 110.0}, {"id": "M1", "un_kv": 20.0},
                  {"id": "M2", "un_kv": 20.0}, {"id": "BT", "un_kv": 0.4}],
        "external_grids": [{"id": "Q", "bus": "AT", "skq_max_mva": 3000, "rx_max": 0.1,
                            "vm_pu": 1.03}],
        "transformers": [
            {"id": "TA", "hv_bus": "AT", "lv_bus": "M1", "sr_mva": 25, "ur_hv_kv": 110,
             "ur_lv_kv": 20, "ukr_percent": 11, "urr_percent": 0.5, "vector_group": "Dyn5",
             "tap_pos": 1, "tap_step_percent": 1.25},
            {"id": "TB", "hv_bus": "AT", "lv_bus": "M2", "sr_mva": 16, "ur_hv_kv": 110,
             "ur_lv_kv": 21, "ukr_percent": 10, "urr_percent": 0.6, "vector_group": "YNd5",
             "i0_percent": 0.1, "pfe_kw": 12},
            {"id": "TC", "hv_bus": "M2", "lv_bus": "BT", "sr_mva": 0.8, "ur_hv_kv": 20,
             "ur_lv_kv": 0.4, "ukr_percent": 6, "urr_percent": 1.1, "vector_group": "Dyn11"},
        ],
        "lines": [{"id": "L", "from_bus": "M1", "to_bus": "M2", "length_km": 4,
                   "r1_ohm_per_km": 0.16, "x1_ohm_per_km": 0.11, "c_nf_per_km": 280}],
        "loads": [{"id": "C1", "bus": "M1", "p_mw": 9.0, "q_mvar": 3.0},
                  {"id": "C2", "bus": "M2", "p_mw": 6.0, "q_mvar": 2.5},
                  {"id": "C3", "bus": "BT", "p_mw": 0.5, "q_mvar": 0.2}],
    }
    res, net, _ = _confronta(data)
    names = list(net.trafo.index)
    for k, t in enumerate(data["transformers"]):
        r, ref = res.branch(t["id"]), net.res_trafo.loc[names[k]]
        assert r.p_from_mw == pytest.approx(ref.p_hv_mw, abs=TOL), t["id"]
        assert r.q_to_mvar == pytest.approx(ref.q_lv_mvar, abs=TOL), t["id"]
    assert res.branch("L").p_from_mw == pytest.approx(net.res_line.p_from_mw.iloc[0], abs=TOL)
    # BT: Dyn5 + Dyn11 → −150° − 330° = −480° ≡ −120°
    assert _dang(res.bus("BT").va_degree, -120.0) == pytest.approx(0.0, abs=5.0)


# --- tre avvolgimenti: presa e magnetizzazione ------------------------------------


@pytest.mark.parametrize("lato", ["hv", "mv", "lv"])
@pytest.mark.parametrize("gruppo", ["YNyn0d5", "YNd11d1"])
def test_tre_avvolgimenti_presa_e_magnetizzazione(lato, gruppo):
    data = copy.deepcopy(RETE_LF)
    data["transformers3w"][0].update(tap_side=lato, tap_pos=-3, tap_step_percent=1.5,
                                     i0_percent=0.3, pfe_kw=20.0, vector_group=gruppo)
    res, net, _ = _confronta(data)
    ref = net.res_trafo3w.iloc[0]
    for w in ("hv", "mv", "lv"):
        br = res.branch(f"T3W:{w}")
        assert br.p_from_mw == pytest.approx(ref[f"p_{w}_mw"], abs=TOL), w
        assert br.q_from_mvar == pytest.approx(ref[f"q_{w}_mvar"], abs=TOL), w
        assert br.i_from_ka == pytest.approx(ref[f"i_{w}_ka"], abs=TOL), w
    perdite = res.branch("T3W:hv").pl_mw + res.branch("T3W:mv").pl_mw + res.branch("T3W:lv").pl_mw
    assert perdite == pytest.approx(ref.pl_mw, abs=TOL)


def test_tre_avvolgimenti_perdite_a_vuoto():
    """A vuoto (MT e BT aperti) il tre avvolgimenti assorbe le perdite nel ferro.

    Magnetizzazione sul ramo AT (metà ai morsetti AT, metà al centro stella,
    come pandapower con trafo3w_losses="hv"): con impedenza di dispersione
    piccola rispetto a quella di magnetizzazione P ≈ pfe_kw·U², Q ≈ i0·Sr·U².
    """
    data = {
        "buses": [{"id": "A", "un_kv": 132.0}, {"id": "B", "un_kv": 20.0},
                  {"id": "C", "un_kv": 10.0}],
        "external_grids": [{"id": "Q", "bus": "A", "skq_max_mva": 5000, "rx_max": 0.1,
                            "vm_pu": 1.0}],
        "transformers3w": [{
            "id": "T", "hv_bus": "A", "mv_bus": "B", "lv_bus": "C",
            "ur_hv_kv": 132, "ur_mv_kv": 20, "ur_lv_kv": 10,
            "sr_hv_mv_mva": 40, "sr_hv_lv_mva": 20, "sr_mv_lv_mva": 20,
            "ukr_hv_mv_percent": 12, "ukr_hv_lv_percent": 15, "ukr_mv_lv_percent": 8,
            "urr_hv_mv_percent": 0.3, "urr_hv_lv_percent": 0.35, "urr_mv_lv_percent": 0.3,
            "vector_group": "YNyn0d11", "i0_percent": 0.5, "pfe_kw": 30.0}],
    }
    res = run_load_flow(network_from_dict(data))
    q = res.source("Q")
    assert q.p_mw == pytest.approx(0.030, rel=2e-3)
    assert q.q_mvar == pytest.approx(math.sqrt((0.005 * 40) ** 2 - 0.03**2), rel=2e-3)
    # BT a vuoto in anticipo di 30° (d11), a meno della caduta della corrente magnetizzante
    assert _dang(res.bus("C").va_degree, -330.0) == pytest.approx(0.0, abs=0.01)
    _confronta(data)


# --- regolazione automatica delle prese --------------------------------------------


def _con_controllo(indici, low, high):
    from pandapower.control import DiscreteTapControl

    def aggiungi(net):
        for k in indici:
            DiscreteTapControl(net, k, vm_lower_pu=low, vm_upper_pu=high, side="lv")
    return aggiungi


@pytest.mark.parametrize("vm, banda, presa_attesa", [(1.0, 0.01, -2), (1.07, 0.008, 1), (1.04, 0.01, 0)])
def test_variatore_lato_bt_come_pandapower(vm, banda, presa_attesa):
    """T3 (presa sul lato BT, passo 2,5 %) regola la tensione del nodo BT."""
    data = copy.deepcopy(RETE_LF)
    data["transformers"][2].update(tap_pos=0, tap_min=-4, tap_max=4, control_bus="BT",
                                   control_vm_pu=vm, control_band_pu=banda)
    res, net, _ = _confronta(data, pf={"run_control": True},
                             controllo=_con_controllo([2], vm - banda, vm + banda))
    assert res.taps["T3"] == net.trafo.tap_pos.iloc[2] == presa_attesa
    assert abs(res.bus("BT").vm_pu - vm) <= banda
    assert not res.warnings


def test_variatore_lato_at_trasformatori_in_parallelo():
    """T1 e T2 in parallelo (presa AT) regolano insieme il nodo A, un passo per volta."""
    data = copy.deepcopy(RETE_LF)
    for t in data["transformers"][:2]:
        t.update(tap_pos=0, tap_min=-9, tap_max=9, control_bus="A", control_vm_pu=1.03,
                 control_band_pu=0.006)
    res, net, _ = _confronta(data, pf={"run_control": True},
                             controllo=_con_controllo([0, 1], 1.024, 1.036))
    assert res.taps == {"T1": net.trafo.tap_pos.iloc[0], "T2": net.trafo.tap_pos.iloc[1]}
    assert res.taps["T1"] == res.taps["T2"] < 0  # presa AT più bassa per alzare la tensione MT
    assert abs(res.bus("A").vm_pu - 1.03) <= 0.006
    # passo minimo necessario: una presa in meno lascerebbe la tensione fuori banda
    meno = copy.deepcopy(data)
    for t in meno["transformers"][:2]:
        t.update(tap_pos=res.taps["T1"] + 1, control_bus=None)
    assert run_load_flow(network_from_dict(meno)).bus("A").vm_pu < 1.03 - 0.006


def test_variatore_al_limite_e_prese_fisse():
    data = copy.deepcopy(RETE_LF)
    data["transformers"][2].update(tap_pos=0, tap_min=-1, tap_max=1, control_bus="BT",
                                   control_vm_pu=0.95, control_band_pu=0.005)
    res = run_load_flow(network_from_dict(data))
    assert res.taps["T3"] == -1
    assert any("fuori banda" in w for w in res.warnings)
    fisse = run_load_flow(network_from_dict(data), tap_control=False)
    assert fisse.taps == {}
    data["transformers"][2]["control_bus"] = None
    assert fisse.bus("BT").vm_pu == pytest.approx(run_load_flow(network_from_dict(data)).bus("BT").vm_pu)


def test_variatore_pendolamento():
    """Banda più stretta di mezzo passo: nessuna presa soddisfa la banda."""
    data = copy.deepcopy(RETE_LF)
    data["transformers"][2].update(tap_pos=0, tap_min=-5, tap_max=5, control_bus="BT",
                                   control_vm_pu=1.0, control_band_pu=0.002)
    res = run_load_flow(network_from_dict(data))
    assert res.converged
    assert any("pendolamento" in w for w in res.warnings)


# --- regolazione remota della tensione ----------------------------------------------


def test_regolazione_remota():
    """G1 (nodo B) regola la tensione del nodo C a 1,0 p.u.

    Verifica indipendente: con G1 a regolazione locale alla tensione di B
    trovata, il nodo C si porta a 1,0 p.u. e la potenza reattiva coincide
    (anche in pandapower, che non ha la regolazione remota).
    """
    data = copy.deepcopy(RETE_LF)
    data["generators"][0].update(regulated_bus="C", vm_pu=1.0)
    res = run_load_flow(network_from_dict(data), tol_mva=1e-10)
    assert res.converged
    assert res.bus("C").vm_pu == pytest.approx(1.0, abs=1e-12)
    locale = copy.deepcopy(RETE_LF)
    locale["generators"][0].update(vm_pu=res.bus("B").vm_pu)
    rl, net, _ = _confronta(locale)
    assert rl.bus("C").vm_pu == pytest.approx(1.0, abs=1e-9)
    assert net.res_bus.vm_pu.iloc[3] == pytest.approx(1.0, abs=TOL)
    assert rl.source("G1").q_mvar == pytest.approx(res.source("G1").q_mvar, abs=1e-6)
    for b in res.buses:
        assert rl.bus(b.bus).vm_pu == pytest.approx(b.vm_pu, abs=1e-9)
    # bilancio di potenza
    gen = sum(s.p_mw for s in res.sources) + 1.5
    carichi = 12 + 5 + 6 + 0.6 + 8 + 4 + 0.8 * 2.0 / 0.96 + 0.002 * res.bus("MT3").vm_pu ** 2
    assert gen == pytest.approx(carichi + res.losses_mw, rel=1e-9)


def test_regolazione_remota_attraverso_trasformatore_con_limiti():
    """Generatore sul nodo A che regola il nodo BT (oltre T3); con il limite di Q
    il generatore passa a PQ e la tensione di BT scende sotto il riferimento."""
    data = copy.deepcopy(RETE_LF)
    data["generators"].append({"id": "G2", "bus": "A", "sr_mva": 20, "ur_kv": 20,
                               "xd2_percent": 15, "p_mw": 4.0, "vm_pu": 1.08,
                               "regulated_bus": "BT", "q_max_mvar": 8.0})
    libero = run_load_flow(network_from_dict(data))
    assert libero.bus("BT").vm_pu == pytest.approx(1.08, abs=1e-9)
    assert libero.source("G2").q_mvar > 8.0
    res = run_load_flow(network_from_dict(data), enforce_q_lims=True)
    assert res.source("G2").q_mvar == pytest.approx(8.0, abs=1e-7)
    assert res.bus("BT").vm_pu < 1.08


def test_regolazione_remota_errori():
    data = copy.deepcopy(RETE_LF)
    data["generators"][0].update(regulated_bus="AT")
    with pytest.raises(ValueError, match="nodo di saldo"):
        run_load_flow(network_from_dict(data))
    data["generators"][0].update(regulated_bus="X")
    with pytest.raises(ValueError, match="inesistente"):
        run_load_flow(network_from_dict(data))


# --- saldo distribuito ------------------------------------------------------------


@pytest.mark.parametrize("w_rete, w_gen", [(1.0, 2.0), (0.0, 1.0), (1.0, 0.0)])
def test_saldo_distribuito_come_pandapower(w_rete, w_gen):
    data = copy.deepcopy(RETE_LF)
    data["external_grids"][0]["slack_weight"] = w_rete
    data["generators"][0]["slack_weight"] = w_gen
    res, net, _ = _confronta(data, lf={"distributed_slack": True}, pf={"distributed_slack": True})
    assert res.source("G1").p_mw == pytest.approx(net.res_gen.p_mw.iloc[0], abs=TOL)
    # ripartizione secondo i pesi: G1 = p_mw + w_gen/Σw·Δ, rete = w_rete/Σw·Δ
    quota = res.slack_mw / (w_rete + w_gen)
    assert res.source("G1").p_mw == pytest.approx(6.0 + w_gen * quota, rel=1e-9)
    assert res.source("Q").p_mw == pytest.approx(w_rete * quota, abs=1e-9)


def test_saldo_distribuito_ieee14():
    """IEEE 14 nodi con tutti i generatori e la rete esterna a peso unitario."""
    pn = pytest.importorskip("pandapower.networks")
    from tests.test_loadflow_ieee14 import case14_to_dict

    net = pn.case14()
    data = case14_to_dict(net)
    net.ext_grid["slack_weight"] = 1.0
    net.gen["slack_weight"] = [1.0, 2.0, 0.5, 0.5]
    for g, w in zip(data["generators"], [1.0, 2.0, 0.5, 0.5]):
        g["slack_weight"] = w
    pp.runpp(net, calculate_voltage_angles=True, trafo_model="pi", init="flat",
             tolerance_mva=1e-10, distributed_slack=True)
    res = run_load_flow(network_from_dict(data), tol_mva=1e-10, distributed_slack=True)
    for b in net.bus.index:
        lb = res.bus(str(net.bus.at[b, "name"]))
        assert lb.vm_pu == pytest.approx(net.res_bus.at[b, "vm_pu"], abs=TOL)
        assert lb.va_degree == pytest.approx(net.res_bus.at[b, "va_degree"], abs=TOL)
    for i in net.gen.index:
        assert res.source(f"G{i}").p_mw == pytest.approx(net.res_gen.at[i, "p_mw"], abs=TOL)
    assert res.source("Q0").p_mw == pytest.approx(net.res_ext_grid.p_mw.iloc[0], abs=TOL)


def test_saldo_distribuito_senza_pesi():
    data = copy.deepcopy(RETE_LF)
    data["external_grids"][0]["slack_weight"] = 0.0
    with pytest.raises(ValueError, match="slack_weight"):
        run_load_flow(network_from_dict(data), distributed_slack=True)


# --- carichi dipendenti dalla tensione (ZIP) -------------------------------------


def test_zip_come_pandapower():
    data = copy.deepcopy(RETE_LF)
    data["loads"][0].update(const_z_p_percent=30, const_i_p_percent=20,
                            const_z_q_percent=50, const_i_q_percent=10)
    data["loads"][3].update(const_z_p_percent=100, const_z_q_percent=100)
    data["loads"][4].update(const_i_p_percent=100, const_i_q_percent=60)
    res, net, _ = _confronta(data, lf={"enforce_q_lims": False})
    # potenza assorbita dal carico LA alla tensione calcolata
    v = res.bus("A").vm_pu
    assert net.res_load.p_mw.iloc[0] == pytest.approx(12.0 * (0.3 * v * v + 0.2 * v + 0.5), rel=1e-9)
    assert net.res_load.q_mvar.iloc[0] == pytest.approx(4.0 * (0.5 * v * v + 0.1 * v + 0.4), rel=1e-9)


def test_zip_impedenza_costante_forma_chiusa():
    """Carico a impedenza costante: circuito lineare, V2 = V1·Zc/(Zl + Zc)."""
    data = {
        "buses": [{"id": "1", "un_kv": 20.0}, {"id": "2", "un_kv": 20.0}],
        "external_grids": [{"id": "Q", "bus": "1", "skq_max_mva": 500, "vm_pu": 1.02}],
        "lines": [{"id": "L", "from_bus": "1", "to_bus": "2", "length_km": 10,
                   "r1_ohm_per_km": 0.2, "x1_ohm_per_km": 0.35}],
        "loads": [{"id": "C", "bus": "2", "p_mw": 8.0, "q_mvar": 3.0,
                   "const_z_p_percent": 100, "const_z_q_percent": 100}],
    }
    res = run_load_flow(network_from_dict(data), tol_mva=1e-12)
    zb = 20.0**2 / 100.0
    zl = complex(2.0, 3.5) / zb
    zc = 1.0 / complex(0.08, -0.03)  # S = V²·Y* → Y = (P − jQ) con V = 1
    v2 = 1.02 * zc / (zl + zc)
    assert res.bus("2").vm_pu == pytest.approx(abs(v2), rel=1e-10)
    assert res.bus("2").va_degree == pytest.approx(math.degrees(cmath.phase(v2)), abs=1e-8)


def test_zip_quote_non_valide():
    data = copy.deepcopy(RETE_LF)
    data["loads"][0].update(const_z_p_percent=70, const_i_p_percent=40)
    with pytest.raises(ValueError, match="const_z_p"):
        run_load_flow(network_from_dict(data))


# --- i campi del flusso di potenza non cambiano il cortocircuito ---------------------


def test_cortocircuito_invariato():
    data = copy.deepcopy(RETE_LF)
    base = calculate(network_from_dict(data))
    data["transformers"][2].update(tap_pos=2, tap_min=-4, tap_max=4, control_bus="BT")
    data["transformers3w"][0].update(tap_side="mv", tap_pos=3, tap_step_percent=1.5,
                                     i0_percent=0.3, pfe_kw=20.0)
    data["generators"][0].update(regulated_bus="C", slack_weight=2.0)
    data["external_grids"][0]["slack_weight"] = 0.5
    data["loads"][0].update(const_z_p_percent=50, const_i_q_percent=50)
    mod = calculate(network_from_dict(data))
    for b in base.buses:
        assert mod.bus(b.bus).ikss3_ka == b.ikss3_ka
        assert mod.bus(b.bus).ikss1_ka == b.ikss1_ka
