"""Dimensionamento dei cavi (IEC 60364-5-52, IEC 60364-4-43, IEC 60364-4-41).

Per ogni linea con una voce in `cable_sizing` si cerca il minor numero di
conduttori in parallelo e, a parità, la sezione più piccola che soddisfa:

1. **portata:** Ib ≤ In ≤ Iz e I2 ≤ 1,45·Iz, con Iz = n·I0·k (I0 dalle
   tabelle dell'allegato B della IEC 60364-5-52, k prodotto dei fattori di
   correzione per temperatura, terreno e raggruppamento);
2. **caduta di tensione:** ΔU = √3·Ib·L·(R·cosφ + X·sinφ)/n, con R alla
   temperatura di esercizio θ = θa + (θz − θa)·(Ib/Iz)², più la caduta a monte;
3. **cortocircuito (IEC 60364-4-43):** (I/n)²·t ≤ k²·S² alla corrente massima
   all'inizio della linea e alla minima alla fine, con t dalla curva del
   dispositivo (sotto 0,1 s l'I²t passante del costruttore, se indicato);
   anche per il conduttore di protezione;
4. **interruzione automatica (IEC 60364-4-41, sistemi TN):** il dispositivo
   interviene entro il tempo prescritto con la corrente di guasto a terra
   minima alla fine della linea.

Le correnti di cortocircuito vengono dal calcolo IEC 60909 della rete: le
impedenze di sequenza nel nodo di partenza più quelle del cavo candidato,
Z1 = Z2 = Zf, Z0 = Zf + 3·Zpe (anello fase–protezione).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Optional

from . import cable_tables as tab
from .network import CableSizing, Line, Network, ProtectiveDevice

ALPHA = {"cu": 0.00393, "al": 0.00403}  # coefficiente di temperatura della resistenza [1/K]
I2_DEFAULT = {"breaker": 1.3, "fuse": 1.6, "relay": 1.3}


@dataclass
class Candidate:
    section_mm2: float
    parallel: int
    iz_a: float
    vdrop_percent: float
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class SizingResult:
    id: str
    line: str
    un_kv: float
    length_km: float
    ib_a: float
    cos_phi: float
    in_a: Optional[float]
    i2_a: Optional[float]
    k_total: float
    factors: dict[str, float]
    section_mm2: Optional[float] = None
    parallel: int = 1
    pe_section_mm2: Optional[float] = None
    iz_a: Optional[float] = None
    vdrop_percent: Optional[float] = None
    temperature_c: Optional[float] = None
    ik_max_ka: Optional[float] = None
    t_max_s: Optional[float] = None
    ik1_min_end_ka: Optional[float] = None
    t_min_s: Optional[float] = None
    k_phase: Optional[float] = None
    candidates: list[Candidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.section_mm2 is not None


def _r_ohm_per_km(cs: CableSizing, s: float, temperature_c: float) -> float:
    r20 = tab.resistance_20c(cs.material, s)
    return r20 * (1.0 + ALPHA[cs.material] * (temperature_c - 20.0))


def pe_section(s: float, given: Optional[float] = None) -> float:
    """Sezione del conduttore di protezione (IEC 60364-5-54, tabella 54.2, stesso materiale)."""
    if given is not None:
        return given
    if s <= 16:
        return s
    if s <= 35:
        return 16.0
    return tab.next_section(s / 2.0)


def voltage_drop_percent(ib_a: float, length_km: float, r_ohm_per_km: float, x_ohm_per_km: float,
                         cos_phi: float, un_kv: float, parallel: int = 1) -> float:
    """Caduta di tensione trifase ΔU% = √3·Ib·L·(R·cosφ + X·sinφ)/(n·Un)·100."""
    sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi**2))
    dv = math.sqrt(3) * ib_a * length_km * (r_ohm_per_km * cos_phi + x_ohm_per_km * sin_phi) / parallel
    return dv / (un_kv * 1000.0) * 100.0


def min_section_short_circuit(i_a: float, t_s: float, k: float) -> float:
    """Sezione minima per la tenuta al cortocircuito S = I·√t/k [mm²] (IEC 60364-4-43, 434.5.2)."""
    return i_a * math.sqrt(t_s) / k


# resistività convenzionali a temperatura di servizio per il metodo convenzionale [Ω·mm²/m]
RHO_CONVENTIONAL = {"cu": 22.5e-3, "al": 36e-3}


def max_length_tn(u0_v: float, s_ph_mm2: float, s_pe_mm2: float, ia_a: float, material: str = "cu") -> float:
    """Lunghezza massima [m] per l'interruzione automatica nei sistemi TN con il metodo
    convenzionale: Lmax = 0,8·U0·Sph·Spe/(Ia·ρ·(Sph + Spe)), con l'80 % di U0 all'origine del
    circuito e la reattanza trascurata (valido fino a circa 120 mm²)."""
    return 0.8 * u0_v * s_ph_mm2 * s_pe_mm2 / (ia_a * RHO_CONVENTIONAL[material] * (s_ph_mm2 + s_pe_mm2))


def _device_rating(net: Network, cs: CableSizing) -> tuple[Optional[ProtectiveDevice], Optional[float], Optional[float]]:
    dev = None
    in_a = cs.in_a
    if cs.device is not None:
        dev = next((d for d in net.protective_devices if d.id == cs.device), None)
        if dev is None:
            raise ValueError(f"{cs.id}: dispositivo inesistente {cs.device!r}")
        if in_a is None:
            if dev.kind == "breaker":
                in_a = dev.ir * dev.in_a
            elif dev.kind == "relay":
                in_a = dev.pickup_a
            else:
                in_a = dev.in_a
    if in_a is None:
        return dev, None, None
    kind = dev.kind if dev is not None else "breaker"
    ratio = cs.i2_ratio if cs.i2_ratio is not None else I2_DEFAULT[kind]
    return dev, in_a, ratio * in_a


def _trip_time(dev: Optional[ProtectiveDevice], cs: CableSizing, i_a: float) -> Optional[float]:
    if cs.t_sc_s is not None:
        return cs.t_sc_s
    if dev is None:
        return None
    from .coordination import trip_time_s

    return trip_time_s(dev, i_a, "max")


def _mv_ratings(net: Network, cs: CableSizing) -> tuple[dict[float, float], float]:
    """Portate IEC 60287 dei cavi indicati in `ratings` (una per sezione)."""
    from .iec60287 import rating_of

    table: dict[float, float] = {}
    temps = set()
    for rid in cs.ratings:
        cr = next((r for r in net.cable_ratings if r.id == rid), None)
        if cr is None:
            raise ValueError(f"{cs.id}: portata inesistente {rid!r} in cable_ratings")
        c, res = rating_of(cr)
        if c.area_mm2 in table:
            raise ValueError(f"{cs.id}: due portate per la sezione {c.area_mm2:g} mm²")
        table[float(c.area_mm2)] = res.current_a
        temps.add(c.max_temperature_c)
    if len(temps) != 1:
        raise ValueError(f"{cs.id}: i cavi di ratings devono avere la stessa temperatura massima")
    return table, temps.pop()


def _i2t(cs: CableSizing, i_a: float, t_s: float) -> float:
    """Energia specifica passante: I²·t, oppure il valore del costruttore sotto 0,1 s
    (IEC 60364-4-43, 434.5.2)."""
    if t_s < 0.1 and cs.let_through_a2s is not None:
        return cs.let_through_a2s
    return i_a**2 * t_s


def size_cable(net: Network, cs: CableSizing, lf=None, sc_max=None, sc_min=None) -> SizingResult:
    """Dimensiona un cavo; `lf`, `sc_max`, `sc_min` sono i risultati già calcolati
    (flusso di potenza, cortocircuito massimo e minimo) o None."""
    line = next((ln for ln in net.lines if ln.id == cs.line), None)
    if line is None:
        raise ValueError(f"{cs.id}: linea inesistente {cs.line!r}")
    un_kv = next(b.un_kv for b in net.buses if b.id == line.from_bus)
    ib, cos_phi = cs.ib_a, cs.cos_phi
    if ib is None or cos_phi is None:
        if lf is None:
            from .loadflow import run_load_flow

            lf = run_load_flow(net)
        br = lf.branch(line.id)
        if ib is None:
            ib = max(br.i_from_ka, br.i_to_ka) * 1000.0
        if cos_phi is None:
            s = math.hypot(br.p_from_mw, br.q_from_mvar)
            cos_phi = abs(br.p_from_mw) / s if s > 0 else 1.0
    if ib <= 0:
        raise ValueError(f"{cs.id}: corrente di impiego nulla")
    dev, in_a, i2_a = _device_rating(net, cs)

    method = cs.method.upper()
    theta_z = cs.max_temperature_c if cs.max_temperature_c is not None else tab.MAX_TEMPERATURE[tab._insulation(cs.insulation)]
    key = None
    if cs.ratings:
        table, theta_mv = _mv_ratings(net, cs)
        if cs.max_temperature_c is None:
            theta_z = theta_mv
    elif cs.ampacity_a:
        table = {float(k): float(v) for k, v in cs.ampacity_a.items()}
    else:
        key = tab.ampacity_key(cs.material, cs.insulation, cs.loaded_conductors, method, cs.arrangement)
        table = tab.ampacity_table(cs.material, cs.insulation, cs.loaded_conductors, method, cs.cores,
                                   cs.arrangement)
    factors = tab.correction_factors(cs.insulation, method, cs.ambient_c, cs.soil_resistivity_km_w,
                                     cs.grouping, cs.circuits, cs.cores)
    if cs.k_extra != 1.0:
        factors["altro"] = cs.k_extra
    k_total = math.prod(factors.values())
    ambient = cs.ambient_c if cs.ambient_c is not None else (20.0 if method in ("D1", "D2") else 30.0)
    res = SizingResult(cs.id, line.id, un_kv, line.length_km, ib, cos_phi, in_a, i2_a, k_total, factors)
    if in_a is not None and in_a < ib - 1e-9:
        res.warnings.append(f"In = {in_a:.1f} A minore di Ib = {ib:.1f} A: protezione da aumentare")

    # cortocircuito nel nodo di partenza (rete senza la linea da dimensionare non serve: rete radiale)
    need_sc = dev is not None or cs.t_sc_s is not None
    bmax = bmin = None
    if need_sc:
        from .calc import calculate

        if sc_max is None:
            sc_max = calculate(net, "max")
        if sc_min is None:
            sc_min = calculate(net, "min")
        bmax = next(b for b in sc_max.buses if b.bus == line.from_bus)
        bmin = next(b for b in sc_min.buses if b.bus == line.from_bus)
        res.ik_max_ka = max(bmax.ikss3_ka, bmax.ikss1_ka)
        res.t_max_s = _trip_time(dev, cs, res.ik_max_ka * 1000.0)
        if bmin.z0_ohm is None:
            res.warnings.append(f"{line.from_bus}: nessun percorso verso terra, guasto a terra non verificato")

    sections = sorted(float(s) for s in (cs.sections or table))
    sections = [s for s in sections if s in table and s in tab.R20[cs.material]]  # con resistenza IEC 60228
    if not sections:
        raise ValueError(f"{cs.id}: nessuna sezione disponibile per la posa indicata")
    best: Optional[Candidate] = None
    best_data = None
    for n in range(1, cs.max_parallel + 1):
        for s in sections:
            issues: list[str] = []
            iz = n * table[s] * k_total
            if ib > iz + 1e-9:
                issues.append(f"Ib {ib:.1f} A > Iz {iz:.1f} A")
            if in_a is not None:
                if in_a > iz + 1e-9:
                    issues.append(f"In {in_a:.1f} A > Iz {iz:.1f} A")
                if i2_a > 1.45 * iz + 1e-9:
                    issues.append(f"I2 {i2_a:.1f} A > 1,45·Iz {1.45 * iz:.1f} A")
            theta = ambient + (theta_z - ambient) * min(ib / iz, 1.0) ** 2 if iz > 0 else theta_z
            r = _r_ohm_per_km(cs, s, theta)
            dv_pct = voltage_drop_percent(ib, line.length_km, r, cs.x_ohm_per_km, cos_phi, un_kv, n) \
                + cs.upstream_drop_percent
            if dv_pct > cs.vdrop_max_percent + 1e-9:
                issues.append(f"ΔU {dv_pct:.2f} % > {cs.vdrop_max_percent:g} %")
            spe = pe_section(s, cs.pe_section_mm2)
            k_phase = tab.k_factor(cs.material, tab._insulation(cs.insulation), s)
            k_pe = tab.k_factor(cs.material, tab._insulation(cs.insulation), spe)
            data = {"theta": theta, "spe": spe, "k": k_phase}
            if need_sc:
                if res.t_max_s is None:
                    issues.append(f"il dispositivo non interviene con Ik max {res.ik_max_ka:.2f} kA")
                elif _i2t(cs, res.ik_max_ka * 1000.0 / n, res.t_max_s) > (k_phase * s) ** 2:
                    issues.append(f"I²t {_i2t(cs, res.ik_max_ka * 1000 / n, res.t_max_s):.3g} A²s > "
                                  f"k²S² {(k_phase * s) ** 2:.3g} A²s (Ik max)")
                if bmin.z0_ohm is not None:
                    # anello di guasto alla fine della linea, cavo alla temperatura massima di esercizio
                    rf = _r_ohm_per_km(cs, s, theta_z) * line.length_km / n
                    rpe = _r_ohm_per_km(cs, spe, theta_z) * line.length_km / n
                    x = cs.x_ohm_per_km * line.length_km / n
                    zf, zpe = complex(rf, x), complex(rpe, x)
                    ztot = bmin.z1_ohm + bmin.z2_ohm + bmin.z0_ohm + 3 * (zf + zpe)
                    ik1 = math.sqrt(3) * bmin.c * un_kv / abs(ztot)  # kA
                    t1 = _trip_time(dev, cs, ik1 * 1000.0)
                    data.update(ik1=ik1, t1=t1)
                    if t1 is None:
                        issues.append(f"il dispositivo non interviene con Ik1 min {ik1:.3f} kA a fine linea")
                    else:
                        i2t = _i2t(cs, ik1 * 1000.0 / n, t1)
                        if i2t > (k_phase * s) ** 2:
                            issues.append(f"I²t {i2t:.3g} A²s > k²S² (Ik1 min)")
                        if i2t > (k_pe * spe) ** 2:
                            issues.append(f"I²t {i2t:.3g} A²s > k²S²PE {(k_pe * spe) ** 2:.3g} A²s")
                        if cs.disconnection_time_s is not None and t1 > cs.disconnection_time_s + 1e-12:
                            issues.append(f"interruzione in {t1:.3g} s > {cs.disconnection_time_s:g} s")
            cand = Candidate(s, n, iz, dv_pct, issues)
            res.candidates.append(cand)
            if cand.ok and best is None:  # il minor numero di conduttori in parallelo, poi la sezione minore
                best, best_data = cand, data
        if best is not None:
            break
    if best is None:
        res.warnings.append("nessuna sezione soddisfa tutte le verifiche")
        return res
    res.section_mm2, res.parallel, res.iz_a = best.section_mm2, best.parallel, best.iz_a
    res.vdrop_percent = best.vdrop_percent
    res.temperature_c = best_data["theta"]
    res.pe_section_mm2 = best_data["spe"]
    res.ik1_min_end_ka = best_data.get("ik1")
    res.t_min_s = best_data.get("t1")
    res.k_phase = best_data["k"]
    if key is not None:
        note = tab.confidence_note(key, best.section_mm2)
        if note is not None:
            res.warnings.append(f"portata di {best.section_mm2:g} mm² con confidenza ridotta: {note}")
    return res


def cable_sizing_study(net: Network) -> list[SizingResult]:
    if not net.cable_sizing:
        return []
    lf = sc_max = sc_min = None
    if any(cs.ib_a is None or cs.cos_phi is None for cs in net.cable_sizing):
        from .loadflow import run_load_flow

        lf = run_load_flow(net)
    if any(cs.device is not None or cs.t_sc_s is not None for cs in net.cable_sizing):
        from .calc import calculate

        sc_max, sc_min = calculate(net, "max"), calculate(net, "min")
    return [size_cable(net, cs, lf, sc_max, sc_min) for cs in net.cable_sizing]


def apply_sizing(net: Network, results: list[SizingResult]) -> Network:
    """Copia della rete con le linee aggiornate alla sezione scelta (R a 20 °C,
    Z0 = Zf + 3·Zpe)."""
    out = copy.deepcopy(net)
    by_id = {cs.id: cs for cs in out.cable_sizing}
    lines = {ln.id: ln for ln in out.lines}
    for r in results:
        if not r.ok:
            continue
        cs = by_id[r.id]
        ln: Line = lines[r.line]
        x = cs.x_ohm_per_km
        ln.parallel = r.parallel
        ln.r1_ohm_per_km = tab.resistance_20c(cs.material, r.section_mm2)
        ln.x1_ohm_per_km = x
        ln.r0_ohm_per_km = ln.r1_ohm_per_km + 3 * tab.resistance_20c(cs.material, r.pe_section_mm2)
        ln.x0_ohm_per_km = 4 * x
        ln.max_i_ka = r.iz_a / r.parallel / 1000.0
    return out


def results_to_markdown(results: list[SizingResult], title: str = "") -> str:
    out = [f"# Dimensionamento dei cavi{' — ' + title if title else ''}", "",
           "| Cavo | Linea | Ib [A] | In [A] | k | Sezione | PE | Iz [A] | ΔU [%] | θ [°C] | Ik max [kA] "
           "| t [s] | Ik1 min fine [kA] | t [s] | Esito |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def f(v, fmt):
        return "—" if v is None else format(v, fmt)

    for r in results:
        sez = "—" if not r.ok else (f"{r.parallel}×{r.section_mm2:g}" if r.parallel > 1 else f"{r.section_mm2:g}")
        out.append(f"| {r.id} | {r.line} | {r.ib_a:.1f} | {f(r.in_a, '.1f')} | {r.k_total:.3f} | {sez} "
                   f"| {f(r.pe_section_mm2, 'g')} | {f(r.iz_a, '.1f')} | {f(r.vdrop_percent, '.2f')} "
                   f"| {f(r.temperature_c, '.0f')} | {f(r.ik_max_ka, '.2f')} | {f(r.t_max_s, '.3g')} "
                   f"| {f(r.ik1_min_end_ka, '.3f')} | {f(r.t_min_s, '.3g')} "
                   f"| {'OK' if r.ok else 'non dimensionabile'} |")
    for r in results:
        fac = ", ".join(f"{k} {v:.3f}" for k, v in r.factors.items()) or "nessuno"
        out += ["", f"## {r.id}", "", f"Fattori di correzione: {fac}."]
        if r.warnings:
            out += [""] + [f"- {w}" for w in r.warnings]
        scartati = [c for c in r.candidates if c.issues
                    and (not r.ok or (c.parallel, c.section_mm2) < (r.parallel, r.section_mm2))]
        if scartati:
            out += ["", "| Sezione scartata | Iz [A] | ΔU [%] | Motivi |", "|---|---|---|---|"]
            for c in scartati:
                sez = f"{c.parallel}×{c.section_mm2:g}" if c.parallel > 1 else f"{c.section_mm2:g}"
                out.append(f"| {sez} | {c.iz_a:.1f} | {c.vdrop_percent:.2f} | {'; '.join(c.issues)} |")
    return "\n".join(out) + "\n"


def results_to_dict(results: list[SizingResult]) -> list[dict]:
    return [{
        "id": r.id, "line": r.line, "ok": r.ok, "ib_a": r.ib_a, "cos_phi": r.cos_phi, "in_a": r.in_a,
        "i2_a": r.i2_a, "k_total": r.k_total, "factors": r.factors, "section_mm2": r.section_mm2,
        "parallel": r.parallel, "pe_section_mm2": r.pe_section_mm2, "iz_a": r.iz_a,
        "vdrop_percent": r.vdrop_percent, "temperature_c": r.temperature_c, "ik_max_ka": r.ik_max_ka,
        "t_max_s": r.t_max_s, "ik1_min_end_ka": r.ik1_min_end_ka, "t_min_s": r.t_min_s,
        "warnings": r.warnings,
        "candidates": [{"section_mm2": c.section_mm2, "parallel": c.parallel, "iz_a": c.iz_a,
                        "vdrop_percent": c.vdrop_percent, "issues": c.issues} for c in r.candidates],
    } for r in results]
