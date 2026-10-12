"""Gruppi di generazione (generatore + trasformatore elevatore dedicato): calcoli a mano.

Rete RETE_GRUPPO_GENERAZIONE: rete 110 kV (S"kQ 3000/2000 MVA) - linea 20 km -
nodo AT2 - trasformatore 115/10,5 kV 100 MVA (uk 13 %, ur 0,3 %, YNd5) - nodo
GEN - generatore 10,5 kV 100 MVA (x"d 17 %, cosφ 0,85).
Impedenze in Ω, aritmetica complessa semplice.
"""

import copy
import math

import pytest

from iec60909 import calculate, factors, network_from_dict
from iec60909.calc import _Builder

from .reti import RETE_GRUPPO_GENERAZIONE

UN_Q = 110.0
UN_G = 10.5
UR_THV, UR_TLV = 115.0, 10.5
TR = UR_THV / UR_TLV  # rapporto nominale t_r
SIN_PHI = math.sqrt(1 - 0.85**2)
XD = 0.17
XT = math.sqrt(13.0**2 - 0.3**2) / 100
C_MAX = 1.1


def _rete(**gen):
    data = copy.deepcopy(RETE_GRUPPO_GENERAZIONE)
    data["generators"][0].update(gen)
    return data


def _z_rete(case="max"):
    """Rete di alimentazione + linea, in Ω a 110 kV."""
    if case == "max":
        c, skq, rx, k_theta = 1.1, 3000.0, 0.1, 1.0
    else:
        c, skq, rx, k_theta = 1.0, 2000.0, 0.12, 1.0 + 0.004 * (80 - 20)
    zq = c * UN_Q**2 / skq
    xq = zq / math.sqrt(1 + rx**2)
    return complex(rx * xq, xq) + 20 * complex(0.12 * k_theta, 0.39)


def _z_trafo_hv():
    zr = UR_THV**2 / 100.0
    rt = 0.003 * zr
    return complex(rt, math.sqrt((0.13 * zr) ** 2 - rt**2))


def _z_gen():
    return complex(0.0094, XD * UN_G**2 / 100.0)


def _k_s():
    return (UN_Q**2 / UN_G**2) * (UR_TLV**2 / UR_THV**2) * C_MAX / (1 + abs(XD - XT) * SIN_PHI)


def _k_so(pg=0.0, pt=0.0):
    return UN_Q / (UN_G * (1 + pg)) * (UR_TLV / UR_THV) * (1 - pt) * C_MAX / (1 + XD * SIN_PHI)


def _ik(c, un_kv, z):
    return c * un_kv / (math.sqrt(3) * abs(z))


def _parallelo(*zs):
    return 1 / sum(1 / z for z in zs)


# --- fattori -------------------------------------------------------------------


def test_fattori_ks_kso():
    comuni = dict(
        un_q_kv=UN_Q, ur_g_kv=UN_G, ur_t_hv_kv=UR_THV, ur_t_lv_kv=UR_TLV,
        c_max_q=C_MAX, c_max_g=C_MAX, xd2_pu=XD, xt_pu=XT, cos_phi=0.85,
    )
    k_s, k_gs, k_ts = factors.power_station_factors(oltc=True, **comuni)
    assert k_s == pytest.approx(_k_s(), rel=1e-12)
    assert k_s == pytest.approx((110 / 115) ** 2 * 1.1 / (1 + abs(XD - XT) * SIN_PHI), rel=1e-12)
    assert k_gs == pytest.approx(1.1 / (1 + XD * SIN_PHI), rel=1e-12)
    assert k_ts == pytest.approx(1.1 / (1 - XT * SIN_PHI), rel=1e-12)

    k_so, k_gso, k_tso = factors.power_station_factors(oltc=False, pg=0.05, pt=0.025, **comuni)
    assert k_so == pytest.approx(_k_so(0.05, 0.025), rel=1e-12)
    assert k_so == pytest.approx(
        110 / (10.5 * 1.05) * (10.5 / 115) * 0.975 * 1.1 / (1 + XD * SIN_PHI), rel=1e-12
    )
    assert k_gso == pytest.approx(k_gs / 1.05, rel=1e-12)
    assert k_tso == pytest.approx(k_ts / 1.05, rel=1e-12)


# --- guasti fuori dal gruppo ---------------------------------------------------


@pytest.mark.parametrize(
    "gen, k",
    [
        (dict(oltc=True), _k_s()),
        (dict(oltc=False, pg_percent=5.0), _k_so(pg=0.05)),
        (dict(oltc=False, pt_percent=2.5), _k_so(pt=0.025)),
    ],
)
def test_trifase_nodo_at_fuori_dal_gruppo(gen, k):
    """Z_S = K·(t_r²·Z_G + Z_THV) in parallelo alla rete (rete + linea)."""
    z_s = k * (TR**2 * _z_gen() + _z_trafo_hv())
    r = calculate(network_from_dict(_rete(**gen))).bus("AT2")
    z = _parallelo(_z_rete(), z_s)
    assert r.z1_ohm == pytest.approx(z, rel=1e-9)
    assert r.ikss3_ka == pytest.approx(_ik(1.1, UN_Q, z), rel=1e-9)


def test_trifase_nodo_at_caso_minimo():
    """Nel caso minimo K_S resta calcolato con cmax; il guasto usa cmin = 1,0."""
    z_s = _k_s() * (TR**2 * _z_gen() + _z_trafo_hv())
    r = calculate(network_from_dict(_rete(oltc=True)), "min").bus("AT2")
    z = _parallelo(_z_rete("min"), z_s)
    assert r.ikss3_ka == pytest.approx(_ik(1.0, UN_Q, z), rel=1e-9)


def test_trasformatore_del_gruppo_senza_kt():
    """Il trasformatore del gruppo usa K_S (o K_T,S), mai K_T; il generatore non usa K_G."""
    net = network_from_dict(_rete(oltc=True))
    b = _Builder(net, "max", [])
    t, g = net.transformers[0], net.generators[0]
    z_t_lv = _z_trafo_hv() / TR**2
    z1, z0, _ = b._transformer_data(t)
    assert z1 * b.zbase("GEN") == pytest.approx(_k_s() * z_t_lv, rel=1e-12)
    assert z0 * b.zbase("GEN") == pytest.approx(_k_s() * z_t_lv, rel=1e-12)  # uk0 = uk
    k_t = factors.transformer_kt(1.1, XT)
    assert abs(z1 * b.zbase("GEN") - k_t * z_t_lv) > 1e-3 * abs(z_t_lv)
    assert b.generator_z(g, 1) * b.zbase("GEN") == pytest.approx(_k_s() * _z_gen(), rel=1e-12)

    # senza gruppo lo stesso trasformatore riceve K_T e il generatore K_G
    plain = _rete(unit_transformer=None)
    b2 = _Builder(network_from_dict(plain), "max", [])
    z1b, _, _ = b2._transformer_data(network_from_dict(plain).transformers[0])
    assert z1b * b2.zbase("GEN") == pytest.approx(k_t * z_t_lv, rel=1e-12)


# --- guasto all'interno del gruppo (nodo del generatore) -----------------------


@pytest.mark.parametrize("oltc, pg", [(True, 0.0), (False, 0.0), (False, 5.0)])
def test_trifase_nodo_generatore(oltc, pg):
    """I"k = contributo del generatore (K_G,S) + contributo della rete attraverso
    il trasformatore (K_T,S), con la rete riportata al lato BT con 1/t_r²."""
    scale = 1.0 if oltc else 1 / (1 + pg / 100)
    k_gs = scale * C_MAX / (1 + XD * SIN_PHI)
    k_ts = scale * C_MAX / (1 - XT * SIN_PHI)
    z_g = k_gs * _z_gen()
    z_rt = k_ts * _z_trafo_hv() / TR**2 + _z_rete() / TR**2
    r = calculate(network_from_dict(_rete(oltc=oltc, pg_percent=pg))).bus("GEN")

    i_g = 1.1 * UN_G / (math.sqrt(3) * z_g)
    i_t = 1.1 * UN_G / (math.sqrt(3) * z_rt)
    assert r.ikss3_ka == pytest.approx(abs(i_g + i_t), rel=1e-9)
    assert r.z1_ohm == pytest.approx(_parallelo(z_g, z_rt), rel=1e-9)
    # la somma algebrica della norma (I"kG + I"kT) differisce di poco (correnti quasi in fase)
    assert r.ikss3_ka == pytest.approx(abs(i_g) + abs(i_t), rel=2e-3)
    # pT non interviene nei guasti interni
    if not oltc:
        r_pt = calculate(network_from_dict(_rete(oltc=False, pg_percent=pg, pt_percent=2.5)))
        assert r_pt.bus("GEN").ikss3_ka == pytest.approx(r.ikss3_ka, rel=1e-12)


def test_nodo_generatore_non_altera_i_nodi_esterni():
    """Il calcolo interno sostituisce solo il nodo del generatore."""
    r = calculate(network_from_dict(_rete(oltc=True)))
    z_s = _k_s() * (TR**2 * _z_gen() + _z_trafo_hv())
    z_at = _parallelo(_z_rete() - 20 * complex(0.12, 0.39), 20 * complex(0.12, 0.39) + z_s)
    assert r.bus("AT").ikss3_ka == pytest.approx(_ik(1.1, UN_Q, z_at), rel=1e-9)


# --- corrente di interruzione --------------------------------------------------


def test_corrente_di_interruzione_nodo_at():
    r = calculate(network_from_dict(_rete(oltc=True)), tmin_s=0.1).bus("AT2")
    i_rete = _ik(1.1, UN_Q, _z_rete())
    # contributo del gruppo ben oltre 2·IrG: μ < 1, Ib ridotta
    assert r.ib_ka < r.ikss3_ka
    assert r.ib_ka >= i_rete
    # con tmin < 0,02 s nessun decadimento
    r0 = calculate(network_from_dict(_rete(oltc=True)), tmin_s=0.01).bus("AT2")
    assert r0.ib_ka == pytest.approx(r0.ikss3_ka, rel=1e-12)


# --- validazione ---------------------------------------------------------------


def test_errore_trasformatore_inesistente():
    with pytest.raises(ValueError, match="trasformatore del gruppo inesistente"):
        calculate(network_from_dict(_rete(unit_transformer="TX")))


def test_errore_lato_bt_non_sul_nodo_del_generatore():
    data = _rete()
    data["buses"].append({"id": "GEN2", "un_kv": 10.5})
    data["transformers"].append(
        {"id": "TG2", "hv_bus": "AT2", "lv_bus": "GEN2", "sr_mva": 100, "ur_hv_kv": 115,
         "ur_lv_kv": 10.5, "ukr_percent": 13, "urr_percent": 0.3, "vector_group": "YNd5"}
    )
    data["generators"][0]["unit_transformer"] = "TG2"
    with pytest.raises(ValueError, match="lato BT di TG2"):
        calculate(network_from_dict(data))


def test_errore_trasformatore_in_parallelo():
    data = _rete()
    data["transformers"][0]["parallel"] = 2
    with pytest.raises(ValueError, match="parallel > 1"):
        calculate(network_from_dict(data))


def test_errore_trasformatore_in_due_gruppi():
    data = _rete()
    data["generators"].append(dict(data["generators"][0], id="G2"))
    with pytest.raises(ValueError, match="assegnato a più gruppi"):
        calculate(network_from_dict(data))
