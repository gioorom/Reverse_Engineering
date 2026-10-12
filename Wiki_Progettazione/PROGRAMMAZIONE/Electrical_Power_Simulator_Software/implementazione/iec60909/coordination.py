"""Coordinamento delle protezioni (selettività amperometrica e cronometrica).

Dispositivi (sezione `protective_devices` del file di rete), installati a un
estremo (`bus`) di un ramo (`branch`: linea, trasformatore, avvolgimento
`<id>:hv|mv|lv` di un tre avvolgimenti o trasformatore di messa a terra):

- `relay`: relè di massima corrente con curva a tempo inverso IEC 60255-151
  (`IEC_SI`, `IEC_VI`, `IEC_EI`, `IEC_LTI`: t = TMS·A/(M^p − 1)) o IEEE C37.112
  (`IEEE_MI`, `IEEE_VI`, `IEEE_EI`: t = TD·(A/(M^p − 1) + B)), soglie a tempo
  definito (`stages`) e tempo di apertura dell'interruttore;
- `breaker`: interruttore BT con sganciatore L-S-I (lungo ritardo a I²t
  costante, corto ritardo a tempo definito o a I²t costante, istantaneo);
- `fuse`: fusibile o curva qualsiasi per punti (corrente, tempo), con
  interpolazione log-log.

Relè e interruttori misurano la corrente di fase maggiore (`measure:
"phase"`) oppure la corrente residua 3·I0 (`"residual"`, protezione di
terra); possono essere direzionali (`directional`). Bande di tolleranza su
soglie e tempi; limiti di selettività energetica dichiarati dal costruttore
(`selectivity_limits`).

Livelli di guasto: trifase nel caso massimo ("max"), bifase nel caso minimo
("min"), monofase a terra nel caso massimo e minimo ("max_1ph", "min_1ph",
solo nei nodi con percorso verso terra). Correnti nei rami dalle tre reti di
sequenza (`calc.fault_currents`).
"""

from __future__ import annotations

import cmath
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

# livello: (caso IEC 60909, tipo di guasto)
LEVELS = {
    "max": ("max", "3ph"),
    "min": ("min", "2ph"),
    "max_1ph": ("max", "1ph"),
    "min_1ph": ("min", "1ph"),
}
LEVEL_LABELS = {"max": "I\"k3 max", "min": "I\"k2 min", "max_1ph": "I\"k1 max", "min_1ph": "I\"k1 min"}


def _nominal_time_s(dev: "ProtectiveDevice", i_a: float) -> Optional[float]:
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


def has_tolerance(dev: "ProtectiveDevice") -> bool:
    return bool(dev.current_tolerance_percent or dev.time_tolerance_percent or dev.time_tolerance_s)


def trip_time_s(dev: "ProtectiveDevice", i_a: float, band: str = "nom") -> Optional[float]:
    """Tempo di eliminazione (s) del dispositivo per la corrente i_a (A); None se non interviene.

    `band`: "nom" (curva nominale), "min" o "max" (limiti della banda di
    tolleranza). Tutte le soglie di corrente scalano insieme di
    ±`current_tolerance_percent` (la curva è funzione di I/soglia: t(I) con
    soglie ·(1 ± k) = t_nom(I/(1 ± k))); il tempo varia di
    ±max(`time_tolerance_percent`·t, `time_tolerance_s`).
    """
    if band == "nom":
        return _nominal_time_s(dev, i_a)
    if band not in ("min", "max"):
        raise ValueError(f"banda non valida {band!r} (nom, min, max)")
    k = dev.current_tolerance_percent / 100.0
    t = _nominal_time_s(dev, i_a / (1.0 - k if band == "min" else 1.0 + k))
    if t is None:
        return None
    dt = max(t * dev.time_tolerance_percent / 100.0, dev.time_tolerance_s)
    return max(t - dt, 0.0) if band == "min" else t + dt


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
    if dev.measure not in ("phase", "residual"):
        raise ValueError(f"{dev.id}: measure deve essere 'phase' o 'residual'")
    if dev.kind == "fuse" and (dev.measure != "phase" or dev.directional):
        raise ValueError(f"{dev.id}: un fusibile misura la corrente di fase e non è direzionale")
    if not 0.0 <= dev.current_tolerance_percent < 100.0 or not 0.0 <= dev.time_tolerance_percent < 100.0:
        raise ValueError(f"{dev.id}: le tolleranze in % devono essere tra 0 e 100")
    if dev.time_tolerance_s < 0.0:
        raise ValueError(f"{dev.id}: time_tolerance_s non può essere negativo")
    if not isinstance(dev.selectivity_limits, dict) or any(
            not isinstance(v, (int, float)) or v <= 0 for v in dev.selectivity_limits.values()):
        raise ValueError(f"{dev.id}: selectivity_limits deve essere {{id a valle: Is in kA > 0}}")


def cti_s(dev: "ProtectiveDevice") -> float:
    return dev.cti_s if dev.cti_s is not None else DEFAULT_CTI_S[dev.kind]


# --- studio ------------------------------------------------------------------------------


@dataclass
class DeviceOperation:
    device: str
    current_a: float  # corrente misurata dal dispositivo (di fase o residua)
    time_s: Optional[float]
    forward: bool  # corrente nel verso protetto
    order: Optional[int] = None  # 0 = principale, 1 = prima riserva, …
    time_min_s: Optional[float] = None  # banda di tolleranza
    time_max_s: Optional[float] = None
    measure: str = "phase"


@dataclass
class PairCheck:
    primary: str
    backup: str
    t_primary_s: Optional[float]
    t_backup_s: Optional[float]
    required_s: float
    ok: bool
    # verifica sull'intero campo di correnti (fino alla corrente di guasto, casi massimi)
    worst_margin_s: Optional[float] = None
    worst_current_a: Optional[float] = None  # corrente nel dispositivo principale
    # tempi per il margine: massimo del principale e minimo della riserva (bande di tolleranza)
    t_primary_max_s: Optional[float] = None
    t_backup_min_s: Optional[float] = None
    # selettività energetica da tabella del costruttore: limite Is (kA) e corrente nel principale
    selectivity_limit_ka: Optional[float] = None

    @property
    def margin_s(self) -> Optional[float]:
        tp = self.t_primary_max_s if self.t_primary_max_s is not None else self.t_primary_s
        tq = self.t_backup_min_s if self.t_backup_min_s is not None else self.t_backup_s
        if tp is None or tq is None:
            return None
        return tq - tp


@dataclass
class FaultCase:
    bus: str
    level: str  # "max", "min", "max_1ph", "min_1ph" (vedi LEVELS)
    ik_ka: float
    operations: list[DeviceOperation]
    pairs: list[PairCheck]


@dataclass
class CoordinationResult:
    network: str
    faults: list[FaultCase]
    issues: list[str] = field(default_factory=list)
    load_currents_a: dict[str, float] = field(default_factory=dict)
    current_basis: str = "ik"  # "ik" (I"k) o "ib" (corrente di interruzione nel guasto trifase)
    warnings: list[str] = field(default_factory=list)

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
    # trasformatori di messa a terra: derivazioni con un solo estremo
    for et in net.earthing_transformers:
        ends[et.id] = (et.bus, et.bus)
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


def _measure(dev: "ProtectiveDevice", fc, ref: float) -> tuple[float, int]:
    """Corrente misurata (A) e sequenza usata per il verso.

    Fase: corrente di fase maggiore, verso dalla sequenza diretta (guasto
    trifase) o inversa (guasti dissimmetrici). Residua: 3·I0, verso dalla
    sequenza zero.
    """
    key = (dev.branch, dev.bus)
    seq = fc.branch_seq_ka.get(key, (0j, 0j, 0j))
    if dev.measure == "residual":
        return float(3.0 * abs(seq[0]) * 1000.0), 0
    i_a = float(max(abs(i) for i in fc.branch_phase_ka.get(key, (0j, 0j, 0j))) * 1000.0)
    if fc.fault_type == "3ph":
        return i_a, 1
    small = 1e-6 * ref
    if abs(seq[2]) > small:
        return i_a, 2
    return i_a, (0 if abs(seq[0]) > small else 1)


def _into_branch(dev: "ProtectiveDevice", fc, s: int) -> bool:
    """La corrente della sequenza s va dal nodo verso il ramo?

    Dispositivi direzionali: polarizzazione con la tensione, come un relè:
    l'impedenza vista dietro il dispositivo, −ΔV_s/I_s, deve stare entro ±90°
    dall'angolo caratteristico. Gli altri: proiezione sulla corrente di guasto
    della stessa sequenza (rete senza sfasamenti).
    """
    i_s = fc.branch_seq_ka.get((dev.branch, dev.bus), (0j, 0j, 0j))[s]
    if dev.directional:
        dv = fc.bus_dv_seq_kv[dev.bus][s]
        if abs(dv) > 1e-12:
            rot = cmath.exp(-1j * math.radians(dev.characteristic_angle_deg))
            return bool((-dv * i_s.conjugate() * rot).real > 0.0)
    ref = fc.fault_seq_ka[s]
    return bool((i_s * ref.conjugate()).real > 0.0)


def coordination_study(
    net: "Network",
    fault_buses: Optional[list[str]] = None,
    max_time_s: float = 5.0,
    check_load: bool = True,
    earth_faults: bool = True,
    current_basis: str = "ik",
    tmin_s: float = 0.1,
) -> CoordinationResult:
    """Sequenza di intervento, selettività e sensibilità per guasti nei nodi.

    Per ogni nodo guasto e livello (trifase massimo "max", bifase minimo
    "min" e, con `earth_faults` e percorso verso terra, monofase massimo e
    minimo "max_1ph", "min_1ph") i dispositivi percorsi dalla corrente di
    guasto nel verso protetto sono ordinati dal più vicino al guasto
    (principale) al più lontano (riserve): distanza in rami dal lato protetto
    del dispositivo al nodo guasto, poi dal nodo di installazione. Per ogni
    coppia consecutiva principale/riserva si richiede t_riserva,min −
    t_principale,max ≥ CTI della riserva (default 0,3 s relè, 0,1 s interruttori
    e fusibili), oppure, se la riserva dichiara un limite di selettività
    energetica Is per il principale, corrente nel principale ≤ Is. La
    protezione principale deve intervenire entro `max_time_s` con le correnti
    minime. Con `check_load` le correnti del flusso di potenza (se la rete ha
    carichi) non devono provocare interventi.

    `current_basis`: "ik" (correnti iniziali I"k) oppure "ib" (correnti di
    interruzione al tempo `tmin_s` per il guasto trifase massimo, con il
    decadimento dei contributi delle macchine; vedi `calc.fault_currents`).
    """
    from .calc import calculate, fault_currents

    if not net.protective_devices:
        raise ValueError("la rete non contiene dispositivi di protezione (protective_devices)")
    if current_basis not in ("ik", "ib"):
        raise ValueError("current_basis deve essere 'ik' o 'ib'")
    adj, ends = _topology(net)
    devs = {d.id: d for d in net.protective_devices}
    for dev in net.protective_devices:
        validate_device(dev)
        if dev.branch not in ends:
            raise ValueError(f"{dev.id}: ramo inesistente {dev.branch!r}")
        if dev.bus not in ends[dev.branch]:
            raise ValueError(f"{dev.id}: il nodo {dev.bus!r} non è un estremo di {dev.branch}")
        for other in dev.selectivity_limits:
            if other not in devs or other == dev.id:
                raise ValueError(f"{dev.id}: selectivity_limits cita un dispositivo inesistente {other!r}")
    buses = fault_buses or [b.id for b in net.buses]
    sc = {"max": calculate(net, "max"), "min": calculate(net, "min")}
    hops = {k: _hops(adj, k) for k in adj}
    result = CoordinationResult(net.name, [], current_basis=current_basis)

    for fb in buses:
        levels = ["max", "min"]
        if earth_faults:
            levels += [lv for lv in ("max_1ph", "min_1ph") if sc[LEVELS[lv][0]].bus(fb).ikss1_ka > 0.0]
        for level in levels:
            case, ftype = LEVELS[level]
            fc = fault_currents(net, fb, case, fault_type=ftype,
                                breaking=current_basis == "ib" and level == "max", tmin_s=tmin_s)
            result.warnings += [w for w in fc.warnings if w not in result.warnings]
            i_ref = abs(fc.ikss_ka) * 1000.0
            ops = []
            keys = {}
            for dev in net.protective_devices:
                i_a, s = _measure(dev, fc, abs(fc.ikss_ka))
                into_branch = _into_branch(dev, fc, s)
                forward = into_branch if dev.protects == "branch" else not into_branch
                if i_a < 1e-6 * i_ref:
                    forward = False
                if dev.directional and not forward:
                    times = (None, None, None)  # verso opposto: il relè direzionale non interviene
                else:
                    times = tuple(trip_time_s(dev, i_a, band) for band in ("nom", "min", "max"))
                op = DeviceOperation(dev.id, i_a, times[0], forward, None, times[1], times[2], dev.measure)
                ops.append(op)
                if forward:
                    i, j = ends[dev.branch]
                    down = (j if dev.bus == i else i) if dev.protects == "branch" else dev.bus
                    keys[dev.id] = (hops[down].get(fb, math.inf), hops[dev.bus].get(fb, math.inf))
            # dispositivi nella stessa posizione (es. elementi di fase e di terra dello
            # stesso interruttore) formano un unico gradino della catena
            loc = {}
            for d in net.protective_devices:
                loc.setdefault((d.branch, d.bus, d.protects), len(loc))
            chain = sorted(keys, key=lambda d: (keys[d], loc[(devs[d].branch, devs[d].bus, devs[d].protects)]))
            groups: list[list[str]] = []
            for d in chain:
                where = (devs[d].branch, devs[d].bus, devs[d].protects)
                if groups and (devs[groups[-1][0]].branch, devs[groups[-1][0]].bus,
                               devs[groups[-1][0]].protects) == where:
                    groups[-1].append(d)
                else:
                    groups.append([d])
            opmap = {o.device: o for o in ops}
            for k, g in enumerate(groups):
                for d in g:
                    opmap[d].order = k
            pairs = []
            for gp, gq in zip(groups, groups[1:]):
                p = _fastest(gp, opmap, "max")
                q = _fastest(gq, opmap, "min")
                limit = None
                for qq in gq:
                    for pp in gp:
                        if limit is None and pp in devs[qq].selectivity_limits:
                            p, q, limit = pp, qq, devs[qq].selectivity_limits[pp]
                pair = _pair_check(opmap[p], opmap[q], devs[q], limit)
                ok = pair.ok  # esito al punto di guasto
                if not ok:
                    result.issues.append(_pair_issue(fb, level, pair, opmap[p].current_a))
                if level in ("max", "max_1ph") and limit is None:
                    # con la tabella del costruttore le correnti inferiori sono entro Is
                    _sweep(pair, [(devs[d], opmap[d].current_a) for d in gp],
                           [(devs[d], opmap[d].current_a) for d in gq], opmap[p].current_a)
                    if ok and not pair.ok:
                        result.issues.append(
                            f"guasto {fb} ({level}): {p}–{q} non selettivi con correnti inferiori a quella di "
                            f"guasto: margine {pair.worst_margin_s:.3f} s < {pair.required_s:.3f} s con "
                            f"{pair.worst_current_a:.0f} A in {p}" if pair.worst_margin_s is not None else
                            f"guasto {fb} ({level}): con {pair.worst_current_a:.0f} A in {p} interviene solo {q}")
                pairs.append(pair)
            if level in ("min", "min_1ph") and groups:
                prim = opmap[_fastest(groups[0], opmap, "max")]
                t = prim.time_max_s
                if t is None or t > max_time_s:
                    txt = "non interviene" if t is None else f"interviene in {t:.3f} s"
                    result.issues.append(
                        f"guasto {fb} ({level}): la protezione principale {prim.device} {txt} con "
                        f"{prim.current_a:.0f} A (limite {max_time_s:g} s)")
            ops.sort(key=lambda o: (o.time_s is None, o.time_s or 0.0, o.device))
            result.faults.append(FaultCase(fb, level, float(abs(fc.ikss_ka)), ops, pairs))

    if check_load and (net.loads or net.motors):
        _check_load(net, result)
    return result


def _fastest(group: list[str], opmap: dict[str, DeviceOperation], band: str) -> str:
    """Dispositivo del gruppo che interviene per primo (tempo minimo o massimo della banda)."""
    def t(d: str) -> float:
        v = opmap[d].time_min_s if band == "min" else opmap[d].time_max_s
        return math.inf if v is None else v
    return min(group, key=t)


def _pair_check(op_p: DeviceOperation, op_q: DeviceOperation, back: "ProtectiveDevice",
                limit: Optional[float]) -> PairCheck:
    """Verifica al punto di guasto di una coppia principale/riserva.

    Con il limite di selettività `limit` (Is in kA, tabella del costruttore) la
    coppia è selettiva se la corrente nel principale non supera Is; altrimenti
    serve t_riserva,min − t_principale,max ≥ CTI.
    """
    req = cti_s(back)
    tp, tq = op_p.time_max_s, op_q.time_min_s
    if limit is not None:
        # tabella del costruttore: selettivi fino a Is (purché il principale intervenga)
        ok = bool(op_p.current_a <= limit * 1000.0 * (1.0 + 1e-9) and (tq is None or tp is not None))
    else:
        ok = bool(tq is None or (tp is not None and tq - tp >= req - 1e-9))
    return PairCheck(op_p.device, op_q.device, op_p.time_s, op_q.time_s, req, ok,
                     t_primary_max_s=tp, t_backup_min_s=tq, selectivity_limit_ka=limit)


def _pair_issue(fb: str, level: str, pair: PairCheck, i_prim_a: float) -> str:
    p, q = pair.primary, pair.backup
    if pair.selectivity_limit_ka is not None:
        if pair.t_primary_max_s is None and i_prim_a <= pair.selectivity_limit_ka * 1000.0 * (1.0 + 1e-9):
            return f"guasto {fb} ({level}): {p} non interviene, interviene {q}"
        return (f"guasto {fb} ({level}): {p}–{q} non selettivi, corrente {i_prim_a / 1000.0:.2f} kA in {p} "
                f"oltre il limite di selettività Is = {pair.selectivity_limit_ka:g} kA del costruttore")
    if pair.t_primary_max_s is None:
        return f"guasto {fb} ({level}): {p} non interviene, interviene {q}"
    return (f"guasto {fb} ({level}): {p}–{q} non selettivi, margine "
            f"{pair.margin_s:.3f} s < {pair.required_s:.3f} s")


def _sweep(pair: PairCheck, prim: list[tuple["ProtectiveDevice", float]],
           back: list[tuple["ProtectiveDevice", float]], i_prim_a: float, n: int = 120) -> None:
    """Margine minimo tra le curve per correnti da 1/1000 della corrente di guasto
    fino a questa, con il rapporto tra le correnti nei dispositivi del guasto
    considerato (rete lineare: le correnti scalano insieme). Margine tra il tempo
    minimo della riserva e il tempo massimo del principale (bande di tolleranza);
    per i dispositivi nella stessa posizione vale il più rapido."""

    def group_time(group: list[tuple["ProtectiveDevice", float]], k: float, band: str) -> Optional[float]:
        times = [t for t in (trip_time_s(d, k * i, band) for d, i in group) if t is not None]
        return min(times) if times else None

    worst, worst_i = math.inf, None
    for s in range(n + 1):
        k = 10 ** (-3.0 + 3.0 * s / n)
        tq = group_time(back, k, "min")
        if tq is None:
            continue
        tp = group_time(prim, k, "max")
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
    branches = {br.id for br in lf.branches}
    for dev in net.protective_devices:
        if dev.branch not in branches:
            continue  # trasformatore di messa a terra: nessuna corrente di carico
        br = lf.branch(dev.branch)
        at_from = br.from_bus == dev.bus
        i_a = (br.i_from_ka if at_from else br.i_to_ka) * 1000.0
        if dev.measure == "residual":
            i_a = 0.0  # carichi equilibrati: nessuna corrente residua
        result.load_currents_a[dev.id] = i_a
        if dev.directional:
            into_branch = (br.p_from_mw if at_from else br.p_to_mw) > 0.0
            if into_branch != (dev.protects == "branch"):
                continue  # potenza nel verso opposto: il relè direzionale non interviene
        t = trip_time_s(dev, i_a, "min")
        if t is not None:
            result.issues.append(f"{dev.id}: interviene con la corrente di carico {i_a:.1f} A in {t:.1f} s")


# --- uscita ------------------------------------------------------------------------------


def _fmt_t(t: Optional[float]) -> str:
    return "—" if t is None else f"{t:.3f}"


def result_to_markdown(res: CoordinationResult) -> str:
    out = [f"# Coordinamento delle protezioni — {res.network}", ""]
    if res.current_basis == "ib":
        out += ["Guasto trifase massimo con le correnti di interruzione Ib (decadimento delle macchine).", ""]
    if res.issues:
        out += ["## Problemi", ""] + [f"- {i}" for i in res.issues] + [""]
    else:
        out += ["Nessun problema di selettività, sensibilità o intervento con le correnti di carico.", ""]
    if res.warnings:
        out += ["## Avvertenze", ""] + [f"- {w}" for w in res.warnings] + [""]
    if res.load_currents_a:
        out += ["## Correnti di carico", "", "| Dispositivo | I carico [A] |", "|---|---|"]
        out += [f"| {d} | {i:.1f} |" for d, i in res.load_currents_a.items()] + [""]
    out += ["## Sequenza di intervento", ""]
    ruolo = {0: "principale"}
    for f in res.faults:
        livello = LEVEL_LABELS.get(f.level, f.level)
        out += [f"### Guasto in {f.bus} — {livello} = {f.ik_ka:.3f} kA", "",
                "| Dispositivo | Ruolo | Misura | I [A] | t [s] | banda [s] |", "|---|---|---|---|---|---|"]
        for o in f.operations:
            if o.order is not None:
                r = ruolo.get(o.order, f"riserva {o.order}")
            else:
                r = "—" if o.current_a > 0 else "non percorso"
            misura = "3I0" if o.measure == "residual" else "fase"
            banda = "—" if o.time_min_s == o.time_max_s else f"{_fmt_t(o.time_min_s)}–{_fmt_t(o.time_max_s)}"
            out.append(f"| {o.device} | {r} | {misura} | {o.current_a:.0f} | {_fmt_t(o.time_s)} | {banda} |")
        if f.pairs:
            out += ["", "| Principale | Riserva | t princ. max [s] | t ris. min [s] | Margine [s] | "
                    "Margine minimo [s] (I princ. [A]) | Richiesto [s] | Criterio | Esito |",
                    "|---|---|---|---|---|---|---|---|---|"]
            for p in f.pairs:
                m = "—" if p.margin_s is None else f"{p.margin_s:.3f}"
                if p.worst_current_a is None:
                    w = "—"
                else:
                    wm = "solo riserva" if p.worst_margin_s is None else f"{p.worst_margin_s:.3f}"
                    w = f"{wm} ({p.worst_current_a:.0f})"
                crit = "curve" if p.selectivity_limit_ka is None else f"tabella, Is = {p.selectivity_limit_ka:g} kA"
                out.append(f"| {p.primary} | {p.backup} | {_fmt_t(p.t_primary_max_s)} | {_fmt_t(p.t_backup_min_s)} "
                           f"| {m} | {w} | {p.required_s:.3f} | {crit} | {'OK' if p.ok else 'NO'} |")
        elif not any(o.order is not None for o in f.operations):
            out += ["", "Nessun dispositivo percorso dalla corrente di guasto nel verso protetto."]
        out.append("")
    return "\n".join(out)


def result_to_dict(res: CoordinationResult) -> dict:
    import dataclasses

    return {
        "network": res.network,
        "current_basis": res.current_basis,
        "issues": res.issues,
        "warnings": res.warnings,
        "load_currents_a": res.load_currents_a,
        "faults": [dict(dataclasses.asdict(f), pairs=[dict(dataclasses.asdict(p), margin_s=p.margin_s)
                                                       for p in f.pairs]) for f in res.faults],
    }


def tcc_svg(net: "Network", devices: list[str], ref_kv: float, marks_ka: Optional[dict[str, float]] = None,
            title: str = "") -> str:
    """Curve tempo-corrente (scala log-log) dei dispositivi, correnti riferite a ref_kv.

    marks_ka: linee verticali (es. {"I\\"k max": 12.3}) in kA alla tensione ref_kv.
    I dispositivi con bande di tolleranza hanno anche le curve di tempo minimo
    e massimo (tratteggiate); per le protezioni di terra la corrente è 3·I0.
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

    def curve(dev: "ProtectiveDevice", f: float, band: str) -> list[str]:
        pts = []
        n = 400
        for s in range(n + 1):
            i_ref = 10 ** (math.log10(i_lo) + s / n * (math.log10(i_hi) - math.log10(i_lo)))
            t = trip_time_s(dev, i_ref / f, band)
            if t is not None and t_lo <= t <= t_hi:
                pts.append(f"{x(i_ref):.1f},{y(t):.1f}")
        return pts

    for k, d in enumerate(devices):
        dev = devs[d]
        f = un[dev.bus] / ref_kv  # corrente riferita alla tensione di riferimento
        col = palette[k % len(palette)]
        pts = curve(dev, f, "nom")
        if pts:
            parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(pts)}"/>')
        if has_tolerance(dev):
            for band in ("min", "max"):
                bp = curve(dev, f, band)
                if bp:
                    parts.append(f'<polyline class="banda" fill="none" stroke="{col}" stroke-width="1" '
                                 f'stroke-dasharray="5 3" points="{" ".join(bp)}"/>')
        label = f"{d} (3I0)" if dev.measure == "residual" else d
        parts.append(f'<text x="{w - mr - 5}" y="{mt + 15 + 14 * k}" text-anchor="end" fill="{col}">{label}</text>')
    for k, (label, i_ka) in enumerate((marks_ka or {}).items()):
        xi = x(i_ka * 1000.0)
        parts.append(f'<line x1="{xi:.1f}" y1="{mt}" x2="{xi:.1f}" y2="{h - mb}" stroke="#111827" '
                     'stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{xi + 3:.1f}" y="{h - mb - 6 - 13 * k}">{label}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
