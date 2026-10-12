"""Verifiche con calcoli a mano sul trasformatore a tre avvolgimenti (IEC 60909-0, 6.3.2).

Tutte le impedenze sono calcolate in Ω riferite al lato AT (tensione nominale
dell'avvolgimento AT 138 kV) e poi riportate al nodo di guasto con il rapporto
di trasformazione nominale t_r, come prescrive la norma. Nessuna funzione
interna del pacchetto viene riutilizzata, tranne ``calculate``,
``network_from_dict`` e ``factors.voltage_factor``.
"""

import copy
import math

import pytest

from iec60909 import calculate, factors, network_from_dict

from .reti import RETE_TRE_AVVOLGIMENTI

T = RETE_TRE_AVVOLGIMENTI["transformers3w"][0]
Q = RETE_TRE_AVVOLGIMENTI["external_grids"][0]
UN = {"AT": 132.0, "MT": 20.0, "TER": 10.0}
UR = {"hv": 138.0, "mv": 21.0, "lv": 10.5}


def _rete(**trafo):
    data = copy.deepcopy(RETE_TRE_AVVOLGIMENTI)
    data["transformers3w"][0].update(trafo)
    return network_from_dict(data)


def _parallelo(a, b):
    return a * b / (a + b)


def _rete_q(caso="max"):
    """Impedenze di sequenza diretta e omopolare della rete Q, in Ω a 132 kV."""
    c = factors.voltage_factor(132.0, caso)
    skq = Q["skq_max_mva"] if caso == "max" else Q["skq_min_mva"]
    rx = Q["rx_max"] if caso == "max" else Q["rx_min"]
    zq = c * 132.0**2 / skq
    xq = zq / math.sqrt(1 + rx**2)
    x0 = Q["x0x1"] * xq
    return complex(rx * xq, xq), complex(Q["r0x0"] * x0, x0)


def _coppie(t, caso="max", zero=False, cmax_bt=1.10):
    """Impedenze di coppia Z_AB, Z_AC, Z_BC in Ω lato AT (con K_TAB, K_TAC, K_TBC)."""
    out = {}
    for coppia in ("hv_mv", "hv_lv", "mv_lv"):
        sr = t[f"sr_{coppia}_mva"]
        uk = t[f"ukr_{coppia}_percent"]
        ur = t[f"urr_{coppia}_percent"]
        x = math.sqrt(uk**2 - ur**2) / 100
        # cmax del lato a tensione più bassa della coppia (MT per AB, terziario per AC e BC)
        cmax = 1.10 if coppia == "hv_mv" else cmax_bt
        kt = 0.95 * cmax / (1 + 0.6 * x) if caso == "max" else 1.0
        if zero:
            uk = t.get(f"uk0_{coppia}_percent") or uk
            ur = t.get(f"ur0_{coppia}_percent") or ur
        zr = UR["hv"] ** 2 / sr
        out[coppia] = kt * complex(ur / 100 * zr, math.sqrt(uk**2 - ur**2) / 100 * zr)
    return out


def _stella(t, **kw):
    z = _coppie(t, **kw)
    ab, ac, bc = z["hv_mv"], z["hv_lv"], z["mv_lv"]
    return 0.5 * (ab + ac - bc), 0.5 * (ab + bc - ac), 0.5 * (ac + bc - ab)


def _ik3(c, un, z):
    return c * un / (math.sqrt(3) * abs(z))


def _ik1(c, un, z1, z0):
    return math.sqrt(3) * c * un / abs(2 * z1 + z0)


# --- a. corrente trifase massima con K_T e rapporti fuori nominali ----------


def test_trifase_mt_e_terziario_caso_massimo():
    r = calculate(_rete())
    zq, _ = _rete_q()
    zh, zm, zl = _stella(T)
    # guasto su MT: rete Q + Z_A + Z_B, tutto riportato a 21 kV con t_r = 138/21
    t_am = UR["hv"] / UR["mv"]
    z_mt = (zq + zh + zm) / t_am**2
    assert r.bus("MT").ikss3_ka == pytest.approx(_ik3(1.1, 20.0, z_mt), rel=1e-9)
    assert r.bus("MT").z1_ohm == pytest.approx(z_mt, rel=1e-9)
    # guasto sul terziario: rete Q + Z_A + Z_C riportati con t_r = 138/10,5
    t_at = UR["hv"] / UR["lv"]
    z_ter = (zq + zh + zl) / t_at**2
    assert r.bus("TER").ikss3_ka == pytest.approx(_ik3(1.1, 10.0, z_ter), rel=1e-9)
    assert r.bus("TER").ikss2_ka == pytest.approx(math.sqrt(3) / 2 * _ik3(1.1, 10.0, z_ter), rel=1e-9)
    # guasto su AT: il trasformatore non porta contributi (nessuna sorgente a valle)
    assert r.bus("AT").ikss3_ka == pytest.approx(_ik3(1.1, 132.0, zq), rel=1e-9)


def test_stella_con_impedenza_negativa():
    # Con questi dati Z_B (avvolgimento MT) risulta con reattanza negativa: lo
    # schema a stella resta valido perché tra due nodi compaiono solo somme di rami.
    zh, zm, zl = _stella(T)
    assert zm.imag < 0 < zh.imag and zl.imag > 0
    zq, _ = _rete_q()
    r = calculate(_rete()).bus("MT2")
    ln = RETE_TRE_AVVOLGIMENTI["lines"][0]
    zl1 = complex(ln["r1_ohm_per_km"], ln["x1_ohm_per_km"]) * ln["length_km"]
    z = (zq + zh + zm) / (UR["hv"] / UR["mv"]) ** 2 + zl1
    assert r.ikss3_ka == pytest.approx(_ik3(1.1, 20.0, z), rel=1e-9)


def test_terziario_bt_cmax_di_coppia():
    # Terziario a 0,4 kV: K_TAC e K_TBC usano cmax = 1,05 (BT, +6 %), K_TAB usa 1,10.
    data = copy.deepcopy(RETE_TRE_AVVOLGIMENTI)
    data["buses"][3]["un_kv"] = 0.4
    data["transformers3w"][0]["ur_lv_kv"] = 0.42
    r = calculate(network_from_dict(data)).bus("TER")
    zq, _ = _rete_q()
    zh, zm, zl = _stella(T, cmax_bt=1.05)
    z = (zq + zh + zl) / (UR["hv"] / 0.42) ** 2
    assert r.ikss3_ka == pytest.approx(_ik3(1.05, 0.4, z), rel=1e-9)


# --- b. guasto monofase sul nodo AT per diversi gruppi vettoriali -----------


def test_monofase_at_ynyd():
    # YN-y-d: l'avvolgimento MT (y) è aperto, il terziario a triangolo chiude Z0 dal centro stella
    r = calculate(_rete(vector_group="YNyd5")).bus("AT")
    zq, z0q = _rete_q()
    z0h, _, z0l = _stella(T, zero=True)
    z0 = _parallelo(z0q, z0h + z0l)
    assert r.z0_ohm == pytest.approx(z0, rel=1e-9)
    assert r.ikss1_ka == pytest.approx(_ik1(1.1, 132.0, zq, z0), rel=1e-9)


def test_monofase_at_yndd():
    # YN-d-d: i due triangoli sono in parallelo dal centro stella
    r = calculate(_rete(vector_group="YNdd5")).bus("AT")
    zq, z0q = _rete_q()
    z0h, z0m, z0l = _stella(T, zero=True)
    z0 = _parallelo(z0q, z0h + _parallelo(z0m, z0l))
    assert r.z0_ohm == pytest.approx(z0, rel=1e-9)
    assert r.ikss1_ka == pytest.approx(_ik1(1.1, 132.0, zq, z0), rel=1e-9)


@pytest.mark.parametrize("gruppo", ["Ddd0", "Yynd5", "Yyd5", "Dynd1"])
def test_monofase_at_senza_neutro_lato_at(gruppo):
    # Avvolgimento AT senza neutro accessibile: in AT vale solo Z0 = Z0Q
    r = calculate(_rete(vector_group=gruppo)).bus("AT")
    zq, z0q = _rete_q()
    assert r.z0_ohm == pytest.approx(z0q, rel=1e-9)
    assert r.ikss1_ka == pytest.approx(_ik1(1.1, 132.0, zq, z0q), rel=1e-9)


def test_monofase_ynynd_neutro_at_con_impedenza():
    # Impedenza di neutro sull'AT: compare come 3·Zn in serie al ramo Z0A
    zn = complex(5.0, 20.0)
    r = calculate(_rete(vector_group="YNynd5", zn_hv_ohm=zn)).bus("AT")
    zq, z0q = _rete_q()
    z0h, z0m, z0l = _stella(T, zero=True)
    # Il ramo MT (yn) termina su nodi senza percorso verso terra: non contribuisce
    z0 = _parallelo(z0q, z0h + 3 * zn + z0l)
    assert r.ikss1_ka == pytest.approx(_ik1(1.1, 132.0, zq, z0), rel=1e-9)


# --- c. guasto monofase in MT con YNynd5 ------------------------------------


def test_monofase_mt_ynynd():
    r = calculate(_rete()).bus("MT")
    zq, z0q = _rete_q()
    zh, zm, _ = _stella(T)
    z0h, z0m, z0l = _stella(T, zero=True)
    t2 = (UR["hv"] / UR["mv"]) ** 2
    z1 = (zq + zh + zm) / t2
    # dal nodo MT: Z0B fino al centro stella, poi triangolo (Z0C) in parallelo al percorso AT + rete
    z0 = (z0m + _parallelo(z0l, z0h + z0q)) / t2
    assert r.z0_ohm == pytest.approx(z0, rel=1e-9)
    assert r.ikss1_ka == pytest.approx(_ik1(1.1, 20.0, z1, z0), rel=1e-9)
    ike = math.sqrt(3) * 1.1 * 20.0 / abs(z1 + 2 * z0)
    assert r.ikss2e_earth_ka == pytest.approx(ike, rel=1e-9)


def test_monofase_mt_yny_senza_terziario_a_triangolo():
    # YN-yn-y: senza triangolo il percorso omopolare passa solo attraverso la rete AT
    r = calculate(_rete(vector_group="YNyny0")).bus("MT")
    zq, z0q = _rete_q()
    zh, zm, _ = _stella(T)
    z0h, z0m, _ = _stella(T, zero=True)
    t2 = (UR["hv"] / UR["mv"]) ** 2
    z1 = (zq + zh + zm) / t2
    z0 = (z0m + z0h + z0q) / t2
    assert r.ikss1_ka == pytest.approx(_ik1(1.1, 20.0, z1, z0), rel=1e-9)


def test_terziario_a_triangolo_senza_corrente_monofase():
    r = calculate(_rete()).bus("TER")
    assert r.ikss1_ka == 0.0
    assert r.z0_ohm is None


# --- d. caso minimo: niente K_T, cmin, Skq min, linea a temperatura finale --


def test_caso_minimo_mt_e_mt2():
    r = calculate(_rete(), "min")
    zq, z0q = _rete_q("min")
    zh, zm, _ = _stella(T, caso="min")
    z0h, z0m, z0l = _stella(T, caso="min", zero=True)
    t2 = (UR["hv"] / UR["mv"]) ** 2
    z_mt = (zq + zh + zm) / t2
    assert r.bus("MT").ikss3_ka == pytest.approx(_ik3(1.0, 20.0, z_mt), rel=1e-9)
    z0_mt = (z0m + _parallelo(z0l, z0h + z0q)) / t2
    assert r.bus("MT").ikss1_ka == pytest.approx(_ik1(1.0, 20.0, z_mt, z0_mt), rel=1e-9)
    ln = RETE_TRE_AVVOLGIMENTI["lines"][0]
    k_theta = 1 + 0.004 * (ln["end_temperature_c"] - 20)
    zl1 = complex(ln["r1_ohm_per_km"] * k_theta, ln["x1_ohm_per_km"]) * ln["length_km"]
    assert r.bus("MT2").ikss3_ka == pytest.approx(_ik3(1.0, 20.0, z_mt + zl1), rel=1e-9)
    # il caso massimo (con K_T < 1 qui) dà correnti maggiori
    assert calculate(_rete()).bus("MT").ikss3_ka > r.bus("MT").ikss3_ka


# --- e. validazione del gruppo vettoriale -----------------------------------


@pytest.mark.parametrize("gruppo", ["YNd5", "YNynx5", "YNyndd", "", "Dyn11"])
def test_gruppo_vettoriale_non_valido(gruppo):
    with pytest.raises(ValueError, match="gruppo vettoriale"):
        calculate(_rete(vector_group=gruppo))


def test_urr_maggiore_di_ukr_non_valido():
    with pytest.raises(ValueError, match="urr_mv_lv"):
        calculate(_rete(urr_mv_lv_percent=8.0))
