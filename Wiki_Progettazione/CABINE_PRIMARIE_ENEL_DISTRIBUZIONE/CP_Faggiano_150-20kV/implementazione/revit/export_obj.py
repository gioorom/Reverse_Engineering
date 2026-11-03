"""Esporta il modello SolidCraft finale in OBJ (mesh in coordinate sito, mm) + elenco componenti, per Revit."""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8")
from scl import SC
HERE = os.path.dirname(os.path.abspath(__file__))
M = os.path.normpath(os.path.join(HERE, "..", "..", "modelli"))
OUT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\pietr\Desktop\sc_mcp\revit"
os.makedirs(OUT, exist_ok=True)
s = SC(port=None)
r = s.tool("open", {"path": os.path.join(M, "CP_Faggiano_Sezione_AT.solidcraft")})
print("open:", str(r)[:300])
json.dump(s.ex("component.list"), open(os.path.join(OUT, "complist.json"), "w", encoding="utf-8"), indent=1)
print(s.tool("export", {"path": os.path.join(OUT, "stallo.obj")}))
s.close()
