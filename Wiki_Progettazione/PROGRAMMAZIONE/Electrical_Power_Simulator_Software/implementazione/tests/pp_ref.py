"""Conversione di una rete di prova in una rete pandapower (riferimento indipendente)."""

import math

from iec60909 import factors


def to_pandapower(data):
    import pandapower as pp

    net = pp.create_empty_network(f_hz=data.get("f_hz", 50))
    ids = {}
    for b in data["buses"]:
        ids[b["id"]] = pp.create_bus(net, vn_kv=b["un_kv"], name=b["id"])
    for g in data.get("external_grids", []):
        pp.create_ext_grid(
            net, ids[g["bus"]], s_sc_max_mva=g["skq_max_mva"], rx_max=g["rx_max"],
            s_sc_min_mva=g.get("skq_min_mva", g["skq_max_mva"]),
            rx_min=g.get("rx_min", g["rx_max"]),
            x0x_max=g.get("x0x1", math.nan), r0x0_max=g.get("r0x0", math.nan),
            x0x_min=g.get("x0x1", math.nan), r0x0_min=g.get("r0x0", math.nan),
        )
    for t in data.get("transformers", []):
        pp.create_transformer_from_parameters(
            net, ids[t["hv_bus"]], ids[t["lv_bus"]], sn_mva=t["sr_mva"],
            vn_hv_kv=t["ur_hv_kv"], vn_lv_kv=t["ur_lv_kv"], vkr_percent=t["urr_percent"],
            vk_percent=t["ukr_percent"], pfe_kw=0, i0_percent=0,
            vector_group=t.get("vector_group", "Dyn").rstrip("0123456789"),
            vk0_percent=t.get("uk0_percent", t["ukr_percent"]),
            vkr0_percent=t.get("ur0_percent", t["urr_percent"]),
            mag0_percent=100, mag0_rx=0, si0_hv_partial=0.9,
            parallel=t.get("parallel", 1),
        )
    for t in data.get("transformers3w", []):
        sn_hv = max(t["sr_hv_mv_mva"], t["sr_hv_lv_mva"])
        sn_mv = max(t["sr_hv_mv_mva"], t["sr_mv_lv_mva"])
        sn_lv = max(t["sr_hv_lv_mva"], t["sr_mv_lv_mva"])
        assert (min(sn_hv, sn_mv), min(sn_mv, sn_lv), min(sn_hv, sn_lv)) == (
            t["sr_hv_mv_mva"], t["sr_mv_lv_mva"], t["sr_hv_lv_mva"]
        ), "potenze di coppia non rappresentabili in pandapower"
        kw = {}
        for pp_side, pair in (("hv", "hv_mv"), ("mv", "mv_lv"), ("lv", "hv_lv")):
            kw[f"vk_{pp_side}_percent"] = t[f"ukr_{pair}_percent"]
            kw[f"vkr_{pp_side}_percent"] = t[f"urr_{pair}_percent"]
            kw[f"vk0_{pp_side}_percent"] = t.get(f"uk0_{pair}_percent", t[f"ukr_{pair}_percent"])
            kw[f"vkr0_{pp_side}_percent"] = t.get(f"ur0_{pair}_percent", t[f"urr_{pair}_percent"])
        pp.create_transformer3w_from_parameters(
            net, ids[t["hv_bus"]], ids[t["mv_bus"]], ids[t["lv_bus"]],
            vn_hv_kv=t["ur_hv_kv"], vn_mv_kv=t["ur_mv_kv"], vn_lv_kv=t["ur_lv_kv"],
            sn_hv_mva=sn_hv, sn_mv_mva=sn_mv, sn_lv_mva=sn_lv, pfe_kw=0, i0_percent=0,
            vector_group="".join(c for c in t["vector_group"] if not c.isdigit()), **kw,
        )
    for ln in data.get("lines", []):
        pp.create_line_from_parameters(
            net, ids[ln["from_bus"]], ids[ln["to_bus"]], length_km=ln["length_km"],
            r_ohm_per_km=ln["r1_ohm_per_km"], x_ohm_per_km=ln["x1_ohm_per_km"],
            c_nf_per_km=0, max_i_ka=1, r0_ohm_per_km=ln.get("r0_ohm_per_km", math.nan),
            x0_ohm_per_km=ln.get("x0_ohm_per_km", math.nan), c0_nf_per_km=0,
            endtemp_degree=ln.get("end_temperature_c", 20), parallel=ln.get("parallel", 1),
        )
    for g in data.get("generators", []):
        xd = g["xd2_percent"] / 100 * g["ur_kv"] ** 2 / g["sr_mva"]
        rg = g.get("rg_ohm", factors.generator_rx(g["ur_kv"], g["sr_mva"]) * xd)
        pp.create_gen(
            net, ids[g["bus"]], p_mw=0, sn_mva=g["sr_mva"], vn_kv=g["ur_kv"],
            xdss_pu=g["xd2_percent"] / 100, rdss_ohm=rg, cos_phi=g["cos_phi"],
        )
    for m in data.get("motors", []):
        rx = m.get("rx") or factors.motor_rx(m["ur_kv"], m["pr_mw"], m.get("pole_pairs"))
        pp.create_motor(
            net, ids[m["bus"]], pn_mech_mw=m["pr_mw"], cos_phi=m["cos_phi"],
            efficiency_percent=m["efficiency"] * 100, lrc_pu=m["ilr_ir"], rx=rx,
            cos_phi_n=m["cos_phi"], efficiency_n_percent=m["efficiency"] * 100,
            vn_kv=m["ur_kv"], scaling=m.get("count", 1),
        )
    return net, ids


def run(data, fault, case, **kwargs):
    from pandapower.shortcircuit import calc_sc

    net, ids = to_pandapower(data)
    calc_sc(net, fault=fault, case=case, lv_tol_percent=data.get("lv_tolerance_percent", 6),
            topology="meshed", **kwargs)
    return {name: net.res_bus_sc.loc[idx] for name, idx in ids.items()}
