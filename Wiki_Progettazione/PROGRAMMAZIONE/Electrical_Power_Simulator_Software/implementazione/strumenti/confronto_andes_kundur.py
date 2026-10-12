"""Kundur a due aree (modello classico): ANDES 2.0.0 contro iec60909.stability.

Uso (ambiente con andes installato): python confronto_andes_kundur.py <cartella implementazione>
"""
import json, math, os, sys
import numpy as np
import andes

IMPL = sys.argv[1]
sys.path.insert(0, IMPL)
from iec60909 import network_from_dict
from iec60909.loadflow import run_load_flow
from iec60909.stability import simulate, StabilityEvent

andes.config_logger(stream_level=40)
CASES = os.path.dirname(andes.__file__) + "/cases/kundur/"
T_F, T_C, T_END, XF = 1.0, 1.083, 5.0, 1e-4


def andes_run(trip):
    ss = andes.load(CASES + "kundur.raw", addfile=CASES + "kundur_gencls.dyr", setup=False,
                    no_output=True, default_config=True)
    ss.add("Fault", {"bus": 8, "tf": T_F, "tc": T_C, "xf": XF, "rf": 0.0})
    if trip:
        ss.add("Toggle", {"model": "Line", "dev": "Line_5", "t": T_C})
    ss.setup()
    ss.PFlow.run()
    ss.v_pf = np.array(ss.Bus.v.v).copy()
    ss.a_pf = np.array(ss.Bus.a.v).copy()
    ss.TDS.config.tf = T_END
    ss.TDS.config.tstep = 0.001
    ss.TDS.config.no_tqdm = 1
    ss.TDS.run()
    t = np.array(ss.dae.ts.t)
    delta = np.array(ss.dae.ts.x)[:, ss.GENCLS.delta.a]
    return ss, t, delta


def to_dict(ss):
    sb = ss.config.mva
    bus = ss.Bus.as_df()
    vn = dict(zip(bus.idx, bus.Vn))
    data = {"name": "Kundur due aree (classico)", "f_hz": float(ss.config.freq),
            "buses": [{"id": str(i), "un_kv": float(vn[i])} for i in bus.idx],
            "lines": [], "transformers": [], "generators": [], "loads": []}
    for _, r in ss.Line.as_df().iterrows():
        b1, b2 = r.bus1, r.bus2
        if r.trans:
            hv, lv = (b2, b1) if vn[b2] > vn[b1] else (b1, b2)
            assert r.tap == 1.0 and r.phi == 0.0
            data["transformers"].append({
                "id": r.idx, "hv_bus": str(hv), "lv_bus": str(lv), "sr_mva": sb,
                "ur_hv_kv": float(vn[hv]), "ur_lv_kv": float(vn[lv]),
                "ukr_percent": 100 * math.hypot(r.r, r.x), "urr_percent": 100 * r.r,
                "vector_group": "YNyn0"})
        else:
            zb = vn[b1] ** 2 / sb
            data["lines"].append({
                "id": r.idx, "from_bus": str(b1), "to_bus": str(b2), "length_km": 1.0,
                "r1_ohm_per_km": r.r * zb, "x1_ohm_per_km": r.x * zb,
                "c_nf_per_km": r.b / zb / (2 * math.pi * ss.config.freq) * 1e9})
    for _, r in ss.PQ.as_df().iterrows():
        data["loads"].append({"id": r.idx, "bus": str(r.bus), "p_mw": r.p0 * sb, "q_mvar": r.q0 * sb})
    gcls = ss.GENCLS.as_df().set_index("gen")
    sources = [("slack", r) for _, r in ss.Slack.as_df().iterrows()] + \
              [("pv", r) for _, r in ss.PV.as_df().iterrows()]
    for kind, r in sources:
        g = gcls.loc[r.idx]
        k = g.Sn / sb  # parametri di ANDES già sulla base di sistema
        data["generators"].append({
            "id": f"G{r.bus}", "bus": str(r.bus), "sr_mva": float(g.Sn), "ur_kv": float(g.Vn),
            "xd2_percent": 100 * g.xd1 * k, "xd1_percent": 100 * g.xd1 * k, "rg_ohm": 0.0,
            "p_mw": float(r.p0 * sb), "vm_pu": float(r.v0),
            "h_s": float(g.M / (2 * k)), "d_pu": float(g.D / k)})
    return data


out = {}
for trip in (False, True):
    ss, ta, da = andes_run(trip)
    data = to_dict(ss)
    net = network_from_dict(data)
    lf = run_load_flow(net)
    v_andes = ss.v_pf
    v_ours = np.array([lf.bus(str(i)).vm_pu for i in ss.Bus.idx.v])
    evs = [StabilityEvent(T_F, "fault", bus="8", x_ohm=XF * 230**2 / 100),
           StabilityEvent(T_C, "clear_fault", bus="8")]
    if trip:
        evs.append(StabilityEvent(T_C, "trip_branch", element="Line_5"))
    # evento già presente nel file dinamico di ANDES (kundur_gencls.dyr)
    evs.append(StabilityEvent(2.0, "trip_branch", element="Line_8"))
    res = simulate(net, T_END, 0.001, evs)
    names = [f"G{b}" for b in ss.GENCLS.bus.v]
    ref = names[0]
    err = 0.0
    for k, n in enumerate(names[1:], start=1):
        ours = np.interp(ta, res.t, res.delta_deg[n] - res.delta_deg[ref])
        theirs = np.degrees(da[:, k] - da[:, 0])
        # ANDES registra due valori all'istante degli eventi: si confrontano gli altri
        mask = np.all([np.abs(ta - te) > 2e-3 for te in (T_F, T_C, 2.0)], axis=0)
        err = max(err, float(np.max(np.abs(ours - theirs)[mask])))
    out["con_apertura_linea" if trip else "solo_guasto"] = {
        "scarto_tensioni_flusso_pu": float(np.max(np.abs(v_andes - v_ours))),
        "scarto_max_angoli_relativi_gradi": err,
        "stabile": res.stable,
        "max_diff_angoli_gradi": res.max_angle_diff_deg,
    }
print(json.dumps(out, indent=2))

# rete convertita e valori di riferimento per i test
ss, ta, da = andes_run(False)
data = to_dict(ss)
data["stability_events"] = [
    {"t_s": T_F, "kind": "fault", "bus": "8", "x_ohm": XF * 230**2 / 100},
    {"t_s": T_C, "kind": "clear_fault", "bus": "8"},
    {"t_s": 2.0, "kind": "trip_branch", "element": "Line_8"},
]
ref = {}
for t in (0.5, 1.05, 1.5, 2.5, 3.5, 5.0):
    k = int(np.argmin(np.abs(ta - t)))
    ref[str(t)] = [float(np.degrees(da[k, j] - da[k, 0])) for j in range(1, 4)]
json.dump({"rete": data, "andes_angoli_relativi_gradi": ref, "tempi_effettivi": {str(t): float(ta[int(np.argmin(np.abs(ta - t)))]) for t in (0.5, 1.05, 1.5, 2.5, 3.5, 5.0)}},
          open("kundur_ref.json", "w"), indent=1)
