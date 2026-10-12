"""Armoniche: OpenDSS (DSS C-API) contro iec60909.harmonics su una cabina MT/BT.

Uso (ambiente con opendssdirect.py): python confronto_opendss_armoniche.py <cartella implementazione> [YNyn0|Dyn11|Dyn1] [salva]
"""
import json, math, sys
import numpy as np
import opendssdirect as dss

sys.path.insert(0, sys.argv[1])
from iec60909 import network_from_dict
from iec60909.harmonics import harmonic_analysis, SPECTRA

GRUPPO = sys.argv[2] if len(sys.argv) > 2 else "YNyn0"
RETE = {
    "name": "Cabina con convertitore", "f_hz": 50,
    "buses": [{"id": "MT", "un_kv": 20.0}, {"id": "BT", "un_kv": 0.4}, {"id": "BT2", "un_kv": 0.4}],
    "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 500, "rx_max": 0.1, "vm_pu": 1.0,
                        "x0x1": 1.0, "r0x0": 0.1}],
    "transformers": [{"id": "TR", "hv_bus": "MT", "lv_bus": "BT", "sr_mva": 1.0, "ur_hv_kv": 20,
                      "ur_lv_kv": 0.4, "ukr_percent": 6, "urr_percent": 1, "vector_group": GRUPPO}],
    "lines": [{"id": "C", "from_bus": "BT", "to_bus": "BT2", "length_km": 0.08, "r1_ohm_per_km": 0.1,
               "x1_ohm_per_km": 0.08, "c_nf_per_km": 600, "r0_ohm_per_km": 0.4, "x0_ohm_per_km": 0.32}],
    "loads": [{"id": "CL", "bus": "BT", "p_mw": 0.4, "q_mvar": 0.15},
              {"id": "AZ", "bus": "BT2", "p_mw": 0.2, "q_mvar": 0.05}],
    "shunts": [{"id": "RIF", "bus": "BT", "q_mvar": -0.25}],
    "harmonic_sources": [{"id": "VFD", "bus": "BT2", "element": "AZ", "spectrum": "6_impulsi"},
                         {"id": "UPS", "bus": "BT", "element": "CL", "spectrum": {"5": [12.0, 40.0], "7": [6.0, -20.0], "11": [3.0, 10.0]}}],
}


def opendss():
    spec = SPECTRA["6_impulsi"]
    hs = [1] + sorted(spec)
    mags = [100] + [spec[h][0] for h in sorted(spec)]
    conn = {"YNyn0": "(wye wye)", "Dyn11": "(delta wye)", "Dyn1": "(delta wye)"}[GRUPPO]
    leadlag = "lead" if GRUPPO == "Dyn11" else "lag"
    cmds = f"""
clear
set defaultbasefrequency=50
new circuit.cabina basekv=20 pu=1.0 angle=0 mvasc3=500 mvasc1=500 x1r1=10 x0r0=10
new spectrum.vfd numharm={len(hs)} harmonic=({' '.join(map(str, hs))}) %mag=({' '.join(f'{m:.12g}' for m in mags)}) angle=({' '.join('0' for _ in hs)})
new transformer.tr phases=3 windings=2 buses=(sourcebus, bt) conns={conn} kvs=(20 0.4) kvas=(1000 1000) xhl={math.sqrt(36 - 1):.12g} %rs=(0.5 0.5) %noloadloss=0 %imag=0 ppm_antifloat=0 leadlag={leadlag}
new linecode.cavo nphases=3 r1=0.1 x1=0.08 c1=600 r0=0.4 x0=0.32 c0=600 units=km
new line.c bus1=bt bus2=bt2 linecode=cavo length=0.08 units=km
new spectrum.ups numharm=4 harmonic=(1 5 7 11) %mag=(100 12 6 3) angle=(0 40 -20 10)
new load.cl bus1=bt phases=3 kv=0.4 kw=400 kvar=150 model=1 %seriesrl=0 spectrum=ups vminpu=0.5 vmaxpu=1.5
new load.az bus1=bt2 phases=3 kv=0.4 kw=200 kvar=50 model=1 %seriesrl=0 spectrum=vfd vminpu=0.5 vmaxpu=1.5
new capacitor.rif bus1=bt phases=3 kv=0.4 kvar=250 conn=delta
set voltagebases=(20 0.4)
calcvoltagebases
solve
"""
    for c in cmds.strip().splitlines():
        dss.Text.Command(c)
    v1 = {b: None for b in ("sourcebus", "bt", "bt2")}
    for b in v1:
        dss.Circuit.SetActiveBus(b)
        v1[b] = dss.Bus.puVmagAngle()[:2]
    out = {}
    for h in sorted(spec):
        dss.Text.Command(f"set mode=harmonics harmonics=({h})")
        dss.Solution.Solve()
        row = {}
        for b in v1:
            dss.Circuit.SetActiveBus(b)
            row[b] = dss.Bus.puVmagAngle()[0] * 100
        out[h] = row
        dss.Text.Command("set mode=snap")
    return v1, out


v1, ref = opendss()
# OpenDSS impone 1 p.u. alla fem dietro l'impedenza della sorgente: stessa tensione
# delle sbarre MT nel flusso di potenza di partenza
mag, ang = v1["sourcebus"]
RETE["external_grids"][0].update(vm_pu=mag, va_degree=ang)
res = harmonic_analysis(network_from_dict(RETE))
mappa = {"sourcebus": "MT", "bt": "BT", "bt2": "BT2"}
err = max(abs(res.bus(mappa[b]).vh_percent[h] - ref[h][b]) / max(ref[h][b], 1e-12)
          for h in ref for b in mappa)
print(json.dumps({"gruppo": GRUPPO, "v1_opendss": v1,
                  "v1_nostro": {b.bus: b.v1_pu for b in res.buses},
                  "scarto_relativo_max": err,
                  "V5": {b: [ref[5][b], res.bus(mappa[b]).vh_percent[5]] for b in mappa},
                  "V7": {b: [ref[7][b], res.bus(mappa[b]).vh_percent[7]] for b in mappa}}, indent=1))
if len(sys.argv) > 3:
    for h in sorted(ref):
        print(h, ["%.2e" % ((res.bus(mappa[b]).vh_percent[h] - ref[h][b]) / ref[h][b]) for b in mappa])
if len(sys.argv) > 3 and sys.argv[3] == "salva":
    dati = {"fonte": f"OpenDSS (DSS C-API {dss.Basic.Version()[:40]}), modalità armoniche, gruppo {GRUPPO}",
            "rete": RETE,
            "vh_percent": {mappa[b]: {str(h): ref[h][b] for h in ref} for b in mappa}}
    json.dump(dati, open("armoniche_opendss.json", "w"), indent=1, ensure_ascii=False)
