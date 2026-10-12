"""Portate dei cavi MT/AT (IEC 60287): casi della CIGRE TB 880 (2022), "Power cable rating
examples for calculation tool verification", caso introduttivo 0: cavo 132 kV, 630 mm² Cu,
XLPE 15,5 mm, guaina di alluminio 0,8 mm, interrato a 1 m a trifoglio a contatto, terreno
20 °C e 1 K·m/W.

Valori di riferimento: risultati della brochure (803,1596 A e 679,8410 A, varianti con le
perdite per correnti parassite adottate dal WG B1.56) e, per le altre varianti, i notebook
che riproducono i casi della brochure (github.com/frdmendoza/cbl_CIGRE_TB880)."""

import math

import pytest

from iec60909.iec60287 import CableConstruction, Installation, rating

CAVO_132 = dict(area_mm2=630, conductor_diameter_mm=30.3, r20_ohm_per_km=0.0283, conductor_screen_mm=1.5,
                insulation_mm=15.5, insulation_screen_mm=1.3, insulation_tan_delta=0.001, semicon_rho_t=2.5,
                screen_kind="sheath", screen_material="al", screen_thickness_mm=0.8, oversheath_mm=3.5)
U0 = 132 / math.sqrt(3)


@pytest.mark.parametrize("posa, attesa", [
    (dict(bonding="both_ends", eddy_both_ends=True), 803.1595966445),  # TB 880 4.6.4 (CIGRE)
    (dict(bonding="both_ends"), 821.7763334392),  # 4.4-4.5, correnti parassite trascurate
    (dict(bonding="single_point"), 886.1752854720),  # 4.6.3
    (dict(kind="ducts", duct_inner_mm=119.4, duct_outer_mm=140, eddy_both_ends=True), 679.8409804502),  # 4.7.7 (CIGRE)
    (dict(kind="ducts", duct_inner_mm=119.4, duct_outer_mm=140), 682.8144648700),  # 4.7
])
def test_cigre_tb880_caso_0(posa, attesa):
    r = rating(CableConstruction(**CAVO_132), Installation(u0_kv=U0, **posa))
    assert r.current_a == pytest.approx(attesa, abs=1e-6)


def test_cigre_tb880_grandezze_intermedie():
    """Grandezze indipendenti dalla temperatura del caso 0-1 (notebook TB 880, celle 4.4)."""
    c = CableConstruction(**CAVO_132)
    r = rating(c, Installation(u0_kv=U0))
    assert r.t1 == pytest.approx(0.4198714890, abs=1e-10)
    assert r.t3 == pytest.approx(0.0867193748, abs=1e-10)  # con il fattore 1,6 del trifoglio a contatto
    assert r.t4 == pytest.approx(1.5946928925, abs=1e-10)
    assert r.wd_w_per_m == pytest.approx(0.3851382172, abs=1e-10)
    assert r.r_ac_ohm_per_m == pytest.approx(3.9521526380e-05, rel=1e-10)
    assert r.lambda1 == pytest.approx(0.2939044611, abs=1e-9)
    assert r.screen_temperature_c == pytest.approx(78.7129719135, abs=1e-8)
    from iec60909.iec60287 import t4_external

    inst = Installation(kind="ducts", u0_kv=U0, duct_inner_mm=119.4, duct_outer_mm=140)
    assert t4_external(c, inst) == pytest.approx(1.38002093961, abs=1e-10)  # T4''' dei tubi a trifoglio
    r = rating(c, inst)
    assert r.t4 - 1.38002093961 - 0.08866064719 == pytest.approx(0.3520961015, abs=0.02)  # T4' (θm iterata)


def test_skin_effect_e_immagini():
    """ys della CIGRE TB 880 caso 4 (240 mm² Cu, R20 = 7,54·10⁻⁵ Ω/m): 0,00884. Per tre cavi a
    trifoglio a contatto la norma dà una formula propria (4.2.4.3.2); il metodo delle immagini,
    usato per i cavi distanziati, è più cautelativo di qualche per cento."""
    from iec60909.iec60287 import _t4_images, ac_resistance, t4_external

    c = CableConstruction(area_mm2=240, conductor_diameter_mm=18.4, r20_ohm_per_km=0.0754)
    _, ys, _ = ac_resistance(c, Installation(), 90.0)
    assert ys == pytest.approx(0.00884, abs=5e-6)
    inst = Installation(depth_m=1.0)
    de = c.diameters_mm()["outer"] / 1000
    assert 1.0 < _t4_images(inst, de, de) / t4_external(c, inst) < 1.05


def test_dimensionamento_mt_con_portate_iec60287():
    from iec60909 import network_from_dict
    from iec60909.cables import size_cable

    cavo = dict(CAVO_132, area_mm2=240, conductor_diameter_mm=18.4, r20_ohm_per_km=None, insulation_mm=5.5,
                insulation_tan_delta=0.004, screen_kind="wires", screen_area_mm2=16, screen_thickness_mm=0.6,
                insulation_screen_mm=0.8, conductor_screen_mm=0.8)
    posa = {"u0_kv": 20 / math.sqrt(3), "depth_m": 1.0}
    ratings = [{"id": f"R{s}", "cable": dict(cavo, area_mm2=s, conductor_diameter_mm=d), "installation": posa}
               for s, d in ((95, 11.4), (150, 14.2), (240, 18.4))]
    net = network_from_dict({
        "name": "MT", "buses": [{"id": "A", "un_kv": 20}, {"id": "B", "un_kv": 20}],
        "external_grids": [{"id": "G", "bus": "A", "skq_max_mva": 500}],
        "lines": [{"id": "L", "from_bus": "A", "to_bus": "B", "length_km": 2.0, "r1_ohm_per_km": 0.2,
                   "x1_ohm_per_km": 0.12}],
        "cable_ratings": ratings,
        "cable_sizing": [{"id": "C", "line": "L", "ib_a": 300.0, "cos_phi": 0.9, "insulation": "xlpe",
                          "ratings": ["R95", "R150", "R240"], "x_ohm_per_km": 0.12, "vdrop_max_percent": 5}],
    })
    r = size_cable(net, net.cable_sizing[0])
    portate = {c.section_mm2: c.iz_a for c in r.candidates}
    assert portate[95] < portate[150] < portate[240]
    assert r.section_mm2 == min(s for s, iz in portate.items() if iz >= 300)
