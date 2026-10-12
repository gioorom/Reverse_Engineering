"""Verifiche con calcoli a mano sulle formule della IEC 60909-0."""

import math

import pytest

from iec60909 import calculate, factors, load_network, network_from_dict
from iec60909.network import Bus, ExternalGrid, Line, Network, Transformer

ESEMPIO = __file__.rsplit("/", 2)[0] + "/esempi/cabina_mt_bt.json"


def _cabina(**trafo):
    data = dict(
        id="TR", hv_bus="MT", lv_bus="BT", sr_mva=0.63, ur_hv_kv=20.0, ur_lv_kv=0.4,
        ukr_percent=6.0, urr_percent=1.03, vector_group="Dyn11",
    )
    data.update(trafo)
    return Network(
        buses=[Bus("MT", 20.0), Bus("BT", 0.4)],
        external_grids=[ExternalGrid("Q", "MT", skq_max_mva=500.0, rx_max=0.1)],
        transformers=[Transformer(**data)],
    )


def test_fattori_di_tensione():
    assert factors.voltage_factor(0.4, "max", 6) == 1.05
    assert factors.voltage_factor(0.4, "min", 6) == 0.95
    assert factors.voltage_factor(0.4, "max", 10) == 1.10
    assert factors.voltage_factor(0.4, "min", 10) == 0.90
    assert factors.voltage_factor(20.0, "max") == 1.10
    assert factors.voltage_factor(20.0, "min") == 1.00
    with pytest.raises(ValueError):
        factors.voltage_factor(0.4, "max", 8)


def test_kappa_e_m():
    assert factors.kappa(0.0) == pytest.approx(2.0)
    assert factors.kappa(0.1) == pytest.approx(1.02 + 0.98 * math.exp(-0.3))
    assert factors.thermal_m(2.0, 50, 1.0) == pytest.approx(2.0)
    # continuità attorno a κ = 2
    assert factors.thermal_m(2.0 - 1e-9, 50, 1.0) == pytest.approx(2.0, rel=1e-5)
    assert factors.thermal_m(1.0, 50, 1.0) == 0.0


def test_cabina_trifase_a_mano():
    """Rete 500 MVA + trasformatore 630 kVA, guasto sulle sbarre BT."""
    r = calculate(_cabina()).bus("BT")
    c = 1.05
    zq = 1.1 * 0.4**2 / 500.0
    xq = zq / math.sqrt(1.01)
    zt = 0.06 * 0.16 / 0.63
    rt = 0.0103 * 0.16 / 0.63
    xt = math.sqrt(zt**2 - rt**2)
    kt = 0.95 * 1.05 / (1 + 0.6 * math.sqrt(6.0**2 - 1.03**2) / 100)
    zk = complex(0.1 * xq + kt * rt, xq + kt * xt)
    ik3 = c * 0.4 / (math.sqrt(3) * abs(zk))
    assert r.ikss3_ka == pytest.approx(ik3, rel=1e-9)
    assert r.ikss2_ka == pytest.approx(math.sqrt(3) / 2 * ik3, rel=1e-9)
    # Dyn: Z0 = Z_T (K_T incluso), la rete MT non entra in sequenza zero
    z0 = kt * complex(rt, xt)
    ik1 = math.sqrt(3) * c * 0.4 / abs(2 * zk + z0)
    assert r.ikss1_ka == pytest.approx(ik1, rel=1e-9)
    ike = math.sqrt(3) * c * 0.4 / abs(zk + 2 * z0)  # Z1 = Z2
    assert r.ikss2e_earth_ka == pytest.approx(ike, rel=1e-9)
    assert r.ip3_ka == pytest.approx(factors.kappa(zk.real / zk.imag) * math.sqrt(2) * ik3, rel=1e-9)
    assert r.ik_ka == pytest.approx(ik3, rel=1e-9)


def test_guasto_bifase_a_terra_correnti_di_fase():
    r = calculate(_cabina()).bus("BT")
    assert r.ikss2e_l2_ka > 0 and r.ikss2e_l3_ka > 0
    # con Z0 → ∞ le correnti di fase tendono a quelle del guasto bifase
    r_iso = calculate(_cabina(vector_group="Dy5")).bus("BT")
    assert r_iso.ikss1_ka == 0.0
    assert r_iso.z0_ohm is None


def test_gruppi_vettoriali_sequenza_zero():
    # YNd: messa a terra lato MT, nessun percorso lato BT
    assert calculate(_cabina(vector_group="YNd5")).bus("BT").ikss1_ka == 0.0
    assert calculate(_cabina(vector_group="YNd5")).bus("MT").ikss1_ka > 0.0
    # Dd e Yy: nessuna corrente monofase
    for group in ("Dd0", "Yy0", "Yyn0"):
        assert calculate(_cabina(vector_group=group)).bus("BT").ikss1_ka == 0.0


def test_impedenza_di_neutro():
    base = calculate(_cabina()).bus("BT")
    zn = calculate(_cabina(zn_lv_ohm=complex(0.01, 0))).bus("BT")
    zk = base.z1_ohm
    z0 = zn.z0_ohm
    assert z0 == pytest.approx(base.z0_ohm + 0.03, rel=1e-9)
    assert zn.ikss1_ka == pytest.approx(math.sqrt(3) * 1.05 * 0.4 / abs(2 * zk + z0), rel=1e-9)


def test_ynyn_serie_in_sequenza_zero():
    net = _cabina(vector_group="YNyn0")
    net.external_grids[0].x0x1 = 1.0
    net.external_grids[0].r0x0 = 0.1
    r = calculate(net).bus("BT")
    # Z0 = Z0Q (riferita alla BT) + Z0T
    zq = 1.1 * 0.4**2 / 500.0
    xq = zq / math.sqrt(1.01)
    zt = calculate(_cabina()).bus("BT").z0_ohm  # Z0T con K_T
    assert r.z0_ohm == pytest.approx(complex(0.1 * xq, xq) + zt, rel=1e-9)


def test_caso_minimo_temperatura_linea():
    net = _cabina()
    net.buses.append(Bus("QD", 0.4))
    net.lines.append(Line("C", "BT", "QD", 0.1, 0.1, 0.08, 0.4, 0.32, end_temperature_c=160))
    r_min = calculate(net, "min").bus("QD")
    zq = 1.0 * 0.4**2 / 500.0
    xq = zq / math.sqrt(1.01)
    zt = 0.06 * 0.16 / 0.63
    rt = 0.0103 * 0.16 / 0.63
    xt = math.sqrt(zt**2 - rt**2)
    rl = 0.1 * 0.1 * (1 + 0.004 * 140)
    zk = complex(0.1 * xq + rt + rl, xq + xt + 0.008)  # niente K_T nel caso minimo
    assert r_min.ikss3_ka == pytest.approx(0.95 * 0.4 / (math.sqrt(3) * abs(zk)), rel=1e-9)


def test_rapporto_fuori_nominale():
    # Trasformatore 21/0,42 kV su rete 20/0,4 kV: la rete MT riferita con t_r = 50
    net = _cabina(ur_hv_kv=21.0, ur_lv_kv=0.42)
    r = calculate(net).bus("BT")
    zq = 1.1 * 20.0**2 / 500.0 / 50.0**2
    xq = zq / math.sqrt(1.01)
    zr = 0.42**2 / 0.63
    zt = 0.06 * zr
    rt = 0.0103 * zr
    xt = math.sqrt(zt**2 - rt**2)
    kt = 0.95 * 1.05 / (1 + 0.6 * math.sqrt(6.0**2 - 1.03**2) / 100)
    zk = complex(0.1 * xq + kt * rt, xq + kt * xt)
    assert r.ikss3_ka == pytest.approx(1.05 * 0.4 / (math.sqrt(3) * abs(zk)), rel=1e-9)


def test_esempio_e_validazione_input():
    result = calculate(load_network(ESEMPIO))
    assert result.bus("QGBT").ikss3_ka > result.bus("QD1").ikss3_ka
    with pytest.raises(ValueError, match="campi sconosciuti"):
        network_from_dict({"buses": [{"id": "A", "un_kv": 20, "xx": 1}]})
    with pytest.raises(ValueError, match="nodo inesistente"):
        calculate(network_from_dict({
            "buses": [{"id": "A", "un_kv": 20}],
            "external_grids": [{"id": "Q", "bus": "Z", "skq_max_mva": 100}],
        }))
