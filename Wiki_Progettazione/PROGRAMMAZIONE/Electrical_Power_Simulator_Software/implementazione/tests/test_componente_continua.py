"""Componente continua i_DC e corrente di interruzione asimmetrica."""

import math

import pytest

from iec60909 import calculate, factors
from iec60909.network import Bus, ExternalGrid, Motor, Network, Transformer


def _cabina(motore=False):
    net = Network(
        buses=[Bus("MT", 20.0), Bus("BT", 0.4)],
        external_grids=[ExternalGrid("Q", "MT", skq_max_mva=500.0, rx_max=0.1)],
        transformers=[Transformer("TR", "MT", "BT", 0.63, 20.0, 0.4, 6.0, 1.03, "Dyn11")],
    )
    if motore:
        net.motors.append(Motor("M", "BT", pr_mw=0.1, ur_kv=0.4, efficiency=0.94, cos_phi=0.86,
                                ilr_ir=7.0, pole_pairs=2))
    return net


@pytest.mark.parametrize(
    "ft, atteso", [(0.5, 0.27), (0.99, 0.27), (1.0, 0.15), (2.49, 0.15), (2.5, 0.092),
                   (4.99, 0.092), (5.0, 0.055), (50.0, 0.055)],
)
def test_rapporto_frequenza_equivalente(ft, atteso):
    assert factors.dc_frequency_ratio(ft) == atteso


@pytest.mark.parametrize("tmin", [0.01, 0.02, 0.05, 0.1])
def test_rete_radiale_usa_r_su_x_di_z1(tmin):
    """Rami solo in serie: con la frequenza equivalente R/X coincide con quello di Z1."""
    r = calculate(_cabina(), tmin_s=tmin).bus("BT")
    rx = r.z1_ohm.real / r.z1_ohm.imag
    idc = math.sqrt(2) * r.ikss3_ka * math.exp(-2 * math.pi * 50 * tmin * rx)
    assert r.idc_ka == pytest.approx(idc, rel=1e-9)
    assert r.ib_asym_ka == pytest.approx(math.hypot(r.ib_ka, idc), rel=1e-12)


def test_rami_in_parallelo_usano_la_frequenza_equivalente():
    """Con un motore in parallelo R/X dipende da fc: diverso da quello di Z1."""
    net = _cabina(motore=True)
    r = calculate(net, tmin_s=0.05).bus("BT")
    rx_z1 = r.z1_ohm.real / r.z1_ohm.imag
    idc_z1 = math.sqrt(2) * r.ikss3_ka * math.exp(-2 * math.pi * 50 * 0.05 * rx_z1)
    assert r.idc_ka != pytest.approx(idc_z1, rel=1e-6)
    # calcolo a mano: rete+trasformatore in parallelo al motore, reattanze × fc/f
    k = factors.dc_frequency_ratio(50 * 0.05)
    zq = 1.1 * 0.4**2 / 500.0
    xq = zq / math.sqrt(1.01)
    zt = 0.06 * 0.16 / 0.63
    rt = 0.0103 * 0.16 / 0.63
    xt = math.sqrt(zt**2 - rt**2)
    kt = 0.95 * 1.05 / (1 + 0.6 * math.sqrt(6.0**2 - 1.03**2) / 100)
    za = complex(0.1 * xq + kt * rt, (xq + kt * xt) * k)
    srm = 0.1 / (0.94 * 0.86)
    zm = 0.4**2 / (7.0 * srm)
    xm = zm / math.sqrt(1 + 0.42**2)
    zb = complex(0.42 * xm, xm * k)
    zc = za * zb / (za + zb)
    rx = zc.real / zc.imag * k
    assert r.idc_ka == pytest.approx(
        math.sqrt(2) * r.ikss3_ka * math.exp(-2 * math.pi * 50 * 0.05 * rx), rel=1e-9
    )


def test_componente_continua_si_smorza_nel_tempo():
    valori = [calculate(_cabina(), tmin_s=t).bus("BT").idc_ka for t in (0.01, 0.02, 0.05, 0.1)]
    assert valori == sorted(valori, reverse=True)
    assert valori[0] < math.sqrt(2) * calculate(_cabina()).bus("BT").ikss3_ka


def test_frequenza_60_hz():
    net = _cabina()
    net.f_hz = 60.0
    r = calculate(net, tmin_s=0.05).bus("BT")
    rx = r.z1_ohm.real / r.z1_ohm.imag
    assert r.idc_ka == pytest.approx(
        math.sqrt(2) * r.ikss3_ka * math.exp(-2 * math.pi * 60 * 0.05 * rx), rel=1e-9
    )
