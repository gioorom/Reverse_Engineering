"""CP Faggiano - toglie i vecchi collegamenti MT a tubo/corda (collegamento_MT*) rimasti nel corpo importato:
fra passanti MT e castelletto resta solo il piatto Cu 100x10 (piatti_MT_cu.py).
Uso: python rimuovi_tubi_MT.py <design.solidcraft> <step_out>"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from scl import SC
des, step = sys.argv[1], sys.argv[2]
s = SC()
s.tool("open", {"path": des})
comps = s.ex("component.list")["components"]
n = 0
for c in comps:
    old = [b for b in c["bodies"] if b.startswith("collegamento_MT")]
    if old:
        s.ex("component.activate", component=c["id"])
        s.ex("solid.remove", bodies=old)
        n += len(old)
s.ex("component.activate", component="root")
print("corpi rimossi:", n)
s.tool("save", {"path": des}); s.tool("export", {"path": step}); s.tool("open", {"path": des})
left = [b for c in s.ex("component.list")["components"] for b in c["bodies"] if b.startswith("collegamento_MT")]
cu = [b for c in s.ex("component.list")["components"] for b in c["bodies"] if b.startswith("piatto_Cu100x10")]
print("dopo la riapertura: collegamento_MT rimasti", len(left), "- piatti Cu", len(cu))
for tag, cam in (("tr1", {"target": [23700, -3800, 4000], "yaw": 2.2, "pitch": 0.35, "distance": 7000}),
                 ("tr2", {"target": [23700, 16200, 4000], "yaw": 0.9, "pitch": 0.35, "distance": 7000})):
    s.tool("screenshot", {"source": "model", "camera": cam, "path": rf"C:\Users\pietr\Desktop\sc_mcp\cu2_{tag}.png", "width": 1400, "height": 900})
s.close()
