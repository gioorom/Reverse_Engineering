"""Flusso di potenza (load flow) con il metodo di Newton-Raphson in coordinate polari.

Usa lo stesso modello di rete del calcolo di cortocircuito, con i dati di
esercizio (carichi, potenze dei generatori, tensioni regolate, prese dei
trasformatori, capacità delle linee). Valori in per unità con potenza di base
100 MVA e tensione di base pari alla tensione nominale di ogni nodo; nessun
fattore di correzione della IEC 60909.

Modelli:
- rete esterna: nodo di saldo con tensione e angolo imposti;
- generatore: nodo PV (p_mw, vm_pu) oppure PQ (vm_pu = None, q_mvar), con
  limiti di potenza reattiva facoltativi; la tensione regolata può essere
  quella di un altro nodo (regulated_bus, regolazione remota);
- carichi: modello ZIP (quote a impedenza, corrente e potenza costante,
  separate per P e Q); motori (P = loading·Pr/η, Q = P·tanφ) e generatori
  statici: potenza costante;
- derivazioni (shunts): impedenza costante;
- linea: circuito a π con metà della capacità a ogni estremo;
- trasformatore a due avvolgimenti: impedenza di cortocircuito riferita alla
  tensione nominale (con presa) del lato BT, rapporto complesso con il
  variatore e lo sfasamento del gruppo vettoriale, magnetizzazione divisa a
  metà tra i due lati (modello a π); variatore sotto carico facoltativo che
  regola la tensione di un nodo a passi discreti;
- trasformatore a tre avvolgimenti: stella equivalente delle impedenze di
  coppia (tre trasformatori a due avvolgimenti verso il centro stella), con
  variatore su un avvolgimento, sfasamenti degli avvolgimenti MT e BT e
  magnetizzazione sul ramo AT.
Sfasamenti dei gruppi vettoriali (phase_shift): la tensione di un avvolgimento
con numero orario k è in ritardo di k·30° su quella dell'avvolgimento AT.
Saldo distribuito (distributed_slack): lo sbilancio di potenza attiva è
ripartito tra reti esterne e generatori secondo slack_weight.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from .network import Generator, Line, Network, Transformer, Transformer3W

S_BASE_MVA = 100.0
MAX_TAP_ITER = 200  # iterazioni esterne massime della regolazione delle prese


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
    # prese finali dei trasformatori con variatore regolato (control_bus)
    taps: dict[str, float] = field(default_factory=dict)
    # saldo distribuito: sbilancio di potenza attiva ripartito [MW]
    slack_mw: Optional[float] = None

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
    shift: float = 0.0  # ritardo della tensione del lato t rispetto al lato f [rad]


def _star_node(t: Transformer3W) -> str:
    return f"{t.id}::stella"


def clock_numbers(group: str, windings: int, owner: str = "") -> list[int]:
    """Numeri orari degli avvolgimenti MT/BT rispetto all'avvolgimento AT.

    Es. "Dyn11" → [11], "YNd5" → [5], "YNyn0d5" → [0, 5]; senza cifre 0.
    """
    tokens = re.findall(r"(YN|ZN|Y|D|Z)(\d*)", group.strip(), flags=re.IGNORECASE)
    if len(tokens) != windings or "".join(a + b for a, b in tokens).upper() != group.strip().upper():
        raise ValueError(f"{owner}: gruppo vettoriale non riconosciuto {group!r}")
    out = []
    for _, digits in tokens[1:]:
        k = int(digits) if digits else 0
        if k > 11:
            raise ValueError(f"{owner}: numero orario {k} non valido nel gruppo {group!r}")
        out.append(k)
    return out


def _pi_branch(y: complex, yh: complex, a: complex, lato: str) -> tuple[complex, complex, complex, complex]:
    """Ammettenze (yff, yft, ytf, ytt) di un ramo con trasformatore ideale.

    Ramo serie y, magnetizzazione yh a ciascun estremo, trasformatore ideale di
    rapporto complesso a sul lato `lato` ("f" o "t"): V_lato = a·V_interna e
    I_lato = I_interna/a*. Con a complesso la matrice non è simmetrica.
    """
    if lato == "f":
        return (y + yh) / abs(a) ** 2, -y / a.conjugate(), -y / a, y + yh
    return y + yh, -y / a, -y / a.conjugate(), (y + yh) / abs(a) ** 2


class _Model:
    def __init__(self, net: Network, phase_shift: bool = True, taps: Optional[dict[str, float]] = None):
        self.net = net
        self.phase_shift = phase_shift
        self.taps = taps or {}
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
        for hf in net.harmonic_filters:
            # filtri armonici: ammettenza alla frequenza fondamentale
            from .harmonics import filter_impedance_pu

            self.ysh[self.idx[hf.bus]] += 1.0 / filter_impedance_pu(hf, 1.0)
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
        tap = 1.0 + self.taps.get(t.id, t.tap_pos) * t.tap_step_percent / 100.0
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
        # trasformatore ideale sul lato AT, rapporto complesso: la tensione BT è
        # in ritardo di k·30° (numero orario k del gruppo vettoriale)
        shift = math.radians(30.0 * clock_numbers(t.vector_group, 2, t.id)[0]) if self.phase_shift else 0.0
        y = _pi_branch(ys, yh, ratio * cmath.exp(1j * shift), "f")
        self.branches.append(
            _Branch(t.id, "trafo", self.idx[t.hv_bus], self.idx[t.lv_bus], *y,
                    t.sr_mva * t.parallel, shift=shift)
        )

    def _trafo3w(self, t: Transformer3W) -> None:
        """Tre trasformatori a due avvolgimenti verso il centro stella (base UrAT).

        Come in pandapower: ramo AT con trasformatore ideale ai morsetti AT
        (presa AT) e impedenza riferita al centro stella, con la magnetizzazione
        divisa a metà tra morsetti AT e centro stella; rami MT e BT con
        trasformatore ideale (rapporto, presa, sfasamento) dal lato del centro
        stella e impedenza riferita alla tensione nominale (con presa)
        dell'avvolgimento.
        """
        star = _star_node(t)
        zb_hv = t.ur_hv_kv**2  # Ω per MVA alla tensione AT

        def pair(p: str) -> complex:
            sr = getattr(t, f"sr_{p}_mva")
            zk = getattr(t, f"ukr_{p}_percent") / 100.0 * zb_hv / sr
            rk = getattr(t, f"urr_{p}_percent") / 100.0 * zb_hv / sr
            return complex(rk, math.sqrt(zk**2 - rk**2))

        hm, hl, ml = pair("hv_mv"), pair("hv_lv"), pair("mv_lv")
        z_star = {"hv": (hm + hl - ml) / 2, "mv": (hm + ml - hl) / 2, "lv": (hl + ml - hm) / 2}
        sr_hv = max(t.sr_hv_mv_mva, t.sr_hv_lv_mva)
        rating = {
            "hv": sr_hv,
            "mv": max(t.sr_hv_mv_mva, t.sr_mv_lv_mva),
            "lv": max(t.sr_hv_lv_mva, t.sr_mv_lv_mva),
        }
        tap = 1.0 + t.tap_pos * t.tap_step_percent / 100.0
        ur = {w: getattr(t, f"ur_{w}_kv") * (tap if t.tap_side == w else 1.0) for w in ("hv", "mv", "lv")}
        k = clock_numbers(t.vector_group, 3, t.id) if self.phase_shift else [0, 0]
        shift = {"hv": 0.0, "mv": math.radians(30.0 * k[0]), "lv": math.radians(30.0 * k[1])}
        # magnetizzazione: corrente a vuoto riferita alla potenza dell'avvolgimento AT
        g = t.pfe_kw / 1000.0 / S_BASE_MVA
        ym_abs = t.i0_percent / 100.0 * sr_hv / S_BASE_MVA
        ym = complex(g, -math.sqrt(max(0.0, ym_abs**2 - g**2)))
        for w in ("hv", "mv", "lv"):
            bus = getattr(t, f"{w}_bus")
            if w == "hv":
                y = 1.0 / (z_star["hv"] / (t.ur_hv_kv**2 / S_BASE_MVA))
                yy = _pi_branch(y, ym / 2.0, complex(ur["hv"] / self.un[bus]), "f")
            else:
                z = z_star[w] * (ur[w] / t.ur_hv_kv) ** 2 / self.zbase(bus)
                a = self.un[bus] / ur[w] * cmath.exp(1j * shift[w])
                yy = _pi_branch(1.0 / z, 0j, a, "t")
            # ramo dal nodo dell'avvolgimento al centro stella
            self.branches.append(
                _Branch(f"{t.id}:{w}", "trafo3w", self.idx[bus], self.idx[star], *yy,
                        rating[w], shift=-shift[w])
            )

    def initial_angles(self, slack: dict[int, complex]) -> np.ndarray:
        """Angoli iniziali: angolo del nodo di saldo meno gli sfasamenti incontrati."""
        va = np.zeros(self.n)
        adj: dict[int, list[tuple[int, float]]] = {}
        for br in self.branches:
            adj.setdefault(br.f, []).append((br.t, -br.shift))
            adj.setdefault(br.t, []).append((br.f, br.shift))
        for i, vs in slack.items():
            va[i] = cmath.phase(vs)
        seen = set(slack)
        stack = list(slack)
        while stack:
            k = stack.pop()
            for j, d in adj.get(k, []):
                if j not in seen:
                    seen.add(j)
                    va[j] = va[k] + d
                    stack.append(j)
        return va


class _Spec:
    """Potenze impresse nei nodi (p.u.), con i carichi dipendenti dalla tensione.

    Assorbimento dei carichi S_c(V) = sz·V² + si·V + sc (coefficienti complessi:
    parte reale per P, immaginaria per Q).
    """

    def __init__(self, net: Network, idx: dict[str, int], n: int):
        self.sz = np.zeros(n, dtype=complex)
        self.si = np.zeros(n, dtype=complex)
        self.sc = np.zeros(n, dtype=complex)
        self.sgen = np.zeros(n, dtype=complex)  # generatori statici
        self.gen = np.zeros(n, dtype=complex)  # generatori sincroni (Q solo dei PQ)
        for ld in net.loads:
            i = idx[ld.bus]
            p, q = ld.p_mw * ld.count / S_BASE_MVA, ld.q_mvar * ld.count / S_BASE_MVA
            zp, ip = ld.const_z_p_percent / 100.0, ld.const_i_p_percent / 100.0
            zq, iq = ld.const_z_q_percent / 100.0, ld.const_i_q_percent / 100.0
            self.sz[i] += complex(p * zp, q * zq)
            self.si[i] += complex(p * ip, q * iq)
            self.sc[i] += complex(p * (1.0 - zp - ip), q * (1.0 - zq - iq))
        for m in net.motors:
            p = m.loading * m.pr_mw / m.efficiency * m.count
            self.sc[idx[m.bus]] += complex(p, p * math.tan(math.acos(m.cos_phi))) / S_BASE_MVA
        for sg in net.static_generators:
            self.sgen[idx[sg.bus]] += complex(sg.p_mw, sg.q_mvar) * sg.count / S_BASE_MVA
        for g in net.generators:
            self.gen[idx[g.bus]] += complex(g.p_mw, g.q_mvar if g.vm_pu is None else 0.0) / S_BASE_MVA

    def load(self, vm: np.ndarray) -> np.ndarray:
        return self.sz * vm**2 + self.si * vm + self.sc

    def dload(self, vm: np.ndarray) -> np.ndarray:
        return 2.0 * self.sz * vm + self.si

    def spec(self, vm: np.ndarray) -> np.ndarray:
        """Potenza netta impressa: generazione meno carichi."""
        return self.sgen + self.gen - self.load(vm)


def _newton(
    ybus: np.ndarray, spec: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]], v0: np.ndarray,
    ang: np.ndarray, prow: np.ndarray, vmc: np.ndarray, qrow: np.ndarray,
    tol: float, max_iter: int, w: Optional[np.ndarray] = None, delta0: float = 0.0,
) -> tuple[np.ndarray, float, bool, int]:
    """Newton-Raphson in coordinate polari.

    Incognite: angoli dei nodi `ang`, moduli dei nodi `vmc` e, con il saldo
    distribuito (pesi w), lo sbilancio Δ ripartito come w·Δ. Equazioni:
    potenza attiva nei nodi `prow`, reattiva nei nodi `qrow`.
    spec(|V|) restituisce la potenza impressa e la sua derivata rispetto a |V|.
    """
    v = v0.copy()
    delta = delta0
    na, nv = len(ang), len(vmc)
    if len(prow) + len(qrow) != na + nv + (w is not None):
        raise ValueError("flusso di potenza: numero di equazioni diverso dal numero di incognite")

    def mismatch(v: np.ndarray, delta: float) -> np.ndarray:
        s = v * np.conj(ybus @ v) - spec(np.abs(v))[0]
        if w is not None:
            s = s - w * delta
        return np.r_[s[prow].real, s[qrow].imag]

    f = mismatch(v, delta)
    for it in range(max_iter + 1):
        if np.max(np.abs(f), initial=0.0) < tol:
            return v, delta, True, it
        if it == max_iter:
            break
        ibus = ybus @ v
        dv = np.diag(v)
        dvn = np.diag(v / np.abs(v))
        ds_dvm = dv @ np.conj(ybus @ dvn) + np.conj(np.diag(ibus)) @ dvn
        ds_dvm[np.diag_indices(len(v))] -= spec(np.abs(v))[1]  # carichi dipendenti dalla tensione
        ds_dva = 1j * dv @ np.conj(np.diag(ibus) - ybus @ dv)
        blocks = [
            [ds_dva[np.ix_(prow, ang)].real, ds_dvm[np.ix_(prow, vmc)].real],
            [ds_dva[np.ix_(qrow, ang)].imag, ds_dvm[np.ix_(qrow, vmc)].imag],
        ]
        if w is not None:
            blocks[0].append(-w[prow].reshape(-1, 1))
            blocks[1].append(np.zeros((len(qrow), 1)))
        dx = np.linalg.solve(np.block(blocks), -f)
        va = np.angle(v)
        vm = np.abs(v)
        va[ang] += dx[:na]
        vm[vmc] += dx[na:na + nv]
        if w is not None:
            delta += dx[-1]
        v = vm * np.exp(1j * va)
        f = mismatch(v, delta)
    return v, delta, False, max_iter


def _tap_direction(t: Transformer) -> int:
    """+1 se aumentando la presa la tensione del nodo regolato diminuisce.

    Stessa convenzione di pandapower (DiscreteTapControl): presa sul lato AT e
    nodo regolato dal lato BT (o a valle) → +1; segno invertito se la presa è
    sul lato BT, se il nodo regolato è il nodo AT o se il passo è negativo.
    """
    d = 1 if t.tap_side == "hv" else -1
    if t.control_bus == t.hv_bus:
        d = -d
    if t.tap_step_percent < 0:
        d = -d
    return d


def _band(t: Transformer) -> float:
    """Semiampiezza della banda di regolazione [p.u.] (default 0,75 passi)."""
    return t.control_band_pu if t.control_band_pu is not None else 0.75 * abs(t.tap_step_percent) / 100.0


def run_load_flow(
    net: Network, tol_mva: float = 1e-8, max_iter: int = 30, enforce_q_lims: bool = False,
    phase_shift: bool = True, distributed_slack: bool = False, tap_control: bool = True,
) -> LoadFlowResult:
    """Flusso di potenza con il metodo di Newton-Raphson.

    tol_mva: tolleranza sugli scarti di potenza (MW/Mvar).
    enforce_q_lims: i generatori PV che superano q_min_mvar/q_max_mvar passano a
    nodi PQ con la potenza reattiva al limite (iterazione esterna).
    phase_shift: sfasamenti dei gruppi vettoriali dei trasformatori (angoli
    assoluti); False: angoli relativi, come se tutti i trasformatori avessero
    sfasamento nullo.
    distributed_slack: lo sbilancio di potenza attiva è ripartito tra reti
    esterne e generatori in proporzione a slack_weight (un solo nodo di saldo,
    riferimento degli angoli); la rete esterna parte da potenza attiva nulla.
    tap_control: regolazione automatica delle prese dei trasformatori con
    control_bus (iterazione esterna, un passo per volta); False: prese fisse.
    """
    net.validate()
    model = _Model(net, phase_shift)
    idx, n = model.idx, model.n
    warnings: list[str] = []

    # nodo di saldo: reti esterne; senza reti esterne il primo generatore PV locale
    slack: dict[int, complex] = {}
    for q in net.external_grids:
        slack[idx[q.bus]] = q.vm_pu * cmath.exp(1j * math.radians(q.va_degree))
    for g in net.generators:
        if g.vm_pu is None and g.regulated_bus is not None:
            raise ValueError(f"{g.id}: regulated_bus richiede vm_pu (generatore PV)")
    pv_gens = [g for g in net.generators if g.vm_pu is not None]
    slack_gen = None
    if not slack:
        local = [g for g in pv_gens if g.regulated_bus in (None, g.bus)]
        if not local:
            raise ValueError("flusso di potenza: serve una rete esterna o un generatore con vm_pu")
        slack_gen = local[0]
        slack[idx[slack_gen.bus]] = complex(slack_gen.vm_pu, 0.0)
        warnings.append(f"{slack_gen.id}: nessuna rete esterna, il generatore è il nodo di saldo")

    # regolazione della tensione: nodo del generatore (potenza reattiva libera)
    # → nodo regolato (modulo della tensione imposto); coincidono se locale
    ctrl: dict[int, int] = {}
    vset: dict[int, float] = {}
    owner: dict[int, int] = {}
    for g in pv_gens:
        i = idx[g.bus]
        r = idx[g.regulated_bus or g.bus]
        if i in slack:
            if r != i:
                raise ValueError(f"{g.id}: un generatore sul nodo di saldo non può regolare un nodo remoto")
            if abs(abs(slack[i]) - g.vm_pu) > 1e-9:
                raise ValueError(f"{g.id}: vm_pu diversa da quella del nodo di saldo")
            continue
        if r in slack:
            raise ValueError(f"{g.id}: il nodo regolato è il nodo di saldo")
        if i in ctrl and ctrl[i] != r:
            raise ValueError(f"{g.id}: generatori dello stesso nodo regolano nodi diversi")
        if r in owner and owner[r] != i:
            raise ValueError(f"{g.id}: nodo regolato da generatori di nodi diversi")
        if r in vset and abs(vset[r] - g.vm_pu) > 1e-9:
            raise ValueError(f"{g.id}: generatori PV sullo stesso nodo con tensioni diverse")
        ctrl[i], vset[r], owner[r] = r, g.vm_pu, i

    # saldo distribuito: pesi per nodo normalizzati a somma unitaria
    weights = None
    wsum = 0.0
    if distributed_slack:
        if len(slack) > 1:
            raise ValueError("saldo distribuito: è ammesso un solo nodo di saldo (riferimento)")
        weights = np.zeros(n)
        for q in net.external_grids:
            weights[idx[q.bus]] += q.slack_weight
        for g in net.generators:
            weights[idx[g.bus]] += g.slack_weight
        wsum = float(weights.sum())
        if wsum <= 1e-12:
            raise ValueError("saldo distribuito: la somma dei pesi slack_weight deve essere positiva")
        weights /= wsum

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

    spec = _Spec(net, idx, n)
    tol = tol_mva / S_BASE_MVA
    gens_at_ctrl = {i: [g for g in pv_gens if idx[g.bus] == i] for i in ctrl}

    def solve(model: _Model) -> tuple[np.ndarray, float, bool, int]:
        """Newton-Raphson con l'iterazione esterna dei limiti di potenza reattiva."""
        q_fixed: dict[int, float] = {}  # nodi passati a PQ: potenza reattiva al limite (p.u.)
        total = 0
        va0 = model.initial_angles(slack)
        ang = np.array([k for k in range(n) if k not in slack], dtype=int)
        prow = np.arange(n) if weights is not None else ang
        for _ in range(len(ctrl) + 1):
            active = {i: r for i, r in ctrl.items() if i not in q_fixed}
            vmc = np.array([k for k in ang if k not in active.values()], dtype=int)
            qrow = np.array([k for k in ang if k not in active], dtype=int)
            vm0 = np.ones(n)
            for r in active.values():
                vm0[r] = vset[r]
            v0 = vm0 * np.exp(1j * va0)
            for i, vs in slack.items():
                v0[i] = vs
            qf = np.zeros(n)
            for i, q in q_fixed.items():
                qf[i] = q

            def s_spec(vm: np.ndarray, qf: np.ndarray = qf) -> tuple[np.ndarray, np.ndarray]:
                return spec.spec(vm) + 1j * qf, -spec.dload(vm)

            delta0 = -float(np.sum(spec.spec(np.ones(n)).real))
            v, delta, converged, iters = _newton(model.ybus, s_spec, v0, ang, prow, vmc, qrow,
                                                 tol, max_iter, weights, delta0)
            total += iters
            if not converged or not enforce_q_lims:
                break
            sinj = v * np.conj(model.ybus @ v)
            s0 = spec.spec(np.abs(v))
            violated = False
            for i in active:
                gens = gens_at_ctrl[i]
                # potenza reattiva dei generatori = immessa nel nodo + assorbita dai carichi
                q_gen = (sinj[i] - s0[i]).imag
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
        return v, delta, converged, total

    # regolazione delle prese: iterazione esterna a passi discreti, come
    # DiscreteTapControl di pandapower (un passo per trasformatore e iterazione)
    controlled = [t for t in net.transformers if t.control_bus is not None] if tap_control else []
    taps: dict[str, float] = {t.id: t.tap_pos for t in net.transformers}
    visited = {tuple(taps[t.id] for t in controlled)}
    total_iter = 0
    for _ in range(MAX_TAP_ITER):
        model = _Model(net, phase_shift, taps)
        v, delta, converged, iters = solve(model)
        total_iter += iters
        if not converged or not controlled:
            break
        moved = False
        for t in controlled:
            vm = abs(v[idx[t.control_bus]])
            d = _tap_direction(t)
            step = -d if vm < t.control_vm_pu - _band(t) else d if vm > t.control_vm_pu + _band(t) else 0
            new = taps[t.id] + step
            if step == 0 or (t.tap_min is not None and new < t.tap_min) or (
                    t.tap_max is not None and new > t.tap_max):
                continue
            taps[t.id] = new
            moved = True
        if not moved:
            break
        state = tuple(taps[t.id] for t in controlled)
        if state in visited:
            warnings.append("regolazione delle prese: pendolamento (banda più stretta del passo), "
                            "prese fermate all'ultima posizione")
            model = _Model(net, phase_shift, taps)
            v, delta, converged, iters = solve(model)
            total_iter += iters
            break
        visited.add(state)
    else:
        warnings.append(f"regolazione delle prese non conclusa in {MAX_TAP_ITER} passi")
    if not converged:
        warnings.append(f"flusso di potenza non convergente in {max_iter} iterazioni")
    for t in controlled:
        if converged and abs(abs(v[idx[t.control_bus]]) - t.control_vm_pu) > _band(t) + 1e-12:
            warnings.append(f"{t.id}: tensione di {t.control_bus} fuori banda (presa {taps[t.id]:g} al limite)")

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

    # potenze delle sorgenti: generazione del nodo = potenza immessa + consumi − generatori statici
    gen_s = (sinj - (spec.sgen - spec.load(np.abs(v)))) * S_BASE_MVA

    def p_gen(g: Generator) -> float:
        """Potenza attiva di un generatore: p_mw più la sua quota del saldo distribuito."""
        if weights is None:
            return g.p_mw
        return g.p_mw + g.slack_weight / wsum * delta * S_BASE_MVA

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
        fixed = {g.id: complex(p_gen(g), g.q_mvar if g.vm_pu is None else 0.0)
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
                sources.append(LfSource(g.id, "gen", g.bus, p_gen(g), q_share))
            else:
                sources.append(LfSource(g.id, "gen", g.bus, p_gen(g), g.q_mvar))
    return LoadFlowResult(
        net.name, converged, total_iter, buses, branches, sources, warnings,
        taps={t.id: taps[t.id] for t in controlled},
        slack_mw=None if weights is None else delta * S_BASE_MVA,
    )


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
        "taps": res.taps,
        "slack_mw": res.slack_mw,
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
    if res.slack_mw is not None:
        out += ["", f"Saldo distribuito: {res.slack_mw:.4f} MW ripartiti secondo slack_weight."]
    if res.taps:
        out += ["", "## Prese regolate", "", "| Trasformatore | Presa |", "|---|---|"]
        out += [f"| {tid} | {pos:g} |" for tid, pos in res.taps.items()]
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
