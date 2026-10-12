"""Confronto con pandapower, implementazione indipendente della IEC 60909-0."""

import copy
import warnings

import pytest

from iec60909 import calculate, network_from_dict

from .reti import RETE_GRUPPO_GENERAZIONE, RETE_MAGLIATA, RETE_TRE_AVVOLGIMENTI

pytest.importorskip("pandapower")
from .pp_ref import run  # noqa: E402

REL = 1e-6


def _no_generators():
    data = copy.deepcopy(RETE_MAGLIATA)
    data["generators"] = []
    return data


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


@pytest.mark.parametrize("case", ["max", "min"])
def test_correnti_iniziali(case):
    result = calculate(network_from_dict(RETE_MAGLIATA), case)
    ref3 = run(RETE_MAGLIATA, "3ph", case)
    ref2 = run(RETE_MAGLIATA, "2ph", case)
    ref1 = run(RETE_MAGLIATA, "1ph", case)
    for b in result.buses:
        assert b.ikss3_ka == pytest.approx(ref3[b.bus].ikss_ka, rel=REL), b.bus
        assert b.ikss2_ka == pytest.approx(ref2[b.bus].ikss_ka, rel=REL), b.bus
        # pandapower lascia nella sequenza zero un'impedenza molto grande (~1 MΩ) per
        # il generatore; qui il generatore ha neutro isolato: scarto di pochi ppm.
        assert b.ikss1_ka == pytest.approx(ref1[b.bus].ikss_ka, rel=1e-5), b.bus


@pytest.mark.parametrize("case", ["max", "min"])
def test_corrente_monofase_senza_generatori(case):
    data = _no_generators()
    result = calculate(network_from_dict(data), case)
    ref = run(data, "1ph", case)
    for b in result.buses:
        assert b.ikss1_ka == pytest.approx(ref[b.bus].ikss_ka, rel=REL), b.bus


@pytest.mark.parametrize("case", ["max", "min"])
@pytest.mark.parametrize("method", ["B", "C"])
def test_corrente_di_picco(case, method):
    result = calculate(network_from_dict(RETE_MAGLIATA), case, method)
    ref = run(RETE_MAGLIATA, "3ph", case, ip=True, kappa_method=method)
    for b in result.buses:
        assert b.ip3_ka == pytest.approx(ref[b.bus].ip_ka, rel=REL), b.bus


def test_corrente_termica_metodo_c():
    data = _no_generators()
    result = calculate(network_from_dict(data), "max", "C", tk_s=0.5)
    ref = run(data, "3ph", "max", ip=True, ith=True, tk_s=0.5, kappa_method="C")
    for b in result.buses:
        assert b.ith_ka == pytest.approx(ref[b.bus].ith_ka, rel=REL), b.bus


def test_corrente_termica_metodo_b_sotto_il_limite():
    # Con κ al limite 2,0 pandapower azzera m (0/0); qui si confrontano solo i nodi
    # con κ < 2, il limite è verificato in test_formule.
    data = _no_generators()
    result = calculate(network_from_dict(data), "max", "B", tk_s=0.5)
    ref = run(data, "3ph", "max", ip=True, ith=True, tk_s=0.5, kappa_method="B")
    checked = 0
    for b in result.buses:
        if b.kappa < 2.0:
            assert b.ith_ka == pytest.approx(ref[b.bus].ith_ka, rel=REL), b.bus
            checked += 1
    assert checked >= 3


def _tre_avvolgimenti(vector_group):
    data = copy.deepcopy(RETE_TRE_AVVOLGIMENTI)
    data["transformers3w"][0]["vector_group"] = vector_group
    return data


@pytest.mark.parametrize("case", ["max", "min"])
@pytest.mark.parametrize("vector_group", ["YNynd5", "YNyd5", "Yynd5", "YNdd5", "Ddd0"])
def test_tre_avvolgimenti_trifase_bifase_picco(case, vector_group):
    data = _tre_avvolgimenti(vector_group)
    result = calculate(network_from_dict(data), case)
    ref3 = run(data, "3ph", case, ip=True, kappa_method="C")
    ref2 = run(data, "2ph", case)
    for b in result.buses:
        assert b.ikss3_ka == pytest.approx(ref3[b.bus].ikss_ka, rel=REL), b.bus
        assert b.ip3_ka == pytest.approx(ref3[b.bus].ip_ka, rel=REL), b.bus
        assert b.ikss2_ka == pytest.approx(ref2[b.bus].ikss_ka, rel=REL), b.bus


@pytest.mark.parametrize("case", ["max", "min"])
@pytest.mark.parametrize("vector_group", ["YNynd5", "Yynd5"])
def test_tre_avvolgimenti_monofase(case, vector_group):
    # Per YNyd, YNdd e Ddd pandapower 3.5.6 non modella correttamente la sequenza
    # zero del trasformatore a tre avvolgimenti (es. Ddd: Z0 ≈ 0 al nodo AT); quei
    # casi sono verificati con calcoli a mano in test_tre_avvolgimenti.py.
    data = _tre_avvolgimenti(vector_group)
    result = calculate(network_from_dict(data), case)
    ref = run(data, "1ph", case)
    for b in result.buses:
        assert b.ikss1_ka == pytest.approx(ref[b.bus].ikss_ka, rel=REL), b.bus


def _gruppo(oltc, pg, pt):
    data = copy.deepcopy(RETE_GRUPPO_GENERAZIONE)
    data["generators"][0].update(oltc=oltc, pg_percent=pg, pt_percent=pt)
    return data


@pytest.mark.parametrize("case", ["max", "min"])
@pytest.mark.parametrize("oltc, pg, pt", [(True, 0, 0), (False, 5, 0), (False, 0, 2.5)])
def test_gruppo_di_generazione_guasti_esterni(case, oltc, pg, pt):
    # Guasti fuori dal gruppo (nodi AT): generatore e trasformatore corretti con
    # K_S / K_SO. Al nodo del generatore pandapower non applica K_T,S al
    # trasformatore: quel caso è verificato a mano in test_gruppi_generazione.
    data = _gruppo(oltc, pg, pt)
    result = calculate(network_from_dict(data), case)
    ref3 = run(data, "3ph", case)
    ref1 = run(data, "1ph", case)
    for bus in ("AT", "AT2"):
        b = result.bus(bus)
        assert b.ikss3_ka == pytest.approx(ref3[bus].ikss_ka, rel=REL), bus
        assert b.ikss1_ka == pytest.approx(ref1[bus].ikss_ka, rel=REL), bus
