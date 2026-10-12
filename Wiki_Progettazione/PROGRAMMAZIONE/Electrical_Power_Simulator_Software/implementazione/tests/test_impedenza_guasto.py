"""Guasti attraverso un'impedenza di guasto Z_F (in serie a ogni fase guasta)."""

import math

import pytest

from iec60909 import calculate, factors
from iec60909.network import Bus, ExternalGrid, Network, Transformer

SQ3 = math.sqrt(3)
ZF = complex(0.004, 0.002)  # Ω, guasto BT con arco/contatto


def _cabina(gruppo="Dyn11"):
    return Network(
        buses=[Bus("MT", 20.0), Bus("BT", 0.4)],
        external_grids=[ExternalGrid("Q", "MT", skq_max_mva=500.0, rx_max=0.1)],
        transformers=[Transformer("TR", "MT", "BT", 0.63, 20.0, 0.4, 6.0, 1.03, gruppo)],
    )


def test_correnti_iniziali_a_mano():
    franco = calculate(_cabina()).bus("BT")
    r = calculate(_cabina(), zf_ohm=ZF).bus("BT")
    z1, z2, z0 = franco.z1_ohm, franco.z2_ohm, franco.z0_ohm
    c, un = 1.05, 0.4
    assert r.ikss3_ka == pytest.approx(c * un / (SQ3 * abs(z1 + ZF)), rel=1e-9)
    assert r.ikss2_ka == pytest.approx(c * un / abs(z1 + z2 + 2 * ZF), rel=1e-9)
    assert r.ikss1_ka == pytest.approx(SQ3 * c * un / abs(z1 + z2 + z0 + 3 * ZF), rel=1e-9)
    a, b_, o = z1 + ZF, z2 + ZF, z0 + ZF
    ike = SQ3 * c * un * abs(b_) / abs(a * b_ + a * o + b_ * o)
    assert r.ikss2e_earth_ka == pytest.approx(ike, rel=1e-9)
    # le impedenze riportate restano quelle della rete
    assert r.z1_ohm == pytest.approx(z1, rel=1e-12)
    assert r.ikss3_ka < franco.ikss3_ka and r.ikss1_ka < franco.ikss1_ka


def test_bifase_a_terra_senza_percorso_verso_terra():
    r = calculate(_cabina("Dy5"), zf_ohm=ZF).bus("BT")
    assert r.ikss1_ka == 0.0 and r.ikss2e_earth_ka == 0.0
    assert r.ikss2e_l2_ka == pytest.approx(r.ikss2_ka, rel=1e-12)


@pytest.mark.parametrize("metodo", ["B", "C"])
def test_picco_rete_radiale(metodo):
    """Rete solo radiale: con il metodo C R/X coincide con quello di Z1 + Z_F."""
    r = calculate(_cabina(), kappa_method=metodo, zf_ohm=ZF).bus("BT")
    z = r.z1_ohm + ZF
    k = factors.kappa(z.real / z.imag)
    if metodo == "B":
        k = min(1.15 * k, 1.8)
    assert r.kappa == pytest.approx(k, rel=1e-9)
    assert r.ip3_ka == pytest.approx(k * math.sqrt(2) * r.ikss3_ka, rel=1e-9)


def test_ib_ik_e_componente_continua():
    r = calculate(_cabina(), tmin_s=0.05, zf_ohm=ZF).bus("BT")
    z = r.z1_ohm + ZF
    assert r.ib_ka == pytest.approx(r.ikss3_ka, rel=1e-12)  # nessuna macchina
    assert r.ik_ka == pytest.approx(r.ikss3_ka, rel=1e-12)
    idc = math.sqrt(2) * r.ikss3_ka * math.exp(-2 * math.pi * 50 * 0.05 * z.real / z.imag)
    assert r.idc_ka == pytest.approx(idc, rel=1e-9)


def test_zf_nulla_e_resistenza_negativa():
    a = calculate(_cabina()).bus("BT")
    b = calculate(_cabina(), zf_ohm=0).bus("BT")
    assert a == b
    with pytest.raises(ValueError, match="negativa"):
        calculate(_cabina(), zf_ohm=complex(-0.1, 0))
