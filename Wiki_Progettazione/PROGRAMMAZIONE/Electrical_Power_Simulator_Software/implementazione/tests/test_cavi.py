"""Dimensionamento dei cavi: calcoli a mano (portata, caduta di tensione, cortocircuito,
interruzione automatica) ed esempi svolti pubblicati."""

import math

import pytest

from iec60909 import network_from_dict
from iec60909.cables import apply_sizing, cable_sizing_study, pe_section, size_cable

CATALOGO = {"16": 70, "25": 90, "35": 110, "50": 135, "70": 170}


def _rete(km=0.1, skq=500.0, **cs):
    d = {"id": "C", "line": "L", "ib_a": 80.0, "cos_phi": 0.9, "ampacity_a": CATALOGO}
    d.update(cs)
    return network_from_dict({
        "name": "Linea BT", "lv_tolerance_percent": 10,
        "buses": [{"id": "Q", "un_kv": 0.4}, {"id": "U", "un_kv": 0.4}],
        "external_grids": [{"id": "G", "bus": "Q", "skq_max_mva": skq, "skq_min_mva": skq, "rx_max": 0.1,
                            "rx_min": 0.1, "x0x1": 1.0, "r0x0": 0.1}],
        "lines": [{"id": "L", "from_bus": "Q", "to_bus": "U", "length_km": km,
                   "r1_ohm_per_km": 0.524, "x1_ohm_per_km": 0.08}],
        "loads": [{"id": "U", "bus": "U", "p_mw": 0.05}],
        "cable_sizing": [d],
    })


def _dv_percent(s, r20, ib, km, cos_phi=0.9, iz=None, n=1):
    theta = 30 + 40 * (ib / iz) ** 2
    r = r20 * (1 + 0.00393 * (theta - 20))
    sin_phi = math.sqrt(1 - cos_phi**2)
    return math.sqrt(3) * ib * km * (r * cos_phi + 0.08 * sin_phi) / n / 400 * 100


def test_portata_e_protezione():
    net = _rete(in_a=100.0)  # Iz >= In: 35 mm² (110 A); I2 = 1,3·100 <= 1,45·110
    r = size_cable(net, net.cable_sizing[0])
    assert r.section_mm2 == 35 and r.iz_a == 110 and r.i2_a == pytest.approx(130)
    assert r.vdrop_percent == pytest.approx(_dv_percent(35, 0.524, 80, 0.1, iz=110), rel=1e-12)
    # con un fusibile gG (I2 = 1,6·In) serve I2 <= 1,45·Iz: 160 > 1,45·110 -> 50 mm²
    r = size_cable(net, net.cable_sizing[0].__class__(**{**net.cable_sizing[0].__dict__, "i2_ratio": 1.6}))
    assert r.section_mm2 == 50
    assert any("I2" in c.issues[0] for c in r.candidates if c.section_mm2 == 35)


def test_caduta_di_tensione_e_paralleli():
    net = _rete(km=0.08, vdrop_max_percent=2.0)
    r = size_cable(net, net.cable_sizing[0])
    attese = {s: _dv_percent(s, r20, 80, 0.08, iz=CATALOGO[str(s)])
              for s, r20 in ((25, 0.727), (35, 0.524), (50, 0.387), (70, 0.268))}
    scelta = min(s for s, dv in attese.items() if dv <= 2.0)
    assert scelta > 25  # decide la caduta di tensione, non la portata
    assert r.section_mm2 == scelta
    assert r.vdrop_percent == pytest.approx(attese[scelta], rel=1e-12)
    # corrente oltre la sezione massima: due conduttori in parallelo
    net = _rete(ib_a=300.0, max_parallel=3, vdrop_max_percent=10)
    r = size_cable(net, net.cable_sizing[0])
    assert (r.parallel, r.section_mm2) == (2, 70) and r.iz_a == 340


def test_conduttore_di_protezione():
    assert [pe_section(s) for s in (10, 16, 25, 35, 50, 95, 240)] == [10, 16, 16, 16, 25, 50, 120]
    assert pe_section(95, 35) == 35


def test_cortocircuito_e_interruzione_automatica():
    """Interruttore con soglia istantanea: t costante = ti_s. I²t = I²·ti ≤ k²S² e
    corrente di guasto a terra a fine linea dall'anello Z1+Z2+Z0+3(Zf+Zpe)."""
    from iec60909 import calculate

    net = _rete(km=0.2, skq=20.0, device="CB", disconnection_time_s=0.4)
    from iec60909.network import ProtectiveDevice

    net.protective_devices.append(ProtectiveDevice("CB", "L", "Q", "breaker", in_a=100.0, ir=1.0, tr_s=10.0,
                                                   ii=10.0, ti_s=0.02))
    r = size_cable(net, net.cable_sizing[0])
    bmax = next(b for b in calculate(net, "max").buses if b.bus == "Q")
    bmin = next(b for b in calculate(net, "min").buses if b.bus == "Q")
    assert r.ik_max_ka == pytest.approx(max(bmax.ikss3_ka, bmax.ikss1_ka))
    assert r.t_max_s == pytest.approx(0.02)
    s, spe = r.section_mm2, r.pe_section_mm2
    rf = 1.15 if s == 16 else {25: 0.727, 35: 0.524, 50: 0.387, 70: 0.268}[s]
    rpe = {16: 1.15, 25: 1.15, 35: 1.15, 50: 0.727, 70: 0.524}[s]
    k70 = 1 + 0.00393 * 50
    zl = complex(rf * k70 * 0.2, 0.08 * 0.2) + complex(rpe * k70 * 0.2, 0.08 * 0.2)
    ik1 = math.sqrt(3) * bmin.c * 0.4 / abs(bmin.z1_ohm + bmin.z2_ohm + bmin.z0_ohm + 3 * zl)
    assert r.ik1_min_end_ka == pytest.approx(ik1, rel=1e-12)
    assert ik1 * 1000 >= 1000  # soglia istantanea 10·In: interruzione in 0,02 s
    # linea più lunga: la corrente di guasto a terra scende sotto la soglia istantanea, la zona L
    # (tr = 10 s a 6·Ir) non interrompe entro 0,4 s e serve una sezione maggiore o un dispositivo diverso
    net.lines[0].length_km = 1.0
    r2 = size_cable(net, net.cable_sizing[0])
    motivi = " ".join(i for c in r2.candidates for i in c.issues)
    assert "interruzione in" in motivi


def test_applica_e_riga_di_comando(tmp_path, capsys):
    import json

    from iec60909.cavi import main
    from iec60909.io import network_to_dict

    net = _rete(in_a=100.0)
    res = cable_sizing_study(net)
    out = apply_sizing(net, res)
    assert out.lines[0].r1_ohm_per_km == 0.524 and out.lines[0].r0_ohm_per_km == pytest.approx(0.524 + 3 * 1.15)
    f = tmp_path / "rete.json"
    f.write_text(json.dumps(network_to_dict(net)), encoding="utf-8")
    assert main([str(f), "--applica", str(tmp_path / "out.json")]) == 0
    assert "| C | L |" in capsys.readouterr().out
    assert network_from_dict(json.loads((tmp_path / "out.json").read_text()))
