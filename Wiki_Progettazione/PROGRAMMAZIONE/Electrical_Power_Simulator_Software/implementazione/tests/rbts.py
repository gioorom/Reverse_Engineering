"""Roy Billinton Test System, Bus 2: rete di distribuzione a 11 kV (Allan, Billinton,
Sjarief, Goel, So, "A reliability test system for educational purposes - basic
distribution system data and results", IEEE Trans. Power Systems 6(2), 1991)."""

# lunghezze delle sezioni (tabella 2) [km]
LUNGHEZZE = {**{s: 0.60 for s in (2, 6, 10, 14, 17, 21, 25, 28, 30, 34)},
             **{s: 0.75 for s in (1, 4, 7, 9, 12, 16, 19, 22, 24, 27, 29, 32, 35)},
             **{s: 0.80 for s in (3, 5, 8, 11, 13, 15, 18, 20, 23, 26, 31, 33, 36)}}
# dorsali: sezioni principali dalla cabina verso la fine (figura 2)
DORSALI = {1: (1, 4, 7, 10), 2: (12, 14), 3: (16, 18, 21, 24), 4: (26, 29, 32, 34)}
# punto di carico: (dorsale, indice della sezione principale alla cui fine si deriva, derivazione)
PUNTI = {1: (1, 0, 2), 2: (1, 0, 3), 3: (1, 1, 5), 4: (1, 1, 6), 5: (1, 2, 8), 6: (1, 2, 9),
         7: (1, 3, 11), 8: (2, 0, 13), 9: (2, 1, 15), 10: (3, 0, 17), 11: (3, 1, 19), 12: (3, 1, 20),
         13: (3, 2, 22), 14: (3, 2, 23), 15: (3, 3, 25), 16: (4, 0, 27), 17: (4, 0, 28), 18: (4, 1, 30),
         19: (4, 1, 31), 20: (4, 2, 33), 21: (4, 3, 35), 22: (4, 3, 36)}
# clienti e carico medio [MW] (tabella 3)
CLIENTI = {**{i: (210, 0.535) for i in (1, 2, 3, 10, 11)}, **{i: (200, 0.450) for i in (12, 17, 18, 19)},
           8: (1, 1.00), 9: (1, 1.15), **{i: (1, 0.566) for i in (4, 5, 13, 14, 20, 21)},
           **{i: (10, 0.454) for i in (6, 7, 15, 16, 22)}}
# punti normalmente aperti tra le fini delle dorsali 1-2 e 3-4
CONTRO_ALIMENTAZIONI = ((1, 2), (3, 4))
# dati dei componenti (tabella 5): guasti [1/(km·anno)], riparazione e manovra [h]
COMPONENTI = {"linee": (0.065, 5.0, 1.0), "cavi": (0.04, 30.0, 3.0)}


def rbts_bus2(tipo="linee", trasformatori_h=200.0):
    """Rete in formato JSON; LP8 e LP9 (utenze in MT) non hanno trasformatore."""
    lam, rip, manovra = COMPONENTI[tipo]
    lin = {"r1_ohm_per_km": 0.2, "x1_ohm_per_km": 0.35}
    buses = [{"id": "SE", "un_kv": 11}]
    lines, trafos, switches, loads = [], [], [], []
    for f, sezioni in DORSALI.items():
        prec = "SE"
        for k, s in enumerate(sezioni):
            nodo = f"F{f}N{k}"
            buses.append({"id": nodo, "un_kv": 11})
            lines.append({"id": f"S{s}", "from_bus": prec, "to_bus": nodo, "length_km": LUNGHEZZE[s], **lin})
            # interruttore in testa alla dorsale, sezionatore a valle di ogni derivazione
            switches.append({"id": f"Q{s}", "branch": f"S{s}", "bus": prec,
                             "kind": "breaker" if k == 0 else "switch", "switching_time_h": manovra})
            prec = nodo
    for lp, (f, k, lat) in PUNTI.items():
        mt = f"LP{lp}_MT"
        buses.append({"id": mt, "un_kv": 11})
        lines.append({"id": f"S{lat}", "from_bus": f"F{f}N{k}", "to_bus": mt, "length_km": LUNGHEZZE[lat], **lin})
        switches.append({"id": f"FU{lat}", "branch": f"S{lat}", "bus": f"F{f}N{k}", "kind": "fuse"})
        nodo = mt
        if lp not in (8, 9):
            nodo = f"LP{lp}"
            buses.append({"id": nodo, "un_kv": 0.415})
            trafos.append({"id": f"T{lp}", "hv_bus": mt, "lv_bus": nodo, "sr_mva": 1.0, "ur_hv_kv": 11,
                           "ur_lv_kv": 0.415, "ukr_percent": 5, "urr_percent": 1})
        n, p = CLIENTI[lp]
        loads.append({"id": f"LP{lp}", "bus": nodo, "p_mw": p, "average_mw": p, "customers": n})
    for a, b in CONTRO_ALIMENTAZIONI:
        fa, fb = f"F{a}N{len(DORSALI[a]) - 1}", f"F{b}N{len(DORSALI[b]) - 1}"
        lines.append({"id": f"NA{a}{b}", "from_bus": fa, "to_bus": fb, "length_km": 0.5, **lin})
        switches.append({"id": f"QNA{a}{b}", "branch": f"NA{a}{b}", "bus": fa, "normally_open": True,
                         "switching_time_h": manovra})
    rel = [{"element": "@lines", "failure_rate_per_km": lam, "repair_time_h": rip},
           {"element": "@transformers", "failure_rate": 0.015, "repair_time_h": trasformatori_h}]
    rel += [{"element": f"NA{a}{b}", "failure_rate": 0.0, "repair_time_h": 0.0} for a, b in CONTRO_ALIMENTAZIONI]
    return {"name": f"RBTS Bus 2 ({tipo})", "f_hz": 50, "buses": buses,
            "external_grids": [{"id": "RETE", "bus": "SE", "skq_max_mva": 500}],
            "lines": lines, "transformers": trafos, "loads": loads, "switches": switches,
            "reliability_data": rel}


# Risultati pubblicati, caso base A (tabella 7): λ [1/anno], r [h], U [h/anno]
TABELLA_7 = {
    "cavi": {1: (0.153, 31.84, 4.87), 2: (0.161, 31.75, 5.11), 3: (0.161, 31.75, 5.11), 4: (0.153, 31.84, 4.87),
             5: (0.161, 31.75, 5.11), 6: (0.159, 31.77, 5.05), 7: (0.161, 30.75, 4.95), 8: (0.086, 22.47, 1.93),
             9: (0.086, 20.58, 1.77), 10: (0.155, 31.47, 4.88), 11: (0.161, 31.75, 5.11),
             12: (0.163, 31.73, 5.17), 13: (0.161, 30.41, 4.90), 14: (0.163, 30.41, 4.96),
             15: (0.155, 31.47, 4.88), 16: (0.161, 31.75, 5.11), 17: (0.155, 31.82, 4.93),
             18: (0.155, 31.47, 4.88), 19: (0.163, 31.40, 5.12), 20: (0.163, 31.40, 5.12),
             21: (0.161, 30.41, 4.90), 22: (0.163, 30.41, 4.96)},
    "linee": {1: (0.240, 14.90, 3.58), 2: (0.253, 14.40, 3.64), 3: (0.253, 14.40, 3.64), 4: (0.240, 14.90, 3.58),
              5: (0.253, 14.40, 3.64), 6: (0.250, 14.51, 3.63), 7: (0.253, 14.24, 3.60), 8: (0.140, 3.89, 0.54),
              9: (0.140, 3.60, 0.50), 10: (0.243, 14.73, 3.58), 11: (0.253, 14.40, 3.64),
              12: (0.256, 14.29, 3.66), 13: (0.253, 14.19, 3.59), 14: (0.256, 14.08, 3.61),
              15: (0.243, 14.73, 3.58), 16: (0.253, 14.40, 3.64), 17: (0.243, 14.78, 3.59),
              18: (0.243, 14.73, 3.58), 19: (0.256, 14.24, 3.65), 20: (0.256, 14.24, 3.65),
              21: (0.253, 14.19, 3.59), 22: (0.256, 14.08, 3.61)},
}
# indici di sistema (tabella 9): SAIFI, SAIDI, CAIDI, ASAI, ENS [kWh/anno], AENS [kWh/cliente·anno]
TABELLA_9 = {
    ("linee", 200.0): (0.248, 3.61, 14.55, 0.999588, 37746, 19.78),
    ("cavi", 200.0): (0.159, 5.02, 31.65, 0.999427, 54655, 28.65),
    ("linee", 10.0): (0.248, 0.77, 3.08, 0.999913, 8844, 4.64),
    ("cavi", 10.0): (0.159, 2.17, 13.69, 0.999752, 25753, 13.50),
}
