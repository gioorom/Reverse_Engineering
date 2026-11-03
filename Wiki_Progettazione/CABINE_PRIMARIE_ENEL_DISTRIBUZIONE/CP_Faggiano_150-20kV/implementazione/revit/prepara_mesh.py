"""CP Faggiano - prepara la geometria per Revit (DirectShape) dall'OBJ esportato da SolidCraft.

- raggruppa i corpi per apparecchio (occorrenza) -> un elemento Revit per apparecchio
- assegna categoria Revit, classe IFC, stallo, materiale
- semplifica le mesh pesanti (isolatori) con pyfqmr
- scrive lotti di testo semplice (nessuna dipendenza lato Revit)
Frame: sito, mm (X lungo lo stallo verso il TR, Y lungo le sbarre, Z in alto).
Uso: python prepara_mesh.py <cartella con stallo.obj, stallo.mtl, complist.json>
"""
import sys, os, re, json, collections
import numpy as np, pyfqmr
sys.stdout.reconfigure(encoding="utf-8")

D = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\pietr\Desktop\sc_mcp\revit"
OUT = os.path.join(D, "lotti"); os.makedirs(OUT, exist_ok=True)
TRI_SOGLIA, RAPPORTO, TRI_MIN = 600, 0.15, 300      # semplificazione mesh
Y_STALLO2 = 6200.0                                     # oltre: stallo 2
MAX_TRI_LOTTO = 60000

# ---- componenti -> (categoria Revit, IfcExportAs, IfcPredefinedType, descrizione) ----
MAPPA = [
    (r"^TR_MATELEC",            "OST_ElectricalEquipment", "IfcTransformer", "VOLTAGE", "Trasformatore AT/MT Matelec 25 MVA 150/20 kV"),
    (r"^INT_GL313",             "OST_ElectricalEquipment", "IfcSwitchingDevice", "CIRCUITBREAKER", "Interruttore AT GE GL313 (polo)"),
    (r"^SEZ_S3CT_TERRA",        "OST_ElectricalEquipment", "IfcSwitchingDevice", "DISCONNECTOR", "Sezionatore AT S3CT con lame di terra"),
    (r"^SEZ_S3C",               "OST_ElectricalEquipment", "IfcSwitchingDevice", "DISCONNECTOR", "Sezionatore AT S3C"),
    (r"^TA_DY34",               "OST_ElectricalEquipment", "IfcTransformer", "CURRENT", "Trasformatore di corrente AT DY34"),
    (r"^TV_DY46",               "OST_ElectricalEquipment", "IfcTransformer", "VOLTAGE", "Trasformatore di tensione AT DY46"),
    (r"^SCAR_",                 "OST_ElectricalEquipment", "IfcProtectiveDevice", "VARISTOR", "Scaricatore di sovratensione AT"),
    (r"^ARM_",                  "OST_ElectricalEquipment", "IfcElectricDistributionBoard", "SWITCHBOARD", "Armadio di comando"),
    (r"^ISO_",                  "OST_ElectricalFixtures",  "IfcDiscreteAccessory", "INSULATOR", "Isolatore portante"),
    (r"^MORS_",                 "OST_ElectricalFixtures",  "IfcFastener", "USERDEFINED", "Morsetto"),
    (r"^TERM_CAVO",             "OST_ElectricalFixtures",  "IfcJunctionBox", "USERDEFINED", "Terminale cavo MT"),
    (r"^(SBARRA_|SBARRE_|COLL_MT|COND_|CAVI_MT)", "OST_GenericModel", "IfcCableSegment", "BUSBARSEGMENT", "Conduttore / sbarra"),
    (r"^SOST_",                 "OST_StructuralFraming",   "IfcMember", "POST", "Sostegno in acciaio zincato"),
    (r"^(RINVIO_|TUBI_)",       "OST_GenericModel",        "IfcBuildingElementProxy", "USERDEFINED", "Rinvio / tubazione cavi"),
    (r"^MURO_",                 "OST_Walls",               "IfcWall", "SOLIDWALL", "Muro tagliafiamme REI 120"),
    (r"^(FOND|FONDAZIONE)",     "OST_StructuralFoundation", "IfcFooting", "PAD_FOOTING", "Fondazione in c.a."),
]
def mappa(comp):
    for rx, cat, ifc, pt, des in MAPPA:
        if re.search(rx, comp):
            return cat, ifc, pt, des
    return "OST_GenericModel", "IfcBuildingElementProxy", "USERDEFINED", comp

# ---- materiale dal nome del corpo ----
MAT = [
    (r"(?i)Cu|rame|codolo|bandiera|contatt|lama|treccia|piatto", "CPF_Rame Cu-ETP", (184, 115, 51)),
    (r"(?i)isolat|composit|porcell|cappello", "CPF_Isolatore porcellana/composito", (150, 150, 150)),
    (r"(?i)sbarra|conduttor|cavo|tubo_Al|attacchi|morsett|Al", "CPF_Alluminio", (200, 200, 205)),
    (r"(?i)muro|plinto|fond|basament", "CPF_Calcestruzzo C30/37", (181, 177, 168)),
    (r"(?i)cassa|radiator|conservat|coperchio|carrello|armadio|cassetta|comando", "CPF_Acciaio verniciato RAL 7033", (110, 115, 110)),
]
def materiale(body):
    for rx, nome, rgb in MAT:
        if re.search(rx, body):
            return nome, rgb
    return "CPF_Acciaio zincato S275", (165, 168, 170)

# ---- proprietario dei corpi senza percorso (prima occorrenza) ----
cl = json.load(open(os.path.join(D, "complist.json"), encoding="utf-8"))
if isinstance(cl, str):
    cl = json.JSONDecoder().raw_decode(cl.strip())[0]
owner = {}
for c in cl["components"]:
    for b in c["bodies"]:
        owner.setdefault(b, c["name"])

# ---- lettura OBJ ----
V = []; objs = []; cur = None
with open(os.path.join(D, "stallo.obj"), encoding="utf-8", errors="replace") as f:
    for l in f:
        if l.startswith("v "):
            V.append(l.split()[1:4])
        elif l.startswith("o "):
            cur = {"name": l[2:].strip(), "f": []}; objs.append(cur)
        elif l.startswith("f "):
            cur["f"].append([int(p.split("/")[0]) - 1 for p in l.split()[1:4]])
V = np.array(V, dtype=np.float64)
print("vertici", len(V), "oggetti", len(objs))

RX_PATH = re.compile(r"^(.*) \((base_tr2_esterno:1/.*)\)$")
elementi = collections.OrderedDict(); visti = set(); tri_in = tri_out = 0
for o in objs:
    if not o["f"] or re.match(r"^Body\d+$", o["name"]):   # Body1/Body2: copia senza nome del muro
        continue
    F = np.array(o["f"], dtype=np.int64)
    idx, inv = np.unique(F.ravel(), return_inverse=True)
    v = V[idx]; t = inv.reshape(-1, 3)
    firma = (len(t), tuple(np.round(v.min(0))), tuple(np.round(v.max(0))))
    if firma in visti:                  # corpo duplicato (stessa geometria)
        continue
    visti.add(firma)
    m = RX_PATH.match(o["name"])
    if m:
        body, path = m.group(1), m.group(2)
        segs = [s for s in path.split("/") if not s.startswith(("base_tr2_esterno", "Seazione AT STEP", "CP_FAGGIANO"))]
        occ = segs[1] if len(segs) > 1 else segs[0]
        comp = occ.split(":")[0]; key = "/".join(segs[:2])
    else:
        body = o["name"]; comp = owner.get(body, "STALLO_AT"); occ = comp + ":1"; key = "@" + comp
    tri_in += len(t)
    if len(t) > TRI_SOGLIA:             # semplificazione
        s = pyfqmr.Simplify(); s.setMesh(v.astype(np.float64), t.astype(np.int32))
        s.simplify_mesh(target_count=max(TRI_MIN, int(len(t) * RAPPORTO)), aggressiveness=5, preserve_border=True, verbose=0)
        v, t, _ = s.getMesh()
    tri_out += len(t)
    e = elementi.setdefault(key, {"key": key, "comp": comp, "occ": occ, "mesh": [], "pts": []})
    e["mesh"].append((body, v, t))
    e["pts"].append(v.mean(0))

# ---- metadati per elemento ----
mats = collections.OrderedDict()
righe = []
for e in elementi.values():
    c = np.mean(e["pts"], axis=0)
    stallo = 2 if c[1] > Y_STALLO2 else 1
    zona = "Linea" if c[0] < -1500 else ("Trafo" if c[0] > 1500 else "Sbarre AT")
    nome_stallo = f"Stallo {zona} {stallo}" if zona != "Sbarre AT" else "Sistema sbarre AT"
    if e["comp"].startswith(("MURO_", "FONDAZIONE_MURO")):
        nome_stallo = "TR1-TR2"
    cat, ifc, pt, des = mappa(e["comp"])
    e.update(cat=cat, ifc=ifc, pt=pt, des=des, stallo=nome_stallo, nome=f"{e['comp']} ({e['occ']}) - {nome_stallo}")
    for body, v, t in e["mesh"]:
        mats.setdefault(*materiale(body))

# ---- scrittura lotti ----
mid = {n: i for i, n in enumerate(mats)}
def fmt(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")
lotto, tri_lotto, n_lotto, files = [], 0, 0, []
def scrivi():
    global lotto, tri_lotto, n_lotto
    if not lotto:
        return
    p = os.path.join(OUT, f"lotto_{n_lotto:03d}.txt")
    with open(p, "w", encoding="utf-8") as f:
        for i, (n, rgb) in enumerate(mats.items()):
            f.write(f"MAT|{i}|{n}|{rgb[0]}|{rgb[1]}|{rgb[2]}\n")
        for e in lotto:
            f.write("E|" + "|".join([e["key"], e["nome"], e["cat"], e["ifc"], e["pt"], e["stallo"], e["comp"], e["des"]]) + "\n")
            for body, v, t in e["mesh"]:
                f.write(f"M|{mid[materiale(body)[0]]}|{body}\n")
                f.write("V|" + " ".join(fmt(x) for x in np.asarray(v).ravel()) + "\n")
                f.write("T|" + " ".join(str(int(x)) for x in np.asarray(t).ravel()) + "\n")
    files.append(p); lotto, tri_lotto, n_lotto = [], 0, n_lotto + 1
for e in elementi.values():
    nt = sum(len(t) for _, _, t in e["mesh"])
    if lotto and tri_lotto + nt > MAX_TRI_LOTTO:
        scrivi()
    lotto.append(e); tri_lotto += nt
scrivi()
riep = collections.Counter(e["cat"] for e in elementi.values())
json.dump({"elementi": len(elementi), "triangoli_in": tri_in, "triangoli_out": tri_out, "lotti": files,
           "categorie": riep, "materiali": list(mats)}, open(os.path.join(OUT, "riepilogo.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("elementi", len(elementi), "triangoli", tri_in, "->", tri_out, "lotti", len(files))
print(dict(riep)); print(list(mats))
