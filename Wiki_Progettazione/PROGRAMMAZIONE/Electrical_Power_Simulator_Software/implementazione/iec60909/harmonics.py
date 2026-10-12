"""Armoniche: propagazione delle correnti armoniche, scansione in frequenza, limiti.

Metodo (rete lineare, sovrapposizione degli effetti, sistema trifase
equilibrato): per ogni ordine h le sorgenti armoniche iniettano correnti di
sequenza diretta (h = 3k+1), inversa (h = 3k−1) od omopolare (h = 3k) e le
tensioni armoniche dei nodi sono V_h = Z_h·I_h, con Z_h la matrice delle
impedenze della rete della sequenza corrispondente alla frequenza h·f.

Modelli alla frequenza h·f (per unità, base 100 MVA e tensione del nodo):
- linee: R costante (o R·√h con `r_skin=True`), X·h, capacità B·h; sequenza
  zero con r0/x0 se indicate;
- trasformatori: R costante, X·h, rapporto con presa; sfasamento del gruppo
  vettoriale +k·30° (ritardo BT) per la sequenza diretta e −k·30° per
  l'inversa; sequenza zero secondo i collegamenti (come nel cortocircuito);
- rete esterna: R + jX·h da skq_max_mva e rx_max (c = 1), zero da x0x1/r0x0;
- generatori: R + jX₂·h (X₂ = x2_percent o X"d); zero: R + jX₀·h + 3·Zn;
- motori: impedenza a rotore bloccato R + jX·h;
- carichi: R e L in parallelo dalla potenza assorbita a tensione nominale
  (R = Un²/P, X = Un²/Q a frequenza fondamentale), o esclusi;
- derivazioni: condensatori B·h, reattori X·h, conduttanza costante;
- filtri accordati: R + j(h·X_L − X_C/h).
Fondamentale (V1, I1): dal flusso di potenza.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .calc import _parse_vector_group, _parse_vector_group_3w
from .loadflow import S_BASE_MVA, _pi_branch, clock_numbers, run_load_flow
from .network import HarmonicFilter, HarmonicSource, Network

# Spettri ideali dei convertitori (ampiezza 1/h, ordini 6k±1 e 12k±1, fino al 49°)
SPECTRA: dict[str, dict[int, tuple[float, float]]] = {
    "6_impulsi": {h: (100.0 / h, 0.0) for h in range(5, 50) if h % 6 in (1, 5)},
    "12_impulsi": {h: (100.0 / h, 0.0) for h in range(11, 50) if h % 12 in (1, 11)},
}

# EN 50160 (e IEC 61000-2-2): livelli di tensione armonica in % della fondamentale
# (la norma non indica limiti per le singole armoniche oltre la 25ª)
EN50160 = {2: 2.0, 3: 5.0, 4: 1.0, 5: 6.0, 6: 0.5, 7: 5.0, 9: 1.5, 11: 3.5, 13: 3.0, 15: 0.5,
           17: 2.0, 19: 1.5, 21: 0.5, 23: 1.5, 25: 1.5}
EN50160_THD = 8.0


def ieee519_voltage_limits(un_kv: float) -> tuple[float, float]:
    """IEEE 519-2014, tabella 1: (limite singola armonica %, THD %) per la tensione nominale."""
    if un_kv <= 1.0:
        return 5.0, 8.0
    if un_kv <= 69.0:
        return 3.0, 5.0
    if un_kv <= 161.0:
        return 1.5, 2.5
    return 1.0, 1.5


def ieee519_current_limits(isc_il: float, un_kv: float = 1.0) -> tuple[list[tuple[int, int, float]], float]:
    """IEEE 519-2014, tabelle 2–4: limiti delle correnti armoniche dispari in % di IL.

    Restituisce ([(h_min, h_max, limite)], TDD). Le armoniche pari sono
    limitate al 25 % del valore delle dispari della stessa fascia.
    """
    if un_kv <= 69.0:
        rows = [(20, [4.0, 2.0, 1.5, 0.6, 0.3], 5.0), (50, [7.0, 3.5, 2.5, 1.0, 0.5], 8.0),
                (100, [10.0, 4.5, 4.0, 1.5, 0.7], 12.0), (1000, [12.0, 5.5, 5.0, 2.0, 1.0], 15.0),
                (math.inf, [15.0, 7.0, 6.0, 2.5, 1.4], 20.0)]
    elif un_kv <= 161.0:
        rows = [(20, [2.0, 1.0, 0.75, 0.3, 0.15], 2.5), (50, [3.5, 1.75, 1.25, 0.5, 0.25], 4.0),
                (100, [5.0, 2.25, 2.0, 0.75, 0.35], 6.0), (1000, [6.0, 2.75, 2.5, 1.0, 0.5], 7.5),
                (math.inf, [7.5, 3.5, 3.0, 1.25, 0.7], 10.0)]
    else:
        rows = [(25, [1.0, 0.5, 0.38, 0.15, 0.1], 1.5), (50, [2.0, 1.0, 0.75, 0.3, 0.15], 2.5),
                (math.inf, [3.0, 1.5, 1.15, 0.45, 0.22], 3.75)]
    bands = [(3, 10), (11, 16), (17, 22), (23, 34), (35, 50)]
    for limit, vals, tdd in rows:
        if isc_il < limit:
            return [(a, b, v) for (a, b), v in zip(bands, vals)], tdd
    raise AssertionError


def filter_impedance_pu(hf: HarmonicFilter, h: float) -> complex:
    """Impedenza del filtro accordato all'ordine h (p.u. sulla base 100 MVA).

    Q_1 = U²/(X_C − X_L) con X_L = X_C/h_t²; R = h_t·X_L/qualità.
    """
    ht = hf.tuned_order
    xc = S_BASE_MVA / hf.q_mvar * ht**2 / (ht**2 - 1.0)
    xl = xc / ht**2
    r = ht * xl / hf.quality
    return complex(r, h * xl - xc / h)


def sequence_of(h: int) -> int:
    """Sequenza dell'armonica h in un sistema equilibrato: 1 diretta, 2 inversa, 0 omopolare."""
    return {1: 1, 2: 2, 0: 0}[h % 3]


def _spectrum(src: HarmonicSource) -> dict[int, tuple[float, float]]:
    if isinstance(src.spectrum, str):
        if src.spectrum not in SPECTRA:
            raise ValueError(f"{src.id}: spettro sconosciuto {src.spectrum!r} ({sorted(SPECTRA)})")
        return SPECTRA[src.spectrum]
    if isinstance(src.spectrum, dict):
        out = {}
        for k, v in src.spectrum.items():
            h = int(k)
            if h < 2:
                raise ValueError(f"{src.id}: ordini armonici da 2 in su")
            mag, ang = (v, 0.0) if isinstance(v, (int, float)) else (v[0], v[1])
            out[h] = (float(mag), float(ang))
        return out
    raise ValueError(f"{src.id}: spectrum deve essere un nome o un dizionario")


class _HarmonicNetwork:
    def __init__(self, net: Network, include_loads: bool = True, r_skin: bool = False):
        self.net = net
        self.include_loads = include_loads
        self.r_skin = r_skin
        self.idx = net.bus_index()
        self.un = {b.id: b.un_kv for b in net.buses}
        for t in net.transformers3w:
            self.idx[f"{t.id}::stella"] = len(self.idx)
            self.un[f"{t.id}::stella"] = t.ur_hv_kv
        self.n = len(self.idx)
        self.warnings: list[str] = []
        # elementi in serie registrati per le correnti nei rami: (id, i, j, yff, yft, ytf, ytt)
        self.branches: list = []

    def zbase(self, bus: str) -> float:
        return self.un[bus] ** 2 / S_BASE_MVA

    def ybus(self, h: float, seq: int) -> np.ndarray:
        n = self.n
        y = np.zeros((n, n), dtype=complex)
        self.branches = []
        rf = math.sqrt(h) if self.r_skin else 1.0

        def stamp(name: str, i: int, j: int, yy: tuple) -> None:
            yff, yft, ytf, ytt = yy
            y[i, i] += yff
            y[i, j] += yft
            y[j, i] += ytf
            y[j, j] += ytt
            self.branches.append((name, i, j, yy))

        def shunt(i: int, yy: complex) -> None:
            y[i, i] += yy

        for ln in self.net.lines:
            if seq == 0:
                if ln.r0_ohm_per_km is None or ln.x0_ohm_per_km is None:
                    msg = f"{ln.id}: dati di sequenza zero mancanti, linea aperta per le armoniche omopolari"
                    if msg not in self.warnings:
                        self.warnings.append(msg)
                    continue
                r, x = ln.r0_ohm_per_km, ln.x0_ohm_per_km
                b = 0.0
            else:
                r, x = ln.r1_ohm_per_km, ln.x1_ohm_per_km
                b = 2.0 * math.pi * self.net.f_hz * ln.c_nf_per_km * 1e-9
            zb = self.zbase(ln.from_bus)
            z = complex(r * rf, x * h) * ln.length_km / ln.parallel / zb
            yh = complex(0.0, b * h * ln.length_km * ln.parallel * zb / 2.0)
            ys = 1.0 / z
            stamp(ln.id, self.idx[ln.from_bus], self.idx[ln.to_bus], (ys + yh, -ys, -ys, ys + yh))

        for t in self.net.transformers:
            tap = 1.0 + t.tap_pos * t.tap_step_percent / 100.0
            ur_hv = t.ur_hv_kv * (tap if t.tap_side == "hv" else 1.0)
            ur_lv = t.ur_lv_kv * (tap if t.tap_side == "lv" else 1.0)
            zr = ur_lv**2 / t.sr_mva
            uk, ur = (t.ukr_percent, t.urr_percent)
            if seq == 0:
                uk = t.uk0_percent if t.uk0_percent is not None else uk
                ur = t.ur0_percent if t.ur0_percent is not None else ur
            rk = ur / 100.0 * zr
            xk = math.sqrt((uk / 100.0 * zr) ** 2 - rk**2)
            z = complex(rk * rf, xk * h) / self.zbase(t.lv_bus) / t.parallel
            ratio = (ur_hv / ur_lv) / (self.un[t.hv_bus] / self.un[t.lv_bus])
            i, j = self.idx[t.hv_bus], self.idx[t.lv_bus]
            if seq in (1, 2):
                k = clock_numbers(t.vector_group, 2, t.id)[0]
                shift = math.radians(30.0 * k) * (1 if seq == 1 else -1)
                stamp(t.id, i, j, _pi_branch(1.0 / z, 0j, ratio * cmath.exp(1j * shift), "f"))
                continue
            hv, lv = _parse_vector_group(t.vector_group)
            zn_hv = 3.0 * complex(t.zn_hv_ohm).real / self.zbase(t.hv_bus) + 3j * complex(t.zn_hv_ohm).imag * h / self.zbase(t.hv_bus)
            zn_lv = 3.0 * complex(t.zn_lv_ohm).real / self.zbase(t.lv_bus) + 3j * complex(t.zn_lv_ohm).imag * h / self.zbase(t.lv_bus)
            if hv == "YN" and lv == "YN":
                yy = 1.0 / (z + zn_lv + zn_hv / ratio**2)
                stamp(t.id, i, j, _pi_branch(yy, 0j, complex(ratio), "f"))
            elif hv == "YN" and lv == "D":
                shunt(i, 1.0 / (z * ratio**2 + zn_hv))
            elif hv == "D" and lv == "YN":
                shunt(j, 1.0 / (z + zn_lv))
            elif "ZN" in (hv, lv):
                if hv == "ZN":
                    shunt(i, 1.0 / (z * ratio**2 + zn_hv))
                if lv == "ZN":
                    shunt(j, 1.0 / (z + zn_lv))

        for t in self.net.transformers3w:
            self._trafo3w(t, h, seq, rf, stamp, shunt)

        for q in self.net.external_grids:
            zq = S_BASE_MVA / q.skq_max_mva
            xq = zq / math.sqrt(1.0 + q.rx_max**2)
            i = self.idx[q.bus]
            if seq in (1, 2):
                shunt(i, 1.0 / complex(q.rx_max * xq * rf, xq * h))
            elif q.x0x1 is not None:
                x0 = q.x0x1 * xq
                r0 = (q.r0x0 if q.r0x0 is not None else q.rx_max) * x0
                shunt(i, 1.0 / complex(r0 * rf, x0 * h))

        for g in self.net.generators:
            zb_g = g.ur_kv**2 / g.sr_mva
            xd2 = g.xd2_percent / 100.0 * zb_g
            x2 = g.x2_percent / 100.0 * zb_g if g.x2_percent is not None else xd2
            r = g.rg_ohm if g.rg_ohm is not None else 0.07 * xd2
            i = self.idx[g.bus]
            zb = self.zbase(g.bus)
            if seq in (1, 2):
                shunt(i, 1.0 / (complex(r * rf, x2 * h) / zb))
            elif g.x0_percent is not None:
                x0 = g.x0_percent / 100.0 * zb_g
                zn = complex(g.zn_ohm)
                shunt(i, 1.0 / (complex(r * rf + 3 * zn.real, x0 * h + 3 * zn.imag * h) / zb))

        if seq in (1, 2):
            for m in self.net.motors:
                sr = m.pr_mw / (m.efficiency * m.cos_phi)
                zm = m.ur_kv**2 / (m.ilr_ir * sr) / m.count
                rx = m.rx if m.rx is not None else 0.1
                xm = zm / math.sqrt(1.0 + rx**2)
                shunt(self.idx[m.bus], 1.0 / (complex(rx * xm * rf, xm * h) / self.zbase(m.bus)))
            if self.include_loads:
                for ld in self.net.loads:
                    i = self.idx[ld.bus]
                    p, q = ld.p_mw * ld.count / S_BASE_MVA, ld.q_mvar * ld.count / S_BASE_MVA
                    # R e L in parallelo: Y = P − jQ/h (potenze a tensione nominale)
                    shunt(i, complex(p, -q / h))

        for sh in self.net.shunts:
            i = self.idx[sh.bus]
            g, q = sh.p_mw / S_BASE_MVA, sh.q_mvar / S_BASE_MVA
            if seq == 0:
                continue  # derivazioni trifase senza collegamento a terra
            # condensatore (Q < 0): B·h; reattore (Q > 0): 1/(X·h)
            shunt(i, complex(g, -q / h) if q > 0 else complex(g, -q * h))
        if seq in (1, 2):
            for hf in self.net.harmonic_filters:
                shunt(self.idx[hf.bus], 1.0 / filter_impedance_pu(hf, h))
        return y

    def _trafo3w(self, t, h, seq, rf, stamp, shunt) -> None:
        star = self.idx[f"{t.id}::stella"]
        zb_hv = t.ur_hv_kv**2

        def pair(p: str) -> complex:
            sr = getattr(t, f"sr_{p}_mva")
            uk = getattr(t, f"ukr_{p}_percent")
            ur = getattr(t, f"urr_{p}_percent")
            if seq == 0:
                uk = getattr(t, f"uk0_{p}_percent") or uk
                ur = getattr(t, f"ur0_{p}_percent") or ur
            rk = ur / 100.0 * zb_hv / sr
            xk = math.sqrt((uk / 100.0 * zb_hv / sr) ** 2 - rk**2)
            return complex(rk * rf, xk * h)

        hm, hl, ml = pair("hv_mv"), pair("hv_lv"), pair("mv_lv")
        zs = {"hv": (hm + hl - ml) / 2, "mv": (hm + ml - hl) / 2, "lv": (hl + ml - hm) / 2}
        k = clock_numbers(t.vector_group, 3, t.id)
        shifts = {"hv": 0.0, "mv": math.radians(30.0 * k[0]), "lv": math.radians(30.0 * k[1])}
        conns = dict(zip(("hv", "mv", "lv"), _parse_vector_group_3w(t.vector_group)))
        for w in ("hv", "mv", "lv"):
            bus = getattr(t, f"{w}_bus")
            ur_w = getattr(t, f"ur_{w}_kv")
            z = zs[w] * (ur_w / t.ur_hv_kv) ** 2 / self.zbase(bus)
            i = self.idx[bus]
            if seq in (1, 2):
                sgn = 1 if seq == 1 else -1
                a = (self.un[bus] / ur_w) * cmath.exp(1j * sgn * shifts[w])
                # nodo dell'avvolgimento (f) — centro stella (t), trasformatore ideale lato stella
                stamp(f"{t.id}:{w}", i, star, _pi_branch(1.0 / z, 0j, a, "t"))
            elif conns[w] == "YN":
                zn = complex(getattr(t, f"zn_{w}_ohm"))
                zn3 = complex(3 * zn.real, 3 * zn.imag * h) / self.zbase(bus)
                stamp(f"{t.id}:{w}", i, star, _pi_branch(1.0 / (z + zn3), 0j,
                                                         complex(self.un[bus] / ur_w), "t"))
            elif conns[w] == "D":
                shunt(star, 1.0 / (zs[w] / (t.ur_hv_kv**2 / S_BASE_MVA)))


# --- risultati ------------------------------------------------------------------------------


@dataclass
class HarmonicBus:
    bus: str
    un_kv: float
    v1_pu: float
    vh_percent: dict[int, float]  # in % della tensione nominale
    thd_percent: float
    limit_violations: list[str] = field(default_factory=list)


@dataclass
class HarmonicBranch:
    id: str
    bus: str  # estremo a cui si riferiscono le correnti
    i1_a: float
    ih_a: dict[int, float]
    thd_percent: float
    rms_a: float
    k_factor: float


@dataclass
class HarmonicResult:
    network: str
    orders: list[int]
    buses: list[HarmonicBus]
    branches: list[HarmonicBranch]
    vh_complex: dict[int, dict[str, complex]]  # tensioni armoniche complesse (p.u.)
    warnings: list[str] = field(default_factory=list)
    pcc: Optional[dict] = None

    def bus(self, bus_id: str) -> HarmonicBus:
        return next(b for b in self.buses if b.bus == bus_id)

    def branch(self, branch_id: str, bus: Optional[str] = None) -> HarmonicBranch:
        return next(b for b in self.branches if b.id == branch_id and (bus is None or b.bus == bus))


def harmonic_analysis(
    net: Network,
    include_loads: bool = True,
    r_skin: bool = False,
    limits: str = "en50160",
    pcc_bus: Optional[str] = None,
    pcc_branch: Optional[str] = None,
    il_a: Optional[float] = None,
) -> HarmonicResult:
    """Tensioni e correnti armoniche, THD e verifica dei limiti.

    limits: "en50160" (EN 50160/IEC 61000-2-2, singole armoniche e THD 8 %) o
    "ieee519" (IEEE 519-2014, limiti di tensione per livello di tensione).
    Con pcc_bus, pcc_branch (ramo che alimenta il punto di consegna, correnti
    all'estremo pcc_bus) e il_a (massima corrente di carico) verifica anche i
    limiti di corrente IEEE 519 (TDD e singole armoniche) con Isc/IL dalla
    corrente di cortocircuito trifase IEC 60909 massima.
    """
    if limits not in ("en50160", "ieee519"):
        raise ValueError("limits deve essere 'en50160' o 'ieee519'")
    if not net.harmonic_sources:
        raise ValueError("la rete non contiene sorgenti armoniche (harmonic_sources)")
    lf = run_load_flow(net)
    if not lf.converged:
        raise ValueError("armoniche: flusso di potenza non convergente")
    hn = _HarmonicNetwork(net, include_loads, r_skin)
    idx = hn.idx
    names = {i: k for k, i in idx.items()}
    v1 = {b.bus: b.vm_pu * cmath.exp(1j * math.radians(b.va_degree)) for b in lf.buses}

    # correnti armoniche assorbite dalle sorgenti (p.u. della base del nodo)
    inj: dict[int, np.ndarray] = {}
    for src in net.harmonic_sources:
        i1 = _fundamental_current(net, lf, src, v1, hn)
        for h, (mag, ang) in _spectrum(src).items():
            ih = abs(i1) * mag / 100.0 * cmath.exp(1j * (h * cmath.phase(i1) + math.radians(ang)))
            arr = inj.setdefault(h, np.zeros(hn.n, dtype=complex))
            arr[idx[src.bus]] -= ih  # corrente iniettata nella rete
    orders = sorted(inj)

    vh: dict[int, dict[str, complex]] = {}
    ih_br: dict[tuple[str, str], dict[int, complex]] = {}
    for h in orders:
        seq = sequence_of(h)
        y = hn.ybus(h, seq)
        v = _solve(y, inj[h])
        vh[h] = {names[i]: v[i] for i in range(hn.n)}
        for name, i, j, (yff, yft, ytf, ytt) in hn.branches:
            ib_i = S_BASE_MVA / (math.sqrt(3.0) * hn.un[names[i]]) * 1000.0
            ib_j = S_BASE_MVA / (math.sqrt(3.0) * hn.un[names[j]]) * 1000.0
            ih_br.setdefault((name, names[i]), {})[h] = (yff * v[i] + yft * v[j]) * ib_i
            ih_br.setdefault((name, names[j]), {})[h] = (ytf * v[i] + ytt * v[j]) * ib_j
    warnings = list(hn.warnings)

    buses = []
    for b in net.buses:
        vhp = {h: abs(vh[h][b.id]) * 100.0 for h in orders}
        v1m = abs(v1[b.id])
        thd = math.sqrt(sum(x**2 for x in vhp.values())) / v1m if v1m > 0 else 0.0
        viol = []
        if limits == "en50160":
            for h, lim in EN50160.items():
                if vhp.get(h, 0.0) / v1m > lim:
                    viol.append(f"V{h} = {vhp[h] / v1m:.2f} % > {lim:g} %")
            # THD della norma: armoniche fino alla 40ª
            thd40 = math.sqrt(sum(x**2 for h, x in vhp.items() if h <= 40)) / v1m if v1m > 0 else 0.0
            if thd40 > EN50160_THD:
                viol.append(f"THD (fino alla 40ª) = {thd40:.2f} % > {EN50160_THD:g} %")
        else:
            lim_h, lim_thd = ieee519_voltage_limits(b.un_kv)
            for h, val in vhp.items():
                if val / v1m > lim_h:
                    viol.append(f"V{h} = {val / v1m:.2f} % > {lim_h:g} %")
            if thd > lim_thd:
                viol.append(f"THD = {thd:.2f} % > {lim_thd:g} %")
        buses.append(HarmonicBus(b.id, b.un_kv, v1m, vhp, thd, viol))

    branches = []
    for br in lf.branches:
        for end, i1_ka in ((br.from_bus, br.i_from_ka), (br.to_bus, br.i_to_ka)):
            if end.endswith("::stella"):
                continue
            hs = ih_br.get((br.id, end), {})
            mags = {h: abs(hs.get(h, 0j)) for h in orders}
            i1 = i1_ka * 1000.0
            sq = sum(x**2 for x in mags.values())
            thd = math.sqrt(sq) / i1 * 100.0 if i1 > 0 else 0.0
            rms = math.sqrt(i1**2 + sq)
            num = i1**2 + sum((h * x) ** 2 for h, x in mags.items())
            kf = num / (i1**2 + sq) if i1**2 + sq > 0 else 1.0
            branches.append(HarmonicBranch(br.id, end, i1, mags, thd, rms, kf))

    res = HarmonicResult(net.name, orders, buses, branches, vh, warnings)
    if pcc_bus is not None:
        res.pcc = _check_pcc(net, res, pcc_bus, pcc_branch, il_a)
    return res


def _solve(y: np.ndarray, i: np.ndarray) -> np.ndarray:
    """V = Y⁻¹·I sulle parti di rete con collegamento verso terra (altrove 0)."""
    n = y.shape[0]
    v = np.zeros(n, dtype=complex)
    seen = np.zeros(n, dtype=bool)
    for start in range(n):
        if seen[start]:
            continue
        comp, stack = [], [start]
        seen[start] = True
        while stack:
            k = stack.pop()
            comp.append(k)
            for j in np.nonzero(y[k])[0]:
                if not seen[j]:
                    seen[j] = True
                    stack.append(j)
        sub = np.ix_(comp, comp)
        try:
            v[comp] = np.linalg.solve(y[sub], i[comp])
        except np.linalg.LinAlgError:
            if np.any(np.abs(i[comp]) > 0):
                raise ValueError("armoniche: parte di rete senza percorso per le correnti iniettate") from None
    return v


def _fundamental_current(net: Network, lf, src: HarmonicSource, v1: dict, hn) -> complex:
    """Corrente fondamentale assorbita dalla sorgente, p.u. della base del nodo."""
    ib = S_BASE_MVA / (math.sqrt(3.0) * hn.un[src.bus]) * 1000.0  # A
    if src.i1_a is not None:
        return src.i1_a / ib * cmath.exp(1j * math.radians(src.angle_deg))
    if src.element is None:
        raise ValueError(f"{src.id}: indicare element (carico, motore, generatore statico) o i1_a")
    v = v1[src.bus]
    for ld in net.loads:
        if ld.id == src.element:
            s = complex(ld.p_mw, ld.q_mvar) * ld.count / S_BASE_MVA
            break
    else:
        for m in net.motors:
            if m.id == src.element:
                p = m.loading * m.pr_mw / m.efficiency * m.count / S_BASE_MVA
                s = complex(p, p * math.tan(math.acos(m.cos_phi)))
                break
        else:
            for sg in net.static_generators:
                if sg.id == src.element:
                    # generatore: corrente assorbita = −corrente erogata
                    s = -complex(sg.p_mw, sg.q_mvar) * sg.count / S_BASE_MVA
                    break
            else:
                raise ValueError(f"{src.id}: elemento inesistente {src.element!r}")
    if abs(s) == 0:
        raise ValueError(f"{src.id}: l'elemento {src.element} ha potenza nulla")
    return (s / v).conjugate()


def _check_pcc(net: Network, res: HarmonicResult, pcc_bus: str, pcc_branch: Optional[str],
               il_a: Optional[float]) -> dict:
    from .calc import calculate

    b = next(x for x in net.buses if x.id == pcc_bus)
    out: dict = {"bus": pcc_bus, "violations": []}
    if pcc_branch is None or il_a is None:
        return out
    isc = calculate(net).bus(pcc_bus).ikss3_ka * 1000.0
    ratio = isc / il_a
    bands, tdd_lim = ieee519_current_limits(ratio, b.un_kv)
    br = res.branch(pcc_branch, pcc_bus)
    tdd = math.sqrt(sum(x**2 for x in br.ih_a.values())) / il_a * 100.0
    out.update(isc_a=isc, il_a=il_a, isc_il=ratio, tdd_percent=tdd, tdd_limit=tdd_lim,
               individual={h: x / il_a * 100.0 for h, x in br.ih_a.items()})
    if tdd > tdd_lim:
        out["violations"].append(f"TDD = {tdd:.2f} % > {tdd_lim:g} %")
    for h, val in out["individual"].items():
        for a, c, lim in bands:
            if a <= h <= c or (h == 2 and a == 3):
                lim_h = lim if h % 2 else lim * 0.25
                if val > lim_h:
                    out["violations"].append(f"I{h} = {val:.2f} % di IL > {lim_h:g} %")
    return out


# --- scansione in frequenza --------------------------------------------------------------------


@dataclass
class FrequencyScan:
    bus: str
    orders: np.ndarray
    z_ohm: np.ndarray  # modulo dell'impedenza vista dal nodo (sequenza diretta)
    resonances: list[tuple[float, float]]  # (ordine, |Z| Ω) dei massimi locali


def frequency_scan(net: Network, bus: str, h_max: float = 50.0, step: float = 0.02,
                   include_loads: bool = True, seq: int = 1) -> FrequencyScan:
    """Impedenza vista dal nodo in funzione dell'ordine armonico e risonanze parallelo."""
    hn = _HarmonicNetwork(net, include_loads)
    k = hn.idx[bus]
    orders = np.arange(1.0, h_max + step / 2, step)
    z = np.zeros(len(orders))
    for n_, h in enumerate(orders):
        y = hn.ybus(float(h), seq)
        e = np.zeros(hn.n, dtype=complex)
        e[k] = 1.0
        z[n_] = abs(_solve(y, e)[k]) * hn.zbase(bus)
    res = [(float(orders[i]), float(z[i])) for i in range(1, len(z) - 1) if z[i] > z[i - 1] and z[i] >= z[i + 1]]
    return FrequencyScan(bus, orders, z, res)


def design_single_tuned_filter(q_mvar: float, tuned_order: float, un_kv: float,
                               quality: float = 50.0, f_hz: float = 50.0) -> dict:
    """Componenti del filtro accordato (per fase, collegamento a stella): C [µF], L [mH], R [Ω]."""
    ht = tuned_order
    xc = un_kv**2 / q_mvar * ht**2 / (ht**2 - 1.0)
    xl = xc / ht**2
    w = 2 * math.pi * f_hz
    return {"c_uf": 1e6 / (w * xc), "l_mh": 1e3 * xl / w, "r_ohm": ht * xl / quality,
            "xc_ohm": xc, "xl_ohm": xl, "f_accordo_hz": ht * f_hz}


# --- uscita ------------------------------------------------------------------------------------


def result_to_markdown(res: HarmonicResult, max_orders: int = 12) -> str:
    out = [f"# Armoniche — {res.network}", ""]
    shown = res.orders[:max_orders]
    out += ["## Tensioni armoniche (% della tensione nominale)", "",
            "| Nodo | Un [kV] | " + " | ".join(f"V{h}" for h in shown) + " | THD [%] | Limiti |",
            "|---|---|" + "---|" * len(shown) + "---|---|"]
    for b in res.buses:
        lim = "OK" if not b.limit_violations else "; ".join(b.limit_violations)
        out.append(f"| {b.bus} | {b.un_kv:g} | " + " | ".join(f"{b.vh_percent[h]:.2f}" for h in shown)
                   + f" | {b.thd_percent:.2f} | {lim} |")
    out += ["", "## Correnti nei rami", "",
            "| Ramo | Estremo | I1 [A] | " + " | ".join(f"I{h} [A]" for h in shown)
            + " | THD [%] | I eff. [A] | Fattore K |",
            "|---|---|---|" + "---|" * len(shown) + "---|---|---|"]
    for br in res.branches:
        out.append(f"| {br.id} | {br.bus} | {br.i1_a:.1f} | "
                   + " | ".join(f"{br.ih_a.get(h, 0.0):.2f}" for h in shown)
                   + f" | {br.thd_percent:.2f} | {br.rms_a:.1f} | {br.k_factor:.2f} |")
    if res.pcc and "tdd_percent" in res.pcc:
        p = res.pcc
        out += ["", f"## Punto di consegna {p['bus']} (IEEE 519)", "",
                f"Isc = {p['isc_a']:.0f} A, IL = {p['il_a']:.0f} A, Isc/IL = {p['isc_il']:.1f}; "
                f"TDD = {p['tdd_percent']:.2f} % (limite {p['tdd_limit']:g} %).", ""]
        out += [f"- {v}" for v in p["violations"]] or ["Limiti di corrente rispettati."]
    if res.warnings:
        out += ["", "## Avvisi", ""] + [f"- {w}" for w in res.warnings]
    return "\n".join(out) + "\n"


def result_to_dict(res: HarmonicResult) -> dict:
    import dataclasses

    return {
        "network": res.network,
        "orders": res.orders,
        "buses": [dataclasses.asdict(b) for b in res.buses],
        "branches": [dataclasses.asdict(b) for b in res.branches],
        "pcc": res.pcc,
        "warnings": res.warnings,
    }


def scan_svg(scan: FrequencyScan, f_hz: float = 50.0) -> str:
    """Grafico SVG di |Z| (scala logaritmica) in funzione dell'ordine armonico."""
    w, h, ml, mr, mt, mb = 720, 420, 70, 20, 40, 45
    z = np.maximum(scan.z_ohm, 1e-9)
    lo, hi = math.floor(math.log10(z.min())), math.ceil(math.log10(z.max()))
    if hi == lo:
        hi += 1
    h0, h1 = float(scan.orders[0]), float(scan.orders[-1])

    def x(o: float) -> float:
        return ml + (o - h0) / (h1 - h0) * (w - ml - mr)

    def y(v: float) -> float:
        return mt + (hi - math.log10(v)) / (hi - lo) * (h - mt - mb)

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         'font-family="sans-serif" font-size="11">', f'<rect width="{w}" height="{h}" fill="white"/>',
         f'<text x="{w / 2}" y="20" text-anchor="middle" font-size="13">Scansione in frequenza — nodo {scan.bus}</text>']
    for e in range(lo, hi + 1):
        p.append(f'<line x1="{ml}" y1="{y(10**e):.1f}" x2="{w - mr}" y2="{y(10**e):.1f}" stroke="#e5e7eb"/>')
        p.append(f'<text x="{ml - 5}" y="{y(10**e) + 4:.1f}" text-anchor="end">{10**e:g}</text>')
    for o in range(int(h0), int(h1) + 1, 5 if h1 > 20 else 1):
        p.append(f'<line x1="{x(o):.1f}" y1="{mt}" x2="{x(o):.1f}" y2="{h - mb}" stroke="#f3f4f6"/>')
        p.append(f'<text x="{x(o):.1f}" y="{h - mb + 15}" text-anchor="middle">{o}</text>')
    pts = " ".join(f"{x(float(o)):.1f},{y(float(v)):.1f}" for o, v in zip(scan.orders, z))
    p.append(f'<polyline fill="none" stroke="#2563eb" stroke-width="1.8" points="{pts}"/>')
    for o, v in scan.resonances:
        p.append(f'<circle cx="{x(o):.1f}" cy="{y(v):.1f}" r="3" fill="#dc2626"/>')
        p.append(f'<text x="{x(o) + 5:.1f}" y="{y(v) - 5:.1f}" fill="#dc2626">h = {o:.2f}</text>')
    p.append(f'<text x="{w / 2}" y="{h - 10}" text-anchor="middle">ordine armonico (f / {f_hz:g} Hz)</text>')
    p.append(f'<text x="15" y="{h / 2}" transform="rotate(-90 15 {h / 2})" text-anchor="middle">|Z| [Ω]</text>')
    p.append("</svg>")
    return "\n".join(p)
