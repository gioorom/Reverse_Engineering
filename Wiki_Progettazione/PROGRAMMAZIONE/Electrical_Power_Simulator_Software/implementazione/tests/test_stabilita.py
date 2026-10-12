"""Stabilità transitoria: inizializzazione, criterio delle aree uguali, confronto
con un'integrazione indipendente (scipy) e con ANDES (sistema di Kundur)."""

import cmath
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from iec60909 import network_from_dict
from iec60909.network import StabilityEvent
from iec60909.stability import critical_clearing_time, simulate

ESEMPI = Path(__file__).resolve().parents[1] / "esempi"
DATI = Path(__file__).resolve().parent / "dati"

# Macchina connessa a una rete di potenza infinita (20 kV, Zb = 4 Ω, Sb = Sr = 100 MVA):
# X'd = 0,3 p.u., L1 = 1 p.u., L2 = L2a + L2b = 0,5 + 0,5 p.u., Zq = 0,05 p.u.
SMIB = {
    "name": "Macchina - rete di potenza infinita",
    "f_hz": 50,
    "buses": [{"id": "G", "un_kv": 20.0}, {"id": "M", "un_kv": 20.0}, {"id": "Q", "un_kv": 20.0}],
    "external_grids": [{"id": "INF", "bus": "Q", "skq_max_mva": 2000, "rx_max": 0.0, "vm_pu": 1.0}],
    "lines": [
        {"id": "L1", "from_bus": "G", "to_bus": "Q", "length_km": 10, "r1_ohm_per_km": 0.0, "x1_ohm_per_km": 0.4},
        {"id": "L2a", "from_bus": "G", "to_bus": "M", "length_km": 5, "r1_ohm_per_km": 0.0, "x1_ohm_per_km": 0.4},
        {"id": "L2b", "from_bus": "M", "to_bus": "Q", "length_km": 5, "r1_ohm_per_km": 0.0, "x1_ohm_per_km": 0.4},
    ],
    "generators": [{"id": "G1", "bus": "G", "sr_mva": 100, "ur_kv": 20, "xd2_percent": 20,
                    "xd1_percent": 30, "rg_ohm": 0.0, "p_mw": 80, "vm_pu": 1.02, "h_s": 4.0}],
}
W0 = 2 * math.pi * 50
XD1, XE, XQ_GRID = 0.3, 0.5, 0.05
H, PM = 4.0, 0.8


def _smib(**gen):
    data = copy.deepcopy(SMIB)
    data["generators"][0].update(gen)
    return network_from_dict(data)


def _flusso_analitico():
    """Flusso di potenza della rete SMIB senza perdite: V_G = 1,02∠θ, V_Q = 1∠0."""
    theta = math.asin(PM * XE / 1.02)
    vg = 1.02 * cmath.exp(1j * theta)
    i = (vg - 1.0) / (1j * XE)  # da G verso Q
    eb = 1.0 - 1j * XQ_GRID * i  # fem della rete esterna (corrente uscente dalla rete: −i)
    return vg, i, eb


def _ode_classico(intervalli, t_end):
    """Equazione di oscillazione con Pmax diverse per intervallo: [(t_inizio, Pmax), …]."""
    from scipy.integrate import solve_ivp

    vg, i, eb = _flusso_analitico()
    e1 = vg + 1j * XD1 * i
    d0 = cmath.phase(e1) - cmath.phase(eb)

    def f(t, y):
        pmax = [p for t0, p in intervalli if t >= t0 - 1e-12][-1]
        return [W0 * y[1], (PM - pmax(abs(e1), abs(eb)) * math.sin(y[0])) / (2 * H)]

    ts = sorted({t0 for t0, _ in intervalli} | {t_end})
    y, t_all, d_all = [d0, 0.0], [], []
    for a, b in zip(ts, ts[1:]):
        sol = solve_ivp(f, (a, b), y, rtol=1e-11, atol=1e-12, dense_output=True)
        y = sol.y[:, -1]
        t_all.append(sol)
    return t_all, d0


# --- inizializzazione ----------------------------------------------------------------------


@pytest.mark.parametrize("gen", [
    dict(),
    dict(dyn_model="one_axis", xd_percent=180, xq_percent=170, td01_s=6.0),
    dict(dyn_model="one_axis", xd_percent=180, xq_percent=170, td01_s=6.0, avr_ka=50, avr_ta_s=0.05,
         gov_droop_pu=0.05, gov_tg_s=0.4, d_pu=1.0),
])
def test_regime_iniziale(gen):
    res = simulate(_smib(**gen), 1.0, 0.005, [])
    for arr in (res.delta_deg["G1"], res.speed_pu["G1"], res.pe_mw["G1"], res.efd_pu["G1"]):
        assert np.max(np.abs(arr - arr[0])) < 1e-8
    assert res.pe_mw["G1"][0] == pytest.approx(80.0, rel=1e-9)
    assert res.v_pu["G"][0] == pytest.approx(1.02, rel=1e-9)


# --- criterio delle aree uguali --------------------------------------------------------------


def test_tempo_critico_aree_uguali():
    """Guasto franco ai morsetti (Pe = 0) eliminato senza aprire linee:
    δcr = arccos[(π − 2δ0)·sinδ0 − cosδ0], tcr = √(4H(δcr − δ0)/(ω0·Pm))."""
    vg, i, eb = _flusso_analitico()
    d0 = cmath.phase(vg + 1j * XD1 * i) - cmath.phase(eb)
    dcr = math.acos((math.pi - 2 * d0) * math.sin(d0) - math.cos(d0))
    tcr = math.sqrt(4 * H * (dcr - d0) / (W0 * PM))
    tcc = critical_clearing_time(_smib(), "G", t_end_s=2.0, dt_s=0.001, tol_s=0.0005)
    assert tcc == pytest.approx(tcr, abs=0.001)


# --- integrazione indipendente ----------------------------------------------------------------


def _pmax_guasto_m(e1, eb):
    """Guasto franco a metà di L2 (nodo M a terra): riduzione di Kron della rete E'–G–Q–Eb."""
    y = np.zeros((4, 4), dtype=complex)  # nodi: E', Eb, G, Q (M a terra)

    def br(a, b, x):
        yy = 1 / (1j * x)
        y[a, a] += yy
        y[b, b] += yy
        y[a, b] -= yy
        y[b, a] -= yy

    br(0, 2, XD1)
    br(1, 3, XQ_GRID)
    br(2, 3, 1.0)  # L1
    y[2, 2] += 1 / (1j * 0.5)  # L2a verso M a terra
    y[3, 3] += 1 / (1j * 0.5)  # L2b verso M a terra
    yr = y[:2, :2] - y[:2, 2:] @ np.linalg.inv(y[2:, 2:]) @ y[2:, :2]
    return e1 * eb * abs(yr[0, 1])


def test_classico_come_integrazione_indipendente():
    """Guasto a metà di L2 da 0,1 a 0,25 s, eliminato aprendo L2a e L2b."""
    evs = [StabilityEvent(0.1, "fault", bus="M"), StabilityEvent(0.25, "clear_fault", bus="M"),
           StabilityEvent(0.25, "trip_branch", element="L2a"),
           StabilityEvent(0.25, "trip_branch", element="L2b")]
    res = simulate(_smib(), 2.0, 0.001, evs)
    intervalli = [(0.0, lambda e, b: e * b / (XD1 + XE + XQ_GRID)), (0.1, _pmax_guasto_m),
                  (0.25, lambda e, b: e * b / (XD1 + 1.0 + XQ_GRID))]
    sols, d0 = _ode_classico(intervalli, 2.0)
    rel = res.relative_angles_deg()["G1"]
    assert rel[0] == pytest.approx(math.degrees(d0), abs=1e-9)
    for t in (0.05, 0.2, 0.4, 0.8, 1.2, 1.9):
        sol = next(s for s in sols if s.t[0] <= t <= s.t[-1])
        k = int(np.argmin(np.abs(res.t - t)))
        assert rel[k] == pytest.approx(math.degrees(sol.sol(res.t[k])[0]), abs=1e-4), t
    # dopo l'apertura di L2 Pmax = 1,05·1,0/1,35 < Pm = 0,8: perdita di passo,
    # riprodotta anche dall'integrazione indipendente
    assert not res.stable


def _ode_un_asse(xd, xq, td01, ka, ta, t_f, t_c, xf, t_end):
    """Modello a un asse con regolatore di tensione, rete di potenza infinita dietro
    Xe = 0,55 p.u.; durante il guasto (reattanza xf ai morsetti) equivalente di Thévenin."""
    from scipy.integrate import solve_ivp

    vg, i, eb = _flusso_analitico()
    xe = XE + XQ_GRID
    d = cmath.phase(vg + 1j * xq * i)
    rot = cmath.exp(-1j * (d - math.pi / 2))
    idq, vdq = i * rot, vg * rot
    e1q = vdq.imag + XD1 * idq.real
    efd0 = e1q + (xd - XD1) * idq.real
    vref = abs(vg) + efd0 / ka

    def rete(t):
        if t_f <= t < t_c:
            return eb * xf / (xe + xf), xe * xf / (xe + xf)
        return eb, xe

    def f(t, y):
        delta, dw, eq, efd = y
        vs, x = rete(t)
        ang = delta - cmath.phase(vs)
        i_d = (eq - abs(vs) * math.cos(ang)) / (XD1 + x)
        i_q = abs(vs) * math.sin(ang) / (xq + x)
        pe = eq * i_q + (xq - XD1) * i_d * i_q
        vt = abs(complex(xq * i_q, eq - XD1 * i_d))
        d_efd = (ka * (vref - vt) - efd) / ta
        return [W0 * dw, (PM - pe) / (2 * H), (efd - eq - (xd - XD1) * i_d) / td01, d_efd]

    sols, y = [], [d, 0.0, e1q, efd0]
    for a, b in ((0.0, t_f), (t_f, t_c), (t_c, t_end)):
        sol = solve_ivp(f, (a, b), y, rtol=1e-11, atol=1e-12, dense_output=True)
        y = sol.y[:, -1]
        sols.append(sol)
    return sols


def test_un_asse_con_regolatore_come_integrazione_indipendente():
    xd, xq, td01, ka, ta = 1.8, 1.7, 6.0, 50.0, 0.05
    xf = 0.2
    net = _smib(dyn_model="one_axis", xd_percent=100 * xd, xq_percent=100 * xq, td01_s=td01,
                avr_ka=ka, avr_ta_s=ta, efd_max_pu=99.0, efd_min_pu=-99.0)
    evs = [StabilityEvent(0.1, "fault", bus="G", x_ohm=xf * 4.0), StabilityEvent(0.2, "clear_fault", bus="G")]
    res = simulate(net, 3.0, 0.001, evs)
    sols = _ode_un_asse(xd, xq, td01, ka, ta, 0.1, 0.2, xf, 3.0)
    rel = res.relative_angles_deg()["G1"]
    ang_eb = math.degrees(cmath.phase(_flusso_analitico()[2]))  # angoli riferiti alla fem della rete
    for t in (0.15, 0.3, 0.7, 1.5, 2.9):
        sol = next(s for s in sols if s.t[0] <= t <= s.t[-1])
        k = int(np.argmin(np.abs(res.t - t)))
        ref = sol.sol(res.t[k])
        assert rel[k] == pytest.approx(math.degrees(ref[0]) - ang_eb, abs=1e-3), t
        assert res.efd_pu["G1"][k] == pytest.approx(ref[3], abs=1e-4), t


# --- regolatore di velocità -------------------------------------------------------------------


def test_regolatore_di_velocità_a_regime():
    """Due macchine senza rete esterna, aumento di carico: a regime
    Δω = (ΣPref − ΣPe)/(Σ k/R + ΣD) (potenze in p.u. di sistema, k = Sr/Sb)."""
    data = {
        "name": "Isola con due generatori", "f_hz": 50,
        "buses": [{"id": "A", "un_kv": 20.0}, {"id": "B", "un_kv": 20.0}],
        "lines": [{"id": "L", "from_bus": "A", "to_bus": "B", "length_km": 5,
                   "r1_ohm_per_km": 0.05, "x1_ohm_per_km": 0.35}],
        "generators": [
            {"id": "GA", "bus": "A", "sr_mva": 60, "ur_kv": 20, "xd2_percent": 18, "xd1_percent": 25,
             "p_mw": 30, "vm_pu": 1.0, "h_s": 5.0, "d_pu": 2.0, "gov_droop_pu": 0.05, "gov_tg_s": 0.3},
            {"id": "GB", "bus": "B", "sr_mva": 40, "ur_kv": 20, "xd2_percent": 18, "xd1_percent": 25,
             "p_mw": 20, "vm_pu": 1.0, "h_s": 4.0, "d_pu": 2.0, "gov_droop_pu": 0.04, "gov_tg_s": 0.3},
        ],
        "loads": [{"id": "C", "bus": "B", "p_mw": 45.0, "q_mvar": 10.0}],
        "stability_events": [{"t_s": 0.5, "kind": "load", "bus": "B", "scale": 1.1}],
    }
    res = simulate(network_from_dict(data), 40.0, 0.01)
    dw = res.speed_pu["GA"][-1] - 1.0
    assert res.speed_pu["GB"][-1] - 1.0 == pytest.approx(dw, abs=1e-6)
    pe0 = sum(res.pe_mw[g][0] for g in ("GA", "GB")) / 100
    pe1 = sum(res.pe_mw[g][-1] for g in ("GA", "GB")) / 100
    k_r = 0.6 / 0.05 + 0.4 / 0.04
    d = 2.0 * 0.6 + 2.0 * 0.4
    assert dw < 0
    assert dw == pytest.approx((pe0 - pe1) / (k_r + d), rel=1e-3)


# --- ANDES (sistema di Kundur a due aree) ------------------------------------------------------


def test_kundur_come_andes():
    """Riferimento: ANDES 2.0.0 (GENCLS), guasto nel nodo 8 da 1,0 a 1,083 s e
    apertura di Line_8 a 2,0 s (strumenti/confronto_andes_kundur.py)."""
    net = network_from_dict(json.loads((ESEMPI / "kundur_due_aree.json").read_text(encoding="utf-8")))
    ref = json.loads((DATI / "kundur_andes.json").read_text(encoding="utf-8"))
    res = simulate(net, 5.0, 0.001)
    for g, valori in ref["angoli_relativi_a_G1_gradi"].items():
        ours = np.interp(ref["tempi_s"], res.t, res.delta_deg[g] - res.delta_deg["G1"])
        assert np.max(np.abs(ours - np.array(valori))) < 0.01, g
    assert res.stable


# --- eventi, instabilità, errori -----------------------------------------------------------------


def test_perdita_di_passo():
    evs = [StabilityEvent(0.1, "fault", bus="G"), StabilityEvent(0.5, "clear_fault", bus="G")]
    res = simulate(_smib(), 2.0, 0.002, evs)
    assert not res.stable and 0.1 < res.t_unstable_s < 2.0


def test_distacco_generatore_e_tre_avvolgimenti():
    data = json.loads((ESEMPI / "kundur_due_aree.json").read_text(encoding="utf-8"))
    data["stability_events"] = [{"t_s": 0.2, "kind": "trip_gen", "element": "G4"}]
    for g in data["generators"]:
        g["d_pu"] = 5.0
    res = simulate(network_from_dict(data), 1.0, 0.005)
    assert np.all(res.pe_mw["G4"][res.t > 0.2 + 1e-9] == 0.0)
    assert res.speed_pu["G1"][-1] < 1.0  # perdita di generazione: la frequenza scende


@pytest.mark.parametrize("ev, msg", [
    (StabilityEvent(0.1, "fault", bus="X"), "nodo inesistente"),
    (StabilityEvent(0.1, "trip_branch", element="XX"), "ramo inesistente"),
    (StabilityEvent(0.1, "trip_gen", element="XX"), "generatore inesistente"),
    (StabilityEvent(0.1, "boh", bus="G"), "tipo di evento"),
])
def test_eventi_non_validi(ev, msg):
    with pytest.raises(ValueError, match=msg):
        simulate(_smib(), 0.3, 0.01, [ev])


def test_dati_mancanti():
    with pytest.raises(ValueError, match="h_s"):
        simulate(_smib(h_s=None), 0.1, 0.01, [])
    with pytest.raises(ValueError, match="one_axis richiede"):
        simulate(_smib(dyn_model="one_axis"), 0.1, 0.01, [])


def test_riga_di_comando(tmp_path, capsys):
    from iec60909.stabilita import main

    svg = tmp_path / "angoli.svg"
    assert main([str(ESEMPI / "kundur_due_aree.json"), "--tfine", "2", "--svg", str(svg)]) == 0
    assert "**stabile**" in capsys.readouterr().out
    assert svg.read_text(encoding="utf-8").startswith("<svg")
    rete = tmp_path / "smib.json"
    rete.write_text(json.dumps(SMIB), encoding="utf-8")
    assert main([str(rete), "--tcc", "G", "--tfine", "1.5", "--dt", "0.002"]) == 0
    assert "tempo critico di eliminazione" in capsys.readouterr().out
