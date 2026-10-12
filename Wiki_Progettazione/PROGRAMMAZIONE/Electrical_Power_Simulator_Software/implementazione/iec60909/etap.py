"""Importazione degli studi di cortocircuito IEC di ETAP e confronto dei risultati.

ETAP (2024) salva ogni studio di cortocircuito in un database SQLite
(estensioni .SI2S, .SI1S, .SI4S) che contiene sia i dati di rete usati dal
calcolo (tabelle I*) sia i risultati (SCIECLGSum1, SCIECLGSum2,
ClippingCurrent). Questo modulo legge il database in sola lettura, converte la
rete nel modello di iec60909 e confronta i risultati nodo per nodo.

Uso:
    python -m iec60909.etap studio.SI2S              # tabella di confronto
    python -m iec60909.etap studio.SI2S --json rete.json   # salva la rete convertita

Convenzioni di ETAP ricavate dal confronto (vedi analisi/04_confronto_etap_sc909.md):
- trasformatori: prese (Prim%Tap, Sec%Tap) applicate alle tensioni nominali;
  con IAdjustments.applyXfmrZTol l'impedenza è ridotta della tolleranza (Tol%);
- trasformatori a tre avvolgimenti: impedenze di coppia in % sulla potenza del
  primario, K_T calcolato sulla potenza della coppia (la minore delle due);
- macchine: rapporto X/R di targa (non R_Gf convenzionale), reattanza di
  sequenza inversa X2 di targa; per i motori asincroni R2 = R1;
- macchine con neutro a terra tramite resistenza: Rn = Un/(√3·I_terra).
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .calc import StudyResult, calculate
from .io import network_from_dict


def _open(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _rows(db: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    exists = db.execute(
        "select 1 from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    if not exists:
        return []
    return [dict(r) for r in db.execute(f'select * from "{table}"')]


def _num(value: Any) -> float:
    return float(value) if value not in (None, "") else 0.0


def _winding(conn: str, grounding: Optional[str]) -> str:
    c = conn.strip().upper()
    if c.startswith("D"):
        return "D"
    return "YN" if _grounded(grounding) else "Y"


_FT_KM = 0.3048e-3  # 1 ft in km


def _grounded(grounding: Optional[str]) -> bool:
    return (grounding or "").strip().lower() in ("solid", "resistor", "reactor")


def _neutral_ohm(grounding: Optional[str], amp: Any, kv: float) -> complex:
    """Impedenza di neutro di un trasformatore: Un/(√3·I) resistiva o reattiva."""
    g = (grounding or "").strip().lower()
    if g in ("resistor", "reactor") and _num(amp) > 0:
        z = kv * 1000.0 / (math.sqrt(3.0) * _num(amp))
        return complex(z, 0.0) if g == "resistor" else complex(0.0, z)
    return 0j


def _tap_z_factor(row: dict[str, Any], tap_percent: float) -> float:
    """Variazione dell'impedenza con la presa (Minus5PercTap/Plus5PercTap, lineare)."""
    if tap_percent < 0:
        return 1.0 + _num(row.get("Minus5PercTap")) / 100.0 * (-tap_percent / 5.0)
    if tap_percent > 0:
        return 1.0 + _num(row.get("Plus5PercTap")) / 100.0 * (tap_percent / 5.0)
    return 1.0


def _neutral_fields(prefix: str, grounding: Optional[str], amp: Any, kv: float) -> dict[str, Any]:
    zn = _neutral_ohm(grounding, amp, kv)
    if zn == 0:
        return {}
    return {f"zn_{prefix}_ohm": [zn.real, zn.imag]}


def _earthing(machine: dict[str, Any], kv: float, x0: Any) -> dict[str, Any]:
    """Neutro delle macchine: GNDType 3 resistenza Rn = Un/(√3·I) (verificato);
    GNDType 2 neutro franco a terra (dedotto, non verificato sui dati di ETAP)."""
    if machine.get("GNDType") == 3 and _num(machine.get("GNDAmp")) > 0:
        return {"x0_percent": _num(x0), "zn_ohm": kv * 1000.0 / (math.sqrt(3.0) * _num(machine["GNDAmp"]))}
    if machine.get("GNDType") == 2 and _num(x0) > 0:
        return {"x0_percent": _num(x0)}
    return {}


def network_from_etap(path: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Converte la rete di uno studio ETAP nel formato JSON di iec60909.

    Restituisce il dizionario della rete e la mappa dei nodi uniti dagli
    interruttori di congiuntore (nodo ETAP -> nodo del modello).
    """
    with closing(_open(path)) as db:
        return _convert(db, path)


def _convert(db: sqlite3.Connection, path: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    # congiuntori: ogni nodo unito punta al nodo radice del suo gruppo,
    # qualunque sia l'ordine delle righe (anche per congiuntori in serie)
    parent: dict[str, str] = {}

    def root(bus: str) -> str:
        while parent.get(bus, bus) != bus:
            bus = parent[bus]
        return bus

    for c in _rows(db, "IConnect"):
        if str(c["Type"]).strip().lower().startswith("tie"):
            a, b = root(str(c["From"]).strip()), root(str(c["ToSec"]).strip())
            if a != b:
                parent[b] = a
    alias = {bus: root(bus) for bus in parent}

    def node(bus: Any) -> str:
        b = str(bus).strip()
        return alias.get(b, b)

    study = (_rows(db, "ISCStudyCase") or [{}])[0]
    adjust = (_rows(db, "IAdjustments") or [{}])[0]
    apply_tol = bool(adjust.get("applyXfmrZTol"))
    english = str(study.get("Unit") or "").strip().lower().startswith("eng")
    c_lv = _num(study.get("CFact1"))
    net: dict[str, Any] = {
        "name": f"ETAP {Path(path).name}",
        "f_hz": round(_num(study.get("Freq")) or 50.0),
        # cmax in BT 1,10 → tolleranza +10 %, altrimenti +6 %
        "lv_tolerance_percent": 10 if abs(c_lv - 1.10) < 1e-3 else 6,
        "buses": [
            {"id": str(b["IDBus"]).strip(), "un_kv": _num(b["NomlkV"])}
            for b in _rows(db, "IBus")
            if str(b["IDBus"]).strip() not in alias
        ],
        "external_grids": [],
        "transformers": [],
        "transformers3w": [],
        "lines": [],
        "generators": [],
        "motors": [],
    }
    for u in _rows(db, "IUtility"):
        grid: dict[str, Any] = {
            "id": str(u["ID"]).strip(),
            "bus": node(u["ConnectedBus"]),
            "skq_max_mva": _num(u["MVA3ph"]),
            "rx_max": 1.0 / _num(u["X/R3ph"]),
        }
        if _num(u.get("XZero100MVA")) > 0:
            grid["x0x1"] = _num(u["XZero100MVA"]) / _num(u["XPos100MVA"])
            grid["r0x0"] = _num(u["RZero100MVA"]) / _num(u["XZero100MVA"])
        net["external_grids"].append(grid)

    for t in _rows(db, "IXFMR2"):
        tol = 1.0 - _num(t.get("Tol%")) / 100.0 if apply_tol else 1.0
        tap = _num(t.get("Prim%Tap")) + _num(t.get("Sec%Tap"))
        k = tol * _tap_z_factor(t, tap)
        z, z0 = _num(t["PosZ"]) * k, _num(t["ZeroZ"]) * k
        hv, lv = str(t["Conn"]).split("/")
        net["transformers"].append({
            "id": str(t["ID"]).strip(),
            "hv_bus": node(t["FromBus"]),
            "lv_bus": node(t["ToBus"]),
            "sr_mva": _num(t["MVA"]),
            "ur_hv_kv": _num(t["PrimkV"]) * (1.0 + _num(t.get("Prim%Tap")) / 100.0),
            "ur_lv_kv": _num(t["SeckV"]) * (1.0 + _num(t.get("Sec%Tap")) / 100.0),
            "ukr_percent": z,
            "urr_percent": z / math.sqrt(1.0 + _num(t["PosX/R"]) ** 2),
            "uk0_percent": z0,
            "ur0_percent": z0 / math.sqrt(1.0 + _num(t["ZeroX/R"]) ** 2),
            "vector_group": _winding(hv, t.get("PrimGrdType")) + _winding(lv, t.get("SecGrdType")).lower(),
            **_neutral_fields("hv", t.get("PrimGrdType"), t.get("PrimGrdAmp"), _num(t["PrimkV"])),
            **_neutral_fields("lv", t.get("SecGrdType"), t.get("SecGrdAmp"), _num(t["SeckV"])),
        })

    for t in _rows(db, "IXFMR3"):
        power = {"P": _num(t["PMVA"]), "S": _num(t["SMVA"]), "T": _num(t["TMVA"])}
        tol3 = 1.0 - _num(t.get("Tolerance")) / 100.0 if apply_tol else 1.0
        data: dict[str, Any] = {
            "id": str(t["ID"]).strip(),
            "hv_bus": node(t["Prim"]),
            "mv_bus": node(t["Second"]),
            "lv_bus": node(t["Tri"]),
            "ur_hv_kv": _num(t["PrimkV"]) * (1.0 + _num(t.get("Prim%Tap")) / 100.0),
            "ur_mv_kv": _num(t["SeckV"]) * (1.0 + _num(t.get("Sec%Tap")) / 100.0),
            "ur_lv_kv": _num(t["TerkV"]) * (1.0 + _num(t.get("Ter%Tap")) / 100.0),
            "vector_group": _winding(t["PConn"], t.get("PrimGrdType"))
            + _winding(t["SConn"], t.get("SecGrdType")).lower()
            + _winding(t["TConn"], t.get("TerGrdType")).lower(),
            **_neutral_fields("hv", t.get("PrimGrdType"), t.get("PrimGrdAmp"), _num(t["PrimkV"])),
            **_neutral_fields("mv", t.get("SecGrdType"), t.get("SecGrdAmp"), _num(t["SeckV"])),
            **_neutral_fields("lv", t.get("TerGrdType"), t.get("TerGrdAmp"), _num(t["TerkV"])),
        }
        for ours, etap, a, b in (("hv_mv", "PS", "P", "S"), ("hv_lv", "TP", "P", "T"), ("mv_lv", "ST", "S", "T")):
            sr = min(power[a], power[b])
            data[f"sr_{ours}_mva"] = sr
            for prefix, seq in (("r", "Pos"), ("0", "Zero")):
                z = _num(t[f"{etap}{seq}Z"]) * sr / power["P"] * tol3
                data[f"uk{prefix}_{ours}_percent"] = z
                data[f"ur{prefix}_{ours}_percent"] = z / math.sqrt(1.0 + _num(t[f"{etap}{seq}X/R"]) ** 2)
        net["transformers3w"].append(data)

    # unità metriche: Length in m, impedenze in Ω/km;
    # unità inglesi: Length in ft, impedenze in Ω/1000 ft
    length_km = _FT_KM if english else 1e-3
    per_km = 1.0 / (1000.0 * _FT_KM) if english else 1.0
    for c in _rows(db, "Icable"):
        line: dict[str, Any] = {
            "id": str(c["ID"]).strip(),
            "from_bus": node(c["FromBus"]),
            "to_bus": node(c["ToBus"]),
            "length_km": _num(c["Length"]) * length_km,
            "r1_ohm_per_km": _num(c["RPos"]) * per_km,
            "x1_ohm_per_km": _num(c["XPos"]) * per_km,
            "parallel": int(_num(c.get("No/Ph")) or 1),
        }
        if _num(c.get("XZero")) > 0:
            line["r0_ohm_per_km"] = _num(c["RZero"]) * per_km
            line["x0_ohm_per_km"] = _num(c["XZero"]) * per_km
        net["lines"].append(line)

    for g in _rows(db, "ISynGen"):
        xd = _num(g["Xdpp"]) / 100.0 * _num(g["KV"]) ** 2 / _num(g["MVA"])
        net["generators"].append({
            "id": str(g["ID"]).strip(),
            "bus": node(g["ConnectedBus"]),
            "sr_mva": _num(g["MVA"]),
            "ur_kv": _num(g["KV"]),
            "xd2_percent": _num(g["Xdpp"]),
            "cos_phi": _num(g["PF"]) / 100.0,
            "rg_ohm": xd / _num(g["Xpp/R"]),
            "x2_percent": _num(g["X2"]) or None,
            "xd_sat_percent": _num(g.get("Xdsat")) or None,
            **_earthing(g, _num(g["KV"]), g.get("Xzero")),
        })
    # IEC 60909: i motori sincroni si trattano come generatori sincroni
    for m in _rows(db, "ISynMotor"):
        # kVA del motore sincrono riferiti alla singola macchina
        sr = _num(m["kVA"]) / 1000.0 * max(1, int(_num(m.get("Quantity")) or 1))
        xd = _num(m["Xdpp"]) / 100.0 * _num(m["kV"]) ** 2 / sr
        net["generators"].append({
            "id": str(m["ID"]).strip(),
            "bus": node(m["ConnectedBus"]),
            "sr_mva": sr,
            "ur_kv": _num(m["kV"]),
            "xd2_percent": _num(m["Xdpp"]),
            "cos_phi": _num(m["PF100"]) / 100.0,
            "rg_ohm": xd / _num(m["Xpp/R"]),
            "x2_percent": _num(m["X2"]) or None,
            **_earthing(m, _num(m["kV"]), m.get("X0")),
        })
    for m in _rows(db, "IIndMachine"):
        if m.get("Status") not in (None, 1):
            continue  # motore non in servizio
        kva = _num(m["kVA"])  # potenza apparente nominale, già comprensiva della quantità
        qty = max(1, int(_num(m.get("Quantity")) or 1))
        # potenza attiva di targa da kVA·η·cosφ (indipendente dall'unità HP/kW,
        # il cui indicatore FlagHP/kW cambia significato con il sistema di unità)
        p_kw = kva * _num(m.get("EFF100")) / 100.0 * _num(m.get("PF100")) / 100.0
        if not 0.0 < p_kw <= kva:
            p_kw = kva
        motor: dict[str, Any] = {
            "id": str(m["ID"]).strip(),
            "bus": node(m["ConnectedBus"]),
            # Sr = Pr/(η·cosφ) = kVA: η·cosφ = Pr/kVA, con cosφ = 1
            "pr_mw": p_kw / 1000.0 / qty,
            "ur_kv": _num(m["KV"]),
            "efficiency": p_kw / kva,
            "cos_phi": 1.0,
            "ilr_ir": _num(m["LRC"]) / 100.0,
            "rx": 1.0 / _num(m["Xpp/R"]),
            "count": qty,
        }
        if _num(m.get("Poles")) >= 2:
            motor["pole_pairs"] = int(_num(m["Poles"]) // 2)
        if _num(m.get("X2")) > 0:
            motor["x2_percent"] = _num(m["X2"])
            motor["rx2"] = _num(m["R"]) / _num(m["X2"])
        net["motors"].append(motor)
    # carichi concentrati: la sola quota motori (MTR%) diventa un motore equivalente
    # con Sr = kVA·MTR%, I_LR/Ir = 100/|Z"| (Z" in %) e R/X = 1/(Xpp/R)
    for lump in _rows(db, "ILump"):
        sr_kva = _num(lump["kVA"]) * _num(lump.get("MTR%")) / 100.0
        if sr_kva <= 0.0:
            continue
        net["motors"].append({
            "id": f"{str(lump['ID']).strip()}_motori",
            "bus": node(lump["ConnectedBus"]),
            "pr_mw": sr_kva / 1000.0,
            "ur_kv": _num(lump["KV"]),
            "efficiency": 1.0,
            "cos_phi": 1.0,
            "ilr_ir": 100.0 / math.hypot(_num(lump["Xpp"]), _num(lump["R"])),
            "rx": 1.0 / _num(lump["Xpp/R"]),
        })
    return net, alias


@dataclass
class Comparison:
    bus: str
    quantity: str
    etap: float
    ours: float

    @property
    def diff_percent(self) -> Optional[float]:
        if self.etap == 0.0:
            return None if abs(self.ours) > 1e-9 else 0.0
        return (self.ours / self.etap - 1.0) * 100.0


def compare(path: str | Path, kappa_method: str = "C") -> tuple[StudyResult, list[Comparison]]:
    """Calcola la rete dello studio ETAP e confronta i risultati nodo per nodo."""
    data, alias = network_from_etap(path)
    result = calculate(network_from_dict(data), "max", kappa_method)
    with closing(_open(path)) as db:
        sum2 = {str(r["FaultedBus"]).strip(): r for r in _rows(db, "SCIECLGSum2")}
        clip = {str(r["FaultedBus"]).strip(): r for r in _rows(db, "ClippingCurrent")}
        sum1 = _rows(db, "SCIECLGSum1")
        duty = _rows(db, "SCIEC3phSum")
    out: list[Comparison] = []
    for e in sum1:
        bus = str(e["FaultedBus"]).strip()
        r = result.bus(alias.get(bus, bus))
        z = sum2.get(bus, {})
        pairs = [
            ('I"k3', e["IPPk3ph"], r.ikss3_ka),
            ("ip3", e["ip3ph"], r.ip3_ka),
            ('I"k2', e["IPPkLL"], r.ikss2_ka),
            ('I"k1', e["IPPkLG"], r.ikss1_ka),
            ('I"k2E fase', e["IPPkLLG"], max(r.ikss2e_l2_ka, r.ikss2e_l3_ka)),
            ('I"kE2E (3I0)', clip.get(bus, {}).get("SymmLLG_3I0"), r.ikss2e_earth_ka),
            ("|Z1|", z.get("ZPosOhm"), abs(r.z1_ohm)),
            ("|Z0|", z.get("ZZeroOhm"), abs(r.z0_ohm) if r.z0_ohm is not None else 0.0),
        ]
        out += [Comparison(bus, q, _num(a), float(b)) for q, a, b in pairs]
    out += _compare_duty(duty, alias, data, result, kappa_method)
    return result, out


def _compare_duty(
    duty: list[dict[str, Any]],
    alias: dict[str, str],
    data: dict[str, Any],
    result: StudyResult,
    kappa_method: str,
) -> list[Comparison]:
    """Studi di "duty" (.SI1S): Ik per nodo e Ib dei dispositivi che vedono l'intera corrente.

    Ib è confrontata solo per i dispositivi la cui corrente iniziale coincide con
    I"k del nodo; per gli altri ETAP sottrae il contributo del ramo protetto.
    """
    out: list[Comparison] = []
    by_tmin: dict[float, StudyResult] = {}
    for e in duty:
        bus = str(e["FaultedBus"]).strip()
        r = result.bus(alias.get(bus, bus))
        tmin = _num(e.get("DeviceTD"))
        if tmin <= 0.0:
            if _num(e.get("Ik")) > 0:
                out.append(Comparison(bus, 'I"k3 (duty)', _num(e["IPPk"]), r.ikss3_ka))
                out.append(Comparison(bus, "Ik", _num(e["Ik"]), r.ik_ka or 0.0))
            continue
        if abs(_num(e["IPPk"]) - r.ikss3_ka) > 1e-3 * max(r.ikss3_ka, 1e-9):
            continue
        if tmin not in by_tmin:
            by_tmin[tmin] = calculate(network_from_dict(data), "max", kappa_method, tmin_s=tmin)
        rb = by_tmin[tmin].bus(alias.get(bus, bus))
        out.append(Comparison(bus, f"Ib {e['DeviceID'].strip()} (tmin {tmin:g} s)", _num(e["Ibsymm"]), rb.ib_ka))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="iec60909.etap", description="Confronto con uno studio di cortocircuito IEC di ETAP"
    )
    parser.add_argument("studio", help="file di uscita ETAP (SQLite: .SI2S, .SI1S)")
    parser.add_argument("--kappa", choices=("B", "C"), default="C")
    parser.add_argument("--json", metavar="FILE", help="salva la rete convertita in JSON")
    args = parser.parse_args(argv)
    if args.json:
        data, _ = network_from_etap(args.studio)
        Path(args.json).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _, rows = compare(args.studio, args.kappa)
    print("| Nodo | Grandezza | ETAP | iec60909 | Scarto |")
    print("|---|---|---|---|---|")
    for c in rows:
        d = c.diff_percent
        diff = "—" if d is None else f"{d:+.3f} %"
        print(f"| {c.bus} | {c.quantity} | {c.etap:.4f} | {c.ours:.4f} | {diff} |")
    worst = max((abs(c.diff_percent) for c in rows if c.diff_percent is not None), default=0.0)
    print(f"\nScarto massimo: {worst:.3f} %", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
