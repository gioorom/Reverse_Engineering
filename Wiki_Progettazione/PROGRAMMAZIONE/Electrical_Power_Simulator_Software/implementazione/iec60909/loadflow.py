"""Flusso di potenza (load flow) con il metodo di Newton-Raphson in coordinate polari.

Usa lo stesso modello di rete del calcolo di cortocircuito, con i dati di
esercizio (carichi, potenze dei generatori, tensioni regolate, prese dei
trasformatori, capacità delle linee). Valori in per unità con potenza di base
100 MVA e tensione di base pari alla tensione nominale di ogni nodo; nessun
fattore di correzione della IEC 60909.

Modelli:
- rete esterna: nodo di saldo con tensione e angolo imposti;
- generatore: nodo PV (p_mw, vm_pu) oppure PQ (vm_pu = None, q_mvar), con
  limiti di potenza reattiva facoltativi;
- carichi, motori (P = loading·Pr/η, Q = P·tanφ) e generatori statici: potenza
  costante;
- derivazioni (shunts): impedenza costante;
- linea: circuito a π con metà della capacità a ogni estremo;
- trasformatore a due avvolgimenti: impedenza di cortocircuito riferita alla
  tensione nominale (con presa) del lato BT, rapporto con il variatore,
  magnetizzazione divisa a metà tra i due lati (modello a π);
- trasformatore a tre avvolgimenti: stella equivalente delle impedenze di
  coppia, senza magnetizzazione e senza variatore.
Gli sfasamenti dei gruppi vettoriali non sono considerati (angoli relativi).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .network import Line, Network, Transformer, Transformer3W

S_BASE_MVA = 100.0


@dataclass
class LfBus:
    bus: str
    un_kv: float
    vm_pu: float
    va_degree: float
    p_mw: float  # potenza netta immessa nel nodo
    q_mvar: float

    @property
    def u_kv(self) -> float:
        return self.vm_pu * self.un_kv


@dataclass
class LfBranch:
    """Ramo (linea, trasformatore o avvolgimento di un tre avvolgimenti)."""

    id: str
    kind: str  # "line", "trafo", "trafo3w"
    from_bus: str
    to_bus: str
    p_from_mw: float
    q_from_mvar: float
    p_to_mw: float
    q_to_mvar: float
    i_from_ka: float
    i_to_ka: float
    loading_percent: Optional[float]

    @property
    def pl_mw(self) -> float:
        return self.p_from_mw + self.p_to_mw

    @property
    def ql_mvar(self) -> float:
        return self.q_from_mvar + self.q_to_mvar


@dataclass
class LfSource:
    id: str
    kind: str  # "ext_grid" o "gen"
    bus: str
    p_mw: float
    q_mvar: float


@dataclass
class LoadFlowResult:
    network: str
    converged: bool
    iterations: int
    buses: list[LfBus]
    branches: list[LfBranch]
    sources: list[LfSource]
    warnings: list[str] = field(default_factory=list)

    def bus(self, bus_id: str) -> LfBus:
        return next(b for b in self.buses if b.bus == bus_id)

    def branch(self, branch_id: str) -> LfBranch:
        return next(b for b in self.branches if b.id == branch_id)

    def source(self, source_id: str) -> LfSource:
        return next(s for s in self.sources if s.id == source_id)

    @property
    def losses_mw(self) -> float:
        return sum(b.pl_mw for b in self.branches)

    @property
    def losses_mvar(self) -> float:
        return sum(b.ql_mvar for b in self.branches)


@dataclass
class _Branch:
    id: str
    kind: str
    f: int
    t: int
    yff: complex
    yft: complex
    ytf: complex
    ytt: complex
    rating: Optional[float]  # kA (linee) o MVA (trasformatori)
    show: bool = True  # falso per i lati verso il centro stella


def _star_node(t: Transformer3W) -> str:
    return f"{t.id}::stella"


class _Model:
    def __init__(self, net: Network):
        self.net = net
        self.idx = net.bus_index()
        self.un = {b.id: b.un_kv for b in net.buses}
        for t in net.transformers3w:
            self.idx[_star_node(t)] = len(self.idx)
            self.un[_star_node(t)] = t.ur_hv_kv
        self.n = len(self.idx)
        self.branches: list[_Branch] = []
        self.ysh = np.zeros(self.n, dtype=complex)
        for ln in net.lines:
            self._line(ln)
        for t in net.transformers:
            self._trafo(t)
        for t3 in net.transformers3w:
            self._trafo3w(t3)
        for sh in net.shunts:
            # potenza assorbita a tensione nominale: S = V²·Y*  →  Y = (P − jQ)/S_base
            self.ysh[self.idx[sh.bus]] += complex(sh.p_mw, -sh.q_mvar) / S_BASE_MVA
        self.ybus = np.zeros((self.n, self.n), dtype=complex)
        for br in self.branches:
            self.ybus[br.f, br.f] += br.yff
            self.ybus[br.f, br.t] += br.yft
            self.ybus[br.t, br.f] += br.ytf
            self.ybus[br.t, br.t] += br.ytt
        self.ybus[np.diag_indices(self.n)] += self.ysh

    def zbase(self, bus: str) -> float:
        return self.un[bus] ** 2 / S_BASE_MVA

    def _line(self, ln: Line) -> None:
        zb = self.zbase(ln.from_bus)
        z = complex(ln.r1_ohm_per_km, ln.x1_ohm_per_km) * ln.length_km / ln.parallel / zb
        b = 2.0 * math.pi * self.net.f_hz * ln.c_nf_per_km * 1e-9 * ln.length_km * ln.parallel * zb
        ys, yh = 1.0 / z, complex(0.0, b / 2.0)
        rating = None if ln.max_i_ka is None else ln.max_i_ka * ln.parallel
        self.branches.append(
            _Branch(ln.id, "line", self.idx[ln.from_bus], self.idx[ln.to_bus],
                    ys + yh, -ys, -ys, ys + yh, rating)
        )

    def _trafo(self, t: Transformer) -> None:
        tap = 1.0 + t.tap_pos * t.tap_step_percent / 100.0
        ur_hv = t.ur_hv_kv * (tap if t.tap_side == "hv" else 1.0)
        ur_lv = t.ur_lv_kv * (tap if t.tap_side == "lv" else 1.0)
        zr = ur_lv**2 / t.sr_mva
        zk, rk = t.ukr_percent / 100.0 * zr, t.urr_percent / 100.0 * zr
        z = complex(rk, math.sqrt(zk**2 - rk**2)) / self.zbase(t.lv_bus)
        # magnetizzazione in p.u. del trasformatore, riportata alla base del nodo BT
        g = t.pfe_kw / 1000.0 / t.sr_mva
        ym_abs = t.i0_percent / 100.0
        ym = complex(g, -math.sqrt(max(0.0, ym_abs**2 - g**2)))
        ym *= t.sr_mva / S_BASE_MVA * self.un[t.lv_bus] ** 2 / ur_lv**2
        ys = t.parallel / z
        yh = t.parallel * ym / 2.0
        ratio = (ur_hv / ur_lv) / (self.un[t.hv_bus] / self.un[t.lv_bus])
        self.branches.append(
            _Branch(t.id, "trafo", self.idx[t.hv_bus], self.idx[t.lv_bus],
                    (ys + yh) / ratio**2, -ys / ratio, -ys / ratio, ys + yh,
                    t.sr_mva * t.parallel)
        )

    def _trafo3w(self, t: Transformer3W) -> None:
        star = _star_node(t)
        zb_hv = t.ur_hv_kv**2  # Ω per MVA alla tensione AT

        def pair(p: str) -> complex:
            sr = getattr(t, f"sr_{p}_mva")
            zk = getattr(t, f"ukr_{p}_percent") / 100.0 * zb_hv / sr
            rk = getattr(t, f"urr_{p}_percent") / 100.0 * zb_hv / sr
            return complex(rk, math.sqrt(zk**2 - rk**2))

        hm, hl, ml = pair("hv_mv"), pair("hv_lv"), pair("mv_lv")
        z_star = {"hv": (hm + hl - ml) / 2, "mv": (hm + ml - hl) / 2, "lv": (hl + ml - hm) / 2}
        rating = {
            "hv": max(t.sr_hv_mv_mva, t.sr_hv_lv_mva),
            "mv": max(t.sr_hv_mv_mva, t.sr_mv_lv_mva),
            "lv": max(t.sr_hv_lv_mva, t.sr_mv_lv_mva),
        }
        for w in ("hv", "mv", "lv"):
            bus = getattr(t, f"{w}_bus")
            ur_w = getattr(t, f"ur_{w}_kv")
            z = z_star[w] * (ur_w / t.ur_hv_kv) ** 2 / self.zbase(bus)
            ratio = self.un[bus] / ur_w  # centro stella con base UrAT
            ys = 1.0 / z
            # ramo dal nodo dell'avvolgimento al centro stella (rapporto lato stella)
            self.branches.append(
                _Branch(f"{t.id}:{w}", "trafo3w", self.idx[bus], self.idx[star],
                        ys, -ys / ratio, -ys / ratio, ys / ratio**2, rating[w])
            )


def _injections(net: Network, idx: dict[str, int], n: int) -> np.ndarray:
    s = np.zeros(n, dtype=complex)
    for ld in net.loads:
        s[idx[ld.bus]] -= complex(ld.p_mw, ld.q_mvar) * ld.count
    for m in net.motors:
        p = m.loading * m.pr_mw / m.efficiency * m.count
        s[idx[m.bus]] -= complex(p, p * math.tan(math.acos(m.cos_phi)))
    for sg in net.static_generators:
        s[idx[sg.bus]] += complex(sg.p_mw, sg.q_mvar) * sg.count
    for g in net.generators:
        s[idx[g.bus]] += complex(g.p_mw, g.q_mvar if g.vm_pu is None else 0.0)
    return s / S_BASE_MVA


def _gen_injection(net: Network, idx: dict[str, int], n: int) -> np.ndarray:
    """Potenze impresse dei generatori sincroni (MW/Mvar) per nodo."""
    s = np.zeros(n, dtype=complex)
    for g in net.generators:
        s[idx[g.bus]] += complex(g.p_mw, g.q_mvar if g.vm_pu is None else 0.0)
    return s


def _newton(
    ybus: np.ndarray, sbus: np.ndarray, v0: np.ndarray, pv: np.ndarray, pq: np.ndarray,
    tol: float, max_iter: int,
) -> tuple[np.ndarray, bool, int]:
    v = v0.copy()
    pvpq = np.r_[pv, pq]
    npvpq, npq = len(pvpq), len(pq)

    def mismatch(v: np.ndarray) -> np.ndarray:
        s = v * np.conj(ybus @ v) - sbus
        return np.r_[s[pvpq].real, s[pq].imag]

    f = mismatch(v)
    for it in range(max_iter + 1):
        if np.max(np.abs(f), initial=0.0) < tol:
            return v, True, it
        if it == max_iter:
            break
        ibus = ybus @ v
        dv = np.diag(v)
        dvn = np.diag(v / np.abs(v))
        ds_dvm = dv @ np.conj(ybus @ dvn) + np.conj(np.diag(ibus)) @ dvn
        ds_dva = 1j * dv @ np.conj(np.diag(ibus) - ybus @ dv)
        jac = np.block([
            [ds_dva[np.ix_(pvpq, pvpq)].real, ds_dvm[np.ix_(pvpq, pq)].real],
            [ds_dva[np.ix_(pq, pvpq)].imag, ds_dvm[np.ix_(pq, pq)].imag],
        ])
        dx = np.linalg.solve(jac, -f)
        va = np.angle(v)
        vm = np.abs(v)
        va[pvpq] += dx[:npvpq]
        vm[pq] += dx[npvpq:npvpq + npq]
        v = vm * np.exp(1j * va)
        f = mismatch(v)
    return v, False, max_iter


def run_load_flow(
    net: Network, tol_mva: float = 1e-8, max_iter: int = 30, enforce_q_lims: bool = False,
) -> LoadFlowResult:
    """Flusso di potenza con il metodo di Newton-Raphson.

    tol_mva: tolleranza sugli scarti di potenza (MW/Mvar).
    enforce_q_lims: i generatori PV che superano q_min_mvar/q_max_mvar passano a
    nodi PQ con la potenza reattiva al limite (iterazione esterna).
    """
    net.validate()
    model = _Model(net)
    idx, n = model.idx, model.n
    warnings: list[str] = []

    # nodo di saldo: reti esterne; senza reti esterne il primo generatore PV
    slack: dict[int, complex] = {}
    for q in net.external_grids:
        slack[idx[q.bus]] = q.vm_pu * cmath.exp(1j * math.radians(q.va_degree))
    pv_gens = [g for g in net.generators if g.vm_pu is not None]
    slack_gen = None
    if not slack:
        if not pv_gens:
            raise ValueError("flusso di potenza: serve una rete esterna o un generatore con vm_pu")
        slack_gen = pv_gens[0]
        slack[idx[slack_gen.bus]] = complex(slack_gen.vm_pu, 0.0)
        warnings.append(f"{slack_gen.id}: nessuna rete esterna, il generatore è il nodo di saldo")

    vset: dict[int, float] = {}
    for g in pv_gens:
        i = idx[g.bus]
        if i in slack:
            if abs(abs(slack[i]) - g.vm_pu) > 1e-9:
                raise ValueError(f"{g.id}: vm_pu diversa da quella del nodo di saldo")
            continue
        if i in vset and abs(vset[i] - g.vm_pu) > 1e-9:
            raise ValueError(f"{g.id}: generatori PV sullo stesso nodo con tensioni diverse")
        vset[i] = g.vm_pu

    # nodi isolati: nessun percorso verso il nodo di saldo
    adj = model.ybus != 0
    seen = set(slack)
    stack = list(slack)
    while stack:
        k = stack.pop()
        for j in np.nonzero(adj[k])[0]:
            if j not in seen:
                seen.add(int(j))
                stack.append(int(j))
    isolated = [b.id for b in net.buses if idx[b.id] not in seen]
    if isolated:
        raise ValueError(f"nodi non collegati al nodo di saldo: {isolated}")

    sbus = _injections(net, idx, n)
    q_fixed: dict[int, float] = {}  # nodi PV passati a PQ: potenza reattiva al limite (p.u.)
    tol = tol_mva / S_BASE_MVA
    total_iter = 0
    for _ in range(len(pv_gens) + 1):
        pv = np.array(sorted(i for i in vset if i not in q_fixed), dtype=int)
        pq = np.array([i for i in range(n) if i not in slack and i not in pv], dtype=int)
        v0 = np.ones(n, dtype=complex)
        for i, vs in vset.items():
            v0[i] = vs
        for i, vs in slack.items():
            v0[i] = vs
        s = sbus.copy()
        for i, qf in q_fixed.items():
            s[i] += 1j * qf
        v, converged, iters = _newton(model.ybus, s, v0, pv, pq, tol, max_iter)
        total_iter += iters
        if not converged or not enforce_q_lims:
            break
        sinj = v * np.conj(model.ybus @ v)
        violated = False
        for i in pv:
            gens = [g for g in pv_gens if idx[g.bus] == i]
            # potenza reattiva dei generatori = immessa nel nodo + assorbita dai carichi
            q_gen = (sinj[i] - sbus[i]).imag
            qmin = sum(g.q_min_mvar if g.q_min_mvar is not None else -math.inf for g in gens)
            qmax = sum(g.q_max_mvar if g.q_max_mvar is not None else math.inf for g in gens)
            if q_gen * S_BASE_MVA > qmax + 1e-9:
                q_fixed[i] = qmax / S_BASE_MVA
                violated = True
            elif q_gen * S_BASE_MVA < qmin - 1e-9:
                q_fixed[i] = qmin / S_BASE_MVA
                violated = True
        if not violated:
            break
    if not converged:
        warnings.append(f"flusso di potenza non convergente in {max_iter} iterazioni")

    sinj = v * np.conj(model.ybus @ v)
    buses = []
    for b in net.buses:
        i = idx[b.id]
        buses.append(LfBus(b.id, b.un_kv, abs(v[i]), math.degrees(cmath.phase(v[i])),
                           sinj[i].real * S_BASE_MVA, sinj[i].imag * S_BASE_MVA))

    names = {i: name for name, i in idx.items()}
    branches = []
    for br in model.branches:
        vf, vt = v[br.f], v[br.t]
        i_f = br.yff * vf + br.yft * vt
        i_t = br.ytf * vf + br.ytt * vt
        sf, st = vf * np.conj(i_f) * S_BASE_MVA, vt * np.conj(i_t) * S_BASE_MVA
        ib_f = S_BASE_MVA / (math.sqrt(3.0) * model.un[names[br.f]])
        ib_t = S_BASE_MVA / (math.sqrt(3.0) * model.un[names[br.t]])
        i_f_ka, i_t_ka = abs(i_f) * ib_f, abs(i_t) * ib_t
        loading = None
        if br.rating is not None:
            if br.kind == "line":
                loading = max(i_f_ka, i_t_ka) / br.rating * 100.0
            elif br.kind == "trafo":
                loading = max(abs(sf), abs(st)) / br.rating * 100.0
            else:
                loading = abs(sf) / br.rating * 100.0  # lato dell'avvolgimento
        branches.append(LfBranch(br.id, br.kind, names[br.f], names[br.t], sf.real, sf.imag,
                                 st.real, st.imag, i_f_ka, i_t_ka, loading))

    # potenze delle sorgenti: generazione del nodo = potenza immessa + consumi
    gen_s = sinj * S_BASE_MVA - (_injections(net, idx, n) * S_BASE_MVA - _gen_injection(net, idx, n))
    sources = []
    grids_at: dict[int, list] = {}
    gens_at: dict[int, list] = {}
    for q in net.external_grids:
        grids_at.setdefault(idx[q.bus], []).append(q)
    for g in net.generators:
        gens_at.setdefault(idx[g.bus], []).append(g)
    for i in sorted(set(grids_at) | set(gens_at)):
        total = gen_s[i]
        gens = gens_at.get(i, [])
        fixed = {g.id: complex(g.p_mw, g.q_mvar if g.vm_pu is None else 0.0)
                 for g in gens if g is not slack_gen}
        rest = total - sum(fixed.values())  # quota del nodo di saldo o dei generatori PV
        pv_here = [g for g in gens if g.vm_pu is not None and g is not slack_gen]
        if i in grids_at:
            # reti esterne: tutta la quota libera alla prima; i generatori PV sul nodo
            # di saldo erogano solo la potenza attiva impressa
            for k, q in enumerate(grids_at[i]):
                val = rest if k == 0 else 0j
                sources.append(LfSource(q.id, "ext_grid", q.bus, val.real, val.imag))
            for g in gens:
                sources.append(LfSource(g.id, "gen", g.bus, fixed[g.id].real, fixed[g.id].imag))
            continue
        has_slack = any(g is slack_gen for g in gens)
        q_share = rest.imag / (len(pv_here) + has_slack) if (pv_here or has_slack) else 0.0
        for g in gens:
            if g is slack_gen:
                sources.append(LfSource(g.id, "gen", g.bus, rest.real, q_share))
            elif g.vm_pu is not None:
                # potenza reattiva dei generatori PV dello stesso nodo in parti uguali
                sources.append(LfSource(g.id, "gen", g.bus, g.p_mw, q_share))
            else:
                sources.append(LfSource(g.id, "gen", g.bus, g.p_mw, g.q_mvar))
    return LoadFlowResult(net.name, converged, total_iter, buses, branches, sources, warnings)


# --- uscita -----------------------------------------------------------------------


def result_to_dict(res: LoadFlowResult) -> dict:
    """Risultati del flusso di potenza come dizionario serializzabile in JSON."""
    import dataclasses

    return {
        "network": res.network,
        "converged": res.converged,
        "iterations": res.iterations,
        "losses_mw": res.losses_mw,
        "losses_mvar": res.losses_mvar,
        "buses": [dict(dataclasses.asdict(b), u_kv=b.u_kv) for b in res.buses],
        "branches": [dict(dataclasses.asdict(b), pl_mw=b.pl_mw, ql_mvar=b.ql_mvar) for b in res.branches],
        "sources": [dataclasses.asdict(s) for s in res.sources],
        "warnings": res.warnings,
    }


def _f(value: Optional[float], digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def result_to_markdown(res: LoadFlowResult) -> str:
    stato = "convergente" if res.converged else "NON convergente"
    out = [
        f"# Flusso di potenza — {res.network}",
        "",
        f"Newton-Raphson, {stato} in {res.iterations} iterazioni. "
        f"Perdite: {res.losses_mw:.4f} MW, {res.losses_mvar:.4f} Mvar.",
        "",
        "## Nodi",
        "",
        "| Nodo | Un [kV] | U [kV] | U [p.u.] | Angolo [°] | P immessa [MW] | Q immessa [Mvar] |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in res.buses:
        out.append(f"| {b.bus} | {b.un_kv:g} | {b.u_kv:.4f} | {b.vm_pu:.5f} | {b.va_degree:.4f} "
                   f"| {b.p_mw:.4f} | {b.q_mvar:.4f} |")
    out += ["", "## Sorgenti", "", "| Sorgente | Tipo | Nodo | P [MW] | Q [Mvar] |", "|---|---|---|---|---|"]
    for s in res.sources:
        tipo = "rete esterna" if s.kind == "ext_grid" else "generatore"
        out.append(f"| {s.id} | {tipo} | {s.bus} | {s.p_mw:.4f} | {s.q_mvar:.4f} |")
    out += [
        "", "## Rami", "",
        "| Ramo | Da | A | P da [MW] | Q da [Mvar] | P a [MW] | Q a [Mvar] | I da [kA] | I a [kA] "
        "| Perdite [MW] | Carico [%] |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for br in res.branches:
        out.append(
            f"| {br.id} | {br.from_bus} | {br.to_bus} | {br.p_from_mw:.4f} | {br.q_from_mvar:.4f} "
            f"| {br.p_to_mw:.4f} | {br.q_to_mvar:.4f} | {br.i_from_ka:.4f} | {br.i_to_ka:.4f} "
            f"| {br.pl_mw:.4f} | {_f(br.loading_percent, 1)} |"
        )
    if res.warnings:
        out += ["", "## Avvisi", ""] + [f"- {w}" for w in res.warnings]
    return "\n".join(out) + "\n"
