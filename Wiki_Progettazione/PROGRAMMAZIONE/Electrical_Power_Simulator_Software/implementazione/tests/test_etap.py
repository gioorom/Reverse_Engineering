"""Verifiche dell'importazione degli studi di cortocircuito di ETAP (iec60909.etap).

I database SQLite sono sintetici: vengono creati in tmp_path con le sole
tabelle e colonne lette da etap.py e riempiti con valori inventati. Nessun
file ETAP reale è usato (né va aggiunto al repository).
"""

import copy
import json
import math
import sqlite3

import pytest

from iec60909 import calculate, etap, network_from_dict

# --- dati inventati di una piccola rete AT/MT/BT -------------------------------

TABELLE = {
    "ISCStudyCase": [{"Freq": 50.0}],
    "IAdjustments": [{"applyXfmrZTol": 0}],
    "IBus": [
        {"IDBus": "AT", "NomlkV": 132.0},
        {"IDBus": "MT", "NomlkV": 20.0},
        {"IDBus": "MT2", "NomlkV": 20.0},  # unito a MT dal congiuntore
        {"IDBus": "TER", "NomlkV": 6.0},
        {"IDBus": "BT1", "NomlkV": 0.4},
        {"IDBus": "BT1Q", "NomlkV": 0.4},
        {"IDBus": "BT2", "NomlkV": 0.4},
        {"IDBus": "BT3", "NomlkV": 0.4},
    ],
    "IConnect": [
        {"Type": "Tie Breaker", "From": "MT", "ToSec": "MT2"},
        {"Type": "Cable", "From": "BT1", "ToSec": "BT1Q"},
    ],
    "IUtility": [
        {
            "ID": "Rete", "ConnectedBus": "AT", "MVA3ph": 3000.0, "X/R3ph": 12.5,
            "XPos100MVA": 3.3, "XZero100MVA": 4.62, "RZero100MVA": 0.462,
        }
    ],
    "IXFMR3": [
        {
            "ID": "T3", "Prim": "AT", "Second": "MT", "Tri": "TER",
            "PrimkV": 132.0, "SeckV": 20.0, "TerkV": 6.0,
            "Prim%Tap": 0.0, "Sec%Tap": 2.5, "Ter%Tap": 0.0,
            "PMVA": 40.0, "SMVA": 40.0, "TMVA": 10.0,
            "PConn": "Y", "SConn": "Y", "TConn": "D",
            "PrimGrdType": "Solid", "SecGrdType": "Solid", "TerGrdType": "",
            "PSPosZ": 12.0, "PSPosX/R": 40.0, "PSZeroZ": 11.0, "PSZeroX/R": 35.0,
            "TPPosZ": 20.0, "TPPosX/R": 30.0, "TPZeroZ": 18.0, "TPZeroX/R": 25.0,
            "STPosZ": 16.0, "STPosX/R": 28.0, "STZeroZ": 15.0, "STZeroX/R": 24.0,
        }
    ],
    "IXFMR2": [
        {
            "ID": "T1", "FromBus": "MT2", "ToBus": "BT1", "MVA": 0.8,
            "PrimkV": 20.0, "SeckV": 0.4, "Prim%Tap": -2.5, "Sec%Tap": 0.0,
            "PosZ": 6.0, "PosX/R": 5.0, "ZeroZ": 5.7, "ZeroX/R": 4.5, "Tol%": 7.5,
            "Conn": "D/Y", "PrimGrdType": "", "SecGrdType": "Solid",
        },
        {
            "ID": "T2", "FromBus": "MT", "ToBus": "BT2", "MVA": 1.0,
            "PrimkV": 20.0, "SeckV": 0.42, "Prim%Tap": 0.0, "Sec%Tap": 0.0,
            "PosZ": 6.0, "PosX/R": 6.0, "ZeroZ": 5.5, "ZeroX/R": 5.0, "Tol%": 10.0,
            "Conn": "Y/Y", "PrimGrdType": "Solid", "SecGrdType": "Solid",
        },
        {
            "ID": "T4", "FromBus": "MT", "ToBus": "BT3", "MVA": 0.5,
            "PrimkV": 20.0, "SeckV": 0.4, "Prim%Tap": 0.0, "Sec%Tap": 0.0,
            "PosZ": 4.0, "PosX/R": 3.0, "ZeroZ": 4.0, "ZeroX/R": 3.0, "Tol%": 0.0,
            "Conn": "D/Y", "PrimGrdType": "", "SecGrdType": "Open",
        },
    ],
    "Icable": [
        {
            "ID": "C1", "FromBus": "BT1", "ToBus": "BT1Q", "Length": 45.0,
            "RPos": 0.0754, "XPos": 0.0731, "RZero": 0.302, "XZero": 0.292, "No/Ph": 2,
        }
    ],
    "ISynGen": [
        {
            "ID": "G1", "ConnectedBus": "TER", "MVA": 8.0, "KV": 6.3, "Xdpp": 14.0,
            "PF": 85.0, "Xpp/R": 25.0, "X2": 15.0, "GNDType": 0, "GNDAmp": 0.0, "Xzero": 6.0,
        }
    ],
    "ISynMotor": [
        {
            "ID": "MS1", "ConnectedBus": "MT2", "kVA": 2500.0, "kV": 20.0, "Xdpp": 18.0,
            "PF100": 90.0, "Xpp/R": 20.0, "X2": 17.0, "GNDType": 3, "GNDAmp": 200.0, "X0": 7.0,
        }
    ],
    "IIndMachine": [
        {
            "ID": "MA1", "ConnectedBus": "BT1Q", "kVA": 180.0, "KV": 0.4, "LRC": 650.0,
            "Xpp/R": 4.0, "X2": 16.0, "R": 2.4,
        }
    ],
}


def _tabella(db, nome, righe):
    """Crea la tabella `nome` con le colonne delle righe (lista di dizionari) e la riempie."""
    colonne = list(dict.fromkeys(k for r in righe for k in r))
    elenco = ", ".join(f'"{c}"' for c in colonne)
    db.execute(f'create table "{nome}" ({elenco})')
    segnaposto = ", ".join("?" for _ in colonne)
    db.executemany(
        f'insert into "{nome}" ({elenco}) values ({segnaposto})',
        [tuple(r.get(c) for c in colonne) for r in righe],
    )


def _studio(tmp_path, nome="studio.SI2S", **tabelle):
    """Scrive un database ETAP sintetico; le tabelle passate sostituiscono quelle base."""
    dati = copy.deepcopy(TABELLE)
    dati.update(tabelle)
    path = tmp_path / nome
    db = sqlite3.connect(path)
    try:
        for t, righe in dati.items():
            if righe:
                _tabella(db, t, righe)
        db.commit()
    finally:
        db.close()
    return path


def _per_id(elementi):
    return {e["id"]: e for e in elementi}


def _trafo2(**modifiche):
    righe = copy.deepcopy(TABELLE["IXFMR2"])
    for r in righe:
        r.update(modifiche.get(r["ID"], {}))
    return righe


# --- 1. conversione della rete -------------------------------------------------


def test_prese_applicate_alle_tensioni_nominali(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    t1 = _per_id(rete["transformers"])["T1"]
    assert t1["ur_hv_kv"] == pytest.approx(20.0 * 0.975)
    assert t1["ur_lv_kv"] == pytest.approx(0.4)
    t3 = rete["transformers3w"][0]
    assert t3["ur_hv_kv"] == pytest.approx(132.0)
    assert t3["ur_mv_kv"] == pytest.approx(20.0 * 1.025)
    assert t3["ur_lv_kv"] == pytest.approx(6.0)


def test_tolleranza_trafo_solo_con_applyXfmrZTol(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    senza, _ = etap.network_from_etap(_studio(tmp_path / "a"))
    con, _ = etap.network_from_etap(
        _studio(tmp_path / "b", IAdjustments=[{"applyXfmrZTol": 1}])
    )
    t1, t1_tol = _per_id(senza["transformers"])["T1"], _per_id(con["transformers"])["T1"]
    assert t1["ukr_percent"] == pytest.approx(6.0)
    assert t1["uk0_percent"] == pytest.approx(5.7)
    assert t1["urr_percent"] == pytest.approx(6.0 / math.sqrt(1 + 5.0**2))
    assert t1["ur0_percent"] == pytest.approx(5.7 / math.sqrt(1 + 4.5**2))
    assert t1_tol["ukr_percent"] == pytest.approx(6.0 * 0.925)
    assert t1_tol["uk0_percent"] == pytest.approx(5.7 * 0.925)
    # il rapporto X/R non cambia
    assert t1_tol["urr_percent"] == pytest.approx(6.0 * 0.925 / math.sqrt(1 + 5.0**2))
    assert _per_id(con["transformers"])["T2"]["ukr_percent"] == pytest.approx(6.0 * 0.9)
    # la tolleranza non si applica ai trasformatori a tre avvolgimenti
    assert con["transformers3w"] == senza["transformers3w"]


def test_gruppi_vettoriali(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    gruppi = {t["id"]: t["vector_group"] for t in rete["transformers"]}
    assert gruppi == {"T1": "Dyn", "T2": "YNyn", "T4": "Dy"}
    assert rete["transformers3w"][0]["vector_group"] == "YNynd"


def test_tre_avvolgimenti_impedenze_di_coppia(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    t = rete["transformers3w"][0]
    assert (t["hv_bus"], t["mv_bus"], t["lv_bus"]) == ("AT", "MT", "TER")
    # potenza di coppia = la minore dei due avvolgimenti; %Z di ETAP su PMVA = 40 MVA
    for coppia, etap_id, sr in (("hv_mv", "PS", 40.0), ("hv_lv", "TP", 10.0), ("mv_lv", "ST", 10.0)):
        riga = TABELLE["IXFMR3"][0]
        assert t[f"sr_{coppia}_mva"] == sr
        for pre, seq in (("r", "Pos"), ("0", "Zero")):
            uk = riga[f"{etap_id}{seq}Z"] * sr / 40.0
            xr = riga[f"{etap_id}{seq}X/R"]
            assert t[f"uk{pre}_{coppia}_percent"] == pytest.approx(uk)
            assert t[f"ur{pre}_{coppia}_percent"] == pytest.approx(uk / math.sqrt(1 + xr**2))
            # X/R conservato
            ur = t[f"ur{pre}_{coppia}_percent"]
            assert math.sqrt(t[f"uk{pre}_{coppia}_percent"] ** 2 - ur**2) / ur == pytest.approx(xr)


def test_congiuntore_unisce_i_nodi(tmp_path):
    rete, alias = etap.network_from_etap(_studio(tmp_path))
    assert alias == {"MT2": "MT"}
    nodi = [b["id"] for b in rete["buses"]]
    assert "MT2" not in nodi and "MT" in nodi
    assert _per_id(rete["transformers"])["T1"]["hv_bus"] == "MT"
    assert _per_id(rete["generators"])["MS1"]["bus"] == "MT"


def test_congiuntori_in_serie_in_ordine_qualsiasi(tmp_path):
    """MT3 -> MT2 -> MT: l'ordine delle righe di IConnect non deve contare."""
    bus = TABELLE["IBus"] + [{"IDBus": "MT3", "NomlkV": 20.0}]
    connessioni = [
        {"Type": "Tie Breaker", "From": "MT2", "ToSec": "MT3"},
        {"Type": "Tie Breaker", "From": "MT", "ToSec": "MT2"},
    ]
    motori = copy.deepcopy(TABELLE["ISynMotor"])
    motori[0]["ConnectedBus"] = "MT3"
    rete, alias = etap.network_from_etap(
        _studio(tmp_path, IBus=bus, IConnect=connessioni, ISynMotor=motori)
    )
    assert alias == {"MT2": "MT", "MT3": "MT"}
    assert _per_id(rete["generators"])["MS1"]["bus"] == "MT"
    calculate(network_from_dict(rete))


def test_cavo_unita_di_misura(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    c = rete["lines"][0]
    assert c == {
        "id": "C1", "from_bus": "BT1", "to_bus": "BT1Q",
        "length_km": pytest.approx(0.045),
        "r1_ohm_per_km": 0.0754, "x1_ohm_per_km": 0.0731,
        "r0_ohm_per_km": 0.302, "x0_ohm_per_km": 0.292, "parallel": 2,
    }
    # senza dati omopolari (XZero = 0) i campi non vengono scritti
    cavi = copy.deepcopy(TABELLE["Icable"])
    cavi[0].update(XZero=0.0, RZero=0.0)
    (tmp_path / "b").mkdir()
    rete, _ = etap.network_from_etap(_studio(tmp_path / "b", Icable=cavi))
    assert "x0_ohm_per_km" not in rete["lines"][0]


def test_generatore_sincrono(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    g = _per_id(rete["generators"])["G1"]
    xd = 0.14 * 6.3**2 / 8.0
    assert g["rg_ohm"] == pytest.approx(xd / 25.0)
    assert g["cos_phi"] == pytest.approx(0.85)
    assert g["x2_percent"] == 15.0
    # senza messa a terra (GNDType != 3): nessun dato omopolare
    assert "x0_percent" not in g and "zn_ohm" not in g


def test_motore_sincrono_come_generatore(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    m = _per_id(rete["generators"])["MS1"]
    sr = 2.5
    xd = 0.18 * 20.0**2 / sr
    assert m["sr_mva"] == pytest.approx(sr)
    assert m["ur_kv"] == 20.0
    assert m["xd2_percent"] == 18.0
    assert m["cos_phi"] == pytest.approx(0.9)
    assert m["rg_ohm"] == pytest.approx(xd / 20.0)
    assert m["x2_percent"] == 17.0
    # neutro a terra tramite resistenza: Rn = Un/(√3·I)
    assert m["x0_percent"] == 7.0
    assert m["zn_ohm"] == pytest.approx(20000.0 / (math.sqrt(3) * 200.0))
    assert "MS1" not in _per_id(rete["motors"])


def test_motore_asincrono(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    m = _per_id(rete["motors"])["MA1"]
    assert m == {
        "id": "MA1", "bus": "BT1Q", "pr_mw": pytest.approx(0.18), "ur_kv": 0.4,
        "efficiency": 1.0, "cos_phi": 1.0, "ilr_ir": pytest.approx(6.5),
        "rx": pytest.approx(0.25), "x2_percent": 16.0, "rx2": pytest.approx(2.4 / 16.0),
    }


def test_rete_esterna(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    q = rete["external_grids"][0]
    assert q["bus"] == "AT"
    assert q["skq_max_mva"] == 3000.0
    assert q["rx_max"] == pytest.approx(1 / 12.5)
    assert q["x0x1"] == pytest.approx(4.62 / 3.3)
    assert q["r0x0"] == pytest.approx(0.1)
    assert rete["f_hz"] == 50


# --- 2. la rete convertita si carica e si calcola ------------------------------


def test_rete_convertita_si_calcola(tmp_path):
    rete, _ = etap.network_from_etap(_studio(tmp_path))
    r = calculate(network_from_dict(rete))
    assert {b.bus for b in r.buses} == {"AT", "MT", "TER", "BT1", "BT1Q", "BT2", "BT3"}
    assert all(b.ikss3_ka > 0 for b in r.buses)
    # Dy con stella isolata e TER (triangolo, generatore senza terra): niente omopolare
    assert r.bus("BT3").z0_ohm is None and r.bus("BT3").ikss1_ka == 0.0
    assert r.bus("TER").z0_ohm is None
    assert r.bus("BT1").ikss1_ka > 0 and r.bus("BT2").ikss1_ka > 0


# --- 3. confronto con i risultati ETAP -----------------------------------------


def _risultati_etap(tmp_path, alterazioni=None):
    """Studio con risultati ETAP pari a quelli calcolati da iec60909 sulla rete convertita."""
    (tmp_path / "rete").mkdir()
    rete, alias = etap.network_from_etap(_studio(tmp_path / "rete"))
    r = calculate(network_from_dict(rete), "max", "C")
    nodi = [b["IDBus"] for b in TABELLE["IBus"]]
    sum1, sum2, clip = [], [], []
    for nodo in nodi:
        b = r.bus(alias.get(nodo, nodo))
        sum1.append({
            "FaultedBus": nodo, "IPPk3ph": b.ikss3_ka, "ip3ph": b.ip3_ka, "IPPkLL": b.ikss2_ka,
            "IPPkLG": b.ikss1_ka, "IPPkLLG": max(b.ikss2e_l2_ka, b.ikss2e_l3_ka),
        })
        sum2.append({
            "FaultedBus": nodo, "ZPosOhm": abs(b.z1_ohm),
            "ZZeroOhm": abs(b.z0_ohm) if b.z0_ohm is not None else 0.0,
        })
        clip.append({"FaultedBus": nodo, "SymmLLG_3I0": b.ikss2e_earth_ka})
    for nodo, colonna, fattore in alterazioni or []:
        riga = next(x for x in sum1 + sum2 + clip if x["FaultedBus"] == nodo and colonna in x)
        riga[colonna] *= fattore
    return _studio(tmp_path, SCIECLGSum1=sum1, SCIECLGSum2=sum2, ClippingCurrent=clip)


def test_confronto_scarti_nulli(tmp_path):
    _, righe = etap.compare(_risultati_etap(tmp_path))
    assert len(righe) == len(TABELLE["IBus"]) * 8
    assert {c.bus for c in righe} == {b["IDBus"] for b in TABELLE["IBus"]}
    for c in righe:
        assert c.diff_percent is not None, (c.bus, c.quantity)
        assert abs(c.diff_percent) < 1e-9, (c.bus, c.quantity, c.diff_percent)
    # grandezze nulle in entrambi (BT3 senza percorso omopolare): scarto 0
    zero = {c.quantity: c for c in righe if c.bus == "BT3"}
    assert zero['I"k1'].etap == 0.0 and zero['I"k1'].diff_percent == 0.0
    assert zero["|Z0|"].etap == 0.0 and zero["|Z0|"].diff_percent == 0.0


def test_confronto_scarto_atteso(tmp_path):
    studio = _risultati_etap(tmp_path, [("BT2", "IPPk3ph", 1.02), ("MT2", "ZPosOhm", 0.95)])
    _, righe = etap.compare(studio)
    scarti = {(c.bus, c.quantity): c.diff_percent for c in righe}
    assert scarti[("BT2", 'I"k3')] == pytest.approx((1 / 1.02 - 1) * 100, rel=1e-9)
    assert scarti[("MT2", "|Z1|")] == pytest.approx((1 / 0.95 - 1) * 100, rel=1e-9)
    altri = [d for k, d in scarti.items() if k not in {("BT2", 'I"k3'), ("MT2", "|Z1|")}]
    assert all(abs(d) < 1e-9 for d in altri)


def test_scarto_con_valore_etap_nullo():
    assert etap.Comparison("X", 'I"k1', 0.0, 0.0).diff_percent == 0.0
    assert etap.Comparison("X", 'I"k1', 0.0, 1.5).diff_percent is None
    assert etap.Comparison("X", 'I"k3', 10.0, 10.5).diff_percent == pytest.approx(5.0)


# --- 4. riga di comando --------------------------------------------------------


def test_main_json_e_tabella(tmp_path, capsys):
    studio = _risultati_etap(tmp_path)
    uscita = tmp_path / "rete.json"
    assert etap.main([str(studio), "--json", str(uscita)]) == 0
    salvata = json.loads(uscita.read_text(encoding="utf-8"))
    attesa, _ = etap.network_from_etap(studio)
    assert salvata == json.loads(json.dumps(attesa))
    calculate(network_from_dict(salvata))
    out, err = capsys.readouterr()
    righe = out.splitlines()
    assert righe[0] == "| Nodo | Grandezza | ETAP | iec60909 | Scarto |"
    assert righe[1] == "|---|---|---|---|---|"
    assert len(righe) == 2 + len(TABELLE["IBus"]) * 8
    assert any(r.startswith('| BT1 | I"k3 |') and r.endswith("0.000 % |") for r in righe)
    assert "Scarto massimo: 0.000 %" in err
