"""Verifiche a mano della corrente di interruzione Ib e della corrente permanente Ik.

Tutti i calcoli di riferimento sono svolti in ohm e kA, indipendentemente dal
metodo nodale in per unità usato da ``calculate``.
"""

import math

import pytest

from iec60909 import calculate, factors
from iec60909.network import Bus, ExternalGrid, Generator, Line, Motor, Network

SQ3 = math.sqrt(3.0)


# --- fattori μ e q -------------------------------------------------------------

_MU_ATTESI = {
    0.02: (0.84, 0.26, 0.26),
    0.05: (0.71, 0.51, 0.30),
    0.10: (0.62, 0.72, 0.32),
    0.25: (0.56, 0.94, 0.38),
}
_Q_ATTESI = {0.02: (1.03, 0.12), 0.05: (0.79, 0.12), 0.10: (0.57, 0.12), 0.25: (0.26, 0.10)}


@pytest.mark.parametrize("tmin", [0.02, 0.05, 0.10, 0.25])
def test_mu_valori_tabellati(tmin):
    a, b, c = _MU_ATTESI[tmin]
    for r in (2.5, 5.0, 8.0):
        assert factors.decay_mu(r, tmin) == pytest.approx(a + b * math.exp(-c * r), rel=1e-12)


def test_mu_limiti_e_interpolazione():
    # macchina lontana dal guasto: nessun decadimento
    for tmin in (0.02, 0.05, 0.10, 0.25):
        assert factors.decay_mu(2.0, tmin) == 1.0
        assert factors.decay_mu(1.2, tmin) == 1.0
        # appena sopra 2 le curve valgono quasi 1 ma mai più di 1
        assert factors.decay_mu(2.0001, tmin) <= 1.0
    # tmin = 0,075 s: punto medio tra le curve 0,05 e 0,10
    r = 6.0
    mu05 = 0.71 + 0.51 * math.exp(-0.30 * r)
    mu10 = 0.62 + 0.72 * math.exp(-0.32 * r)
    assert factors.decay_mu(r, 0.075) == pytest.approx(0.5 * (mu05 + mu10), rel=1e-12)
    # tmin ≥ 0,25 s: curva 0,25; tmin < 0,02 s: curva 0,02
    assert factors.decay_mu(r, 0.5) == pytest.approx(0.56 + 0.94 * math.exp(-0.38 * r), rel=1e-12)
    assert factors.decay_mu(r, 0.01) == pytest.approx(0.84 + 0.26 * math.exp(-0.26 * r), rel=1e-12)


@pytest.mark.parametrize("tmin", [0.02, 0.05, 0.10, 0.25])
def test_q_valori_tabellati(tmin):
    a, b = _Q_ATTESI[tmin]
    m = 0.3  # MW per coppia polare: tutte le curve tra 0 e 1
    assert factors.decay_q(m, tmin) == pytest.approx(a + b * math.log(m), rel=1e-12)


def test_q_limiti_e_interpolazione():
    # motori grandi: q limitato a 1
    assert factors.decay_q(100.0, 0.02) == 1.0
    assert factors.decay_q(1e4, 0.25) == 1.0
    # motori molto piccoli: q limitato a 0
    assert factors.decay_q(1e-4, 0.25) == 0.0
    # interpolazione a 0,075 s
    m = 0.3
    q05 = 0.79 + 0.12 * math.log(m)
    q10 = 0.57 + 0.12 * math.log(m)
    assert factors.decay_q(m, 0.075) == pytest.approx(0.5 * (q05 + q10), rel=1e-12)
    # m = 0,005 MW: la curva 0,10 sarebbe negativa (→ 0), quella 0,05 no;
    # si interpola tra le curve già limitate
    m = 0.005
    q05 = 0.79 + 0.12 * math.log(m)
    assert 0.57 + 0.12 * math.log(m) < 0.0 < q05
    assert factors.decay_q(m, 0.075) == pytest.approx(0.5 * q05, rel=1e-12)
    assert factors.decay_q(0.3, 0.5) == pytest.approx(0.26 + 0.10 * math.log(0.3), rel=1e-12)
    with pytest.raises(ValueError):
        factors.decay_q(0.0, 0.1)
    with pytest.raises(ValueError):
        factors.decay_q(-1.0, 0.1)


# --- generatore singolo (isola) ------------------------------------------------

UN_G = 10.5  # kV, pari a Ur del generatore
SR_G = 10.0  # MVA
XD2 = 0.12
COS_G = 0.8
C_MAX_MT = 1.1
C_MIN_MT = 1.0


def _rete_generatore(km=None, **gen):
    """Generatore 10 MVA in isola sul nodo A; eventuale linea A-B di km chilometri."""
    data = dict(id="G", bus="A", sr_mva=SR_G, ur_kv=UN_G, xd2_percent=100 * XD2, cos_phi=COS_G)
    data.update(gen)
    buses = [Bus("A", UN_G)]
    lines = []
    if km is not None:
        buses.append(Bus("B", UN_G))
        lines.append(Line("L", "A", "B", length_km=km, r1_ohm_per_km=0.1, x1_ohm_per_km=0.4))
    return Network(buses=buses, generators=[Generator(**data)], lines=lines)


def _z_generatore():
    """Impedenza del generatore in Ω con K_G (Un = UrG, RGf = 0,07·X"d)."""
    xd = XD2 * UN_G**2 / SR_G
    sin_phi = math.sqrt(1 - COS_G**2)
    kg = C_MAX_MT / (1 + XD2 * sin_phi)
    return kg * complex(0.07 * xd, xd)


IR_G = SR_G / (SQ3 * UN_G)  # kA


def _ib_una_macchina(c, un, z_macchina, ik_tot, ik_macchina, mu, q=1.0):
    """Ib = I"k − (X"·I"k_i / (c·Un/√3))·(1 − μq)·I"k_i, in kA."""
    du = z_macchina.imag * ik_macchina * SQ3 / (c * un)  # ΔU"/(c·Un/√3)
    return ik_tot - du * (1 - mu * q) * ik_macchina


def test_ib_generatore_ai_morsetti():
    zg = _z_generatore()
    ik = C_MAX_MT * UN_G / (SQ3 * abs(zg))
    r = ik / IR_G
    assert r > 2
    mu = 0.62 + 0.72 * math.exp(-0.32 * r)  # tmin = 0,10 s
    res = calculate(_rete_generatore(), tmin_s=0.1).bus("A")
    assert res.ikss3_ka == pytest.approx(ik, rel=1e-9)
    ib = _ib_una_macchina(C_MAX_MT, UN_G, zg, ik, ik, mu)
    assert res.ib_ka == pytest.approx(ib, rel=1e-9)
    # con una sola macchina Ib ≈ μ·I"k (differenza dovuta a X"/|Z| < 1 per RGf ≠ 0)
    # scarto relativo (1 − μ)(1 − X"/|Z|)·I"k/Ib ≈ 1,3e-3
    assert res.ib_ka == pytest.approx(mu * ik, rel=2e-3)
    assert res.ib_ka < res.ikss3_ka


def test_ib_generatore_lontano_senza_decadimento():
    """Guasto dietro 15 km di linea: I"kG < 2·IrG, quindi Ib = I"k."""
    zg = _z_generatore()
    zl = complex(0.1, 0.4) * 15
    ik = C_MAX_MT * UN_G / (SQ3 * abs(zg + zl))
    assert ik / IR_G <= 2
    res = calculate(_rete_generatore(km=15), tmin_s=0.1).bus("B")
    assert res.ikss3_ka == pytest.approx(ik, rel=1e-9)
    assert res.ib_ka == pytest.approx(ik, rel=1e-12)


# --- rete + motore MT sullo stesso nodo -----------------------------------------

UN_M = 6.0
SKQ = 200.0
PR_M, ETA_M, COS_M, ILR_M, P_M = 5.0, 0.97, 0.86, 5.0, 2


def _rete_motore():
    return Network(
        buses=[Bus("M", UN_M)],
        external_grids=[ExternalGrid("Q", "M", skq_max_mva=SKQ, rx_max=0.1, skq_min_mva=150.0)],
        motors=[
            Motor("MM", "M", pr_mw=PR_M, ur_kv=UN_M, efficiency=ETA_M, cos_phi=COS_M,
                  ilr_ir=ILR_M, pole_pairs=P_M)
        ],
    )


def _z_rete(c, un, skq, rx=0.1):
    zq = c * un**2 / skq
    xq = zq / math.sqrt(1 + rx**2)
    return complex(rx * xq, xq)


def _z_motore():
    sr = PR_M / (ETA_M * COS_M)
    zm = UN_M**2 / (ILR_M * sr)
    xm = zm / math.sqrt(1 + 0.1**2)  # PrM/p = 2,5 MW ≥ 1 → RM/XM = 0,10
    return complex(0.1 * xm, xm), sr


def test_ib_rete_e_motore_mt():
    c = C_MAX_MT
    zq = _z_rete(c, UN_M, SKQ)
    zm, sr = _z_motore()
    zff = zq * zm / (zq + zm)
    ik = c * UN_M / (SQ3 * abs(zff))
    ikm = c * UN_M / (SQ3 * abs(zm))  # contributo del motore ai suoi morsetti
    ikq = c * UN_M / (SQ3 * abs(zq))
    irm = sr / (SQ3 * UN_M)
    r = ikm / irm
    assert r > 2
    tmin = 0.1
    mu = 0.62 + 0.72 * math.exp(-0.32 * r)
    q = 0.57 + 0.12 * math.log(PR_M / P_M)
    assert 0 < q < 1
    res = calculate(_rete_motore(), tmin_s=tmin).bus("M")
    assert res.ikss3_ka == pytest.approx(ik, rel=1e-9)
    ib = _ib_una_macchina(c, UN_M, zm, ik, ikm, mu, q)
    assert res.ib_ka == pytest.approx(ib, rel=1e-9)
    # coerenza con la formula radiale Ib = I"kQ + μ·q·I"kM
    assert res.ib_ka == pytest.approx(ikq + mu * q * ikm, rel=1e-2)


def test_ib_tmin_breve_e_caso_minimo():
    # tmin < 0,02 s: nessun decadimento
    res = calculate(_rete_motore(), tmin_s=0.01).bus("M")
    assert res.ib_ka == pytest.approx(res.ikss3_ka, rel=1e-12)
    # caso minimo: niente motori, la rete non decade → Ib = I"k della sola rete
    res = calculate(_rete_motore(), case="min", tmin_s=0.1).bus("M")
    ikq = C_MIN_MT * UN_M / (SQ3 * abs(_z_rete(C_MIN_MT, UN_M, 150.0)))
    assert res.ikss3_ka == pytest.approx(ikq, rel=1e-9)
    assert res.ib_ka == pytest.approx(ikq, rel=1e-12)


# --- corrente permanente Ik -----------------------------------------------------

def test_ik_rete_generatore_motore_senza_motori():
    """Rete su A, linea A-B, generatore e motore su B: Ik = c·Un/(√3·|Z|) senza motore."""
    un = UN_G
    net = Network(
        buses=[Bus("A", un), Bus("B", un)],
        external_grids=[ExternalGrid("Q", "A", skq_max_mva=300.0, rx_max=0.1)],
        lines=[Line("L", "A", "B", length_km=2.0, r1_ohm_per_km=0.1, x1_ohm_per_km=0.4)],
        generators=[Generator("G", "B", sr_mva=SR_G, ur_kv=UN_G, xd2_percent=100 * XD2,
                              cos_phi=COS_G)],
        motors=[Motor("MM", "B", pr_mw=2.0, ur_kv=un, efficiency=0.96, cos_phi=0.85,
                      ilr_ir=5.5, pole_pairs=2)],
    )
    zq = _z_rete(C_MAX_MT, un, 300.0)
    zl = complex(0.1, 0.4) * 2.0
    zg = _z_generatore()

    def par(a, b):
        return a * b / (a + b)

    z_b = par(zq + zl, zg)
    z_a = par(zq, zl + zg)
    res = calculate(net)
    for bus, z in (("A", z_a), ("B", z_b)):
        r = res.bus(bus)
        assert r.ik_ka == pytest.approx(C_MAX_MT * un / (SQ3 * abs(z)), rel=1e-9)
        assert r.ik_ka < r.ikss3_ka  # il motore contribuisce solo a I"k


XD_SAT = 1.8
UF = 1.3


def _xdk_pu():
    """|Z"_GK| (con K_G) in p.u. del generatore."""
    return abs(_z_generatore()) / (UN_G**2 / SR_G)


def _lambda_a_mano(r, c_modello):
    sin_phi = math.sqrt(1 - COS_G**2)
    x_e = max(0.0, c_modello / r - _xdk_pu())
    e = math.sqrt((1 + XD_SAT * sin_phi) ** 2 + (XD_SAT * COS_G) ** 2)
    return min(UF * e / (XD_SAT + x_e), r), min(1 / (XD_SAT + x_e), r)


def test_ik_generatore_singolo_ai_morsetti():
    zg = _z_generatore()
    net = _rete_generatore(xd_sat_percent=100 * XD_SAT, ufmax_ratio=UF)
    # caso massimo: I"kG/IrG con cmax
    r_max = C_MAX_MT * UN_G / (SQ3 * abs(zg)) / IR_G
    lam_max, _ = _lambda_a_mano(r_max, C_MAX_MT)
    res = calculate(net).bus("A")
    assert res.ik_ka == pytest.approx(lam_max * IR_G, rel=1e-9)
    # guasto ai morsetti: reattanza esterna nulla, λmax = Ufmax/Ufr·e_r/xd_sat
    sin_phi = math.sqrt(1 - COS_G**2)
    e = math.sqrt((1 + XD_SAT * sin_phi) ** 2 + (XD_SAT * COS_G) ** 2)
    assert lam_max == pytest.approx(UF * e / XD_SAT, rel=1e-12)
    # caso minimo: stesso c (cmin) per I"kG/IrG e per il modello: λmin = 1/xd_sat
    r_min = C_MIN_MT * UN_G / (SQ3 * abs(zg)) / IR_G
    _, lam_min = _lambda_a_mano(r_min, C_MIN_MT)
    assert lam_min == pytest.approx(1 / XD_SAT, rel=1e-12)
    res = calculate(net, case="min").bus("A")
    assert res.ik_ka == pytest.approx(lam_min * IR_G, rel=1e-9)
    assert res.ik_ka < res.ikss3_ka


def test_ik_generatore_singolo_dietro_linea():
    zg = _z_generatore()
    zl = complex(0.1, 0.4) * 5.0
    net = _rete_generatore(km=5.0, xd_sat_percent=100 * XD_SAT, ufmax_ratio=UF)
    r = C_MAX_MT * UN_G / (SQ3 * abs(zg + zl)) / IR_G
    lam_max, _ = _lambda_a_mano(r, C_MAX_MT)
    assert lam_max < r  # nessun limite da I"k
    assert calculate(net).bus("B").ik_ka == pytest.approx(lam_max * IR_G, rel=1e-9)
    r = C_MIN_MT * UN_G / (SQ3 * abs(zg + zl)) / IR_G
    _, lam_min = _lambda_a_mano(r, C_MIN_MT)
    assert calculate(net, case="min").bus("B").ik_ka == pytest.approx(lam_min * IR_G, rel=1e-9)


def test_ik_generatore_lontano_limitato_a_ikss():
    """Con 30 km di linea λmax supererebbe I"kG/IrG: Ik = I"k."""
    zg = _z_generatore()
    zl = complex(0.1, 0.4) * 30.0
    r = C_MAX_MT * UN_G / (SQ3 * abs(zg + zl)) / IR_G
    sin_phi = math.sqrt(1 - COS_G**2)
    e = math.sqrt((1 + XD_SAT * sin_phi) ** 2 + (XD_SAT * COS_G) ** 2)
    assert UF * e / (XD_SAT + C_MAX_MT / r - _xdk_pu()) > r
    res = calculate(_rete_generatore(km=30.0, xd_sat_percent=100 * XD_SAT)).bus("B")
    assert res.ik_ka == pytest.approx(r * IR_G, rel=1e-9)
    assert res.ik_ka == pytest.approx(res.ikss3_ka, rel=1e-9)


def test_ik_lambda_imposti():
    # λ imposti prevalgono su xd_sat
    net = _rete_generatore(km=5.0, xd_sat_percent=100 * XD_SAT, lambda_max=2.5, lambda_min=0.6)
    for bus in ("A", "B"):
        assert calculate(net).bus(bus).ik_ka == pytest.approx(2.5 * IR_G, rel=1e-12)
        assert calculate(net, case="min").bus(bus).ik_ka == pytest.approx(0.6 * IR_G, rel=1e-12)


def test_ik_dati_mancanti():
    res = calculate(_rete_generatore())
    assert res.bus("A").ik_ka is None
    assert any("xd_sat_percent" in w and "lambda_max" in w for w in res.warnings)
    # un solo λ imposto non basta
    res = calculate(_rete_generatore(lambda_max=2.0))
    assert res.bus("A").ik_ka is None


# --- motori BT senza coppie polari ---------------------------------------------

def test_motore_bt_senza_coppie_polari():
    un, c = 0.4, 1.05
    net = Network(
        buses=[Bus("BT", un)],
        external_grids=[ExternalGrid("Q", "BT", skq_max_mva=20.0, rx_max=0.2)],
        motors=[Motor("MB", "BT", pr_mw=0.1, ur_kv=un, efficiency=0.9, cos_phi=0.85, ilr_ir=6.0)],
    )
    tmin = 0.05
    res = calculate(net, tmin_s=tmin)
    assert any("MB" in w and "0,05 MW" in w for w in res.warnings)
    # verifica di Ib con PrM/p = 0,05 MW e RM/XM = 0,42
    zq = _z_rete(c, un, 20.0, rx=0.2)
    sr = 0.1 / (0.9 * 0.85)
    zm_abs = un**2 / (6.0 * sr)
    xm = zm_abs / math.sqrt(1 + 0.42**2)
    zm = complex(0.42 * xm, xm)
    zff = zq * zm / (zq + zm)
    ik = c * un / (SQ3 * abs(zff))
    ikm = c * un / (SQ3 * abs(zm))
    r = ikm / (sr / (SQ3 * un))
    mu = 0.71 + 0.51 * math.exp(-0.30 * r)
    q = 0.79 + 0.12 * math.log(0.05)
    assert res.bus("BT").ib_ka == pytest.approx(_ib_una_macchina(c, un, zm, ik, ikm, mu, q), rel=1e-9)
    # nel caso minimo i motori sono esclusi: nessun avviso
    assert not any("0,05 MW" in w for w in calculate(net, case="min").warnings)
