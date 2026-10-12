"""Coordinamento delle protezioni (selettività amperometrica e cronometrica).

Dispositivi (sezione `protective_devices` del file di rete), installati a un
estremo (`bus`) di un ramo (`branch`: linea, trasformatore o avvolgimento
`<id>:hv|mv|lv` di un tre avvolgimenti):

- `relay`: relè di massima corrente con curva a tempo inverso IEC 60255-151
  (`IEC_SI`, `IEC_VI`, `IEC_EI`, `IEC_LTI`: t = TMS·A/(M^p − 1)) o IEEE C37.112
  (`IEEE_MI`, `IEEE_VI`, `IEEE_EI`: t = TD·(A/(M^p − 1) + B)), soglie a tempo
  definito (`stages`) e tempo di apertura dell'interruttore;
- `breaker`: interruttore BT con sganciatore L-S-I (lungo ritardo a I²t
  costante, corto ritardo a tempo definito o a I²t costante, istantaneo);
- `fuse`: fusibile o curva qualsiasi per punti (corrente, tempo), con
  interpolazione log-log.

Correnti: guasto trifase con la I"k massima della IEC 60909 per la
selettività; correnti minime = correnti nei rami del guasto trifase nel caso
minimo scalate con I"k2/I"k3 del nodo (guasto bifase, sensibilità).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .network import Network, ProtectiveDevice

# t = TMS·A/(M^p − 1) (IEC) oppure TD·(A/(M^p − 1) + B) (IEEE)
CURVES = {
    "IEC_SI": (0.14, 0.02, 0.0),
    "IEC_VI": (13.5, 1.0, 0.0),
    "IEC_EI": (80.0, 2.0, 0.0),
    "IEC_LTI": (120.0, 1.0, 0.0),
    "IEEE_MI": (0.0515, 0.02, 0.114),
    "IEEE_VI": (19.61, 2.0, 0.491),
    "IEEE_EI": (28.2, 2.0, 0.1217),
}
DEFAULT_CTI_S = {"relay": 0.3, "breaker": 0.1, "fuse": 0.1}
L_PICKUP = 1.05  # lo sganciatore L interviene oltre 1,05·Ir


def trip_time_s(dev: "ProtectiveDevice", i_a: float) -> Optional[float]:
    """Tempo di eliminazione (s) del dispositivo per la corrente i_a (A); None se non interviene."""
    if i_a <= 0.0:
        return None
    times: list[float] = []
    if dev.kind == "relay":
        if dev.curve is not None:
            a, p, b = CURVES[dev.curve]
            m = i_a / dev.pickup_a
            if m > 1.0:
                times.append(dev.tms * (a / (m**p - 1.0) + b))
        for st in dev.stages:
            if i_a >= st["pickup_a"]:
                times.append(st["time_s"])
        if not times:
            return None
        return min(times) + dev.breaker_time_s
    if dev.kind == "breaker":
        # zone in sequenza: L sotto la soglia S (o I), S sotto la soglia I, poi I
        ir = dev.ir * dev.in_a
        i_inst = dev.ii * dev.in_a if dev.ii is not None else math.inf
        i_sd = dev.isd * ir if dev.isd is not None else i_inst
        if i_a >= i_inst:
            return dev.ti_s
        if i_a >= i_sd:
            t = dev.tsd_s
            if dev.i2t_sd and i_a < 10.0 * ir:
                t = max(dev.tsd_s, dev.tsd_s * (10.0 * ir / i_a) ** 2)  # I²t costante fino a 10·Ir
            if dev.tr_s is not None:
                t = min(t, max(dev.tr_s * 36.0 / (i_a / ir) ** 2, dev.tsd_s))
            return t
        if dev.tr_s is not None and i_a > L_PICKUP * ir:
            return dev.tr_s * 36.0 / (i_a / ir) ** 2  # I²t costante, tr a 6·Ir
        return None
    if dev.kind == "fuse":
        pts = sorted(dev.points)
        if i_a < pts[0][0]:
            return None
        if i_a >= pts[-1][0]:
            return pts[-1][1]
        for (i1, t1), (i2, t2) in zip(pts, pts[1:]):
            if i1 <= i_a <= i2:
                x = (math.log10(i_a) - math.log10(i1)) / (math.log10(i2) - math.log10(i1))
                return 10 ** (math.log10(t1) + x * (math.log10(t2) - math.log10(t1)))
    raise ValueError(f"{dev.id}: tipo di dispositivo non valido {dev.kind!r}")


def validate_device(dev: "ProtectiveDevice") -> None:
    if dev.kind == "relay":
        if dev.curve is None and not dev.stages:
            raise ValueError(f"{dev.id}: il relè richiede una curva o almeno una soglia (stages)")
        if dev.curve is not None:
            if dev.curve not in CURVES:
                raise ValueError(f"{dev.id}: curva sconosciuta {dev.curve!r} ({sorted(CURVES)})")
            if not dev.pickup_a or dev.pickup_a <= 0:
                raise ValueError(f"{dev.id}: serve pickup_a > 0")
        for st in dev.stages:
            if set(st) != {"pickup_a", "time_s"}:
                raise ValueError(f"{dev.id}: ogni soglia richiede pickup_a e time_s")
    elif dev.kind == "breaker":
        if not dev.in_a or dev.in_a <= 0:
            raise ValueError(f"{dev.id}: serve in_a > 0")
        if dev.isd is not None and dev.tsd_s is None:
            raise ValueError(f"{dev.id}: con isd serve tsd_s")
    elif dev.kind == "fuse":
        if len(dev.points) < 2 or any(i <= 0 or t <= 0 for i, t in dev.points):
            raise ValueError(f"{dev.id}: servono almeno due punti [I_A, t_s] positivi")
        pts = sorted(dev.points)
        if any(t2 > t1 for (_, t1), (_, t2) in zip(pts, pts[1:])):
            raise ValueError(f"{dev.id}: il tempo deve decrescere al crescere della corrente")
    else:
        raise ValueError(f"{dev.id}: tipo di dispositivo non valido {dev.kind!r} (relay, breaker, fuse)")
    if dev.protects not in ("branch", "bus"):
        raise ValueError(f"{dev.id}: protects deve essere 'branch' o 'bus'")


def cti_s(dev: "ProtectiveDevice") -> float:
    return dev.cti_s if dev.cti_s is not None else DEFAULT_CTI_S[dev.kind]


# --- studio ------------------------------------------------------------------------------


@dataclass
class DeviceOperation:
    device: str
    current_a: float  # corrente nel dispositivo
    time_s: Optional[float]
    forward: bool  # corrente nel verso protetto
    order: Optional[int] = None  # 0 = principale, 1 = prima riserva, …


@dataclass
class PairCheck:
    primary: str
    backup: str
    t_primary_s: Optional[float]
    t_backup_s: Optional[float]
    required_s: float
    ok: bool
    # verifica sull'intero campo di correnti (fino alla corrente di guasto, solo caso massimo)
    worst_margin_s: Optional[float] = None
    worst_current_a: Optional[float] = None  # corrente nel dispositivo principale

    @property
    def margin_s(self) -> Optional[float]:
        if self.t_primary_s is None or self.t_backup_s is None:
            return None
        return self.t_backup_s - self.t_primary_s


@dataclass
class FaultCase:
    bus: str
    level: str  # "max" (trifase, caso massimo) o "min" (bifase, caso minimo)
    ik_ka: float
    operations: list[DeviceOperation]
    pairs: list[PairCheck]


@dataclass
class CoordinationResult:
    network: str
    faults: list[FaultCase]
    issues: list[str] = field(default_factory=list)
    load_currents_a: dict[str, float] = field(default_factory=dict)

    def fault(self, bus: str, level: str = "max") -> FaultCase:
        return next(f for f in self.faults if f.bus == bus and f.level == level)


def _topology(net: "Network"):
    from .calc import _Builder

    b = _Builder(net, "max", [])
    b.build(1)
    adj: dict[str, set[str]] = {k: set() for k in b.idx}
    ends: dict[str, tuple[str, str]] = {}
    for name, i, j, _, _ in b.branches:
        adj[i].add(j)
        adj[j].add(i)
        ends[name] = (i, j)
    return adj, ends


def _hops(adj: dict[str, set[str]], start: str) -> dict[str, int]:
    dist = {start: 0}
    q = deque([start])
    while q:
        k = q.popleft()
        for n in adj[k]:
            if n not in dist:
                dist[n] = dist[k] + 1
                q.append(n)
    return dist


def coordination_study(
    net: "Network",
    fault_buses: Optional[list[str]] = None,
    max_time_s: float = 5.0,
    check_load: bool = True,
) -> CoordinationResult:
    """Sequenza di intervento, selettività e sensibilità per guasti nei nodi.

    Per ogni nodo guasto i dispositivi percorsi dalla corrente di guasto nel
    verso protetto sono ordinati dal più vicino al guasto (principale) al più
    lontano (riserve): distanza in rami dal lato protetto del dispositivo al
    nodo guasto, poi dal nodo di installazione. Per ogni coppia consecutiva
    principale/riserva si richiede t_riserva − t_principale ≥ CTI della riserva
    (default 0,3 s relè, 0,1 s interruttori e fusibili), con la corrente
    massima (trifase, caso massimo) e minima (bifase, caso minimo). La
    protezione principale deve intervenire entro `max_time_s` con la corrente
    minima. Con `check_load` le correnti del flusso di potenza (se la rete ha
    carichi) non devono provocare interventi.
    """
    from .calc import calculate, fault_currents

    if not net.protective_devices:
        raise ValueError("la rete non contiene dispositivi di protezione (protective_devices)")
    adj, ends = _topology(net)
    for dev in net.protective_devices:
        validate_device(dev)
        if dev.branch not in ends:
            raise ValueError(f"{dev.id}: ramo inesistente {dev.branch!r}")
        if dev.bus not in ends[dev.branch]:
            raise ValueError(f"{dev.id}: il nodo {dev.bus!r} non è un estremo di {dev.branch}")
    buses = fault_buses or [b.id for b in net.buses]
    sc_min = calculate(net, "min")
    hops = {k: _hops(adj, k) for k in adj}
    result = CoordinationResult(net.name, [])

    for fb in buses:
        for level in ("max", "min"):
            fc = fault_currents(net, fb, level)
            scale = 1.0
            if level == "min":
                r = sc_min.bus(fb)
                scale = r.ikss2_ka / r.ikss3_ka if r.ikss3_ka > 0 else 0.0
            ops = []
            keys = {}
            for dev in net.protective_devices:
                i_c = fc.branch_ka[(dev.branch, dev.bus)] * scale
                proj = (i_c * fc.ikss_ka.conjugate()).real  # > 0: dal nodo verso il ramo
                into_branch = bool(proj > 0)
                forward = into_branch if dev.protects == "branch" else not into_branch
                i_a = float(abs(i_c)) * 1000.0
                if i_a < 1e-6 * abs(fc.ikss_ka) * 1000.0:
                    forward = False
                op = DeviceOperation(dev.id, i_a, trip_time_s(dev, i_a), forward)
                ops.append(op)
                if forward:
                    i, j = ends[dev.branch]
                    down = (j if dev.bus == i else i) if dev.protects == "branch" else dev.bus
                    keys[dev.id] = (hops[down].get(fb, math.inf), hops[dev.bus].get(fb, math.inf))
            chain = sorted(keys, key=lambda d: keys[d])
            for k, d in enumerate(chain):
                next(o for o in ops if o.device == d).order = k
            devs = {d.id: d for d in net.protective_devices}
            opmap = {o.device: o for o in ops}
            pairs = []
            for p, q in zip(chain, chain[1:]):
                tp, tq = opmap[p].time_s, opmap[q].time_s
                req = cti_s(devs[q])
                ok = tq is None or (tp is not None and tq - tp >= req - 1e-9)
                pair = PairCheck(p, q, tp, tq, req, ok)
                if level == "max":
                    _sweep(pair, devs[p], devs[q], opmap[p].current_a, opmap[q].current_a)
                    if ok and not pair.ok:
                        result.issues.append(
                            f"guasto {fb}: {p}–{q} non selettivi con correnti inferiori a quella di guasto: "
                            f"margine {pair.worst_margin_s:.3f} s < {req:.3f} s con "
                            f"{pair.worst_current_a:.0f} A in {p}" if pair.worst_margin_s is not None else
                            f"guasto {fb}: con {pair.worst_current_a:.0f} A in {p} interviene solo {q}")
                pairs.append(pair)
                if not ok:
                    if tp is None:
                        result.issues.append(f"guasto {fb} ({level}): {p} non interviene, interviene {q}")
                    else:
                        result.issues.append(
                            f"guasto {fb} ({level}): {p}–{q} non selettivi, margine "
                            f"{tq - tp:.3f} s < {req:.3f} s")
            if level == "min" and chain:
                prim = opmap[chain[0]]
                if prim.time_s is None or prim.time_s > max_time_s:
                    t = "non interviene" if prim.time_s is None else f"interviene in {prim.time_s:.3f} s"
                    result.issues.append(
                        f"guasto {fb} (min): la protezione principale {prim.device} {t} con "
                        f"{prim.current_a:.0f} A (limite {max_time_s:g} s)")
            ops.sort(key=lambda o: (o.time_s is None, o.time_s or 0.0, o.device))
            result.faults.append(FaultCase(fb, level, float(abs(fc.ikss_ka) * scale), ops, pairs))

    if check_load and (net.loads or net.motors):
        _check_load(net, result)
    return result


def _sweep(pair: PairCheck, prim: "ProtectiveDevice", back: "ProtectiveDevice",
           i_prim_a: float, i_back_a: float, n: int = 120) -> None:
    """Margine minimo tra le curve per correnti da 1/1000 della corrente di guasto
    fino a questa, con il rapporto tra le correnti nei due dispositivi del guasto
    considerato (rete lineare: le correnti scalano insieme)."""
    worst, worst_i = math.inf, None
    for s in range(n + 1):
        k = 10 ** (-3.0 + 3.0 * s / n)
        tq = trip_time_s(back, k * i_back_a)
        if tq is None:
            continue
        tp = trip_time_s(prim, k * i_prim_a)
        margin = -math.inf if tp is None else tq - tp
        if margin < worst:
            worst, worst_i = margin, k * i_prim_a
    if worst_i is None:
        return
    pair.worst_current_a = worst_i
    pair.worst_margin_s = None if worst == -math.inf else worst
    if worst < pair.required_s - 1e-9:
        pair.ok = False


def _check_load(net: "Network", result: CoordinationResult) -> None:
    from .loadflow import run_load_flow

    try:
        lf = run_load_flow(net)
    except ValueError as exc:
        result.issues.append(f"verifica delle correnti di carico non eseguita: {exc}")
        return
    if not lf.converged:
        result.issues.append("verifica delle correnti di carico non eseguita: flusso di potenza non convergente")
        return
    for dev in net.protective_devices:
        br = lf.branch(dev.branch)
        i_ka = br.i_from_ka if br.from_bus == dev.bus else br.i_to_ka
        i_a = i_ka * 1000.0
        result.load_currents_a[dev.id] = i_a
        t = trip_time_s(dev, i_a)
        if t is not None:
            result.issues.append(f"{dev.id}: interviene con la corrente di carico {i_a:.1f} A in {t:.1f} s")


# --- uscita ------------------------------------------------------------------------------


def _fmt_t(t: Optional[float]) -> str:
    return "—" if t is None else f"{t:.3f}"


def result_to_markdown(res: CoordinationResult) -> str:
    out = [f"# Coordinamento delle protezioni — {res.network}", ""]
    if res.issues:
        out += ["## Problemi", ""] + [f"- {i}" for i in res.issues] + [""]
    else:
        out += ["Nessun problema di selettività, sensibilità o intervento con le correnti di carico.", ""]
    if res.load_currents_a:
        out += ["## Correnti di carico", "", "| Dispositivo | I carico [A] |", "|---|---|"]
        out += [f"| {d} | {i:.1f} |" for d, i in res.load_currents_a.items()] + [""]
    out += ["## Sequenza di intervento", ""]
    ruolo = {0: "principale"}
    for f in res.faults:
        livello = "I\"k3 max" if f.level == "max" else "I\"k2 min"
        out += [f"### Guasto in {f.bus} — {livello} = {f.ik_ka:.3f} kA", "",
                "| Dispositivo | Ruolo | I [A] | t [s] |", "|---|---|---|---|"]
        for o in f.operations:
            if o.order is not None:
                r = ruolo.get(o.order, f"riserva {o.order}")
            else:
                r = "—" if o.current_a > 0 else "non percorso"
            out.append(f"| {o.device} | {r} | {o.current_a:.0f} | {_fmt_t(o.time_s)} |")
        if f.pairs:
            out += ["", "| Principale | Riserva | t princ. [s] | t ris. [s] | Margine [s] | Margine minimo [s] "
                    "(I princ. [A]) | Richiesto [s] | Esito |",
                    "|---|---|---|---|---|---|---|---|"]
            for p in f.pairs:
                m = "—" if p.margin_s is None else f"{p.margin_s:.3f}"
                if p.worst_current_a is None:
                    w = "—"
                else:
                    wm = "solo riserva" if p.worst_margin_s is None else f"{p.worst_margin_s:.3f}"
                    w = f"{wm} ({p.worst_current_a:.0f})"
                out.append(f"| {p.primary} | {p.backup} | {_fmt_t(p.t_primary_s)} | {_fmt_t(p.t_backup_s)} "
                           f"| {m} | {w} | {p.required_s:.3f} | {'OK' if p.ok else 'NO'} |")
        elif not any(o.order is not None for o in f.operations):
            out += ["", "Nessun dispositivo percorso dalla corrente di guasto nel verso protetto."]
        out.append("")
    return "\n".join(out)


def result_to_dict(res: CoordinationResult) -> dict:
    import dataclasses

    return {
        "network": res.network,
        "issues": res.issues,
        "load_currents_a": res.load_currents_a,
        "faults": [dict(dataclasses.asdict(f), pairs=[dict(dataclasses.asdict(p), margin_s=p.margin_s)
                                                       for p in f.pairs]) for f in res.faults],
    }


def tcc_svg(net: "Network", devices: list[str], ref_kv: float, marks_ka: Optional[dict[str, float]] = None,
            title: str = "") -> str:
    """Curve tempo-corrente (scala log-log) dei dispositivi, correnti riferite a ref_kv.

    marks_ka: linee verticali (es. {"I\\"k max": 12.3}) in kA alla tensione ref_kv.
    """
    devs = {d.id: d for d in net.protective_devices}
    un = {b.id: b.un_kv for b in net.buses}
    from .calc import _Builder

    b = _Builder(net, "max", [])
    un.update(b.un)
    w, h, ml, mr, mt, mb = 720, 540, 70, 20, 40, 50
    i_lo, i_hi, t_lo, t_hi = 10.0, 1e6, 0.01, 1000.0

    def x(i: float) -> float:
        return ml + (math.log10(i) - math.log10(i_lo)) / (math.log10(i_hi) - math.log10(i_lo)) * (w - ml - mr)

    def y(t: float) -> float:
        return mt + (math.log10(t_hi) - math.log10(t)) / (math.log10(t_hi) - math.log10(t_lo)) * (h - mt - mb)

    palette = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#4b5563"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
             'font-family="sans-serif" font-size="11">',
             f'<rect width="{w}" height="{h}" fill="white"/>',
             f'<text x="{w / 2}" y="20" text-anchor="middle" font-size="13">{title}</text>']
    for e in range(1, 7):
        for k in range(1, 10):
            i = k * 10**e
            if i_lo <= i <= i_hi:
                parts.append(f'<line x1="{x(i):.1f}" y1="{mt}" x2="{x(i):.1f}" y2="{h - mb}" stroke="#e5e7eb"/>')
        label = {1: "10", 2: "100", 3: "1k", 4: "10k", 5: "100k", 6: "1M"}[e]
        parts.append(f'<text x="{x(10**e):.1f}" y="{h - mb + 15}" text-anchor="middle">{label}</text>')
    for e in range(-2, 4):
        parts.append(f'<line x1="{ml}" y1="{y(10**e):.1f}" x2="{w - mr}" y2="{y(10**e):.1f}" stroke="#d1d5db"/>')
        parts.append(f'<text x="{ml - 5}" y="{y(10**e) + 4:.1f}" text-anchor="end">{10**e:g}</text>')
    parts.append(f'<text x="{w / 2}" y="{h - 12}" text-anchor="middle">corrente [A] a {ref_kv:g} kV</text>')
    parts.append(f'<text x="15" y="{h / 2}" transform="rotate(-90 15 {h / 2})" text-anchor="middle">tempo [s]</text>')
    for k, d in enumerate(devices):
        dev = devs[d]
        f = un[dev.bus] / ref_kv  # corrente riferita alla tensione di riferimento
        pts = []
        n = 400
        for s in range(n + 1):
            i_ref = 10 ** (math.log10(i_lo) + s / n * (math.log10(i_hi) - math.log10(i_lo)))
            t = trip_time_s(dev, i_ref / f)
            if t is not None and t_lo <= t <= t_hi:
                pts.append(f"{x(i_ref):.1f},{y(t):.1f}")
        col = palette[k % len(palette)]
        if pts:
            parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(pts)}"/>')
        parts.append(f'<text x="{w - mr - 5}" y="{mt + 15 + 14 * k}" text-anchor="end" fill="{col}">{d}</text>')
    for k, (label, i_ka) in enumerate((marks_ka or {}).items()):
        xi = x(i_ka * 1000.0)
        parts.append(f'<line x1="{xi:.1f}" y1="{mt}" x2="{xi:.1f}" y2="{h - mb}" stroke="#111827" '
                     'stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{xi + 3:.1f}" y="{h - mb - 6 - 13 * k}">{label}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
