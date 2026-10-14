"""Affidabilità: calcoli a mano su una dorsale radiale con fusibili, sezionatori e
contro-alimentazione, ridondanza in parallelo (secondo ordine) contro Markov e
Monte Carlo, indici di sistema."""

import json
from pathlib import Path

import numpy as np
import pytest

from iec60909 import network_from_dict
from iec60909.reliability import reliability_analysis

ESEMPI = Path(__file__).resolve().parents[1] / "esempi"


def _linea(id_, a, b, km=1.0):
    return {"id": id_, "from_bus": a, "to_bus": b, "length_km": km,
            "r1_ohm_per_km": 0.2, "x1_ohm_per_km": 0.1}


def _dorsale(organi_l2="switch", organi_l3="switch", tie=True, carichi=None):
    """S – B0 –L1(2 km)– B1 –L2(1 km)– B2 –L3(3 km)– B3 [–T (NA)– B4 – S2]
    con le derivazioni Fi (fusibile in testa) verso i carichi Ai."""
    buses = [{"id": f"B{i}", "un_kv": 20} for i in range(5 if tie else 4)]
    buses += [{"id": f"A{i}", "un_kv": 20} for i in (1, 2, 3)]
    lines = [_linea("L1", "B0", "B1", 2), _linea("L2", "B1", "B2", 1), _linea("L3", "B2", "B3", 3)]
    lines += [_linea(f"F{i}", f"B{i}", f"A{i}") for i in (1, 2, 3)]
    switches = [{"id": "CB", "branch": "L1", "bus": "B0", "kind": "breaker"}]
    if organi_l2:
        switches.append({"id": "S2", "branch": "L2", "bus": "B1", "kind": organi_l2})
    if organi_l3:
        switches.append({"id": "S3", "branch": "L3", "bus": "B2", "kind": organi_l3})
    switches += [{"id": f"FU{i}", "branch": f"F{i}", "bus": f"B{i}", "kind": "fuse"} for i in (1, 2, 3)]
    grids = [{"id": "S", "bus": "B0", "skq_max_mva": 500}]
    if tie:
        lines.append(_linea("T", "B3", "B4"))
        switches.append({"id": "NA", "branch": "T", "bus": "B3", "normally_open": True, "switching_time_h": 1.5})
        grids.append({"id": "S2", "bus": "B4", "skq_max_mva": 500})
    loads = carichi or [{"id": f"C{i}", "bus": f"A{i}", "p_mw": 0.5 * i, "customers": 100 * i} for i in (1, 2, 3)]
    return network_from_dict({
        "name": "Dorsale", "buses": buses, "external_grids": grids, "lines": lines, "loads": loads,
        "switches": switches,
        "reliability_data": [
            {"element": "@lines", "failure_rate_per_km": 0.1, "repair_time_h": 4.0},
            {"element": "F1", "failure_rate": 0.2, "repair_time_h": 2.0},
            {"element": "F2", "failure_rate": 0.6, "repair_time_h": 2.0},
            {"element": "F3", "failure_rate": 0.4, "repair_time_h": 2.0},
        ] + ([{"element": "T", "failure_rate": 0.0, "repair_time_h": 0.0}] if tie else []),
    })


def _per_carico(r):
    return {p.id: p for p in r.load_points}


def test_dorsale_con_sezionatori_e_contro_alimentazione():
    r = reliability_analysis(_dorsale())
    p = _per_carico(r)
    lam_main = {"L1": 0.2, "L2": 0.1, "L3": 0.3}
    # durate attese: riparazione 4 h, sezionamento 1 h, contro-alimentazione max(1, 1,5) h
    attese = {
        "C1": ({"L1": 4.0, "L2": 1.0, "L3": 1.0}, 0.2),
        "C2": ({"L1": 1.5, "L2": 4.0, "L3": 1.0}, 0.6),
        "C3": ({"L1": 1.5, "L2": 1.5, "L3": 4.0}, 0.4),
    }
    for cid, (durate, lam_lat) in attese.items():
        lam = sum(lam_main.values()) + lam_lat
        u = sum(lam_main[k] * d for k, d in durate.items()) + lam_lat * 2.0
        assert p[cid].failure_rate == pytest.approx(lam, rel=1e-12)
        assert p[cid].unavailability_h == pytest.approx(u, rel=1e-12)
        assert p[cid].duration_h == pytest.approx(u / lam, rel=1e-12)
    # indici di sistema
    n = 600
    saifi = sum(100 * i * p[f"C{i}"].failure_rate for i in (1, 2, 3)) / n
    saidi = sum(100 * i * p[f"C{i}"].unavailability_h for i in (1, 2, 3)) / n
    ens = sum(0.5 * i * p[f"C{i}"].unavailability_h for i in (1, 2, 3))
    assert r.customers == n
    assert r.saifi == pytest.approx(saifi) and r.saidi == pytest.approx(saidi)
    assert r.caidi == pytest.approx(saidi / saifi)
    assert r.asai == pytest.approx(1 - saidi / 8760)
    assert r.ens_mwh == pytest.approx(ens) and r.aens_kwh == pytest.approx(ens * 1000 / n)
    # nessuna sovrapposizione in una rete radiale
    assert all(c.restoration != "overlap" for q in r.load_points for c in q.contributions)


def test_senza_sezionatori_tutto_a_riparazione():
    r = reliability_analysis(_dorsale(organi_l2=None, organi_l3=None, tie=False))
    for i, lam_lat in ((1, 0.2), (2, 0.6), (3, 0.4)):
        p = _per_carico(r)[f"C{i}"]
        assert p.failure_rate == pytest.approx(0.6 + lam_lat)
        assert p.unavailability_h == pytest.approx(0.6 * 4 + lam_lat * 2)


def test_interruttore_intermedio():
    """Con un interruttore in testa a L2 i guasti di L2 e L3 non interrompono C1."""
    r = reliability_analysis(_dorsale(organi_l2="breaker", tie=False))
    p = _per_carico(r)
    assert p["C1"].failure_rate == pytest.approx(0.2 + 0.2)
    assert p["C1"].unavailability_h == pytest.approx(0.2 * 4 + 0.2 * 2)
    # C2 e C3: L1 a riparazione; per C3 un guasto su L2 si seziona con S3 ma non c'è contro-alimentazione
    assert p["C3"].unavailability_h == pytest.approx(0.2 * 4 + 0.1 * 4 + 0.3 * 4 + 0.4 * 2)
    # tempo di riparazione minore della manovra: vale la riparazione
    net = _dorsale()
    net.reliability_data[0].repair_time_h = 0.5
    p = _per_carico(reliability_analysis(net))
    assert p["C1"].unavailability_h == pytest.approx(0.6 * 0.5 + 0.2 * 2)


def test_guasti_transitori():
    net = _dorsale()
    net.reliability_data[0].temporary_rate = 1.0  # 1/anno per ogni linea senza dati propri
    r = reliability_analysis(net)
    p = _per_carico(r)
    # i guasti transitori di L1, L2 e L3 (le derivazioni e T hanno dati propri senza guasti transitori)
    # interessano tutta la dorsale
    for cid in ("C1", "C2", "C3"):
        assert p[cid].momentary_rate == pytest.approx(3.0)
    assert r.maifi == pytest.approx(3.0)


def _parallelo(lam=2.0, r=50.0):
    return network_from_dict({
        "name": "Due linee in parallelo",
        "buses": [{"id": "B0", "un_kv": 20}, {"id": "B1", "un_kv": 20}],
        "external_grids": [{"id": "S", "bus": "B0", "skq_max_mva": 500}],
        "lines": [_linea("P1", "B0", "B1"), _linea("P2", "B0", "B1")],
        "switches": [{"id": f"CB{k}{b}", "branch": f"P{k}", "bus": b, "kind": "breaker"}
                     for k in (1, 2) for b in ("B0", "B1")],
        "loads": [{"id": "C", "bus": "B1", "p_mw": 1.0, "customers": 10}],
        "reliability_data": [{"element": "@lines", "failure_rate": lam, "repair_time_h": r}],
    })


def test_ridondanza_secondo_ordine():
    lam, rr = 2.0, 50.0
    r = reliability_analysis(_parallelo(lam, rr))
    p = r.load_points[0]
    lam_pp = lam * lam * (2 * rr) / 8760
    assert p.failure_rate == pytest.approx(lam_pp, rel=1e-12)
    assert p.duration_h == pytest.approx(rr / 2, rel=1e-12)
    # Markov esatto con due componenti indipendenti: f = U1·U2·(μ1 + μ2)
    mu = 8760 / rr
    u = lam / (lam + mu)
    assert p.failure_rate == pytest.approx(u * u * 2 * mu, rel=3e-2)  # scarto ~2·λ·r/8760
    assert reliability_analysis(_parallelo(lam, rr), second_order=False).load_points[0].failure_rate == 0.0


def test_monte_carlo_parallelo():
    """Simulazione sequenziale indipendente: due processi di guasto e riparazione esponenziali."""
    lam, rr = 2.0, 50.0
    rng = np.random.default_rng(12345)
    anni = 40000.0
    intervalli = []
    for _ in range(2):
        n = int(anni * lam * 1.2) + 1000
        up = rng.exponential(8760 / lam, n)
        down = rng.exponential(rr, n)
        start = np.cumsum(up + down) - down
        keep = start < anni * 8760
        intervalli.append((start[keep], start[keep] + down[keep]))
    (s1, e1), (s2, e2) = intervalli
    # sovrapposizioni: per ogni guasto di 1, i guasti di 2 che si sovrappongono
    j = np.searchsorted(e2, s1)
    eventi, durata = 0, 0.0
    for a, b, k in zip(s1, e1, j):
        while k < len(s2) and s2[k] < b:
            lo, hi = max(a, s2[k]), min(b, e2[k])
            if hi > lo:
                eventi += 1
                durata += hi - lo
            k += 1
    f_mc, u_mc = eventi / anni, durata / anni
    # Markov esatto (la formula del secondo ordine lo approssima per λ·r << 1)
    mu = 8760 / rr
    u = lam / (lam + mu)
    assert f_mc == pytest.approx(u * u * 2 * mu, rel=0.05)
    assert u_mc == pytest.approx(u * u * 8760, rel=0.07)
    p = reliability_analysis(_parallelo(lam, rr)).load_points[0]
    assert f_mc == pytest.approx(p.failure_rate, rel=0.08)
    assert u_mc == pytest.approx(p.unavailability_h, rel=0.1)


def test_guasto_di_nodo_e_di_sorgente():
    net = network_from_dict({
        "name": "Doppia alimentazione",
        "buses": [{"id": "B0", "un_kv": 20}, {"id": "B1", "un_kv": 20}, {"id": "B2", "un_kv": 0.4}],
        "external_grids": [{"id": "S", "bus": "B0", "skq_max_mva": 500}],
        "generators": [{"id": "G", "bus": "B1", "sr_mva": 2, "ur_kv": 20, "xd2_percent": 15}],
        "lines": [_linea("L", "B0", "B1")],
        "transformers": [{"id": "TR", "hv_bus": "B1", "lv_bus": "B2", "sr_mva": 1, "ur_hv_kv": 20,
                          "ur_lv_kv": 0.4, "ukr_percent": 6, "urr_percent": 1}],
        "switches": [{"id": "CB", "branch": "L", "bus": "B0", "kind": "breaker"},
                     {"id": "CB1", "branch": "L", "bus": "B1", "kind": "breaker"}],
        "loads": [{"id": "C", "bus": "B2", "p_mw": 0.5, "customers": 50}],
        "reliability_data": [
            {"element": "S", "failure_rate": 1.0, "repair_time_h": 3.0},
            {"element": "G", "failure_rate": 2.0, "repair_time_h": 10.0},
            {"element": "L", "failure_rate": 0.5, "repair_time_h": 5.0},
            {"element": "B1", "failure_rate": 0.01, "repair_time_h": 20.0},
            {"element": "@transformers", "failure_rate": 0.02, "repair_time_h": 200.0},
        ],
    })
    p = reliability_analysis(net).load_points[0]
    ev = {c.element: c for c in p.contributions}
    # primo ordine: nodo B1 e trasformatore; L, S e G da soli non interrompono (rete esterna o generatore)
    assert ev["B1"].duration_h == 20.0 and ev["TR"].duration_h == 200.0
    assert "L" not in ev and "S" not in ev and "G" not in ev
    # secondo ordine: coppie che separano B1 da entrambe le sorgenti
    assert set(ev) == {"B1", "TR", "S+G", "L+G"}
    for coppia, (l1, r1, l2, r2) in {"S+G": (1.0, 3.0, 2.0, 10.0), "L+G": (0.5, 5.0, 2.0, 10.0)}.items():
        c = ev[coppia]
        assert c.failure_rate == pytest.approx(l1 * l2 * (r1 + r2) / 8760)
        assert c.duration_h == pytest.approx(r1 * r2 / (r1 + r2))
    # senza il generatore come sorgente S e L sono in serie
    p = reliability_analysis(net, generators_as_sources=False).load_points[0]
    ev = {c.element: c for c in p.contributions}
    assert ev["S"].duration_h == 3.0 and ev["L"].duration_h == 5.0


def test_trasformatore_tre_avvolgimenti():
    net = network_from_dict({
        "name": "3W",
        "buses": [{"id": "H", "un_kv": 132}, {"id": "M", "un_kv": 20}, {"id": "L", "un_kv": 10}],
        "external_grids": [{"id": "S", "bus": "H", "skq_max_mva": 5000}],
        "transformers3w": [{"id": "T3", "hv_bus": "H", "mv_bus": "M", "lv_bus": "L",
                            "sr_hv_mv_mva": 50, "sr_hv_lv_mva": 50, "sr_mv_lv_mva": 50,
                            "ur_hv_kv": 132, "ur_mv_kv": 20, "ur_lv_kv": 10,
                            "ukr_hv_mv_percent": 10, "ukr_hv_lv_percent": 12, "ukr_mv_lv_percent": 8,
                            "urr_hv_mv_percent": 0.3, "urr_hv_lv_percent": 0.3, "urr_mv_lv_percent": 0.3}],
        "switches": [{"id": "CBM", "branch": "T3", "bus": "M", "kind": "breaker"},
                     {"id": "CBL", "branch": "T3", "bus": "L", "kind": "breaker"}],
        "loads": [{"id": "CM", "bus": "M", "p_mw": 5}, {"id": "CL", "bus": "L", "p_mw": 3}],
        "reliability_data": [{"element": "T3", "failure_rate": 0.015, "repair_time_h": 100},
                             {"element": "L", "failure_rate": 0.1, "repair_time_h": 2}],
    })
    p = {q.id: q for q in reliability_analysis(net).load_points}
    # il guasto del nodo L è eliminato da CBL e non interessa CM
    assert p["CM"].failure_rate == pytest.approx(0.015) and p["CL"].failure_rate == pytest.approx(0.115)
    assert p["CM"].unavailability_h == pytest.approx(0.015 * 100)
    assert p["CL"].unavailability_h == pytest.approx(0.015 * 100 + 0.1 * 2)
    # senza CBL il guasto di L fa intervenire la protezione a monte e non si può sezionare
    net.switches.pop()
    p = {q.id: q for q in reliability_analysis(net).load_points}
    assert p["CM"].unavailability_h == pytest.approx(0.015 * 100 + 0.1 * 2)


def test_costo_e_esempio():
    data = json.loads((ESEMPI / "affidabilita_dorsale.json").read_text(encoding="utf-8"))
    net = network_from_dict(data)
    r = reliability_analysis(net, cost_per_kwh=5.0)
    assert r.cost == pytest.approx(r.ens_mwh * 1000 * 5.0)
    assert r.saifi > 0 and r.saidi > 0 and not r.warnings


def test_errori():
    net = _dorsale()
    net.reliability_data.append(net.reliability_data[0])
    with pytest.raises(ValueError, match="dati ripetuti"):
        reliability_analysis(net)
    net = _dorsale()
    net.switches[0].bus = "B1"
    net.switches[0].branch = "L3"
    with pytest.raises(ValueError, match="non è un estremo"):
        reliability_analysis(net)
    net = _dorsale()
    net.switches[0].kind = "boh"
    with pytest.raises(ValueError, match="tipo di organo"):
        reliability_analysis(net)
    net = _dorsale()
    net.reliability_data[1].element = "X"
    with pytest.raises(ValueError, match="elemento inesistente"):
        reliability_analysis(net)
    net = _dorsale()
    net.reliability_data[1].failure_rate_per_km = 0.1
    with pytest.raises(ValueError, match="oppure"):
        reliability_analysis(net)


def test_carico_non_alimentato():
    net = _dorsale(tie=False)
    net.switches.append(type(net.switches[0])("NA3", "F3", "B3", normally_open=True))
    r = reliability_analysis(net)
    assert [p.id for p in r.load_points] == ["C1", "C2"]
    assert "C3" in r.warnings[0]
    net.switches.append(type(net.switches[0])("NA1", "L1", "B1", normally_open=True))
    with pytest.raises(ValueError, match="nessun cliente"):
        reliability_analysis(net)


def test_riga_di_comando(capsys):
    from iec60909.affidabilita import main

    assert main([str(ESEMPI / "affidabilita_dorsale.json"), "--dettagli", "--costo-kwh", "8"]) == 0
    out = capsys.readouterr().out
    assert "SAIFI" in out and "contro-alimentazione" in out
    assert main([str(ESEMPI / "affidabilita_dorsale.json"), "--json", "--primo-ordine"]) == 0
    dati = json.loads(capsys.readouterr().out)
    assert dati["saidi"] > 0 and dati["load_points"]


# --- Roy Billinton Test System, Bus 2 (Allan et al., 1991) ---------------------------------

@pytest.mark.parametrize("tipo, trasformatori_h", [("linee", 200.0), ("cavi", 200.0),
                                                     ("linee", 10.0), ("cavi", 10.0)])
def test_rbts_bus2_indici_di_sistema(tipo, trasformatori_h):
    from .rbts import TABELLA_9, rbts_bus2

    r = reliability_analysis(network_from_dict(rbts_bus2(tipo, trasformatori_h)))
    saifi, saidi, caidi, asai, ens_kwh, aens = TABELLA_9[(tipo, trasformatori_h)]
    assert r.customers == 1908
    # uguali alle cifre pubblicate
    assert round(r.saifi, 3) == saifi and round(r.saidi, 2) == saidi and round(r.caidi, 2) == caidi
    assert round(r.asai, 6) == asai and round(r.ens_mwh * 1000) == ens_kwh and round(r.aens_kwh, 2) == aens


@pytest.mark.parametrize("tipo", ["linee", "cavi"])
def test_rbts_bus2_punti_di_carico(tipo):
    """Tabella 7 (caso base): scarti entro l'arrotondamento dei valori pubblicati."""
    from .rbts import TABELLA_7, rbts_bus2

    r = reliability_analysis(network_from_dict(rbts_bus2(tipo)))
    assert len(r.load_points) == 22
    for p in r.load_points:
        lam, rr, u = TABELLA_7[tipo][int(p.id[2:])]
        assert p.failure_rate == pytest.approx(lam, abs=1.01e-3)
        assert p.unavailability_h == pytest.approx(u, abs=1.01e-2)
        assert p.duration_h == pytest.approx(rr, rel=4e-3)


def test_verifica_contro_alimentazione():
    # linea di contro-alimentazione da 1 kA: la manovra regge, durate invariate
    net = _dorsale()
    for ln in net.lines:
        ln.max_i_ka = 1.0
    base = _per_carico(reliability_analysis(_dorsale()))
    r = reliability_analysis(net, check_transfer=True)
    for cid, p in _per_carico(r).items():
        assert p.unavailability_h == pytest.approx(base[cid].unavailability_h, rel=1e-12)
    assert not r.warnings
    # linea T da 50 A: non riprende C2 + C3 (2,5 MW ≈ 72 A a 20 kV) dopo il guasto di L1,
    # che attendono la riparazione, ma riprende il solo C3 (≈ 43 A) dopo il guasto di L2
    tie = next(ln for ln in net.lines if ln.id == "T")
    tie.max_i_ka = 0.05
    r = reliability_analysis(net, check_transfer=True)
    p = _per_carico(r)
    c3 = {c.element: c for c in p["C3"].contributions}
    assert c3["L1"].restoration == "repair" and c3["L1"].duration_h == 4.0
    assert c3["L2"].restoration == "transfer" and c3["L2"].duration_h == 1.5
    c2 = {c.element: c for c in p["C2"].contributions}
    assert c2["L1"].restoration == "repair"
    assert any("guasto di L1" in w and "T " in w for w in r.warnings)
    # linea T da 30 A: C3 la carica al 144 %, ammesso solo con il limite al 150 %
    tie.max_i_ka = 0.03
    c3 = {c.element: c for c in _per_carico(reliability_analysis(net, check_transfer=True))["C3"].contributions}
    assert c3["L2"].restoration == "repair"
    r = reliability_analysis(net, check_transfer=True, max_loading_percent=150.0)
    c3 = {c.element: c for c in _per_carico(r)["C3"].contributions}
    assert c3["L2"].restoration == "transfer" and c3["L1"].restoration == "repair"
    # linea T di 40 km: dopo il guasto di L1 la tensione di B2…A3 scende a 0,945 pu
    # (respinta con v_min 0,96), dopo il guasto di L2 quella di B3 e A3 resta a 0,969 pu
    net = _dorsale()
    next(ln for ln in net.lines if ln.id == "T").length_km = 40.0
    r = reliability_analysis(net, check_transfer=True, v_min_pu=0.96)
    c3 = {c.element: c for c in _per_carico(r)["C3"].contributions}
    assert c3["L1"].restoration == "repair" and c3["L2"].restoration == "transfer"
    assert len(r.warnings) == 1 and "A3 0.946 pu" in r.warnings[0]
    # L1 già sovraccarica in esercizio normale: la contro-alimentazione che la scarica è accettata
    net = _dorsale()
    next(ln for ln in net.lines if ln.id == "L1").max_i_ka = 0.05
    r = reliability_analysis(net, check_transfer=True)
    assert "esercizio normale" in r.warnings[0] and len(r.warnings) == 1
    c3 = {c.element: c for c in _per_carico(r)["C3"].contributions}
    assert c3["L2"].restoration == "transfer"


def test_mancato_intervento_protezione_di_riserva():
    """Interruttore S2 in testa a L2 che non apre con probabilità 0,1: i guasti di L2
    e L3 fanno intervenire CB e interrompono anche C1 per il tempo di manovra."""
    base = _per_carico(reliability_analysis(_dorsale(organi_l2="breaker", tie=False)))
    r = reliability_analysis(_dorsale(organi_l2="breaker", tie=False), stuck_probability=0.1)
    p = _per_carico(r)
    riserva = {c.element: c for c in p["C1"].contributions if c.restoration == "backup"}
    assert set(riserva) == {"L2", "L3"}
    assert riserva["L2"].failure_rate == pytest.approx(0.1 * 0.1)
    assert riserva["L3"].failure_rate == pytest.approx(0.3 * 0.1)
    assert riserva["L3"].duration_h == pytest.approx(1.0)
    assert p["C1"].unavailability_h == pytest.approx(base["C1"].unavailability_h + 0.04 * 1.0)
    # C2 e C3 sono già interrotti dai guasti di L2 e L3: nessun contributo in più
    for cid in ("C2", "C3"):
        assert p[cid].unavailability_h == pytest.approx(base[cid].unavailability_h)
    # fusibile FU2 che non fonde (0,2): il guasto di F2 fa aprire S2, C3 interrotto;
    # durata: apertura manuale della derivazione (2 h) e richiusura di S2 (1 h)
    net = _dorsale(organi_l2="breaker", tie=False)
    fu2 = next(sw for sw in net.switches if sw.id == "FU2")
    fu2.stuck_probability, fu2.switching_time_h = 0.2, 2.0
    p = _per_carico(reliability_analysis(net))
    riserva = [c for c in p["C3"].contributions if c.restoration == "backup"]
    assert len(riserva) == 1 and riserva[0].element == "F2"
    assert riserva[0].failure_rate == pytest.approx(0.6 * 0.2) and riserva[0].duration_h == 2.0
    assert not any(c.restoration == "backup" for c in p["C1"].contributions)
    with pytest.raises(ValueError, match="stuck_probability"):
        reliability_analysis(net, stuck_probability=1.5)
