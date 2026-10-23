"""CP Faggiano 150/20 kV - sezione AT in SolidCraft: modello finale.

Parte dallo STEP della sezione AT gia' corretto (castelletti MT di TR1 e TR2 sul lato esterno, vedi
tr2_specchio.py) e:
  1) porta gli armadi del TR1 (comando motore CSC, cassetta ausiliari) sulla sinistra del trafo
     (spalle ai TR guardando la linea: sinistra = lato -Y); il TR2 li ha gia' a sinistra;
  2) ricrea il muro tagliafiamme REI 120 parametrico, centrato fra i plinti TR1/TR2;
  3) assegna materiale e attributi BIM; salva .solidcraft ed esporta STEP; riapre e verifica.
Frame: radice = frame sito (X lungo lo stallo verso il TR, Y lungo le sbarre, Z in alto), mm.
Uso: python build_finale.py <step_ingresso> <cartella_modelli>
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from scl import SC

# ---- parametri muro (mm) ----
PAR = {
    "MT_L":  (7400, "Muro tagliafiamme: lunghezza lungo X (trafo + >=1 m oltre radiatori/passanti)"),
    "MT_S":  (300,  "Spessore muro c.a. REI 120 (EN 1992-1-2 tab. 5.4: >=160 mm, adottati 300)"),
    "MT_H":  (5000, "Altezza fuori terra >= sommita passante AT/conservatore (+4740) - CEI EN 61936-1 8.7.2"),
    "MT_X0": (20000, "Inizio muro lungo X sito"),
    "MT_Y0": (6050, "Faccia muro lato TR1: muro centrato fra i plinti TR1/TR2 (bordi a 4000 e 8400, asse 6200)"),
    "MT_FB": (1000, "Larghezza trave di fondazione"),
    "MT_FH": (800,  "Altezza trave di fondazione sotto quota 0"),
}
ARMADI = ["comando_motore_CSC", "cassetta_ausiliari"]
TR1_COMP = "TR_MATELEC_25MVA"
step_in, out_dir = sys.argv[1], sys.argv[2]
DES = os.path.join(out_dir, "CP_Faggiano_Sezione_AT.solidcraft")
STEP = os.path.join(out_dir, "CP_Faggiano_Sezione_AT.step")

s = SC()
bb = lambda b: s.tool("measure", {"body": b})["bodies"][0]["bbox"]
s.tool("open", {"path": step_in})
comps = {c["name"]: c for c in s.ex("component.list")["components"]}

# 1) armadi TR1 a sinistra (-Y): specchio rispetto all'asse del trafo, verificato in coordinate mondo
s.ex("component.activate", component=comps[TR1_COMP]["id"])
for b in ARMADI:
    o = bb(b)
    if o["max"][1] < 0:
        print(b, "gia' a sinistra"); continue
    done = False
    for n in ([0, 1, 0], [0, 0, 1], [0, 0, -1]):
        new = s.ex("solid.mirror", bodies=[b], plane={"origin": [0, 0, 0], "normal": n})["created_bodies"][0]
        a = bb(new)
        if abs(a["min"][1] + o["max"][1]) < 1 and abs(a["max"][1] + o["min"][1]) < 1 and abs(a["min"][2] - o["min"][2]) < 1:
            s.ex("solid.remove", bodies=[b]); s.ex("body.rename", body=new, name=b); done = True
            print(b, "Y", round(o["min"][1]), round(o["max"][1]), "->", round(a["min"][1]), round(a["max"][1]))
            break
        s.ex("solid.remove", bodies=[new])
    assert done, b

# 2) muro tagliafiamme parametrico (radice)
s.ex("component.activate", component="root")
for c in ("MURO_TAGLIAFIAMME_REI120", "FONDAZIONE_MURO_TAGLIAFIAMME"):
    if c in comps:
        s.ex("component.delete", component=comps[c]["id"])
for k, (v, com) in PAR.items():
    s.tool("set_parameter", {"name": k, "value": f"{v} mm", "comment": com})
s.tool("batch", {"verbose": False, "commands": [
    {"command": "solid.box", "params": {"corner": ["MT_X0", "MT_Y0", 0], "length": "MT_L", "width": "MT_S", "height": "MT_H",
                                        "operation": "new", "body_name": "MURO_TAGLIAFIAMME_REI120", "name": "Muro tagliafiamme"}},
    {"command": "solid.box", "params": {"corner": ["MT_X0", "MT_Y0 + MT_S / 2 - MT_FB / 2", "-MT_FH"], "length": "MT_L", "width": "MT_FB",
                                        "height": "MT_FH", "operation": "new", "body_name": "FONDAZIONE_MURO_TAGLIAFIAMME", "name": "Fondazione muro"}},
    {"command": "material.create", "params": {"name": "Calcestruzzo C30/37 armato", "density_g_cm3": 2.5, "color": "#A8A49C"}},
    {"command": "material.assign", "params": {"bodies": ["MURO_TAGLIAFIAMME_REI120", "FONDAZIONE_MURO_TAGLIAFIAMME"], "material": "Calcestruzzo C30/37 armato"}},
    {"command": "appearance.assign", "params": {"bodies": ["MURO_TAGLIAFIAMME_REI120"], "color": "#B5B1A8"}},
    {"command": "appearance.assign", "params": {"bodies": ["FONDAZIONE_MURO_TAGLIAFIAMME"], "color": "#8E8A82"}},
    {"command": "component.from_bodies", "params": {"bodies": ["MURO_TAGLIAFIAMME_REI120", "FONDAZIONE_MURO_TAGLIAFIAMME"]}},
]})

# 3) attributi BIM
s.ex("component.metadata.set", component="MURO_TAGLIAFIAMME_REI120", part_number="CPF-MT-01",
     description="Muro tagliafiamme TR1/TR2 in c.a. REI 120, 7400x300x5000 mm, centrato fra i plinti",
     properties={"IfcClass": "IfcWall", "PredefinedType": "SOLIDWALL", "FireRating": "REI 120",
                 "Materiale": "Calcestruzzo C30/37 XC4, acciaio B450C, copriferro 35 mm",
                 "Norma": "CEI EN 61936-1 par. 8.7.2; EN 1992-1-2; D.M. 15/07/2014", "Stallo": "TR1-TR2"})
s.ex("component.metadata.set", component="FONDAZIONE_MURO_TAGLIAFIAMME", part_number="CPF-MT-02",
     description="Trave di fondazione muro tagliafiamme 7400x1000x800 mm",
     properties={"IfcClass": "IfcFooting", "PredefinedType": "STRIP_FOOTING", "Materiale": "Calcestruzzo C25/30 XC2, B450C", "Stallo": "TR1-TR2"})
for name in [n for n in comps if n.endswith("_TR2")]:
    s.ex("component.metadata.set", component=name, description=f"{name[:-4]} dello stallo TR2 (TR Verde), lato MT verso l'esterno",
         properties={"Stallo": "TR2", "Fonte": f"Specchio di {name[:-4]} (STALLO_TRAFO)"})
s.ex("component.metadata.set", component=TR1_COMP, properties={"Stallo": "TR1", "Note": "armadi CSC e ausiliari a sinistra (lato -Y)"})

# 4) salva, esporta, riapre e verifica
s.tool("save", {"path": DES})
s.tool("export", {"path": STEP})
s.tool("open", {"path": DES})
CHECK = ["comando_motore_CSC", "cassetta_ausiliari", "comando_motore_CSC (2) (2)", "MURO_TAGLIAFIAMME_REI120", "cassa", "cassa (2) (2)"]
for b in CHECK:
    try:
        x = bb(b); print(f"{b:32s} X {x['min'][0]:.0f}..{x['max'][0]:.0f}  Y {x['min'][1]:.0f}..{x['max'][1]:.0f}  Z {x['min'][2]:.0f}..{x['max'][2]:.0f}")
    except Exception as e:
        print(b, "?", str(e)[:120])
for v, cam in (("iso", {"target": [23700, 6200, 2000], "yaw": 2.4, "pitch": 0.45, "distance": 30000}),
               ("top", {"target": [23700, 6200, 1500], "yaw": 0.0, "pitch": 1.5, "distance": 30000})):
    s.tool("screenshot", {"source": "model", "camera": cam, "path": rf"C:\Users\pietr\Desktop\sc_mcp\fin_{v}.png", "width": 1400, "height": 900})
s.close()
print("salvati:", DES, STEP)
