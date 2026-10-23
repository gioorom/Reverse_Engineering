"""CP Faggiano - TR2 (TR Verde, a destra guardando la linea) con castelletto MT sul lato esterno.

Il modello STEP ha STALLO_TRAFO condiviso fra i due stalli: il lato MT (trafo, castelletto, sbarre,
isolatori, terminali, cavi) viene tolto dalla definizione condivisa e rimesso per stallo:
  - TR1 (Rosso): occorrenze ricopiate tali e quali in CP_FAGGIANO (stesse definizioni)
  - TR2 (Verde): corpi specchiati rispetto al piano Y_sito = Y_SPECCHIO in componenti propri
Frame: comp 3 CP_FAGGIANO = frame sito (X lungo stallo, Y lungo sbarre, Z in alto); i corpi copiati restano nel frame sito.
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
from scl import SC

# ---- parametri (mm) ----
Y_BAY2 = 12400.0                # interasse stalli trafo (Y sito)
Y_SPECCHIO = Y_BAY2 / 2         # piano di specchio per portare il lato MT di TR1 su TR2 lato esterno
MT_Y0 = 6050.0                  # muro tagliafiamme centrato fra i plinti (4000 / 8400): 6200 - 300/2
P = [2, 4]                      # path: Seazione AT STEP:1 / CP_FAGGIANO_150-20kV:1
OCC_TR1, OCC_TR2 = 103, 186     # STALLO_TRAFO:1 / :2
COMP_CP = 3

s = SC()
if len(sys.argv) > 1:
    print(s.tool("open", {"path": sys.argv[1]}).get("component", ""))
cl = s.ex("component.list")
comps = {c["id"]: c for c in cl["components"]}
stallo = {ch["id"]: ch for ch in comps[102]["children"]}

MIRROR_COMPS = {146: "TR_MATELEC_25MVA", 150: "SOST_PORTATERMINALI_MT", 152: "SBARRE_MT_CU100x10",
                164: "COLL_MT_TR-CASTELLETTO", 179: "CAVI_MT_USCITA"}
SYMM = [o for o, ch in stallo.items() if ch["component"] in (153, 165)]   # isolatori MT, terminali cavo
ALL = list(MIRROR_COMPS) + SYMM
log = []
try:
    # 1) TR1: ricopia le occorrenze del lato MT in CP_FAGGIANO
    for o in ALL:
        s.ex("occurrence.copy", occurrence=o, path=P + [OCC_TR1, o], parent=COMP_CP)
    log.append(f"TR1: {len(ALL)} occorrenze ricopiate")

    # 2) TR2: isolatori e terminali (simmetrici) ricopiati in posizione specchiata
    for o in SYMM:
        y = stallo[o]["transform"][3][1]            # Y locale stallo (matrice per colonne)
        s.ex("occurrence.copy", occurrence=o, path=P + [OCC_TR2, o], parent=COMP_CP,
             translate=[0, Y_BAY2 - 2 * y, 0])   # la copia parte dalla trasformazione locale dello stallo (senza +Y_BAY2)
    log.append(f"TR2: {len(SYMM)} isolatori/terminali specchiati")

    # 3) TR2: trafo, castelletto, sbarre MT, collegamenti e cavi specchiati in componenti propri
    for o, name in MIRROR_COMPS.items():
        cid = stallo[o]["component"]
        new = s.ex("component.create", name=f"{name}_TR2", parent=COMP_CP, activate=True)
        bodies = comps[cid]["bodies"]
        cp = s.ex("solid.move", bodies=bodies, translate=[0, 0, 0], copy=True)["created_bodies"]
        # la copia arriva con le coordinate del file STEP (Y in alto): +90 gradi attorno a X la riporta nel frame sito
        s.ex("solid.move", bodies=cp, axis=[1, 0, 0], angle="90 deg")
        b0 = s.tool("measure", {"body": cp[0]})["bodies"][0]["bbox"]; o0 = s.tool("measure", {"body": bodies[0]})["bodies"][0]["bbox"]
        assert all(abs(a - b) < 1 for a, b in zip(b0["min"] + b0["max"], o0["min"] + o0["max"])), (name, b0, o0)
        mr = s.ex("solid.mirror", bodies=cp, plane={"origin": [0, Y_SPECCHIO, 0], "normal": [0, 1, 0]})
        s.ex("solid.remove", bodies=cp)
        log.append(f"{name}_TR2: {len(cp)} corpi specchiati -> {len(mr.get('created_bodies', []))}")
        s.ex("component.metadata.set", component=f"{name}_TR2",
             description=f"{name} dello stallo TR2 (TR Verde), specchiato: lato MT verso l'esterno",
             properties={"Stallo": "TR2", "Fonte": "Specchio di " + name + " (STALLO_TRAFO)"})

    # 4) toglie il lato MT dalla definizione condivisa STALLO_TRAFO
    d = s.ex("selection.delete", occurrences=ALL)
    log.append(f"eliminate dalla definizione condivisa: {len(d.get('deleted', d))}")

    # 5) muro tagliafiamme centrale
    s.ex("component.activate", component="root")
    s.tool("set_parameter", {"name": "MT_Y0", "value": f"{MT_Y0} mm",
                             "comment": "Faccia muro lato TR1: muro centrato fra i plinti TR1/TR2 (asse Y 6200)"})
    log.append("MT_Y0 = %.0f" % MT_Y0)
except Exception as e:
    log.append("ERRORE: " + str(e)[:1500])
print("\n".join(log))
s.close()

