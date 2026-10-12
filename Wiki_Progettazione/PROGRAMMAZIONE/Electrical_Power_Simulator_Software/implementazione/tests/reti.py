"""Reti di prova condivise dai test."""

RETE_MAGLIATA = {
    "name": "Rete magliata di prova",
    "f_hz": 50,
    "buses": [
        {"id": "AT", "un_kv": 110.0},
        {"id": "A", "un_kv": 20.0},
        {"id": "B", "un_kv": 20.0},
        {"id": "C", "un_kv": 20.0},
        {"id": "BT", "un_kv": 0.4},
    ],
    "external_grids": [
        {"id": "Q", "bus": "AT", "skq_max_mva": 3000, "rx_max": 0.1,
         "skq_min_mva": 2000, "rx_min": 0.12, "x0x1": 1.2, "r0x0": 0.1}
    ],
    "transformers": [
        {"id": "T1", "hv_bus": "AT", "lv_bus": "A", "sr_mva": 40, "ur_hv_kv": 115,
         "ur_lv_kv": 21, "ukr_percent": 12, "urr_percent": 0.4, "vector_group": "Dyn5"},
        {"id": "T2", "hv_bus": "AT", "lv_bus": "A", "sr_mva": 40, "ur_hv_kv": 115,
         "ur_lv_kv": 21, "ukr_percent": 12, "urr_percent": 0.4, "vector_group": "Dyn5"},
        {"id": "T3", "hv_bus": "C", "lv_bus": "BT", "sr_mva": 1.0, "ur_hv_kv": 20,
         "ur_lv_kv": 0.4, "ukr_percent": 6, "urr_percent": 1.0, "vector_group": "Dyn11"},
    ],
    "lines": [
        {"id": "L_AB", "from_bus": "A", "to_bus": "B", "length_km": 5,
         "r1_ohm_per_km": 0.125, "x1_ohm_per_km": 0.112, "r0_ohm_per_km": 0.5,
         "x0_ohm_per_km": 0.45, "end_temperature_c": 90},
        {"id": "L_BC", "from_bus": "B", "to_bus": "C", "length_km": 3,
         "r1_ohm_per_km": 0.206, "x1_ohm_per_km": 0.118, "r0_ohm_per_km": 0.8,
         "x0_ohm_per_km": 0.47, "end_temperature_c": 90},
        {"id": "L_AC", "from_bus": "A", "to_bus": "C", "length_km": 8,
         "r1_ohm_per_km": 0.125, "x1_ohm_per_km": 0.112, "r0_ohm_per_km": 0.5,
         "x0_ohm_per_km": 0.45, "end_temperature_c": 90},
    ],
    "generators": [
        {"id": "G1", "bus": "B", "sr_mva": 10, "ur_kv": 21, "xd2_percent": 15,
         "cos_phi": 0.8}
    ],
    "motors": [
        {"id": "M1", "bus": "C", "pr_mw": 2.0, "ur_kv": 20, "efficiency": 0.96,
         "cos_phi": 0.88, "ilr_ir": 5.5, "pole_pairs": 2}
    ],
}


RETE_TRE_AVVOLGIMENTI = {
    "name": "Stazione con trasformatore a tre avvolgimenti",
    "f_hz": 50,
    "buses": [
        {"id": "AT", "un_kv": 132.0},
        {"id": "MT", "un_kv": 20.0},
        {"id": "MT2", "un_kv": 20.0},
        {"id": "TER", "un_kv": 10.0},
    ],
    "external_grids": [
        {"id": "Q", "bus": "AT", "skq_max_mva": 5000, "rx_max": 0.1,
         "skq_min_mva": 3000, "rx_min": 0.1, "x0x1": 1.5, "r0x0": 0.1}
    ],
    "transformers3w": [
        {"id": "T3W", "hv_bus": "AT", "mv_bus": "MT", "lv_bus": "TER",
         "ur_hv_kv": 138.0, "ur_mv_kv": 21.0, "ur_lv_kv": 10.5,
         "sr_hv_mv_mva": 63.0, "sr_hv_lv_mva": 20.0, "sr_mv_lv_mva": 20.0,
         "ukr_hv_mv_percent": 13.0, "ukr_hv_lv_percent": 21.0, "ukr_mv_lv_percent": 7.0,
         "urr_hv_mv_percent": 0.35, "urr_hv_lv_percent": 0.5, "urr_mv_lv_percent": 0.4,
         "uk0_hv_mv_percent": 11.0, "uk0_hv_lv_percent": 18.0, "uk0_mv_lv_percent": 6.0,
         "vector_group": "YNynd5"}
    ],
    "lines": [
        {"id": "L1", "from_bus": "MT", "to_bus": "MT2", "length_km": 4,
         "r1_ohm_per_km": 0.125, "x1_ohm_per_km": 0.112, "r0_ohm_per_km": 0.5,
         "x0_ohm_per_km": 0.45, "end_temperature_c": 90},
    ],
}


RETE_GRUPPO_GENERAZIONE = {
    "name": "Gruppo di generazione con trasformatore elevatore",
    "f_hz": 50,
    "buses": [
        {"id": "AT", "un_kv": 110.0},
        {"id": "AT2", "un_kv": 110.0},
        {"id": "GEN", "un_kv": 10.5},
    ],
    "external_grids": [
        {"id": "Q", "bus": "AT", "skq_max_mva": 3000, "rx_max": 0.1,
         "skq_min_mva": 2000, "rx_min": 0.12, "x0x1": 1.2, "r0x0": 0.1}
    ],
    "lines": [
        {"id": "L1", "from_bus": "AT", "to_bus": "AT2", "length_km": 20,
         "r1_ohm_per_km": 0.12, "x1_ohm_per_km": 0.39, "r0_ohm_per_km": 0.36,
         "x0_ohm_per_km": 1.17, "end_temperature_c": 80},
    ],
    "transformers": [
        {"id": "TG", "hv_bus": "AT2", "lv_bus": "GEN", "sr_mva": 100, "ur_hv_kv": 115,
         "ur_lv_kv": 10.5, "ukr_percent": 13, "urr_percent": 0.3, "vector_group": "YNd5"},
    ],
    "generators": [
        {"id": "G", "bus": "GEN", "sr_mva": 100, "ur_kv": 10.5, "xd2_percent": 17,
         "cos_phi": 0.85, "rg_ohm": 0.0094, "unit_transformer": "TG"},
    ],
}
