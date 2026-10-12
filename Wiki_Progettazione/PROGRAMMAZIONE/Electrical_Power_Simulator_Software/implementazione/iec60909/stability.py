"""Stabilità transitoria (angolare) della rete: simulazione nel tempo.

Modello (per unità, potenza di base 100 MVA, tensione di base del nodo):

- rete: matrice delle ammettenze del flusso di potenza (prese, sfasamenti,
  capacità, magnetizzazione), risolta a ogni istante (rete algebrica);
- carichi, motori, generatori statici e derivazioni: ammettenza costante
  ricavata dal flusso di potenza iniziale (Y = −S*/|V|² per la potenza netta
  non dovuta alle macchine);
- rete esterna: nodo a potenza infinita, fem costante dietro l'impedenza di
  cortocircuito Zq (da skq_max_mva e rx_max, con c = 1);
- generatore sincrono, equazione di oscillazione sulla potenza nominale Sr:
  dδ/dt = ω0·Δω, 2H·dΔω/dt = Pm − Pe − D·Δω;
  - "classical": fem E' costante dietro X'd;
  - "one_axis": decadimento del flusso, T'd0·dE'q/dt = Efd − E'q − (Xd − X'd)·Id,
    con Vd = Xq·Iq − Ra·Id, Vq = E'q − Ra·Iq − X'd·Id (interfaccia con la rete:
    sorgente dietro X'd, con il termine (Xq − X'd)·Iq risolto per iterazione);
  - regolatore di tensione TA·dEfd/dt = KA·(Vref − Vt) − Efd con limiti;
  - regolatore di velocità TG·dPm/dt = Pref − Δω/R − Pm con limite Pmax.
Integrazione: Runge-Kutta del quarto ordine a passo fisso, con gli eventi agli
istanti esatti (il passo è spezzato sugli eventi).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .loadflow import S_BASE_MVA, _Model, run_load_flow
from .network import Generator, Network, StabilityEvent

Y_BOLTED = 1e8  # ammettenza del guasto franco (p.u.)


@dataclass
class _Machine:
    gen: Generator
    bus: int
    model: str
    ra: float
    xd1: float  # X'd in p.u. del sistema
    xd: float
    xq: float
    td01: float
    m: float  # 2H in secondi riferiti alla base del sistema (2H·Sr/Sb)
    d: float  # smorzamento in p.u. del sistema
    pref: float
    vref: float
    in_service: bool = True

    @property
    def y(self) -> complex:
        return 1.0 / complex(self.ra, self.xd1)


@dataclass
class StabilityResult:
    """Andamenti nel tempo; angoli in gradi, velocità in p.u., tensioni in p.u."""

    network: str
    t: np.ndarray
    delta_deg: dict[str, np.ndarray]  # angolo rotorico assoluto
    speed_pu: dict[str, np.ndarray]  # 1 + Δω
    pe_mw: dict[str, np.ndarray]
    efd_pu: dict[str, np.ndarray]
    v_pu: dict[str, np.ndarray]
    stable: bool
    t_unstable_s: Optional[float]
    max_angle_diff_deg: float
    events: list[StabilityEvent]
    warnings: list[str] = field(default_factory=list)

    def relative_angles_deg(self) -> dict[str, np.ndarray]:
        """Angoli riferiti al centro d'inerzia (o alla rete esterna, se presente)."""
        return {k: v - self._reference for k, v in self.delta_deg.items()}

    _reference: np.ndarray = field(default=None, repr=False)  # type: ignore[assignment]


class _Simulator:
    def __init__(self, net: Network, angle_limit_deg: float = 180.0):
        self.net = net
        self.warnings: list[str] = []
        lf = run_load_flow(net)
        if not lf.converged:
            raise ValueError("stabilità transitoria: flusso di potenza iniziale non convergente")
        self.lf = lf
        self.model = _Model(net, True, lf.taps)
        self.idx = self.model.idx
        self.n = self.model.n
        self.w0 = 2.0 * math.pi * net.f_hz
        self.angle_limit = angle_limit_deg
        v0 = np.ones(self.n, dtype=complex)
        for b in lf.buses:
            v0[self.idx[b.bus]] = b.vm_pu * cmath.exp(1j * math.radians(b.va_degree))
        # stelle dei tre avvolgimenti: tensione dal flusso di potenza (rete lineare)
        self.v0 = self._star_voltages(v0)

        # sorgenti: rete esterna (infinita) e generatori
        s_mach = np.zeros(self.n, dtype=complex)
        self.grids = []  # (indice nodo, ammettenza, fem)
        for q in net.external_grids:
            i = self.idx[q.bus]
            src = lf.source(q.id)
            s = complex(src.p_mw, src.q_mvar) / S_BASE_MVA
            s_mach[i] += s
            zq = S_BASE_MVA / q.skq_max_mva
            xq = zq / math.sqrt(1.0 + q.rx_max**2)
            z = complex(q.rx_max * xq, xq)
            i_inj = np.conj(s / self.v0[i])
            self.grids.append((i, 1.0 / z, self.v0[i] + z * i_inj))
        self.machines: list[_Machine] = []
        self.x0: list[float] = []
        for g in net.generators:
            self._add_machine(g, lf, s_mach)
        if not self.machines and not self.grids:
            raise ValueError("stabilità transitoria: nessuna macchina sincrona né rete esterna")
        # carichi a ammettenza costante: potenza netta non dovuta alle macchine
        s_bus = np.zeros(self.n, dtype=complex)
        for b in lf.buses:
            s_bus[self.idx[b.bus]] = complex(b.p_mw, b.q_mvar) / S_BASE_MVA
        s_other = s_bus - s_mach
        self.y_load = np.where(np.abs(self.v0) > 0, -np.conj(s_other) / np.abs(self.v0) ** 2, 0.0)
        self.y_fault = np.zeros(self.n, dtype=complex)
        self.branches = {br.id: br for br in self.model.branches}
        self.tripped: set[str] = set()
        self._build()

    def _star_voltages(self, v: np.ndarray) -> np.ndarray:
        stars = [i for name, i in self.idx.items() if name.endswith("::stella")]
        if not stars:
            return v
        y = self.model.ybus
        others = [i for i in range(self.n) if i not in stars]
        v = v.copy()
        v[stars] = np.linalg.solve(y[np.ix_(stars, stars)], -y[np.ix_(stars, others)] @ v[others])
        return v

    def _add_machine(self, g: Generator, lf, s_mach: np.ndarray) -> None:
        if g.h_s is None or g.h_s <= 0:
            raise ValueError(f"{g.id}: per la stabilità transitoria serve h_s > 0")
        if g.dyn_model not in ("classical", "one_axis"):
            raise ValueError(f"{g.id}: dyn_model deve essere 'classical' o 'one_axis'")
        i = self.idx[g.bus]
        zb_gen = g.ur_kv**2 / g.sr_mva
        zb = self.model.zbase(g.bus)

        def pu(percent: Optional[float]) -> Optional[float]:
            return None if percent is None else percent / 100.0 * zb_gen / zb

        xd1 = pu(g.xd1_percent)
        if xd1 is None:
            xd1 = pu(g.xd2_percent)
            self.warnings.append(f"{g.id}: X'd non indicata, si usa X\"d")
        ra = (g.rg_ohm or 0.0) / zb
        model = g.dyn_model
        xd = pu(g.xd_percent)
        xq = pu(g.xq_percent)
        td01 = g.td01_s
        if model == "one_axis":
            if xd is None or td01 is None:
                raise ValueError(f"{g.id}: il modello one_axis richiede xd_percent e td01_s")
            if xq is None:
                xq = xd
        src = lf.source(g.id)
        s = complex(src.p_mw, src.q_mvar) / S_BASE_MVA
        s_mach[i] += s
        v = self.v0[i]
        cur = np.conj(s / v)
        if model == "classical":
            e = v + complex(ra, xd1) * cur
            delta, e1q, efd = cmath.phase(e), abs(e), abs(e)
        else:
            eq = v + complex(ra, xq) * cur
            delta = cmath.phase(eq)
            rot = cmath.exp(-1j * (delta - math.pi / 2))
            i_dq, v_dq = cur * rot, v * rot
            e1q = v_dq.imag + ra * i_dq.imag + xd1 * i_dq.real
            efd = e1q + (xd - xd1) * i_dq.real
        pe = (v * np.conj(cur)).real + ra * abs(cur) ** 2
        k = g.sr_mva / S_BASE_MVA
        vref = abs(v) + (efd / g.avr_ka if g.avr_ka else 0.0)
        mach = _Machine(g, i, model, ra, xd1, xd or xd1, xq or xd1, td01 or 1.0,
                        2.0 * g.h_s * k, g.d_pu * k, pe, vref)
        self.machines.append(mach)
        # stato: δ, Δω, E'q, Efd, Pm
        self.x0 += [delta, 0.0, e1q, efd, pe]

    # --- rete ------------------------------------------------------------------------

    def _build(self) -> None:
        y = np.zeros((self.n, self.n), dtype=complex)
        for br in self.model.branches:
            if br.id in self.tripped or br.id.split(":")[0] in self.tripped:
                continue
            y[br.f, br.f] += br.yff
            y[br.f, br.t] += br.yft
            y[br.t, br.f] += br.ytf
            y[br.t, br.t] += br.ytt
        y[np.diag_indices(self.n)] += self.model.ysh + self.y_load + self.y_fault
        for i, yq, _ in self.grids:
            y[i, i] += yq
        for m in self.machines:
            if m.in_service:
                y[m.bus, m.bus] += m.y
        self.zbus = np.linalg.inv(y)

    def solve_network(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Tensioni dei nodi e correnti delle macchine per lo stato x.

        Macchina a un asse: fem dietro X'd E = u·(j·E'q + (Xq − X'd)·Iq), con
        u = e^(j(δ − π/2)) e Iq = Im(I·u*). Le Iq delle macchine sono la
        soluzione esatta del sistema lineare reale Iq = a + B·Iq (rete lineare).
        """
        nm = len(self.machines)
        u = np.array([cmath.exp(1j * (x[5 * k] - math.pi / 2)) for k in range(nm)])
        e0 = np.zeros(nm, dtype=complex)
        c = np.zeros(nm)
        for k, m in enumerate(self.machines):
            if m.model == "classical":
                e0[k] = x[5 * k + 2] * cmath.exp(1j * x[5 * k])
            else:
                e0[k] = u[k] * 1j * x[5 * k + 2]
                c[k] = m.xq - m.xd1
        on = np.array([m.in_service for m in self.machines], dtype=bool)
        buses = np.array([m.bus for m in self.machines], dtype=int)
        ys = np.array([m.y for m in self.machines])
        inj = np.zeros(self.n, dtype=complex)
        for i, yq, eq in self.grids:
            inj[i] += yq * eq
        for k in range(nm):
            if on[k]:
                inj[buses[k]] += ys[k] * e0[k]
        v = self.zbus @ inj
        sal = [k for k in range(nm) if on[k] and c[k] != 0.0]
        if sal:
            # Iq_k = Im(u_k*·y_k·(E0_k + c_k·u_k·Iq_k − V0_k − Σ_j Z_kj·y_j·c_j·u_j·Iq_j))
            ns = len(sal)
            a = np.zeros(ns)
            bmat = np.zeros((ns, ns))
            for r, k in enumerate(sal):
                a[r] = (np.conj(u[k]) * ys[k] * (e0[k] - v[buses[k]])).imag
                for q, j in enumerate(sal):
                    coeff = -self.zbus[buses[k], buses[j]] * ys[j] * c[j] * u[j]
                    if j == k:
                        coeff += c[k] * u[k]
                    bmat[r, q] = (np.conj(u[k]) * ys[k] * coeff).imag
            iq = np.linalg.solve(np.eye(ns) - bmat, a)
            e = e0.copy()
            for r, k in enumerate(sal):
                e[k] += c[k] * u[k] * iq[r]
                inj[buses[k]] += ys[k] * c[k] * u[k] * iq[r]
            v = self.zbus @ inj
        else:
            e = e0
        cur = np.where(on, (e - v[buses]) * ys, 0j) if nm else np.zeros(0, dtype=complex)
        return v, cur

    # --- equazioni -----------------------------------------------------------------------

    def derivatives(self, x: np.ndarray) -> np.ndarray:
        v, cur = self.solve_network(x)
        dx = np.zeros_like(x)
        for k, m in enumerate(self.machines):
            if not m.in_service:
                continue
            delta, dw, e1q, efd, pm = x[5 * k: 5 * k + 5]
            vt = v[m.bus]
            i_k = cur[k]
            pe = (vt * np.conj(i_k)).real + m.ra * abs(i_k) ** 2
            dx[5 * k] = self.w0 * dw
            dx[5 * k + 1] = (pm - pe - m.d * dw) / m.m
            if m.model == "one_axis":
                i_dq = i_k * cmath.exp(-1j * (delta - math.pi / 2))
                dx[5 * k + 2] = (efd - e1q - (m.xd - m.xd1) * i_dq.real) / m.td01
                g = m.gen
                if g.avr_ka:
                    d_efd = (g.avr_ka * (m.vref - abs(vt)) - efd) / g.avr_ta_s
                    if (efd >= g.efd_max_pu and d_efd > 0) or (efd <= g.efd_min_pu and d_efd < 0):
                        d_efd = 0.0
                    dx[5 * k + 3] = d_efd
            g = m.gen
            if g.gov_droop_pu:
                pmax = g.gov_pmax_pu * g.sr_mva / S_BASE_MVA
                d_pm = (m.pref - dw / g.gov_droop_pu * g.sr_mva / S_BASE_MVA - pm) / g.gov_tg_s
                if pm >= pmax and d_pm > 0:
                    d_pm = 0.0
                dx[5 * k + 4] = d_pm
        return dx

    def clip(self, x: np.ndarray) -> np.ndarray:
        for k, m in enumerate(self.machines):
            g = m.gen
            if m.model == "one_axis" and g.avr_ka:
                x[5 * k + 3] = min(max(x[5 * k + 3], g.efd_min_pu), g.efd_max_pu)
        return x

    def apply(self, ev: StabilityEvent) -> None:
        if ev.kind == "fault":
            zf = complex(ev.r_ohm, ev.x_ohm) / self.model.zbase(ev.bus)
            self.y_fault[self.idx[ev.bus]] = Y_BOLTED if abs(zf) == 0 else 1.0 / zf
        elif ev.kind == "clear_fault":
            self.y_fault[self.idx[ev.bus]] = 0.0
        elif ev.kind == "trip_branch":
            if ev.element not in self.branches and not any(b.split(":")[0] == ev.element for b in self.branches):
                raise ValueError(f"evento a {ev.t_s} s: ramo inesistente {ev.element!r}")
            self.tripped.add(ev.element)
        elif ev.kind == "trip_gen":
            m = next((m for m in self.machines if m.gen.id == ev.element), None)
            if m is None:
                raise ValueError(f"evento a {ev.t_s} s: generatore inesistente {ev.element!r}")
            m.in_service = False
        elif ev.kind == "load":
            self.y_load[self.idx[ev.bus]] *= ev.scale
        else:
            raise ValueError(f"tipo di evento sconosciuto {ev.kind!r}")
        self._build()


def simulate(
    net: Network,
    t_end_s: float = 3.0,
    dt_s: float = 0.002,
    events: Optional[list[StabilityEvent]] = None,
    angle_limit_deg: float = 180.0,
    stop_when_unstable: bool = False,
) -> StabilityResult:
    """Simulazione nel tempo con gli eventi indicati (default: sezione stability_events).

    Instabilità: differenza tra gli angoli rotorici di due macchine (rete esterna
    inclusa, angolo della sua fem) oltre `angle_limit_deg`.
    """
    sim = _Simulator(net, angle_limit_deg)
    evs = sorted(events if events is not None else net.stability_events, key=lambda e: e.t_s)
    for ev in evs:
        if ev.kind in ("fault", "clear_fault", "load") and ev.bus not in sim.idx:
            raise ValueError(f"evento a {ev.t_s} s: nodo inesistente {ev.bus!r}")
    x = np.array(sim.x0, dtype=float)
    ms = sim.machines
    names = [m.gen.id for m in ms]
    grid_angles = [math.degrees(cmath.phase(e)) for _, _, e in sim.grids]
    t_list, d_list, w_list, p_list, f_list, v_list = [], [], [], [], [], []
    bus_ids = [b.id for b in net.buses]

    def record(t: float, x: np.ndarray) -> None:
        v, cur = sim.solve_network(x)
        t_list.append(t)
        d_list.append([math.degrees(x[5 * k]) for k in range(len(ms))])
        w_list.append([1.0 + x[5 * k + 1] for k in range(len(ms))])
        p_list.append([((v[m.bus] * np.conj(cur[k])).real + m.ra * abs(cur[k]) ** 2) * S_BASE_MVA
                       if m.in_service else 0.0 for k, m in enumerate(ms)])
        f_list.append([x[5 * k + 3] for k in range(len(ms))])
        v_list.append([abs(v[sim.idx[b]]) for b in bus_ids])

    def rk4(x: np.ndarray, h: float) -> np.ndarray:
        k1 = sim.derivatives(x)
        k2 = sim.derivatives(x + h / 2 * k1)
        k3 = sim.derivatives(x + h / 2 * k2)
        k4 = sim.derivatives(x + h * k3)
        return sim.clip(x + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4))

    t = 0.0
    ei = 0
    record(t, x)
    stable, t_unstable, max_diff = True, None, 0.0
    while t < t_end_s - 1e-12:
        while ei < len(evs) and evs[ei].t_s <= t + 1e-12:
            sim.apply(evs[ei])
            ei += 1
            record(t, x)  # valori subito dopo l'evento
        t_next = min(t + dt_s, t_end_s)
        if ei < len(evs) and evs[ei].t_s < t_next - 1e-12:
            t_next = evs[ei].t_s
        x = rk4(x, t_next - t)
        t = t_next
        record(t, x)
        angles = [math.degrees(x[5 * k]) for k, m in enumerate(ms) if m.in_service] + grid_angles
        if len(angles) > 1:
            diff = max(angles) - min(angles)
            max_diff = max(max_diff, diff)
            if diff > angle_limit_deg and stable:
                stable, t_unstable = False, t
                if stop_when_unstable:
                    break

    d = np.array(d_list)
    res = StabilityResult(
        net.name, np.array(t_list),
        {n: d[:, k] for k, n in enumerate(names)},
        {n: np.array(w_list)[:, k] for k, n in enumerate(names)},
        {n: np.array(p_list)[:, k] for k, n in enumerate(names)},
        {n: np.array(f_list)[:, k] for k, n in enumerate(names)},
        {b: np.array(v_list)[:, k] for k, b in enumerate(bus_ids)},
        stable, t_unstable, max_diff, evs, sim.warnings,
    )
    if grid_angles:
        res._reference = np.full(len(t_list), grid_angles[0])
    else:
        h = np.array([m.m for m in ms])
        res._reference = d @ h / h.sum()
    return res


def critical_clearing_time(
    net: Network,
    fault_bus: str,
    clear_events: Optional[list[StabilityEvent]] = None,
    t_fault_s: float = 0.1,
    t_max_s: float = 1.0,
    t_end_s: float = 3.0,
    dt_s: float = 0.002,
    tol_s: float = 0.001,
    r_ohm: float = 0.0,
    x_ohm: float = 0.0,
) -> Optional[float]:
    """Tempo critico di eliminazione del guasto trifase nel nodo `fault_bus` (s, dalla
    comparsa del guasto), per bisezione. Allo scadere il guasto è eliminato e si
    applicano `clear_events` (es. apertura della linea guasta), con t_s ignorato.
    None se il sistema resta stabile anche con t_max_s; 0 se è instabile anche
    con eliminazione immediata.
    """

    def stable(tc: float) -> bool:
        t_clear = t_fault_s + tc
        evs = [StabilityEvent(t_fault_s, "fault", bus=fault_bus, r_ohm=r_ohm, x_ohm=x_ohm),
               StabilityEvent(t_clear, "clear_fault", bus=fault_bus)]
        for ev in clear_events or []:
            evs.append(StabilityEvent(t_clear, ev.kind, ev.bus, ev.element, ev.r_ohm, ev.x_ohm, ev.scale))
        return simulate(net, t_end_s, dt_s, evs, stop_when_unstable=True).stable

    if stable(t_max_s):
        return None
    lo, hi = 0.0, t_max_s
    if not stable(lo):
        return 0.0
    while hi - lo > tol_s:
        mid = (lo + hi) / 2
        if stable(mid):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# --- uscita --------------------------------------------------------------------------------


def result_to_markdown(res: StabilityResult) -> str:
    out = [f"# Stabilità transitoria — {res.network}", ""]
    esito = "**stabile**" if res.stable else f"**instabile** (perdita di passo a {res.t_unstable_s:.3f} s)"
    out += [f"Esito: {esito}. Massima differenza tra gli angoli rotorici: {res.max_angle_diff_deg:.1f}°.", ""]
    if res.events:
        out += ["## Eventi", "", "| t [s] | Evento | Nodo / elemento |", "|---|---|---|"]
        for ev in res.events:
            out.append(f"| {ev.t_s:.3f} | {ev.kind} | {ev.bus or ev.element or ''} |")
        out.append("")
    rel = res.relative_angles_deg()
    out += ["## Macchine", "", "| Generatore | δ iniziale [°] | δ max [°] | δ min [°] | Velocità max [p.u.] "
            "| Pe iniziale [MW] |", "|---|---|---|---|---|---|"]
    for g, d in rel.items():
        out.append(f"| {g} | {d[0]:.2f} | {d.max():.2f} | {d.min():.2f} | {res.speed_pu[g].max():.5f} "
                   f"| {res.pe_mw[g][0]:.3f} |")
    out += ["", "Angoli riferiti alla fem della rete esterna (o al centro d'inerzia senza rete esterna).", ""]
    out += ["## Tensioni", "", "| Nodo | U iniziale [p.u.] | U min [p.u.] | U finale [p.u.] |", "|---|---|---|---|"]
    for b, v in res.v_pu.items():
        out.append(f"| {b} | {v[0]:.4f} | {v.min():.4f} | {v[-1]:.4f} |")
    if res.warnings:
        out += ["", "## Avvisi", ""] + [f"- {w}" for w in res.warnings]
    return "\n".join(out) + "\n"


def result_to_dict(res: StabilityResult) -> dict:
    return {
        "network": res.network,
        "stable": res.stable,
        "t_unstable_s": res.t_unstable_s,
        "max_angle_diff_deg": res.max_angle_diff_deg,
        "t_s": res.t.tolist(),
        "delta_deg": {k: v.tolist() for k, v in res.delta_deg.items()},
        "relative_angle_deg": {k: v.tolist() for k, v in res.relative_angles_deg().items()},
        "speed_pu": {k: v.tolist() for k, v in res.speed_pu.items()},
        "pe_mw": {k: v.tolist() for k, v in res.pe_mw.items()},
        "efd_pu": {k: v.tolist() for k, v in res.efd_pu.items()},
        "v_pu": {k: v.tolist() for k, v in res.v_pu.items()},
        "warnings": res.warnings,
    }


def angles_svg(res: StabilityResult, title: str = "") -> str:
    """Grafico SVG degli angoli rotorici relativi (gradi) in funzione del tempo."""
    rel = res.relative_angles_deg()
    w, h, ml, mr, mt, mb = 720, 420, 60, 20, 40, 45
    t0, t1 = float(res.t[0]), float(res.t[-1])
    allv = np.concatenate(list(rel.values())) if rel else np.array([0.0])
    lo, hi = float(np.min(allv)), float(np.max(allv))
    if hi - lo < 1e-6:
        lo, hi = lo - 1.0, hi + 1.0
    pad = 0.05 * (hi - lo)
    lo, hi = lo - pad, hi + pad

    def x(t: float) -> float:
        return ml + (t - t0) / (t1 - t0) * (w - ml - mr)

    def y(v: float) -> float:
        return mt + (hi - v) / (hi - lo) * (h - mt - mb)

    palette = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#4b5563"]
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         'font-family="sans-serif" font-size="11">', f'<rect width="{w}" height="{h}" fill="white"/>',
         f'<text x="{w / 2}" y="20" text-anchor="middle" font-size="13">{title}</text>']
    for k in range(6):
        v = lo + k * (hi - lo) / 5
        p.append(f'<line x1="{ml}" y1="{y(v):.1f}" x2="{w - mr}" y2="{y(v):.1f}" stroke="#e5e7eb"/>')
        p.append(f'<text x="{ml - 5}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
        tt = t0 + k * (t1 - t0) / 5
        p.append(f'<text x="{x(tt):.1f}" y="{h - mb + 15}" text-anchor="middle">{tt:.2f}</text>')
    for ev in res.events:
        p.append(f'<line x1="{x(ev.t_s):.1f}" y1="{mt}" x2="{x(ev.t_s):.1f}" y2="{h - mb}" '
                 'stroke="#9ca3af" stroke-dasharray="4 3"/>')
    for k, (g, d) in enumerate(rel.items()):
        step = max(1, len(d) // 1500)
        pts = " ".join(f"{x(float(t)):.1f},{y(float(v)):.1f}" for t, v in zip(res.t[::step], d[::step]))
        col = palette[k % len(palette)]
        p.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.8" points="{pts}"/>')
        p.append(f'<text x="{w - mr - 5}" y="{mt + 14 * (k + 1)}" text-anchor="end" fill="{col}">{g}</text>')
    p.append(f'<text x="{w / 2}" y="{h - 10}" text-anchor="middle">tempo [s]</text>')
    p.append(f'<text x="15" y="{h / 2}" transform="rotate(-90 15 {h / 2})" text-anchor="middle">'
             'angolo rotorico relativo [°]</text>')
    p.append("</svg>")
    return "\n".join(p)
