"""Fattore n della corrente termica equivalente (effetto della componente alternata).

n = (1/(I"k²·Tk))·∫0^Tk i_ac(t)² dt, con i_ac = Ik + (I'k − Ik)·e^(−t/T'd) +
(I"k − I'k)·e^(−t/T"d) e le ipotesi delle curve della norma: I"k/I'k = 1,12,
T'd = 3,1 s·Ik/I'k, T"d = T'd/10. Verifica con integrazione numerica
indipendente e con i limiti per Tk → 0 e Tk → ∞.
"""

import math

import numpy as np
import pytest

from iec60909 import calculate, factors

from .test_ib_ik import XD_SAT, _rete_generatore


def _n_numerico(x, tk, punti=200_001):
    xp = x / 1.12
    td1 = 3.1 / xp
    td2 = td1 / 10
    t = np.linspace(0.0, tk, punti)
    i = 1.0 + (xp - 1.0) * np.exp(-t / td1) + (x - xp) * np.exp(-t / td2)
    y = i**2
    integrale = float(np.sum((y[1:] + y[:-1]) * np.diff(t)) / 2)  # trapezi
    return integrale / (tk * x**2)


@pytest.mark.parametrize("x", [1.5, 2.0, 3.0, 4.0, 6.0])
@pytest.mark.parametrize("tk", [0.05, 0.2, 0.5, 1.0, 3.0])
def test_n_uguale_all_integrale(x, tk):
    assert factors.thermal_n(x, tk) == pytest.approx(_n_numerico(x, tk), rel=1e-6)


def test_n_lontano_dai_generatori():
    assert factors.thermal_n(1.0, 1.0) == 1.0
    assert factors.thermal_n(0.8, 1.0) == 1.0


def test_n_limiti():
    # Tk → 0: la componente alternata vale ancora I"k
    assert factors.thermal_n(4.0, 1e-7) == pytest.approx(1.0, rel=1e-5)
    # Tk → ∞: resta solo Ik, n → (Ik/I"k)²
    assert factors.thermal_n(4.0, 1e5) == pytest.approx(1 / 16, rel=1e-3)


def test_n_decrescente():
    tks = [0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
    for x in (2.0, 4.0, 6.0):
        valori = [factors.thermal_n(x, tk) for tk in tks]
        assert all(a > b for a, b in zip(valori, valori[1:]))
    for tk in (0.1, 1.0):
        valori = [factors.thermal_n(x, tk) for x in (1.25, 2.0, 4.0, 6.0)]
        assert all(a > b for a, b in zip(valori, valori[1:]))


def test_ith_generatore_singolo():
    """Guasto alimentato da un solo generatore: Ith = I"k·√(m + n), n da I"k/Ik."""
    res = calculate(_rete_generatore(xd_sat_percent=100 * XD_SAT), tk_s=0.5).bus("A")
    n = factors.thermal_n(res.ikss3_ka / res.ik_ka, 0.5)
    m = factors.thermal_m(res.kappa, 50.0, 0.5)
    assert n < 1.0
    assert res.ith_ka == pytest.approx(res.ikss3_ka * math.sqrt(m + n), rel=1e-12)


def test_ith_senza_ik_usa_n_uguale_a_1():
    res = calculate(_rete_generatore(), tk_s=0.5).bus("A")
    assert res.ik_ka is None
    m = factors.thermal_m(res.kappa, 50.0, 0.5)
    assert res.ith_ka == pytest.approx(res.ikss3_ka * math.sqrt(m + 1.0), rel=1e-12)
