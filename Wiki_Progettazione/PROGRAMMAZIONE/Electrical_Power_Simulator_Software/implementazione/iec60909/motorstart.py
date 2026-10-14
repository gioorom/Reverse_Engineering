"""Avviamento dei motori asincroni: caduta di tensione e accelerazione.

Motore: circuito equivalente a gabbia singola (per unità sulla potenza
apparente nominale Sr = Pr/(η·cosφ) e sulla tensione nominale Ur):
Z(s) = Rs + jXs + jXm ∥ (Rr/s + jXr), coppia Te = |Ir|²·Rr/s (p.u. della coppia
di base Sr/ω_sincrono), equazione meccanica 2H·dω/dt = Te − T_L(ω).
Se il circuito non è indicato, è stimato dai dati di targa imponendo
l'impedenza a rotore bloccato (|Z(1)| = 1/(Ilr/Ir), R/X dato o convenzionale
IEC 60909), il punto nominale (Z(s_r) = 1∠φ, cioè corrente nominale con il
cosφ di targa a tensione nominale) e il rendimento (Pmecc = η·Pass); con
Xs = Xr. Incognite Rs, Rr, Xs, Xm e lo scorrimento nominale s_r.

Rete: flusso di potenza a ogni passo, con il motore in avviamento come
ammettenza (gli altri carichi e motori restano a potenza costante). Metodi di
avviamento come trasformatore ideale di rapporto u tra rete e motore:
- diretto: u = 1;
- stella-triangolo: u = 1/√3 fino a `switch_speed` (corrente e coppia 1/3);
- autotrasformatore: u = presa fino a `switch_speed`, corrente di linea u²;
- soft starter: tensione al motore u·V con rampa e limite di corrente; la
  corrente di linea è quella del motore (ammettenza vista dalla rete u·Y).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import factors
from .loadflow import S_BASE_MVA, run_load_flow
from .network import Motor, MotorStart, Network, Shunt


@dataclass
class MotorCircuit:
    rs: float
    xs: float
    xm: float
    rr: float
    xr: float
    s_rated: float  # scorrimento nominale (stimato o calcolato)
    # perdite meccaniche e nel ferro (p.u.), come coppia resistente costante a
    # regime: Pmecc_interna − Pall'albero; 0 se il rendimento è dato dal rame
    p_loss_fw: float = 0.0
    fit: str = "rendimento"  # "rendimento", "rs=rr" o "dati"

    def impedance(self, s: float) -> complex:
        zr = complex(self.rr / max(s, 1e-9), self.xr)
        return complex(self.rs, self.xs) + 1j * self.xm * zr / (1j * self.xm + zr)

    def currents(self, v: complex, s: float) -> tuple[complex, complex]:
        """Correnti di statore e di rotore con tensione v (p.u.)."""
        zr = complex(self.rr / max(s, 1e-9), self.xr)
        zp = 1j * self.xm * zr / (1j * self.xm + zr)
        i_s = v / (complex(self.rs, self.xs) + zp)
        return i_s, i_s * zp / zr

    def torque(self, v: complex, s: float) -> float:
        _, i_r = self.currents(v, s)
        return abs(i_r) ** 2 * self.rr / max(s, 1e-9)


def _newton(f, x0: np.ndarray, tol: float = 1e-12, max_iter: int = 100) -> np.ndarray:
    x = np.array(x0, dtype=float)
    for _ in range(max_iter):
        fx = f(x)
        if np.max(np.abs(fx)) < tol:
            return x
        jac = np.zeros((len(fx), len(x)))
        for k in range(len(x)):
            dx = np.zeros_like(x)
            dx[k] = 1e-7 * max(1.0, abs(x[k]))
            jac[:, k] = (f(x + dx) - fx) / dx[k]
        step = np.linalg.solve(jac, -fx)
        # passo ridotto se porta fuori dal campo fisico (grandezze positive)
        lam = 1.0
        while np.any(x + lam * step <= 0) and lam > 1e-6:
            lam /= 2
        x = x + lam * step
    raise ValueError("stima del circuito equivalente del motore non convergente")


def estimate_circuit(m: Motor, tlr_tr: Optional[float] = None) -> MotorCircuit:
    """Circuito equivalente dai dati di targa (vedi docstring del modulo).

    Prima si impone anche il rendimento con le sole perdite nel rame; se non è
    possibile (R/X a rotore bloccato troppo basso per le perdite del
    rendimento di targa), si assume Rs = Rr e la differenza di potenza è
    attribuita alle perdite meccaniche e nel ferro (p_loss_fw).
    Con tlr_tr (coppia a rotore bloccato / coppia nominale, dato di targa) la
    condizione sulla coppia di spunto sostituisce quella sull'R/X a rotore
    bloccato (resta imposto |Z(1)| = 1/(Ilr/Ir)).
    """
    rx = m.rx if m.rx is not None else factors.motor_rx(m.ur_kv, m.pr_mw, m.pole_pairs)
    zlr = 1.0 / m.ilr_ir
    x_lr = zlr / math.sqrt(1.0 + rx**2)
    r_lr = rx * x_lr
    phi = math.acos(m.cos_phi)
    z_rated = complex(math.cos(phi), math.sin(phi))

    def base(rs, rr, xs, xm, s):
        c = MotorCircuit(rs, xs, xm, rr, xs, s)
        z1, zn = c.impedance(1.0), c.impedance(s)
        return c, [z1.real - r_lr, z1.imag - x_lr, zn.real - z_rated.real, zn.imag - z_rated.imag]

    def eff(c: MotorCircuit, s: float) -> tuple[float, float]:
        i_s, i_r = c.currents(1.0, s)
        return (i_s.conjugate()).real, abs(i_r) ** 2 * c.rr * (1 - s) / s

    def f_eta(x):
        c, r = base(*x)
        p_in, p_mech = eff(c, x[4])
        return np.array(r + [p_mech - m.efficiency * p_in])

    def f_eq(x):
        rs, xs, xm, s = x
        return np.array(base(rs, rs, xs, xm, s)[1])

    if tlr_tr is not None:
        def tlr_eq(c: MotorCircuit, s: float) -> float:
            return c.torque(1.0, 1.0) - tlr_tr * m.efficiency * m.cos_phi / (1.0 - s)

        def g_eta(x):
            rs, rr, xs, xm, s = x
            c = MotorCircuit(rs, xs, xm, rr, xs, s)
            zn = c.impedance(s)
            p_in, p_mech = eff(c, s)
            return np.array([abs(c.impedance(1.0)) - zlr, zn.real - z_rated.real, zn.imag - z_rated.imag,
                             p_mech - m.efficiency * p_in, tlr_eq(c, s)])

        def g_eq(x):
            rs, rr, xs, xm, s = x
            c = MotorCircuit(rs, xs, xm, rr, xs, s)
            zn = c.impedance(s)
            return np.array([abs(c.impedance(1.0)) - zlr, zn.real - z_rated.real, zn.imag - z_rated.imag,
                             rs - rr, tlr_eq(c, s)])

        r0 = 0.25 * x_lr
        x0 = np.array([r0 / 2, r0, x_lr / 2, 1.0 / math.sin(phi) * 0.9, 0.02])
        for g, fit in ((g_eta, "rendimento"), (g_eq, "rs=rr")):
            try:
                rs, rr, xs, xm, s = _newton(g, x0)
            except (ValueError, np.linalg.LinAlgError):
                continue
            c = MotorCircuit(rs, xs, xm, rr, xs, s, 0.0, fit + "+spunto")
            p_in, p_mech = eff(c, s)
            c.p_loss_fw = max(0.0, p_mech - m.efficiency * p_in)
            return c
        raise ValueError(f"{m.id}: impossibile stimare il circuito con la coppia di spunto {tlr_tr}")
    x0 = np.array([r_lr / 2, r_lr / 2, x_lr / 2, 1.0 / math.sin(phi) * 0.9, 0.02])
    try:
        rs, rr, xs, xm, s = _newton(f_eta, x0)
        return MotorCircuit(rs, xs, xm, rr, xs, s, 0.0, "rendimento")
    except (ValueError, np.linalg.LinAlgError):
        pass
    rs, xs, xm, s = _newton(f_eq, np.array([r_lr / 2, x_lr / 2, 1.0 / math.sin(phi) * 0.9, 0.02]))
    c = MotorCircuit(rs, xs, xm, rs, xs, s, 0.0, "rs=rr")
    p_in, p_mech = eff(c, s)
    c.p_loss_fw = max(0.0, p_mech - m.efficiency * p_in)
    return c


def circuit_for(ms: MotorStart, m: Motor) -> MotorCircuit:
    vals = (ms.rs, ms.xs, ms.xm, ms.rr, ms.xr)
    if all(v is not None for v in vals):
        c = MotorCircuit(ms.rs, ms.xs, ms.xm, ms.rr, ms.xr, 0.0, 0.0, "dati")
        # scorrimento nominale: potenza meccanica nominale a tensione nominale
        p_target = m.efficiency * m.cos_phi
        lo, hi = 1e-6, 0.5
        for _ in range(200):
            mid = (lo + hi) / 2
            if c.torque(1.0, mid) * (1 - mid) < p_target:
                lo = mid
            else:
                hi = mid
        c.s_rated = (lo + hi) / 2
        return c
    if any(v is not None for v in vals):
        raise ValueError(f"{ms.id}: indicare tutti i parametri rs, xs, xm, rr, xr oppure nessuno")
    return estimate_circuit(m, ms.tlr_tr)


@dataclass
class MotorStartResult:
    id: str
    motor: str
    method: str
    circuit: MotorCircuit
    t: np.ndarray
    speed_pu: np.ndarray
    i_line_a: np.ndarray
    i_line_ir: np.ndarray  # corrente di linea in multipli della corrente nominale
    v_motor_pu: np.ndarray  # tensione ai morsetti del motore (p.u. di Ur)
    v_bus_pu: dict[str, np.ndarray]
    torque_pu: np.ndarray
    load_torque_pu: np.ndarray
    accelerated: bool
    t_acc_s: Optional[float]
    v_before_pu: dict[str, float]
    t_rated_pu: float  # coppia nominale (p.u. della coppia di base)
    issues: list[str] = field(default_factory=list)

    @property
    def locked_rotor_torque_ratio(self) -> float:
        """Coppia a rotore bloccato a tensione nominale / coppia nominale."""
        return self.circuit.torque(1.0, 1.0) / self.t_rated_pu

    bus: str = ""

    @property
    def v_min_motor_pu(self) -> float:
        """Tensione minima ai morsetti del motore, a valle dell'avviatore (p.u. di Ur)."""
        return float(np.min(self.v_motor_pu))

    @property
    def v_min_supply_pu(self) -> float:
        """Tensione minima della rete nel punto di allacciamento del motore (p.u. di Un)."""
        return float(np.min(self.v_bus_pu[self.bus]))

    def v_min_bus(self) -> dict[str, float]:
        return {b: float(np.min(v)) for b, v in self.v_bus_pu.items()}


def _ratio(ms: MotorStart, t: float, omega: float, switched: bool) -> tuple[float, bool]:
    """Rapporto u e tipo di ammettenza vista dalla rete (True: u², trasformatore ideale)."""
    if ms.method == "dol":
        return 1.0, True
    if ms.method == "star_delta":
        return (1.0, True) if switched else (1.0 / math.sqrt(3.0), True)
    if ms.method == "autotransformer":
        return (1.0, True) if switched else (ms.tap, True)
    if ms.method == "soft_starter":
        return min(1.0, ms.u0 + (1.0 - ms.u0) * t / ms.ramp_s), False
    raise ValueError(f"{ms.id}: metodo di avviamento sconosciuto {ms.method!r}")


def simulate_start(net: Network, ms: MotorStart, dt_s: float = 0.01, static: bool = False) -> MotorStartResult:
    """Avviamento del motore ms.motor: flusso di potenza prima dell'avviamento
    (motore fermo) e poi a ogni passo con il motore come ammettenza.
    static=True: solo l'istante iniziale (rotore bloccato)."""
    mot = next((m for m in net.motors if m.id == ms.motor), None)
    if mot is None:
        raise ValueError(f"{ms.id}: motore inesistente {ms.motor!r}")
    if ms.method not in ("dol", "star_delta", "autotransformer", "soft_starter"):
        raise ValueError(f"{ms.id}: metodo di avviamento sconosciuto {ms.method!r}")
    circ = circuit_for(ms, mot)
    work = copy.deepcopy(net)
    work.motors = [m for m in work.motors if m.id != ms.motor]
    sh = Shunt(f"avviamento:{ms.id}", mot.bus, 0.0, 0.0)
    work.shunts.append(sh)
    sr_mva = mot.pr_mw / (mot.efficiency * mot.cos_phi) * mot.count
    un = next(b.un_kv for b in net.buses if b.id == mot.bus)
    ir_a = sr_mva / (math.sqrt(3.0) * mot.ur_kv) * 1000.0
    bus_ids = [b.id for b in net.buses]
    lf0 = run_load_flow(work)
    if not lf0.converged:
        raise ValueError(f"{ms.id}: flusso di potenza prima dell'avviamento non convergente")
    v_before = {b.bus: b.vm_pu for b in lf0.buses}

    t_rated = mot.efficiency * mot.cos_phi / (1.0 - circ.s_rated)  # coppia nominale all'albero (p.u.)
    t_fw = circ.p_loss_fw / (1.0 - circ.s_rated)  # perdite meccaniche e nel ferro come coppia

    def load_torque(w: float) -> float:
        return t_rated * (ms.a0 + ms.a1 * w + ms.a2 * w * w) + (t_fw if w > 0 else 0.0)

    def network(s: float, u: float, transformer: bool):
        """Flusso di potenza con il motore allo scorrimento s; grandezze del motore."""
        y_m = 1.0 / circ.impedance(s)  # p.u. del motore
        y_net = y_m * (u * u if transformer else u)
        y_sys = y_net * (sr_mva / mot.ur_kv**2) * (un**2 / S_BASE_MVA)
        sh.p_mw, sh.q_mvar = y_sys.real * S_BASE_MVA, -y_sys.imag * S_BASE_MVA
        lf = run_load_flow(work)
        if not lf.converged:
            return None
        vb = lf.bus(mot.bus).vm_pu
        v_term = vb * un / mot.ur_kv  # tensione della rete al punto di allacciamento (p.u. di Ur)
        v_m = u * v_term
        i_m, _ = circ.currents(v_m, s)
        i_line = abs(i_m) * (u if transformer else 1.0)
        te = circ.torque(v_m, s)
        return lf, v_m, i_line, te

    ts, ws, il, vm, te_l, tl_l = [], [], [], [], [], []
    vb_hist: dict[str, list[float]] = {b: [] for b in bus_ids}
    issues: list[str] = []
    w, t, switched = 0.0, 0.0, False
    t_acc = None
    w_target = 1.0 - 2.0 * circ.s_rated  # velocità di fine avviamento

    def state(t: float, w: float):
        nonlocal switched
        u, tr = _ratio(ms, t, w, switched)
        res = network(1.0 - w, u, tr)
        if res is None:
            return None
        if ms.method == "soft_starter" and ms.current_limit is not None and res[2] > ms.current_limit:
            # limite di corrente: tensione ridotta fino a I = limite (iterazione sul rapporto)
            lo, hi = 0.0, u
            for _ in range(40):
                mid = (lo + hi) / 2
                r = network(1.0 - w, mid, False)
                if r is not None and r[2] <= ms.current_limit:
                    lo = mid
                else:
                    hi = mid
            res = network(1.0 - w, lo, False)
        return res

    t_end = 0.0 if static else ms.t_max_s
    while True:
        res = state(t, w)
        if res is None:
            issues.append(f"flusso di potenza non convergente a {t:.2f} s (tensione collassata)")
            break
        lf, v_m, i_line, te = res
        ts.append(t)
        ws.append(w)
        il.append(i_line)
        vm.append(abs(v_m) / 1.0)
        te_l.append(te)
        tl_l.append(load_torque(w))
        for b in lf.buses:
            vb_hist[b.bus].append(b.vm_pu)
        if t_acc is None and w >= w_target:
            t_acc = t
        if t >= t_end - 1e-12 or (t_acc is not None and t >= t_acc + 0.5):
            break
        # Heun (trapezi esplicito) sulla velocità
        d1 = (te - load_torque(w)) / (2.0 * ms.h_s)
        r2 = state(t + dt_s, min(w + dt_s * d1, 1.0))
        if r2 is None:
            issues.append(f"flusso di potenza non convergente a {t + dt_s:.2f} s (tensione collassata)")
            break
        d2 = (r2[3] - load_torque(min(w + dt_s * d1, 1.0))) / (2.0 * ms.h_s)
        w = min(max(w + dt_s * (d1 + d2) / 2.0, 0.0), 1.0)
        t += dt_s
        if ms.method in ("star_delta", "autotransformer") and not switched and w >= ms.switch_speed:
            switched = True

    if not ts:
        raise ValueError(f"{ms.id}: flusso di potenza non convergente all'istante di avviamento")
    accelerated = t_acc is not None
    result = MotorStartResult(
        ms.id, ms.motor, ms.method, circ, np.array(ts), np.array(ws), np.array(il) * ir_a,
        np.array(il), np.array(vm), {b: np.array(v) for b, v in vb_hist.items()},
        np.array(te_l), np.array(tl_l), accelerated, t_acc, v_before, t_rated, issues, mot.bus,
    )
    if not static and not accelerated:
        issues.append(f"il motore non raggiunge la velocità di regime entro {ms.t_max_s:g} s (stallo)")
    if result.v_min_supply_pu < ms.v_min_motor_pu:
        issues.append(f"tensione nel punto di allacciamento del motore ({mot.bus}) "
                      f"{result.v_min_supply_pu:.3f} p.u. < {ms.v_min_motor_pu:g}")
    for b, v in result.v_min_bus().items():
        if b != mot.bus and v < ms.v_min_bus_pu:
            issues.append(f"tensione nel nodo {b} {v:.3f} p.u. < {ms.v_min_bus_pu:g}")
    if ms.t_lr_max_s is not None and accelerated and t_acc > ms.t_lr_max_s:
        issues.append(f"tempo di avviamento {t_acc:.2f} s > tempo ammesso a rotore bloccato {ms.t_lr_max_s:g} s")
    return result


def motor_start_study(net: Network, dt_s: float = 0.01, static: bool = False) -> list[MotorStartResult]:
    """Tutti gli avviamenti della sezione motor_starts (uno alla volta)."""
    if not net.motor_starts:
        raise ValueError("la rete non contiene avviamenti (motor_starts)")
    return [simulate_start(net, ms, dt_s, static) for ms in net.motor_starts]


# --- uscita ----------------------------------------------------------------------------------

METODI = {"dol": "diretto", "star_delta": "stella-triangolo", "autotransformer": "autotrasformatore",
          "soft_starter": "soft starter"}


def results_to_markdown(results: list[MotorStartResult], title: str = "") -> str:
    out = [f"# Avviamento dei motori{' — ' + title if title else ''}", ""]
    out += ["| Avviamento | Motore | Metodo | I iniziale [×Ir] | I max [×Ir] | I max [A] "
            "| U allacciamento min [p.u.] | U al motore min [p.u.] | Nodo più basso | Tempo di avviamento [s] "
            "| Esito |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        vmin = r.v_min_bus()
        b, v = min(vmin.items(), key=lambda kv: kv[1])
        t_acc = "—" if r.t_acc_s is None else f"{r.t_acc_s:.2f}"
        esito = "OK" if not r.issues else "; ".join(r.issues)
        out.append(f"| {r.id} | {r.motor} | {METODI[r.method]} | {r.i_line_ir[0]:.2f} | {r.i_line_ir.max():.2f} "
                   f"| {r.i_line_a.max():.1f} "
                   f"| {r.v_min_supply_pu:.3f} | {r.v_min_motor_pu:.3f} | {b} ({v:.3f}) | {t_acc} | {esito} |")
    for r in results:
        c = r.circuit
        out += ["", f"## {r.id}", "",
                f"Circuito equivalente (p.u. su Sr): Rs = {c.rs:.4f}, Xs = {c.xs:.4f}, Xm = {c.xm:.3f}, "
                f"Rr = {c.rr:.4f}, Xr = {c.xr:.4f}; scorrimento nominale {c.s_rated * 100:.2f} %; "
                f"coppia a rotore bloccato {r.locked_rotor_torque_ratio:.2f} × la nominale.",
                "", "| Nodo | U prima [p.u.] | U min durante l'avviamento [p.u.] |", "|---|---|---|"]
        for b, v in r.v_min_bus().items():
            out.append(f"| {b} | {r.v_before_pu[b]:.4f} | {v:.4f} |")
    return "\n".join(out) + "\n"


def results_to_dict(results: list[MotorStartResult]) -> list[dict]:
    import dataclasses

    return [{
        "id": r.id, "motor": r.motor, "method": r.method, "circuit": dataclasses.asdict(r.circuit),
        "accelerated": r.accelerated, "t_acc_s": r.t_acc_s, "v_min_motor_pu": r.v_min_motor_pu,
        "v_min_supply_pu": r.v_min_supply_pu, "bus": r.bus,
        "v_min_bus_pu": r.v_min_bus(), "v_before_pu": r.v_before_pu, "issues": r.issues,
        "t_s": r.t.tolist(), "speed_pu": r.speed_pu.tolist(), "i_line_a": r.i_line_a.tolist(),
        "v_motor_pu": r.v_motor_pu.tolist(), "torque_pu": r.torque_pu.tolist(),
        "load_torque_pu": r.load_torque_pu.tolist(),
    } for r in results]


def start_svg(r: MotorStartResult) -> str:
    """Grafico SVG: velocità, corrente (×Ir/10) e tensione ai morsetti in funzione del tempo."""
    w, h, ml, mr, mt, mb = 720, 440, 55, 20, 40, 75
    t1 = float(r.t[-1]) if r.t[-1] > 0 else 1.0
    series = [("velocità [p.u.]", r.speed_pu, "#2563eb"),
              ("corrente [×Ir/10]", r.i_line_ir / 10.0, "#dc2626"),
              ("tensione motore [p.u.]", r.v_motor_pu, "#16a34a")]
    hi = max(1.05, max(float(np.max(s)) for _, s, _ in series) * 1.05)

    def x(t: float) -> float:
        return ml + t / t1 * (w - ml - mr)

    def y(v: float) -> float:
        return mt + (hi - v) / hi * (h - mt - mb)

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         'font-family="sans-serif" font-size="11">', f'<rect width="{w}" height="{h}" fill="white"/>',
         f'<text x="{w / 2}" y="20" text-anchor="middle" font-size="13">Avviamento {r.id} ({METODI[r.method]})</text>']
    for k in range(6):
        v = hi * k / 5
        p.append(f'<line x1="{ml}" y1="{y(v):.1f}" x2="{w - mr}" y2="{y(v):.1f}" stroke="#e5e7eb"/>')
        p.append(f'<text x="{ml - 5}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.2f}</text>')
        p.append(f'<text x="{x(t1 * k / 5):.1f}" y="{h - mb + 15}" text-anchor="middle">{t1 * k / 5:.1f}</text>')
    for k, (name, s, col) in enumerate(series):
        pts = " ".join(f"{x(float(t)):.1f},{y(float(v)):.1f}" for t, v in zip(r.t, s))
        p.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.8" points="{pts}"/>')
        # legenda sotto il grafico, fuori dall'area delle curve
        lx = ml + k * 200
        p.append(f'<line x1="{lx}" y1="{h - 14}" x2="{lx + 22}" y2="{h - 14}" stroke="{col}" stroke-width="2.5"/>')
        p.append(f'<text x="{lx + 28}" y="{h - 10}" fill="{col}">{name}</text>')
    p.append(f'<text x="{w / 2}" y="{h - mb + 32}" text-anchor="middle">tempo [s]</text>')
    p.append("</svg>")
    return "\n".join(p)
