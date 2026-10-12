"""Trasformatori dei servizi ausiliari dei gruppi di generazione: calcoli a mano.

Rete RETE_GRUPPO_GENERAZIONE (rete 110 kV - linea - trasformatore del gruppo
115/10,5 kV - generatore 10,5 kV) con i servizi ausiliari sul nodo del
generatore: trasformatore ausiliario TA 10,5/6,3 kV 10 MVA (uk 8 %, ur 0,6 %)
- nodo AUX 6,3 kV - trasformatore TB 6,3/0,4 kV 2 MVA (uk 6 %, ur 1 %) - nodo BT.

I nodi a valle dei trasformatori ausiliari sono interni al gruppo: generatore
con K_G,S, trasformatore del gruppo con K_T,S, trasformatori ausiliari con il
loro K_T (cmax del lato BT). Impedenze in Ω.
"""

import copy
import math

import pytest

from iec60909 import calculate, factors, network_from_dict
from iec60909.calc import _calculate

from .reti import RETE_GRUPPO_GENERAZIONE

UN_Q, UN_G, UN_A, UN_B = 110.0, 10.5, 6.3, 0.4
TR = 115.0 / 10.5
SIN_PHI = math.sqrt(1 - 0.85**2)
XD = 0.17
XT = math.sqrt(13.0**2 - 0.3**2) / 100


def _rete(motore=False, **gen):
    data = copy.deepcopy(RETE_GRUPPO_GENERAZIONE)
    data["generators"][0].update(gen)
    data["buses"] += [{"id": "AUX", "un_kv": UN_A}, {"id": "BT", "un_kv": UN_B}]
    data["transformers"] += [
        {"id": "TA", "hv_bus": "GEN", "lv_bus": "AUX", "sr_mva": 10, "ur_hv_kv": 10.5,
         "ur_lv_kv": 6.3, "ukr_percent": 8, "urr_percent": 0.6, "vector_group": "Dyn11"},
        {"id": "TB", "hv_bus": "AUX", "lv_bus": "BT", "sr_mva": 2, "ur_hv_kv": 6.3,
         "ur_lv_kv": 0.4, "ukr_percent": 6, "urr_percent": 1, "vector_group": "Dyn11"},
    ]
    if motore:
        data["motors"] = [
            {"id": "M", "bus": "AUX", "pr_mw": 2.0, "ur_kv": 6.3, "efficiency": 0.95,
             "cos_phi": 0.85, "ilr_ir": 5.0, "rx": 0.15, "pole_pairs": 2}
        ]
    return data


def _z_rete():
    """Rete di alimentazione + linea, caso massimo, in Ω a 110 kV."""
    zq = 1.1 * UN_Q**2 / 3000.0
    xq = zq / math.sqrt(1 + 0.1**2)
    return complex(0.1 * xq, xq) + 20 * complex(0.12, 0.39)


def _z_trafo(ur_kv, sr_mva, uk, ur):
    zr = ur_kv**2 / sr_mva
    r = ur / 100 * zr
    return complex(r, math.sqrt((uk / 100 * zr) ** 2 - r**2))


def _par(*zs):
    return 1 / sum(1 / z for z in zs)


def _ik(c, un_kv, z):
    return c * un_kv / (math.sqrt(3) * abs(z))


def _z_nodo_generatore(scale=1.0):
    """Impedenza vista dal nodo del generatore con i fattori interni (Ω a 10,5 kV)."""
    k_gs = scale * 1.1 / (1 + XD * SIN_PHI)
    k_ts = scale * 1.1 / (1 - XT * SIN_PHI)
    z_g = k_gs * complex(0.0094, XD * UN_G**2 / 100.0)
    z_rt = k_ts * _z_trafo(115.0, 100, 13, 0.3) / TR**2 + _z_rete() / TR**2
    return _par(z_g, z_rt)


def _kt(c_lv, uk, ur):
    return factors.transformer_kt(c_lv, math.sqrt(uk**2 - ur**2) / 100)


def _z_aux(scale=1.0):
    return _z_nodo_generatore(scale) * (UN_A / UN_G) ** 2 + _kt(1.1, 8, 0.6) * _z_trafo(6.3, 10, 8, 0.6)


def test_regione_del_gruppo():
    net = network_from_dict(_rete())
    region, altre = net.unit_region(net.generators[0])
    assert region == ["GEN", "AUX", "BT"]
    assert not altre


@pytest.mark.parametrize("oltc, pg", [(True, 0.0), (False, 5.0)])
def test_trifase_lato_servizi_ausiliari(oltc, pg):
    """Guasto sul lato BT del trasformatore ausiliario (F3 della norma)."""
    scale = 1.0 if oltc else 1 / (1 + pg / 100)
    r = calculate(network_from_dict(_rete(oltc=oltc, pg_percent=pg))).bus("AUX")
    z = _z_aux(scale)
    assert r.z1_ohm == pytest.approx(z, rel=1e-9)
    assert r.ikss3_ka == pytest.approx(_ik(1.1, UN_A, z), rel=1e-9)


def test_trifase_quadro_bt_a_valle():
    """Anche le reti a valle dei servizi ausiliari sono interne al gruppo."""
    r = calculate(network_from_dict(_rete())).bus("BT")
    # BT con tolleranza +6 %: cmax = 1,05 per il guasto e per K_T di TB
    z = _z_aux() * (UN_B / UN_A) ** 2 + _kt(1.05, 6, 1) * _z_trafo(0.4, 2, 6, 1)
    assert r.ikss3_ka == pytest.approx(_ik(1.05, UN_B, z), rel=1e-9)


def test_nodo_generatore_con_trasformatore_ausiliario():
    """Il trasformatore ausiliario a vuoto non cambia il guasto al nodo del generatore."""
    r = calculate(network_from_dict(_rete())).bus("GEN")
    assert r.ikss3_ka == pytest.approx(_ik(1.1, UN_G, _z_nodo_generatore()), rel=1e-9)


def test_motori_dei_servizi_ausiliari():
    """I motori ausiliari contribuiscono al guasto sul lato ausiliario e al nodo del generatore."""
    r = calculate(network_from_dict(_rete(motore=True)))
    srm = 2.0 / (0.95 * 0.85)
    zm_abs = UN_A**2 / (5.0 * srm)
    xm = zm_abs / math.sqrt(1 + 0.15**2)
    z_m = complex(0.15 * xm, xm)
    assert r.bus("AUX").ikss3_ka == pytest.approx(_ik(1.1, UN_A, _par(_z_aux(), z_m)), rel=1e-9)
    z_ta_hv = _kt(1.1, 8, 0.6) * _z_trafo(6.3, 10, 8, 0.6) * (UN_G / UN_A) ** 2
    z_gen = _par(_z_nodo_generatore(), z_ta_hv + z_m * (UN_G / UN_A) ** 2)
    assert r.bus("GEN").ikss3_ka == pytest.approx(_ik(1.1, UN_G, z_gen), rel=1e-9)


def test_fattori_interni_diversi_da_quelli_esterni():
    """Con i fattori dei guasti esterni (K_S) il risultato sarebbe diverso."""
    net = network_from_dict(_rete())
    interno = calculate(net).bus("AUX").ikss3_ka
    esterno = _calculate(net, "max", "C", 1.0, 0.1, None).bus("AUX").ikss3_ka
    assert abs(interno / esterno - 1) > 1e-3


def test_servizi_ausiliari_con_altra_alimentazione():
    """Servizi ausiliari alimentati anche dalla rete (trasformatore di avviamento):
    solo il nodo del generatore è interno al gruppo, con un avviso."""
    data = _rete()
    data["transformers"].append(
        {"id": "TAV", "hv_bus": "AT2", "lv_bus": "AUX", "sr_mva": 10, "ur_hv_kv": 115,
         "ur_lv_kv": 6.3, "ukr_percent": 10, "urr_percent": 0.5, "vector_group": "YNd11"}
    )
    net = network_from_dict(data)
    region, altre = net.unit_region(net.generators[0])
    assert altre and "AT2" in region
    res = calculate(net)
    assert any("altre sorgenti" in w for w in res.warnings)
    esterno = _calculate(net, "max", "C", 1.0, 0.1, None)
    assert res.bus("AUX").ikss3_ka == pytest.approx(esterno.bus("AUX").ikss3_ka, rel=1e-12)
    assert res.bus("GEN").ikss3_ka != pytest.approx(esterno.bus("GEN").ikss3_ka, rel=1e-6)
