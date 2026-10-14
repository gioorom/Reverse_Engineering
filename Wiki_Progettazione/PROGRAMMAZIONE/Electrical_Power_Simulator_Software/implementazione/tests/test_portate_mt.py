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
    assert t4_external(c, inst) == pytest.approx([1.38002093961] * 3, abs=1e-10)  # T4''' dei tubi a trifoglio
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
    assert 1.0 < max(_t4_images(inst, de, de)) / t4_external(c, inst)[0] < 1.05


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


@pytest.mark.parametrize("parassite, attese", [(False, (765.8209, 891.1261, 792.0775)),
                                               (True, (756.6453, 855.1481, 780.2569))])
def test_cigre_tb880_canaletta_in_piano(parassite, attese):
    """Caso 0-5 (TB 880 §4.10): cavi in piano a contatto in una canaletta chiusa non riempita
    (0,36 × 0,55 m, p = 1,27 m), aria a 25 °C, h con Z = 0,62, E = 1,95, g = 0,25, schermi
    collegati alle due estremità senza trasposizione (λ1' diverso per ogni cavo). Riferimento:
    notebook che riproduce il caso, che nell'iterazione semplifica il riscaldamento dell'aria
    (25 K costanti nel calcolo della temperatura superficiale e perdite del primo cavo per
    tutti): scarto atteso qualche millesimo sul cavo limitante."""
    c = CableConstruction(**CAVO_132)
    inst = Installation(kind="air", formation="flat", air_temperature_c=25, air_z=0.62, air_e=1.95, air_g=0.25,
                        trough_perimeter_m=1.27, u0_kv=U0, eddy_both_ends=parassite)
    r = rating(c, inst)
    assert r.t3 == pytest.approx(0.0541996092, abs=1e-10)  # senza il fattore 1,6 (non interrato)
    assert r.cable == 0  # cavo esterno con la fase in ritardo
    assert r.current_a == pytest.approx(attese[0], rel=5e-3)
    # il notebook calcola le perdite di tutti i cavi con la corrente del primo: per gli altri
    # due si confronta solo l'ordine delle portate (centrale > esterno in anticipo > limitante)
    assert r.currents_a[1] > r.currents_a[2] > r.currents_a[0]


def test_piano_trasposto_e_simmetria():
    """In piano con trasposizione i tre cavi hanno lo stesso λ1'; senza trasposizione il
    cavo centrale ha perdite minori degli esterni."""
    from iec60909.iec60287 import ac_resistance, screen_loss_factors

    c = CableConstruction(**CAVO_132)
    for transposed in (True, False):
        inst = Installation(formation="flat", spacing_mm=200, u0_kv=U0, transposed=transposed)
        r, _, _ = ac_resistance(c, inst, 90.0)
        lam, _, _ = screen_loss_factors(c, inst, r, [80.0] * 3)
        if transposed:
            assert lam[0] == lam[1] == lam[2]
        else:
            assert lam[1] < min(lam[0], lam[2])


def test_cigre_tb880_caso_4_schermo_a_fili():
    """Caso 4 (TB 880 §8, pp. 195-205): 33 kV, 240 mm² Cu, XLPE 7,7 mm, schermo a fili di rame
    35,63 mm² su un nastro da 0,5 mm (ρ 6), trifoglio interrato a contatto a 1 m, 20 °C, 1 K·m/W.
    IEC 60287-2-1:2023: T1 × 1,07 (schermo a fili, U0 ≤ 35 kV) e T3 × 1,6. Dalla brochure
    (citata dalla suite CableSketch): T1 = 0,4110322351, T3 = 0,1241941899, I = 537,4631 A.
    La guaina esterna è descritta in CIGRE in tre sottostrati: qui uno solo con la resistività
    equivalente che dà il T3 base pubblicato (0,0776213687). La resistenza dei fili non tiene
    conto della cordatura (passo non disponibile): portata entro lo 0,2 %."""
    rho_eq = 0.0776213687 * 2 * math.pi / math.log(44.0 / 38.6)
    c = CableConstruction(area_mm2=240, conductor_diameter_mm=18.4, r20_ohm_per_km=0.0754, conductor_screen_mm=0.5,
                          insulation_mm=7.7, insulation_screen_mm=0.5, under_screen_mm=0.5, under_screen_rho_t=6.0,
                          semicon_rho_t=2.5, screen_kind="wires", screen_area_mm2=35.63, screen_thickness_mm=0.9,
                          oversheath_mm=2.7, oversheath_rho_t=rho_eq)
    assert c.diameters_mm()["outer"] == pytest.approx(44.0)
    r = rating(c, Installation(u0_kv=33 / math.sqrt(3)))
    assert r.t1 == pytest.approx(0.4110322351, abs=2e-5)
    assert r.t3 == pytest.approx(0.1241941899, abs=1e-9)
    assert r.t4 == pytest.approx(1.8525, abs=1e-4)
    assert r.ys == pytest.approx(0.00884, abs=5e-6) and r.yp == pytest.approx(0.00662, abs=5e-6)
    assert r.wd_w_per_m == pytest.approx(0.1084, abs=1e-4)
    assert r.current_a == pytest.approx(537.4631099368, rel=2e-3)
    # senza i fattori dell'edizione 2023 la portata sale
    c.t1_factor, c.t3_factor = 1.0, 1.6
    assert rating(c, Installation(u0_kv=33 / math.sqrt(3))).current_a > r.current_a


def test_effetto_pelle_nei_tre_campi_e_aria():
    """ys quasi continuo ai confini dei tre campi di xs (le formule della norma saltano di
    qualche millesimo: 0,001 a 2,8 e 0,0025 a 3,8); coefficienti Z, E, g di default
    per trifoglio e piano a contatto (IEC 60287-2-1, tabella 2)."""
    from iec60909.iec60287 import skin_factor

    for xs in (2.8, 3.8):
        assert skin_factor((xs - 1e-9) ** 2) == pytest.approx(skin_factor((xs + 1e-9) ** 2), abs=3e-3)
    c = CableConstruction(**CAVO_132)
    piano = rating(c, Installation(kind="air", formation="flat", air_temperature_c=25, u0_kv=U0))
    esplicito = rating(c, Installation(kind="air", formation="flat", air_temperature_c=25, u0_kv=U0,
                                       air_z=0.62, air_e=1.95, air_g=0.25))
    assert piano.current_a == esplicito.current_a
    assert rating(c, Installation(kind="air", air_temperature_c=25, u0_kv=U0)).current_a > 0
    with pytest.raises(ValueError, match="air_arrangement"):
        rating(c, Installation(kind="air", formation="flat", spacing_mm=300, u0_kv=U0))


# --- cavi tripolari ---------------------------------------------------------------------

def _caso2(armour="steel", **kw):
    """CIGRE TB 880 caso 2: cavo sottomarino tripolare 30 kV, 3 × 630 mm² Cu, XLPE 8 mm, guaine di
    piombo 2,3 mm e guaina semiconduttiva in PE sulle anime, riempitivi fino a 134,9 mm, 71 fili
    d'armatura da 6 mm (passo 1785 mm), cordatura delle anime con passo 2152 mm, interrato a 1 m
    nel fondale a 15 °C e 0,7 K·m/W."""
    dati = dict(
        cores=3, area_mm2=630, conductor_diameter_mm=30.0, r20_ohm_per_km=0.0283, conductor_tape_mm=0.25,
        conductor_tape_rho_t=6.0, conductor_screen_mm=1.0, insulation_mm=8.0, insulation_screen_mm=0.9,
        under_screen_mm=1.1, under_screen_rho_t=12.0, semicon_rho_t=2.5, insulation_tan_delta=0.004,
        screen_kind="sheath", screen_material="lead", screen_thickness_mm=2.3, core_sheath_mm=2.5,
        core_sheath_rho_t=2.5, filler_diameter_mm=134.9, filler_rho_t=6.0, bedding_mm=1.2, core_lay_length_mm=2152,
        armour_material=armour, armour_wires=71, armour_wire_diameter_mm=6.0, armour_lay_length_mm=1785,
        oversheath_mm=3.0, oversheath_rho_t=6.0)
    return CableConstruction(**{**dati, **kw})


POSA_CASO2 = dict(depth_m=1.0, soil_temperature_c=15, soil_rho_t=0.7, u0_kv=30 / math.sqrt(3), eddy_both_ends=True)


def test_tripolare_armato_cigre_tb880_caso_2():
    """Valori di riferimento del caso 2 (RA, λ2, temperatura dell'armatura e portata) come
    riportati nell'implementazione CableDesign (fcamaraneto/CableDesign)."""
    c = _caso2()
    d = c.diameters_mm()
    assert (d["core"], d["under_armour"], d["armour_mean"], d["outer"]) == pytest.approx((62.1, 137.3, 143.3, 155.3))
    r = rating(c, Installation(**POSA_CASO2))
    assert r.current_a == pytest.approx(838.339973933, abs=1e-6)
    assert r.lambda2 == pytest.approx(0.4206526837, abs=1e-9)
    assert r.armour_temperature_c == pytest.approx(71.308546665890, abs=1e-8)
    assert r.lambda1_eddy / _f(r) == pytest.approx(0.02208098453, abs=1e-9)
    from iec60909.iec60287_tripolari import armour_ac_resistance

    assert armour_ac_resistance(c, 71.308546665890) == pytest.approx(1.2798804135e-4, rel=1e-9)


def _f(r):
    """Fattore F di riduzione delle perdite parassite usato nel risultato (per confrontare λ1'')."""
    from iec60909.iec60287 import _f_reduction

    c = _caso2()
    d = c.diameters_mm()
    f = c.layup_factor
    omega = 2 * math.pi * 50
    rs = 21.4e-8 / (math.pi * d["screen_mean"] * 2.3e-6) * f * (1 + 4.0e-3 * (r.screen_temperature_c - 20))
    x = 2 * omega * 1e-7 * math.log(2 * d["core"] / d["screen_mean"]) * f
    return _f_reduction(rs / x, rs / x)


def test_tripolare_armatura_non_magnetica_e_senza_armatura():
    """Armatura in acciaio inossidabile: niente perdite nell'armatura e niente fattore 1,5;
    senza armatura la guaina esterna sta direttamente sul letto dei riempitivi."""
    acciaio = rating(_caso2(), Installation(**POSA_CASO2))
    inox = rating(_caso2("stainless"), Installation(**POSA_CASO2))
    assert inox.lambda2 == 0 and inox.current_a > acciaio.current_a
    assert inox.r_ac_ohm_per_m < acciaio.r_ac_ohm_per_m  # niente 1,5·(ys + yp)
    # λ1'·R = 1,5·Rs/(1 + (Rs/X)²) con l'armatura magnetica (GP38), senza il fattore con quella inox
    assert inox.lambda1_circ * inox.r_ac_ohm_per_m == pytest.approx(
        acciaio.lambda1_circ * acciaio.r_ac_ohm_per_m / 1.5, rel=0.01)
    nudo = _caso2(None)
    assert nudo.diameters_mm()["outer"] == pytest.approx(137.3 + 6.0)
    r = rating(nudo, Installation(**POSA_CASO2))
    assert r.lambda2 == 0 and r.armour_temperature_c is None


def test_tripolare_cordatura_e_fattore_geometrico():
    from iec60909.iec60287_tripolari import _geometric_factor_g

    c = _caso2()
    assert c.layup_factor == pytest.approx(math.sqrt(1 + (math.pi * 1.29 * 62.1 / 2152) ** 2))
    assert _caso2(core_lay_length_mm=None).layup_factor == 1.0
    # G continuo ai due rami (x = 0,03) entro il millesimo relativo dei polinomi
    assert _geometric_factor_g(0.0299999) == pytest.approx(_geometric_factor_g(0.0300001), rel=1.5e-2)
    with pytest.raises(ValueError, match="fattore geometrico"):
        _geometric_factor_g(0.2)


def test_tripolare_in_tubo_e_in_aria():
    c = _caso2()
    interrato = rating(c, Installation(**POSA_CASO2))
    tubo = rating(c, Installation(**{**POSA_CASO2, "kind": "ducts", "duct_inner_mm": 180, "duct_outer_mm": 200}))
    assert tubo.current_a < interrato.current_a
    aria = rating(c, Installation(**{**POSA_CASO2, "kind": "air", "air_temperature_c": 30}))
    assert aria.current_a > 0 and aria.t4 > 0
