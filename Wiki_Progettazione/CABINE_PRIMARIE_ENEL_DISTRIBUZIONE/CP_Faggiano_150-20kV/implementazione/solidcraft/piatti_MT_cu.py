"""CP Faggiano - collegamento MT fra passanti MT del TR e castelletto con piatto di rame 100x10 (Cu-ETP).

Per ogni fase (passanti MT X 23515/23885/24255, isolatori portanti del castelletto X 23330/23700/24070
a Y -4367, sbarre del castelletto a Y -5570/-5200/-4830, Z 4835..4935):
  B1 risalita verticale imbullonata alla bandiera del passante (di costa, 10 x 100)
  B2 tratto orizzontale in piano (di piatto) dal passante all'isolatore portante, quota ZP
  B3 tratto orizzontale dall'isolatore verso la sbarra della fase, quota ZP
  B4 risalita verticale imbullonata alla faccia della sbarra (sovrapposizione 100 mm)
TR2 = specchio di TR1 rispetto al piano Y = Y_SPECCHIO. Frame radice = sito (mm).
Uso: python piatti_MT_cu.py <design.solidcraft> <step_out>
"""
import sys, math
sys.stdout.reconfigure(encoding="utf-8")
from scl import SC

# ---- parametri (mm) ----
W, T = 100.0, 10.0                    # piatto Cu 100 x 10
X_PASS = [23515.0, 23885.0, 24255.0]  # assi passanti MT L1, L2, L3
FLAG_X = 6.0                          # semispessore bandiera (12 mm): faccia lato +X
Y_PASS = -2200.0                      # asse passanti MT
Z_FLAG = 3560.0                       # base bandiera
X_ISO = [23330.0, 23700.0, 24070.0]   # isolatori portanti C8-125 sul castelletto
Y_ISO = -4367.0
ZP = 4435.0                           # sommita' isolatori portanti = piano di posa dei piatti
Y_BUS_FACE = [-5565.0, -5195.0, -4825.0]  # faccia lato TR delle sbarre del castelletto
Z_BUS_TOP = 4935.0
Y_SPECCHIO = 6200.0
args = sys.argv[1:]

s = SC()
if args:
    s.tool("open", {"path": args[0]})
comps = {c["name"]: c for c in s.ex("component.list")["components"]}

def box(name, x0, x1, y0, y1, z0, z1):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    s.ex("solid.box", corner=[x0, y0, z0], length=x1 - x0, width=y1 - y0, height=z1 - z0, operation="new", body_name=name)

def bar_plan(name, p, q, z0):
    """piatto orizzontale di piatto da p a q (centri, XY), spessore T sopra z0"""
    L = math.dist(p, q); th = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
    s.ex("solid.box", center=[0, 0, z0 + T / 2], length=L, width=W, height=T, operation="new", body_name=name)
    s.ex("solid.move", bodies=[name], axis=[0, 0, 1], angle=f"{th} deg")
    s.ex("solid.move", bodies=[name], translate=[(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, 0])

made = {}
s.ex("component.activate", component="root")
for tr, my in (("TR1", lambda y: y), ("TR2", lambda y: 2 * Y_SPECCHIO - y)):
    cname = f"COLL_MT_CU100x10_{tr}"
    s.ex("component.create", name=cname, parent="root", activate=True)
    names = []
    for i, f in enumerate(("L1", "L2", "L3")):
        xb, xi, yb = X_PASS[i], X_ISO[i], Y_BUS_FACE[i]
        n = [f"piatto_Cu100x10_{tr}_{f}_B{k}" for k in (1, 2, 3, 4)]
        box(n[0], xb + FLAG_X, xb + FLAG_X + T, my(Y_PASS - W / 2), my(Y_PASS + W / 2), Z_FLAG, ZP)
        bar_plan(n[1], (xb, my(Y_PASS + W / 2)), (xi, my(Y_ISO - W / 2)), ZP)   # 50 mm oltre i due appoggi
        box(n[2], xi - W / 2, xi + W / 2, my(yb), my(Y_ISO + W / 2), ZP, ZP + T)
        box(n[3], xi - W / 2, xi + W / 2, my(yb), my(yb + T), ZP + T, Z_BUS_TOP)
        names += n
    s.ex("material.assign", bodies=names, material="Copper")
    s.ex("appearance.assign", bodies=names, color="#B87333")
    s.ex("component.metadata.set", component=cname, part_number=f"CPF-CMT-{tr}",
         description=f"Collegamento MT passanti TR {tr} - castelletto, piatto Cu-ETP 100x10 (3 fasi, 4 tratti per fase)",
         properties={"IfcClass": "IfcFlowSegment", "Materiale": "Rame Cu-ETP (EN 13601), piatto 100x10",
                     "Stallo": tr, "Norma": "CEI EN 61936-1 (distanze MT 24 kV: N 220 mm)"})
    made[tr] = names
    s.ex("component.activate", component="root")

# rimuove i vecchi collegamenti
for c in ("COLL_MT_TR-CASTELLETTO", "COLL_MT_TR-CASTELLETTO_TR2"):
    if c in comps:
        s.ex("component.delete", component=comps[c]["id"])
print("piatti creati:", {k: len(v) for k, v in made.items()})
if args:
    s.tool("save", {"path": args[0]})
    if len(args) > 1:
        s.tool("export", {"path": args[1]})
    s.tool("open", {"path": args[0]})
for b in ("piatto_Cu100x10_TR1_L1_B2", "piatto_Cu100x10_TR1_L3_B4", "piatto_Cu100x10_TR2_L1_B2", "piatto_Cu100x10_TR2_L3_B4"):
    x = s.tool("measure", {"body": b})["bodies"][0]
    bb = x["bbox"]; print(f"{b:28s} X {bb['min'][0]:.0f}..{bb['max'][0]:.0f} Y {bb['min'][1]:.0f}..{bb['max'][1]:.0f} Z {bb['min'][2]:.0f}..{bb['max'][2]:.0f} {x['material']} {x['volume_mm3']:.0f}")
for tag, cam in (("tr1", {"target": [23700, -3800, 4000], "yaw": 2.2, "pitch": 0.35, "distance": 7000}),
                 ("tr2", {"target": [23700, 16200, 4000], "yaw": 0.9, "pitch": 0.35, "distance": 7000})):
    s.tool("screenshot", {"source": "model", "camera": cam, "path": rf"C:\Users\pietr\Desktop\sc_mcp\cu_{tag}.png", "width": 1400, "height": 900})
s.close()
