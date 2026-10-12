"""Flusso di potenza sulla rete di prova IEEE a 14 nodi (pandapower ``case14``).

La rete è presa da ``pandapower.networks.case14()`` (conversione del caso
MATPOWER ``case14``, 100 MVA, 60 Hz), convertita nel formato dict di iec60909 e
risolta con ``run_load_flow``. I risultati sono confrontati:
- con ``pandapower.runpp`` (stessi dati, tolleranza 1e-6 su vm_pu e va_degree),
  senza e con il rispetto dei limiti di potenza reattiva dei generatori;
- con la soluzione pubblicata (MATPOWER ``case14``, moduli a 3 decimali e
  angoli a 2 decimali).
"""

import copy
import math

import pytest

pp = pytest.importorskip("pandapower")
pn = pytest.importorskip("pandapower.networks")

from iec60909 import network_from_dict  # noqa: E402
from iec60909.loadflow import run_load_flow  # noqa: E402

# Soluzione pubblicata della IEEE 14 nodi risolta da MATPOWER (runpf su case14;
# pandapower dà gli stessi valori): moduli in p.u. arrotondati a 3 decimali e
# angoli in gradi arrotondati a 2 decimali.
# Il file originale IEEE CDF contiene la soluzione storica, leggermente
# diversa (non è la soluzione esatta dei suoi stessi dati): nodo 4 1.019
# (MATPOWER 1.0177), angoli -12.72 / -10.33 / -8.78 / -13.37 ai nodi 3 / 4 / 5 / 7
# (MATPOWER -12.725 / -10.313 / -8.774 / -13.360). Si usano i valori MATPOWER.
VM_PUBBLICATE = [1.060, 1.045, 1.010, 1.018, 1.020, 1.070, 1.062,
                 1.090, 1.056, 1.051, 1.057, 1.055, 1.050, 1.036]
VA_PUBBLICATI = [0.00, -4.98, -12.73, -10.31, -8.77, -14.22, -13.36,
                 -13.36, -14.94, -15.10, -14.79, -15.08, -15.16, -16.03]


def _bus_id(net, b: int) -> str:
    return str(net.bus.at[b, "name"])


def case14_to_dict(net) -> dict:
    """Converte una rete pandapower (case14) nel formato dict di iec60909.

    Corrispondenze e approssimazioni:
    - nodi: ``vn_kv`` di pandapower → ``un_kv`` (135, 14, 12 e 0,208 kV sono le
      tensioni fittizie con cui pandapower converte le impedenze in p.u. di
      MATPOWER: il flusso di potenza dipende solo dai valori in p.u.);
    - rete esterna: nodo di saldo con ``vm_pu`` e ``va_degree``; i limiti di
      potenza reattiva della rete esterna sono ignorati, come in pandapower;
      ``skq_max_mva`` è un valore fittizio richiesto solo dalla validazione
      del cortocircuito;
    - linee: r, x, c per km e lunghezza (``g_us_per_km`` deve essere nullo);
      la frequenza della rete è 60 Hz, quella usata da pandapower per
      ricavare c_nf_per_km dalla suscettanza in p.u.;
    - trasformatori: pandapower rappresenta i rapporti fuori nominale di
      MATPOWER (0,978, 0,969, 0,932) con ``vn_hv_kv`` uguale alla tensione del
      nodo e presa ``tap_pos = -1`` di ``tap_step_percent`` sul lato AT
      (presa neutra 0), cioè rapporto 1 + tap_pos·step/100 sul lato AT; il
      modello iec60909 usa la stessa convenzione (tap_pos relativo alla presa
      neutra), quindi i dati si trasferiscono senza modifiche. Per i
      trasformatori senza variatore (tap_pos NaN) si pone tap_pos = 0. La presa
      neutra deve essere 0 (altrimenti si userebbe tap_pos − tap_neutral). Gli
      sfasamenti sono nulli in case14 (shift_degree = 0), quindi l'assenza
      degli sfasamenti nel modello iec60909 non introduce approssimazioni.
      ``vkr_percent`` = 0 (trasformatori ideali senza perdite), ``i0`` e
      ``pfe`` nulli: modello a π e a T coincidono;
    - generatori: nodi PV con ``p_mw``, ``vm_pu`` e limiti ``min/max_q_mvar``;
      i dati di cortocircuito (sr_mva, ur_kv, xd2_percent) sono fittizi;
    - carichi: potenza costante (le quote a impedenza/corrente costante di
      pandapower sono nulle in case14);
    - derivazioni: ``q_mvar`` con la stessa convenzione di pandapower
      (positivo = induttivo, assorbito), riferito alla tensione nominale del
      nodo (``vn_kv`` della derivazione uguale a quella del nodo), moltiplicato
      per ``step``.
    """
    assert (net.trafo.shift_degree == 0).all()
    assert (net.line.g_us_per_km == 0).all()
    assert net.sgen.empty and net.trafo3w.empty

    buses = [{"id": _bus_id(net, b), "un_kv": float(net.bus.at[b, "vn_kv"])} for b in net.bus.index]
    grids = [
        {"id": f"Q{i}", "bus": _bus_id(net, int(r.bus)), "skq_max_mva": 10000.0,
         "rx_max": 0.1, "vm_pu": float(r.vm_pu), "va_degree": float(r.va_degree)}
        for i, r in net.ext_grid.iterrows()
    ]
    lines = []
    for i, r in net.line.iterrows():
        lines.append({
            "id": f"L{i}", "from_bus": _bus_id(net, int(r.from_bus)),
            "to_bus": _bus_id(net, int(r.to_bus)), "length_km": float(r.length_km),
            "r1_ohm_per_km": float(r.r_ohm_per_km), "x1_ohm_per_km": float(r.x_ohm_per_km),
            "c_nf_per_km": float(r.c_nf_per_km), "max_i_ka": float(r.max_i_ka),
            "parallel": int(r.parallel),
        })
    trafos = []
    for i, r in net.trafo.iterrows():
        tap_pos = 0.0 if math.isnan(r.tap_pos) else float(r.tap_pos)
        tap_step = 0.0 if math.isnan(r.tap_step_percent) else float(r.tap_step_percent)
        if tap_pos != 0.0:
            assert float(r.tap_neutral) == 0.0
        trafos.append({
            "id": f"T{i}", "hv_bus": _bus_id(net, int(r.hv_bus)),
            "lv_bus": _bus_id(net, int(r.lv_bus)), "sr_mva": float(r.sn_mva),
            "ur_hv_kv": float(r.vn_hv_kv), "ur_lv_kv": float(r.vn_lv_kv),
            "ukr_percent": float(r.vk_percent), "urr_percent": float(r.vkr_percent),
            "vector_group": "YNyn0", "tap_pos": tap_pos, "tap_step_percent": tap_step,
            "tap_side": r.tap_side if isinstance(r.tap_side, str) else "hv",
            "i0_percent": float(r.i0_percent), "pfe_kw": float(r.pfe_kw),
            "parallel": int(r.parallel),
        })
    gens = []
    for i, r in net.gen.iterrows():
        bus = int(r.bus)
        gens.append({
            "id": f"G{i}", "bus": _bus_id(net, bus), "sr_mva": 100.0,
            "ur_kv": float(net.bus.at[bus, "vn_kv"]), "xd2_percent": 20.0,
            "p_mw": float(r.p_mw) * float(r.scaling), "vm_pu": float(r.vm_pu),
            "q_min_mvar": float(r.min_q_mvar), "q_max_mvar": float(r.max_q_mvar),
        })
    loads = [
        {"id": f"C{i}", "bus": _bus_id(net, int(r.bus)),
         "p_mw": float(r.p_mw) * float(r.scaling), "q_mvar": float(r.q_mvar) * float(r.scaling)}
        for i, r in net.load.iterrows()
    ]
    shunts = []
    for i, r in net.shunt.iterrows():
        assert abs(float(r.vn_kv) - float(net.bus.at[int(r.bus), "vn_kv"])) < 1e-12
        shunts.append({"id": f"S{i}", "bus": _bus_id(net, int(r.bus)),
                       "q_mvar": float(r.q_mvar) * float(r.step),
                       "p_mw": float(r.p_mw) * float(r.step)})
    return {
        "name": "IEEE 14 nodi (pandapower case14)",
        "f_hz": float(net.f_hz),
        "buses": buses,
        "external_grids": grids,
        "transformers": trafos,
        "lines": lines,
        "generators": gens,
        "loads": loads,
        "shunts": shunts,
    }


def _run_pp(net, enforce_q_lims: bool):
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, trafo_model="pi",
             init="flat", tolerance_mva=1e-10, enforce_q_lims=enforce_q_lims)
    return net.res_bus


def _confronta(pp_net, data: dict, enforce_q_lims: bool) -> tuple[float, float]:
    res_pp = _run_pp(pp_net, enforce_q_lims)
    res = run_load_flow(network_from_dict(data), tol_mva=1e-10, enforce_q_lims=enforce_q_lims)
    assert res.converged
    dvm = dva = 0.0
    for b in pp_net.bus.index:
        lb = res.bus(_bus_id(pp_net, b))
        dvm = max(dvm, abs(lb.vm_pu - res_pp.at[b, "vm_pu"]))
        dva = max(dva, abs(lb.va_degree - res_pp.at[b, "va_degree"]))
    assert dvm < 1e-6, dvm
    assert dva < 1e-6, dva
    # potenza della rete esterna e dei generatori PV
    for i, r in pp_net.ext_grid.iterrows():
        s = res.source(f"Q{i}")
        assert s.p_mw == pytest.approx(pp_net.res_ext_grid.at[i, "p_mw"], abs=1e-5)
        assert s.q_mvar == pytest.approx(pp_net.res_ext_grid.at[i, "q_mvar"], abs=1e-5)
    for i in pp_net.gen.index:
        s = res.source(f"G{i}")
        assert s.q_mvar == pytest.approx(pp_net.res_gen.at[i, "q_mvar"], abs=1e-5)
    return dvm, dva


@pytest.mark.parametrize("enforce_q_lims", [False, True])
def test_ieee14_come_pandapower(enforce_q_lims):
    net = pn.case14()
    _confronta(net, case14_to_dict(net), enforce_q_lims)


def test_ieee14_limiti_q_attivi():
    """Limiti di potenza reattiva ristretti: alcuni nodi PV passano a PQ.

    Nella case14 originale nessun generatore raggiunge i limiti (Q = 43,6;
    25,1; 12,7; 17,6 Mvar), quindi con limiti ristretti si verifica anche la
    commutazione PV → PQ: i nodi 3 e 8 restano al limite massimo e la loro
    tensione scende sotto il valore regolato.
    """
    net = pn.case14()
    net.gen.loc[1, "max_q_mvar"] = 15.0   # nodo 3: Q naturale 25,1 Mvar
    net.gen.loc[3, "max_q_mvar"] = 10.0   # nodo 8: Q naturale 17,6 Mvar
    data = case14_to_dict(net)
    _confronta(net, copy.deepcopy(data), enforce_q_lims=True)
    res_pp = net.res_gen
    assert res_pp.at[1, "q_mvar"] == pytest.approx(15.0, abs=1e-6)
    assert res_pp.at[3, "q_mvar"] == pytest.approx(10.0, abs=1e-6)
    res = run_load_flow(network_from_dict(data), tol_mva=1e-10, enforce_q_lims=True)
    assert res.source("G1").q_mvar == pytest.approx(15.0, abs=1e-6)
    assert res.source("G3").q_mvar == pytest.approx(10.0, abs=1e-6)
    assert res.bus("3").vm_pu < 1.010 and res.bus("8").vm_pu < 1.090


def test_ieee14_soluzione_pubblicata():
    net = pn.case14()
    res = run_load_flow(network_from_dict(case14_to_dict(net)), tol_mva=1e-10)
    assert res.converged
    for k, (vm, va) in enumerate(zip(VM_PUBBLICATE, VA_PUBBLICATI), start=1):
        lb = res.bus(str(k))
        # arrotondamento a 3 e 2 decimali: scarto massimo mezza unità dell'ultima cifra
        assert lb.vm_pu == pytest.approx(vm, abs=5e-4 + 1e-9), k
        assert lb.va_degree == pytest.approx(va, abs=5e-3 + 1e-9), k
    # perdite e potenza del nodo di saldo pubblicate: 13,393 MW, 232,39 MW
    assert res.losses_mw == pytest.approx(13.393, abs=1e-3)
    assert res.source("Q0").p_mw == pytest.approx(232.39, abs=5e-3)
