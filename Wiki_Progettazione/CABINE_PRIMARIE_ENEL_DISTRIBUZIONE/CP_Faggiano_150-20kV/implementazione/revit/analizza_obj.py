"""Analizza gli oggetti dell'OBJ esportato: a quale apparecchio (occorrenza) appartiene ogni corpo."""
import sys, json, re, collections, os
sys.stdout.reconfigure(encoding="utf-8")
D = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\pietr\Desktop\sc_mcp\revit"
cl = json.load(open(os.path.join(D, "complist.json"), encoding="utf-8"))
if isinstance(cl, str):                     # risposta headless con nota in coda
    cl = json.JSONDecoder().raw_decode(cl.strip())[0]
owner = {}
for c in cl["components"]:
    for b in c["bodies"]:
        owner.setdefault(b, c["name"])
objs = []
cur = None; nf = collections.Counter()
with open(os.path.join(D, "stallo.obj"), encoding="utf-8", errors="replace") as f:
    for l in f:
        if l.startswith("o "):
            cur = l[2:].strip(); objs.append(cur)
        elif l.startswith("f "):
            nf[cur] += 1
def key(o):
    m = re.match(r"^(.*?) \((.*)\)$", o)
    if m:
        segs = m.group(2).split("/")
        segs = [s for s in segs if not s.startswith(("base_tr2_esterno", "Seazione AT STEP", "CP_FAGGIANO"))]
        return "/".join(segs[:2]) if segs else "?"
    return "@" + owner.get(o, "?")
g = collections.defaultdict(list)
for o in objs:
    g[key(o)].append(o)
for k in sorted(g):
    print(f"{k:60s} corpi {len(g[k]):4d} tri {sum(nf[o] for o in g[k]):8d}")
print("gruppi", len(g), "oggetti", len(objs), "triangoli", sum(nf.values()))
