"""Avviamento dei motori: stima del circuito equivalente, caduta di tensione,
metodi di avviamento, accelerazione contro un'integrazione indipendente (scipy)."""

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from iec60909 import network_from_dict
from iec60909.motorstart import circuit_for, estimate_circuit, simulate_start
from iec60909.network import Motor, MotorStart

ESEMPI = Path(__file__).resolve().parents[1] / "esempi"


def _verifica_targa(m: Motor, c, tlr=None):
    i_s, i_r = c.currents(1.0, c.s_rated)
    p_in = i_s.conjugate().real
    p_shaft = abs(i_r) ** 2 * c.rr * (1 - c.s_rated) / c.s_rated - c.p_loss_fw
    assert abs(i_s) == pytest.approx(1.0, rel=1e-8)  # corrente nominale
    assert p_in / abs(i_s) == pytest.approx(m.cos_phi, rel=1e-8)
    assert p_shaft / p_in == pytest.approx(m.efficiency, rel=1e-8)
    assert abs(c.impedance(1.0)) == pytest.approx(1 / m.ilr_ir, rel=1e-8)
    if tlr is not None:
        t_r = m.efficiency * m.cos_phi / (1 - c.s_rated)
        assert c.torque(1.0, 1.0) / t_r == pytest.approx(tlr, rel=1e-8)


@pytest.mark.parametrize("m, tlr, fit", [
    (Motor("A", "B", 0.075, 0.4, 0.94, 0.86, 7.0), None, "rendimento"),
    (Motor("A", "B", 0.011, 0.4, 0.88, 0.82, 6.5), None, "rs=rr"),
    (Motor("A", "B", 2.0, 6.0, 0.96, 0.88, 5.5, pole_pairs=2), None, "rs=rr"),
    (Motor("A", "B", 2.0, 6.0, 0.96, 0.88, 5.5, pole_pairs=2), 0.8, "rendimento+spunto"),
    (Motor("A", "B", 0.075, 0.4, 0.94, 0.86, 7.0), 2.2, "rendimento+spunto"),
])
def test_stima_del_circuito(m, tlr, fit):
    c = estimate_circuit(m, tlr)
    assert c.fit == fit
    _verifica_targa(m, c, tlr)
    if tlr is None:
        z1 = c.impedance(1.0)
        rx = m.rx if m.rx is not None else (0.42 if m.ur_kv <= 1 else 0.1)
        assert z1.real / z1.imag == pytest.approx(rx, rel=1e-8)


def test_circuito_indicato():
    m = Motor("A", "B", 0.075, 0.4, 0.94, 0.86, 7.0)
    ms = MotorStart("S", "A", rs=0.02, xs=0.07, xm=2.5, rr=0.03, xr=0.07)
    c = circuit_for(ms, m)
    assert c.fit == "dati"
    p_mech = c.torque(1.0, c.s_rated) * (1 - c.s_rated)
    assert p_mech == pytest.approx(0.94 * 0.86, rel=1e-6)
    with pytest.raises(ValueError, match="tutti i parametri"):
        circuit_for(MotorStart("S", "A", rs=0.02), m)


# --- rete di prova: rete esterna Q (nodo di saldo) - linea - nodo M con il motore ------------

M_DATI = {"id": "M", "bus": "M", "pr_mw": 0.25, "ur_kv": 0.4, "efficiency": 0.95, "cos_phi": 0.87,
          "ilr_ir": 6.5, "pole_pairs": 2}


def _rete(skq=1e6, linea_ohm=(0.004, 0.006), nodo_motore="M", **start):
    ms = {"id": "S", "motor": "M", "h_s": 0.4, "tlr_tr": 2.0}
    ms.update(start)
    return network_from_dict({
        "name": "Motore in fondo a una linea", "f_hz": 50,
        "buses": [{"id": "Q", "un_kv": 0.4}, {"id": "M", "un_kv": 0.4}],
        "external_grids": [{"id": "G", "bus": "Q", "skq_max_mva": skq, "rx_max": 0.1}],
        "lines": [{"id": "L", "from_bus": "Q", "to_bus": "M", "length_km": 1.0,
                   "r1_ohm_per_km": linea_ohm[0], "x1_ohm_per_km": linea_ohm[1]}],
        "motors": [dict(M_DATI, bus=nodo_motore)],
        "motor_starts": [ms],
    })


def _z_motore_ohm(c, s=1.0):
    sr = 0.25 / (0.95 * 0.87)
    return c.impedance(s) * 0.4**2 / sr


def test_caduta_di_tensione_a_mano():
    """Istante di avviamento: V_M = V_Q·Zm/(Zm + Z_linea), con V_Q = 1 (nodo di saldo)."""
    net = _rete()
    r = simulate_start(net, net.motor_starts[0], static=True)
    zl = complex(0.004, 0.006)
    zm = _z_motore_ohm(r.circuit)
    assert r.v_bus_pu["M"][0] == pytest.approx(abs(zm / (zm + zl)), rel=1e-9)
    ir = 0.25 / (0.95 * 0.87) / (math.sqrt(3) * 0.4) * 1000
    i = 0.4 / math.sqrt(3) / abs(zm + zl) * 1000
    assert r.i_line_a[0] == pytest.approx(i, rel=1e-9)
    assert r.i_line_ir[0] == pytest.approx(i / ir, rel=1e-9)


@pytest.mark.parametrize("start, fattore", [
    (dict(method="dol"), 1.0),
    (dict(method="star_delta"), 1 / 3),
    (dict(method="autotransformer", tap=0.65), 0.65**2),
    (dict(method="soft_starter", u0=0.45), 0.45),
])
def test_corrente_di_avviamento_per_metodo(start, fattore):
    """Motore sulle sbarre di una rete rigida (nodo di saldo, V = 1): corrente di linea = fattore × Ilr."""
    net = _rete(nodo_motore="Q", **start)
    r = simulate_start(net, net.motor_starts[0], static=True)
    assert r.i_line_ir[0] == pytest.approx(fattore * abs(1 / r.circuit.impedance(1.0)), rel=1e-6)


def test_accelerazione_come_integrazione_indipendente():
    """Motore alimentato da V_Q = 1 attraverso la linea: ω' = (Te − T_L)/(2H) con
    Te dalla tensione ai morsetti V_M = Zm(s)/(Zm(s) + Z_linea)."""
    from scipy.integrate import solve_ivp

    net = _rete(linea_ohm=(0.01, 0.015))
    ms = net.motor_starts[0]
    r = simulate_start(net, ms, dt_s=0.002)
    c = r.circuit
    sr = 0.25 / (0.95 * 0.87)
    zl = complex(0.01, 0.015) / (0.4**2 / sr)  # p.u. del motore
    t_r = 0.95 * 0.87 / (1 - c.s_rated)
    t_fw = c.p_loss_fw / (1 - c.s_rated)

    def f(t, y):
        s = 1 - y[0]
        zm = c.impedance(s)
        v = zm / (zm + zl)
        tl = t_r * (0.1 + 0.9 * y[0] ** 2) + t_fw
        return [(c.torque(v, s) - tl) / (2 * 0.4)]

    sol = solve_ivp(f, (0, r.t[-1]), [0.0], rtol=1e-10, atol=1e-12, dense_output=True, max_step=0.01)
    assert np.max(np.abs(r.speed_pu - sol.sol(r.t)[0])) < 2e-3
    w_target = 1 - 2 * c.s_rated
    tt = np.linspace(0, r.t[-1], 200001)
    t_ref = tt[np.argmax(sol.sol(tt)[0] >= w_target)]
    assert r.accelerated and r.t_acc_s == pytest.approx(t_ref, abs=0.005)


def test_stallo():
    net = _rete(a0=3.0, a2=0.0, t_max_s=3.0)  # coppia resistente oltre la coppia di spunto
    r = simulate_start(net, net.motor_starts[0])
    assert not r.accelerated
    assert any("stallo" in i for i in r.issues)


def test_limite_di_corrente_del_soft_starter():
    net = _rete(method="soft_starter", u0=0.6, ramp_s=4.0, current_limit=2.5)
    r = simulate_start(net, net.motor_starts[0], dt_s=0.01)
    assert r.accelerated
    assert np.max(r.i_line_ir) <= 2.5 + 1e-6
    assert np.max(r.i_line_ir) == pytest.approx(2.5, rel=1e-3)  # il limite interviene


def test_limiti_di_tensione_e_tempo():
    net = _rete(skq=2.0, v_min_motor_pu=0.95, v_min_bus_pu=0.97, t_lr_max_s=0.01)
    r = simulate_start(net, net.motor_starts[0])
    testo = " ".join(r.issues)
    assert "punto di allacciamento" in testo and "rotore bloccato" in testo


def test_stella_triangolo_e_commutazione():
    data = json.loads((ESEMPI / "avviamento_motore.json").read_text(encoding="utf-8"))
    net = network_from_dict(data)
    dol = simulate_start(net, net.motor_starts[0])
    sd = simulate_start(net, net.motor_starts[1])
    # a parità di tensione di rete la corrente in stella è 1/3 di quella diretta
    assert sd.i_line_ir[0] / sd.v_bus_pu["QD1"][0] == pytest.approx(
        dol.i_line_ir[0] / dol.v_bus_pu["QD1"][0] / 3, rel=1e-9)
    assert sd.v_min_supply_pu > dol.v_min_supply_pu
    assert sd.t_acc_s > dol.t_acc_s  # coppia ridotta a 1/3: avviamento più lento
    # alla commutazione la corrente risale
    k = int(np.argmax(sd.speed_pu >= 0.85))
    assert sd.i_line_ir[k + 1] > sd.i_line_ir[k - 1]


def test_errori():
    net = _rete(method="boh")
    with pytest.raises(ValueError, match="metodo di avviamento"):
        simulate_start(net, net.motor_starts[0])
    net = _rete()
    ms = copy.deepcopy(net.motor_starts[0])
    ms.motor = "X"
    with pytest.raises(ValueError, match="motore inesistente"):
        simulate_start(net, ms)


def test_riga_di_comando(tmp_path, capsys):
    from iec60909.avviamento import main

    assert main([str(ESEMPI / "avviamento_motore.json"), "--svg", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "| M1_diretto |" in out and "stella-triangolo" in out
    assert len(list(tmp_path.glob("*.svg"))) == 3
    assert main([str(ESEMPI / "avviamento_motore.json"), "--statico", "--json"]) == 0
    dati = json.loads(capsys.readouterr().out)
    assert len(dati) == 3 and dati[0]["t_acc_s"] is None
