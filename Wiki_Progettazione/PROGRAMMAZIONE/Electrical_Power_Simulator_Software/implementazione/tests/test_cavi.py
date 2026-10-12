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


# --- tabelle IEC 60364-5-52 -------------------------------------------------------------

def test_tabelle_iec60364():
    from iec60909 import cable_tables as tab

    # B.52.4 (PVC, 3 conduttori caricati) e B.52.5 (XLPE), Cu 95 mm²: valori di riferimento
    # dell'allegato B riportati da più trascrizioni (GOST R 50571.5.52, TiSoft, NBR 5410)
    pvc = {"A1": 164, "A2": 150, "B1": 207, "B2": 179, "C": 223, "D1": 169, "D2": 193}
    xlpe = {"A1": 216, "A2": 197, "B1": 269, "B2": 233, "C": 278, "D1": 197, "D2": 226}
    for m, v in pvc.items():
        assert tab.ampacity_table("cu", "pvc", 3, m)[95] == v
    for m, v in xlpe.items():
        assert tab.ampacity_table("cu", "xlpe", 3, m)[95] == v
        assert tab.ampacity_table("cu", "epr", 3, m)[95] == v
    # metodi E, F, G (B.52.10, B.52.12)
    assert tab.ampacity_table("cu", "pvc", 3, "E")[95] == 238
    assert tab.ampacity_table("cu", "pvc", 3, "F")[95] == 264
    assert tab.ampacity_table("cu", "pvc", 3, "G")[95] == 341
    assert tab.ampacity_table("cu", "xlpe", 3, "E")[95] == 298
    # fattori: aria 40 °C (B.52.14), terreno 30 °C (B.52.15), resistività (B.52.16), raggruppamento
    f = tab.correction_factors("pvc", "C", 40, None, "bunched", 3)
    assert f == {"temperatura": 0.87, "raggruppamento": 0.7}
    assert tab.correction_factors("xlpe", "D2", 30, 1.0, "touching", 4) == \
        {"temperatura": 0.93, "terreno": 1.5, "raggruppamento": 0.6}
    assert tab.correction_factors("xlpe", "D1", None, 1.0, "0.25_m", 2) == {"terreno": 1.18, "raggruppamento": 0.9}
    # numero di circuiti non tabellato: il successivo (10 -> 12); file singola oltre 9: nessuna riduzione
    assert tab.correction_factors("pvc", "C", None, None, "bunched", 10)["raggruppamento"] == 0.45
    assert tab.correction_factors("pvc", "C", None, None, "single_layer_wall_floor", 15)["raggruppamento"] == 0.7
    with pytest.raises(ValueError, match="grouping"):
        tab.correction_factors("pvc", "C", None, None, None, 2)
    with pytest.raises(ValueError, match="non tabellata"):
        tab.ampacity_key("al", "pvc", 3, "Z")
    assert 1.5 not in tab.ampacity_table("al", "pvc", 3, "A1")  # alluminio da 2,5 mm²
    # resistenze IEC 60228 e k della tabella 43A
    assert tab.resistance_20c("cu", 95) == 0.193 and tab.resistance_20c("al", 240) == 0.125
    assert tab.k_factor("cu", "pvc", 240) == 115 and tab.k_factor("cu", "pvc", 400) == 103
    assert tab.k_factor("al", "xlpe") == 94


def test_dimensionamento_con_le_tabelle():
    """Cu/PVC, metodo C, 40 °C, 3 circuiti raggruppati: Iz = I0·0,87·0,7 ≥ 150 A richiede
    I0 ≥ 246,3 A: 95 mm² (223 A) non basta, 120 mm² (259 A) sì."""
    net = _rete(ib_a=150.0, ampacity_a={}, method="C", ambient_c=40, grouping="bunched", circuits=3,
                vdrop_max_percent=10)
    r = size_cable(net, net.cable_sizing[0])
    assert r.section_mm2 == 120
    assert r.iz_a == pytest.approx(259 * 0.87 * 0.7)
    assert r.factors == {"temperatura": 0.87, "raggruppamento": 0.7}
    assert not r.warnings
    # valore a confidenza ridotta: avviso (B.52.5 Al, metodo D1, 300 mm², fonti discordi 266/286 A)
    net = _rete(ib_a=270.0, ampacity_a={}, material="al", insulation="xlpe", method="D1", vdrop_max_percent=50)
    r = size_cable(net, net.cable_sizing[0])
    assert r.section_mm2 == 300 and r.iz_a == 286 and "conflict_resolved" in r.warnings[0]


# --- esempi svolti pubblicati -------------------------------------------------------------

def test_esempio_motore_90kw():
    """Power Projects India, "Cable sizing calculation – low voltage": motore 90 kW, 415 V,
    cosφ 0,85, η 0,9, cavo 95 mm² Cu/XLPE da 120 m, R = 0,247 Ω/km, X = 0,0734 Ω/km.
    Pubblicati: Ib 163,67 A, caduta 2,03 % in marcia e 7,10 % all'avviamento (6·Ib, cosφ 0,3),
    sezione minima al cortocircuito 88,455 mm² (40 kA, 0,1 s, k = 143)."""
    from iec60909.cables import min_section_short_circuit, voltage_drop_percent

    ib = 90e3 / (math.sqrt(3) * 415 * 0.85 * 0.9)
    assert ib == pytest.approx(163.67, abs=0.01)
    # la fonte usa sinφ = 0,53 e 0,96 arrotondati: stessa convenzione per confrontare
    assert voltage_drop_percent(ib, 0.12, 0.247, 0.0734 * 0.53 / math.sqrt(1 - 0.85**2), 0.85, 0.415) == \
        pytest.approx(2.03, abs=0.011)
    assert voltage_drop_percent(6 * ib, 0.12, 0.247, 0.0734 * 0.96 / math.sqrt(1 - 0.3**2), 0.3, 0.415) == \
        pytest.approx(7.10, abs=0.011)
    assert min_section_short_circuit(40e3, 0.1, 143) == pytest.approx(88.455, abs=5e-4)


@pytest.mark.parametrize("sph, spe, i_n, attese", [
    (1.5, 1.5, 10, (153, 82, 49)),
    (2.5, 2.5, 20, (128, 68, 41)),
    (4, 2.5, 25, (126, 67, 40)),
    (4, 2.5, 32, (98, 52, 31)),
    (6, 2.5, 40, (90, 48, 29)),
    (10, 4, 50, (117, 62, 37)),
    (16, 6, 63, (142, 76, 45)),
    (16, 6, 80, (112, 59, 36)),
    (25, 6, 100, (99, 53, 32)),
    (35, 10, 125, (127, 68, 41)),
    (50, 16, 160, (155, 83, 50)),
    (70, 25, 200, (188, 100, 60)),
])
def test_lunghezza_massima_tn(sph, spe, i_n, attese):
    """AS/NZS 3000:2018 tabella B1 (stessa formula del metodo convenzionale della guida
    Schneider): interruttori B, C, D con Ia = 4, 7,5, 12,5·In, U0 = 230 V, rame."""
    from iec60909.cables import max_length_tn

    for mult, l_pub in zip((4, 7.5, 12.5), attese):
        assert round(max_length_tn(230, sph, spe, mult * i_n)) == l_pub


def test_energia_passante_del_costruttore():
    """Sotto 0,1 s si usa l'I²t passante dichiarato (IEC 60364-4-43, 434.5.2). Rete da 10 MVA:
    Ik ≈ 14 kA, I²·t con t = 10 ms ≈ 2·10⁶ A²s richiederebbe 16 mm²; con 40 kA²s basta la
    sezione data dalla portata (B1, 3 conduttori caricati, In 25 A: 4 mm², 28 A)."""
    from iec60909.network import ProtectiveDevice

    net = _rete(km=0.03, skq=10.0, ib_a=18.0, ampacity_a={}, method="B1", device="MCB", i2_ratio=1.45,
                vdrop_max_percent=10)
    net.protective_devices.append(ProtectiveDevice("MCB", "L", "Q", "breaker", in_a=25.0, ir=1.0, tr_s=20.0,
                                                   ii=10.0, ti_s=0.01))
    senza = size_cable(net, net.cable_sizing[0])
    i2t = (senza.ik_max_ka * 1000) ** 2 * 0.01
    assert senza.section_mm2 == min(s for s in (6, 10, 16, 25) if (115 * s) ** 2 >= i2t)
    net.cable_sizing[0].let_through_a2s = 40e3
    con = size_cable(net, net.cable_sizing[0])
    assert con.section_mm2 == 4 and con.iz_a == 28


def test_esempio_cabina(tmp_path, capsys):
    import json
    from pathlib import Path

    from iec60909.cavi import main

    esempio = Path(__file__).resolve().parents[1] / "esempi" / "cavi_cabina.json"
    assert main([str(esempio), "--json", "--applica", str(tmp_path / "rete.json")]) == 0
    dati = {r["id"]: r for r in json.loads(capsys.readouterr().out)}
    assert {k: (r["section_mm2"], r["pe_section_mm2"]) for k, r in dati.items()} == \
        {"C_QD1": (185, 95), "C_M1": (120, 70), "C_IL": (10, 10)}
    for r in dati.values():
        assert r["ib_a"] <= r["in_a"] <= r["iz_a"] and r["vdrop_percent"] <= 4.0
    # la rete con le sezioni applicate si ricarica e il flusso di potenza converge
    from iec60909 import load_network, run_load_flow

    net = load_network(tmp_path / "rete.json")
    assert next(ln for ln in net.lines if ln.id == "L_M1").r1_ohm_per_km == 0.153
    assert run_load_flow(net).converged
