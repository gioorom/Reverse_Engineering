"""Avvolgimenti a zig-zag e trasformatori di messa a terra."""

import math

import pytest

from iec60909 import calculate, network_from_dict
from iec60909.network import (
    Bus,
    EarthingTransformer,
    ExternalGrid,
    Network,
    Transformer,
    Transformer3W,
)

SQ3 = math.sqrt(3)


def _cabina(gruppo, uk0=1.0, ur0=0.3, zn_lv=0.0, zn_hv=0.0, x0x1=1.0):
    return Network(
        buses=[Bus("MT", 20.0), Bus("BT", 0.4)],
        external_grids=[ExternalGrid("Q", "MT", skq_max_mva=500.0, rx_max=0.1, x0x1=x0x1, r0x0=0.1)],
        transformers=[Transformer("TR", "MT", "BT", 0.63, 20.0, 0.4, 6.0, 1.03, gruppo,
                                  uk0_percent=uk0, ur0_percent=ur0,
                                  zn_lv_ohm=zn_lv, zn_hv_ohm=zn_hv)],
    )


def _kt():
    return 0.95 * 1.05 / (1 + 0.6 * math.sqrt(6.0**2 - 1.03**2) / 100)


def _z0_trafo(un_kv, kt):
    """Impedenza omopolare del trasformatore (uk0 1 %, ur0 0,3 %) riferita a un lato."""
    zr = un_kv**2 / 0.63
    return kt * complex(0.003 * zr, math.sqrt(0.01**2 - 0.003**2) * zr)


def test_dzn_derivazione_sul_lato_bt():
    r = calculate(_cabina("Dzn0", zn_lv=0.002)).bus("BT")
    z0 = _z0_trafo(0.4, _kt()) + 3 * 0.002
    assert r.z0_ohm == pytest.approx(z0, rel=1e-9)
    z1, z2 = r.z1_ohm, r.z2_ohm
    assert r.ikss1_ka == pytest.approx(SQ3 * 1.05 * 0.4 / abs(z1 + z2 + z0), rel=1e-9)
    # il lato MT non vede il trasformatore in sequenza zero (rete con x0x1)
    mt = calculate(_cabina("Dzn0")).bus("MT")
    assert mt.z0_ohm == pytest.approx(calculate(_cabina("Dd0")).bus("MT").z0_ohm, rel=1e-12)


def test_ynzn_lati_disaccoppiati():
    """YNzn: la stella AT non trasferisce l'omopolare (lo zig-zag la compensa)."""
    ynzn = calculate(_cabina("YNzn11"))
    assert ynzn.bus("MT").z0_ohm == pytest.approx(calculate(_cabina("Dd0")).bus("MT").z0_ohm, rel=1e-12)
    assert ynzn.bus("BT").z0_ohm == pytest.approx(_z0_trafo(0.4, _kt()), rel=1e-9)
    # con YNyn invece il lato BT vede anche la rete MT
    assert calculate(_cabina("YNyn0")).bus("BT").z0_ohm != pytest.approx(ynzn.bus("BT").z0_ohm)


def test_zn_sul_lato_at_e_zig_zag_senza_neutro():
    r = calculate(_cabina("ZNd5", zn_hv=10.0)).bus("MT")
    zq0 = 1.1 * 20.0**2 / 500.0 / math.sqrt(1.01) * complex(0.1, 1.0)  # x0x1 = 1, r0x0 = 0,1
    z0_zz = _z0_trafo(20.0, _kt()) + 30.0
    assert r.z0_ohm == pytest.approx(zq0 * z0_zz / (zq0 + z0_zz), rel=1e-9)
    # zig-zag senza neutro: nessun percorso verso terra
    assert calculate(_cabina("Dz0")).bus("BT").ikss1_ka == 0.0
    # in sequenza diretta lo zig-zag si comporta come una stella
    assert calculate(_cabina("Dzn0")).bus("BT").z1_ohm == pytest.approx(
        calculate(_cabina("Dyn11")).bus("BT").z1_ohm, rel=1e-12
    )


def test_caso_minimo_senza_kt():
    r = calculate(_cabina("Dzn0"), "min").bus("BT")
    assert r.z0_ohm == pytest.approx(_z0_trafo(0.4, 1.0), rel=1e-9)


def test_trasformatore_di_messa_a_terra():
    """Rete MT a neutro isolato (Dd) con zig-zag di messa a terra sul nodo MT."""
    rete = _cabina("Dd0", x0x1=None)
    rete.external_grids[0].x0x1 = None
    assert calculate(rete).bus("MT").ikss1_ka == 0.0
    rete.earthing_transformers.append(EarthingTransformer("ZZ", "MT", z0_ohm=(1.0, 12.0), zn_ohm=20.0))
    r = calculate(rete).bus("MT")
    z0 = complex(1.0, 12.0) + 60.0
    assert r.z0_ohm == pytest.approx(z0, rel=1e-12)
    assert r.ikss1_ka == pytest.approx(SQ3 * 1.1 * 20.0 / abs(r.z1_ohm + r.z2_ohm + z0), rel=1e-9)
    # nessun effetto sulle sequenze diretta e inversa
    assert r.ikss3_ka == pytest.approx(calculate(_cabina("Dd0")).bus("MT").ikss3_ka, rel=1e-12)


def test_json_e_validazione():
    data = {
        "buses": [{"id": "MT", "un_kv": 20.0}],
        "external_grids": [{"id": "Q", "bus": "MT", "skq_max_mva": 500}],
        "earthing_transformers": [{"id": "ZZ", "bus": "MT", "z0_ohm": [1.0, 12.0], "zn_ohm": [20.0, 0.0]}],
    }
    assert calculate(network_from_dict(data)).bus("MT").ikss1_ka > 0
    data["earthing_transformers"][0]["z0_ohm"] = [1.0, 0.0]
    with pytest.raises(ValueError, match="z0_ohm"):
        calculate(network_from_dict(data))
    rete = Network(
        buses=[Bus("A", 132.0), Bus("B", 20.0), Bus("C", 10.0)],
        external_grids=[ExternalGrid("Q", "A", skq_max_mva=3000.0)],
        transformers3w=[Transformer3W("T", "A", "B", "C", 132, 20, 10, 40, 10, 10,
                                      12, 18, 6, 0.4, 0.5, 0.4, vector_group="YNznd5")],
    )
    with pytest.raises(ValueError, match="zig-zag"):
        calculate(rete)
