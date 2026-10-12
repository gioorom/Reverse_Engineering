"""Genera iec60909/_tabelle_iec60364.py da strumenti/dati/iec60364_5_52.json.

Il JSON raccoglie le tabelle dell'allegato B della IEC 60364-5-52:2009 con, per
ogni valore, le fonti indipendenti che lo riportano e il livello di confidenza
(vedi analisi/14_dimensionamento_cavi.md). Uso:

    python strumenti/genera_tabelle_cavi.py
"""

import json
import pprint
from pathlib import Path

QUI = Path(__file__).resolve().parent
d = json.loads((QUI / "dati" / "iec60364_5_52.json").read_text(encoding="utf-8"))
MAT = {"copper": "cu", "aluminium": "al"}

ampacity, confidence = {}, {}
for tab, (ins, loaded) in {"B.52.2": ("pvc", 2), "B.52.3": ("xlpe", 2), "B.52.4": ("pvc", 3),
                           "B.52.5": ("xlpe", 3)}.items():
    t = d["ampacity"][tab]
    for mat in ("copper", "aluminium"):
        for meth, vals in t[mat].items():
            key = (MAT[mat], ins, loaded, meth)
            ampacity[key] = {float(s): float(v) for s, v in vals.items()}
            for s, c in t["_confidence"][mat][meth].items():
                if c != "cross_checked":
                    confidence[key + (float(s),)] = f"{c} ({tab})"
# E, F, G: colonne 2-8 delle tabelle B.52.10-13
COLONNE = {"E_2": (2, "E"), "E_3": (3, "E"), "F_2": (2, "F"), "F_3_trefoil": (3, "F:trefoil"),
           "F_3_flat": (3, "F:flat"), "G_3_horizontal": (3, "G:horizontal"), "G_3_vertical": (3, "G:vertical")}
for tab, (ins, mat) in {"B.52.10": ("pvc", "copper"), "B.52.11": ("pvc", "aluminium"),
                        "B.52.12": ("xlpe", "copper"), "B.52.13": ("xlpe", "aluminium")}.items():
    t = d["ampacity"][tab]
    for col, vals in t[mat].items():
        loaded, meth = COLONNE[col]
        key = (MAT[mat], ins, loaded, meth)
        ampacity[key] = {float(s): float(v) for s, v in vals.items()}
        for s, c in t["_confidence"][mat][col].items():
            if c != "cross_checked":
                confidence[key + (float(s),)] = f"{c} ({tab})"

tc = d["temperature_correction"]
k_air = {ins: {float(k): v for k, v in tc["B.52.14"][ins].items()} for ins in ("pvc", "xlpe")}
k_ground = {ins: {float(k): v for k, v in tc["B.52.15"][ins].items()} for ins in ("pvc", "xlpe")}
soil = d["B.52.16_soil_resistivity"]
k_soil = {"D1": dict(zip(soil["rho_k_m_per_w"], soil["in_buried_ducts"])),
          "D2": dict(zip(soil["rho_k_m_per_w"], soil["direct_buried"]))}
g = d["B.52.17_grouping_air"]
k_group_air = {it["arrangement"]: {n: f for n, f in zip(g["counts"], it["factors"]) if f is not None}
               for it in g["items"].values()}
g = d["B.52.18_grouping_direct_in_ground"]
k_group_d2 = {sp: dict(zip(g["counts"], f)) for sp, f in g["factors"].items()}
g = d["B.52.19_grouping_in_ducts"]
k_group_d1 = {(cores, sp): dict(zip(g["counts"], f))
              for cores, part in (("multi", "multicore_one_cable_per_duct"), ("single", "single_core_one_cable_per_duct"))
              for sp, f in g[part].items()}
r20 = {MAT[m]: {float(s): v for s, v in d["IEC_60228_class2_R20"][m].items()} for m in ("copper", "aluminium")}

out = ['"""Tabelle generate da strumenti/genera_tabelle_cavi.py: non modificare a mano.',
       "",
       "IEC 60364-5-52:2009 allegato B (portate B.52.2-B.52.5 e B.52.10-B.52.13, fattori",
       "B.52.14-B.52.19) e IEC 60228 classe 2 (resistenze a 20 °C). Fonti e confidenza di ogni",
       'valore in strumenti/dati/iec60364_5_52.json."""', ""]
for name, obj in (("AMPACITY", ampacity), ("CONFIDENCE", confidence), ("K_AIR", k_air), ("K_GROUND", k_ground),
                  ("K_SOIL", k_soil), ("K_GROUP_AIR", k_group_air), ("K_GROUP_D2", k_group_d2),
                  ("K_GROUP_D1", k_group_d1), ("R20", r20)):
    out.append(f"{name} = {pprint.pformat(obj, width=110, sort_dicts=True)}")
    out.append("")
(QUI.parent / "iec60909" / "_tabelle_iec60364.py").write_text("\n".join(out), encoding="utf-8")
print(len(ampacity), "tabelle di portata,", len(confidence), "valori non verificati su due fonti")
