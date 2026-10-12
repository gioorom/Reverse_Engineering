"""Generatori statici: convertitori pieni (PF) ed eolico a doppia alimentazione (WD)."""

import math

import pytest

from iec60909 import calculate, factors
from iec60909.network import Bus, ExternalGrid, Line, Network, StaticGenerator

SQ3 = math.sqrt(3)
UN = 20.0
C = 1.1


def _rete(*generatori, km=5.0):
    """Rete 20 kV: Q (300 MVA) – linea – nodo B con i generatori statici."""
    return Network(
        buses=[Bus("A", UN), Bus("B", UN)],
        external_grids=[ExternalGrid("Q", "A", skq_max_mva=300.0, rx_max=0.1)],
        lines=[Line("L", "A", "B", km, 0.2, 0.35, 0.6, 1.05)],
        static_generators=list(generatori),
    )


def _zq():
    z = C * UN**2 / 300.0
    x = z / math.sqrt(1.01)
    return complex(0.1 * x, x)


ZL = complex(0.2, 0.35) * 5.0


def test_convertitore_pieno_trifase_a_mano():
    pf = StaticGenerator("PV", "B", "PF", ikss_ka=0.4)
    r = calculate(_rete(pf))
    # guasto in B: E = c·Un/√3 + |Z_BB|·I_PF (sorgente nel nodo guasto)
    zbb = _zq() + ZL
    e = C * UN / SQ3 + abs(zbb) * 0.4
    assert r.bus("B").ikss3_ka == pytest.approx(e / abs(zbb), rel=1e-9)
    assert r.bus("B").ikss3_ka == pytest.approx(C * UN / (SQ3 * abs(zbb)) + 0.4, rel=1e-9)
    # guasto in A: la sorgente in B vede Z_AB = Z_AA (rete radiale)
    za = _zq()
    assert r.bus("A").ikss3_ka == pytest.approx(C * UN / (SQ3 * abs(za)) + 0.4, rel=1e-9)


def test_convertitore_pieno_guasti_dissimmetrici_e_picco():
    pf = StaticGenerator("PV", "B", "PF", ikss_ka=0.4)
    rete = calculate(_rete()).bus("B")
    r = calculate(_rete(pf)).bus("B")
    zbb = _zq() + ZL
    e = C + abs(zbb) / (UN**2 / 100) * 0.4 / (100 / (SQ3 * UN))  # p.u. su 100 MVA
    rapporto = e / C
    assert r.ikss2_ka == pytest.approx(rete.ikss2_ka * rapporto, rel=1e-9)
    # monofase: nessun percorso verso terra nella rete di prova (Q senza dati omopolari)
    assert r.ikss1_ka == 0.0
    # ip: κ solo sulla quota della rete; i_DC solo della rete
    assert r.ip3_ka == pytest.approx(
        math.sqrt(2) * (rete.kappa * rete.ikss3_ka + (r.ikss3_ka - rete.ikss3_ka)), rel=1e-9
    )
    assert r.idc_ka == pytest.approx(rete.idc_ka, rel=1e-9)
    # Ib e Ik: la quota del convertitore non decade
    assert r.ib_ka == pytest.approx(rete.ib_ka + 0.4, rel=1e-9)
    assert r.ik_ka == pytest.approx(rete.ik_ka + 0.4, rel=1e-9)


def test_convertitore_pieno_escluso_nel_caso_minimo():
    pf = StaticGenerator("PV", "B", "PF", ikss_ka=0.4)
    assert calculate(_rete(pf), "min").bus("B").ikss3_ka == pytest.approx(
        calculate(_rete(), "min").bus("B").ikss3_ka, rel=1e-12
    )


def test_somma_in_modulo_di_piu_convertitori():
    a = StaticGenerator("PV1", "A", "PF", ikss_ka=0.3)
    b = StaticGenerator("PV2", "B", "PF", ikss_ka=0.2, count=2)
    r = calculate(_rete(a, b)).bus("B")
    zbb = _zq() + ZL
    za_b = _zq()  # Z_AB
    e = C * UN / SQ3 + abs(za_b) * 0.3 + abs(zbb) * 0.4
    assert r.ikss3_ka == pytest.approx(e / abs(zbb), rel=1e-9)


def test_eolico_doppia_alimentazione_a_mano():
    wd = StaticGenerator("W", "B", "WD", kappa_wd=1.7, i_wd_max_ka=1.0, rx=0.1)
    r = calculate(_rete(wd)).bus("B")
    z = math.sqrt(2) * 1.7 * UN / (SQ3 * 1.0)
    x = z / math.sqrt(1.01)
    zwd = complex(0.1 * x, x)
    zbb = (_zq() + ZL) * zwd / (_zq() + ZL + zwd)
    assert r.ikss3_ka == pytest.approx(C * UN / (SQ3 * abs(zbb)), rel=1e-9)
    # contributo ai morsetti ≈ c·i_WDmax/(√2·κ_WD)
    contributo = C * UN / (SQ3 * abs(zwd))
    assert contributo == pytest.approx(C * 1.0 / (math.sqrt(2) * 1.7), rel=1e-12)


def test_eolico_unica_sorgente_e_dati_mancanti():
    wd = StaticGenerator("W", "B", "WD", kappa_wd=1.7, i_wd_max_ka=1.0, ur_kv=20.0)
    rete = Network(buses=[Bus("B", UN)], static_generators=[wd])
    r = calculate(rete).bus("B")
    assert r.ikss3_ka == pytest.approx(C * 1.0 / (math.sqrt(2) * 1.7), rel=1e-9)
    with pytest.raises(ValueError, match="ikss_ka"):
        calculate(_rete(StaticGenerator("PV", "B", "PF")))
    with pytest.raises(ValueError, match="kappa_wd"):
        calculate(_rete(StaticGenerator("W", "B", "WD", kappa_wd=1.7)))
    with pytest.raises(ValueError, match="tipo"):
        calculate(_rete(StaticGenerator("X", "B", "XX", ikss_ka=1.0)))
    with pytest.raises(ValueError, match="sorgenti"):
        calculate(Network(buses=[Bus("B", UN)],
                          static_generators=[StaticGenerator("PV", "B", "PF", ikss_ka=0.4)]))


def test_fattore_kappa_invariato_senza_convertitori():
    r = calculate(_rete()).bus("B")
    assert r.ip3_ka == pytest.approx(r.kappa * math.sqrt(2) * r.ikss3_ka, rel=1e-12)
    assert factors.kappa(0.0) == pytest.approx(2.0)
