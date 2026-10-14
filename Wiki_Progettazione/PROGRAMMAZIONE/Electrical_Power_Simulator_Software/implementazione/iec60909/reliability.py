"""Affidabilità delle reti di distribuzione: analisi dei modi di guasto (FMEA).

Per ogni guasto permanente di un elemento (ramo, nodo, sorgente) si segue la
sequenza di esercizio:

1. **intervento delle protezioni:** aprono gli interruttori e i fusibili che
   delimitano la zona del guasto (ricerca dal guasto che si ferma agli estremi
   dotati di interruttore o fusibile); i carichi non più collegati a una
   sorgente sono interrotti;
2. **sezionamento:** la parte guasta viene separata con gli organi di manovra
   più vicini (ricerca che si ferma a qualunque organo) e il resto della zona
   è rialimentato dopo il tempo di manovra;
3. **contro-alimentazione:** si chiudono i punti normalmente aperti, in ordine
   di tempo di manovra; i carichi rialimentati lo sono dopo quel tempo;
4. i carichi rimasti all'interno della parte guasta aspettano la riparazione.

La durata dell'interruzione è il minimo tra il tempo della fase che rialimenta
il carico e il tempo di riparazione. I guasti transitori (eliminati dalla
richiusura) danno interruzioni momentanee ai carichi della zona della fase 1.
Le sovrapposizioni di due guasti (insiemi di taglio del secondo ordine) danno
λ = λ1·λ2·(r1 + r2)/8760 e r = r1·r2/(r1 + r2) ai carichi che restano
alimentati con uno solo dei due elementi fuori servizio.

Verifica facoltativa della contro-alimentazione (check_transfer): ogni
configurazione di emergenza (elementi guasti tolti, punti normalmente aperti
chiusi fino a quel tempo di manovra) è risolta con il flusso di potenza; se una
linea o un trasformatore supera il carico ammesso o una tensione scende sotto
v_min_pu la manovra non è accettata e i carichi che ne dipendono aspettano la
fase successiva o la riparazione.

Indici IEEE 1366: SAIFI, SAIDI, CAIDI, ASAI, MAIFI; energia non fornita ENS e
AENS; costo delle interruzioni facoltativo.
"""

from __future__ import annotations

import copy
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .network import Network, ReliabilityData

HOURS_PER_YEAR = 8760.0

_CATEGORIES = {
    "@lines": "lines",
    "@transformers": "transformers",
    "@transformers3w": "transformers3w",
    "@buses": "buses",
    "@external_grids": "external_grids",
    "@generators": "generators",
}

RESTORATION = {
    "repair": "riparazione",
    "isolation": "sezionamento",
    "transfer": "contro-alimentazione",
    "overlap": "sovrapposizione",
    "momentary": "momentanea",
}


@dataclass
class _Device:
    id: str
    kind: str  # "switch" | "breaker" | "fuse"
    normally_open: bool
    switching_time_h: float


@dataclass
class _Element:
    id: str
    category: str
    failure_rate: float
    repair_time_h: float
    temporary_rate: float


@dataclass
class Contribution:
    """Contributo di un evento (guasto di un elemento o di una coppia) a un carico."""

    element: str
    failure_rate: float  # [1/anno]
    duration_h: float
    restoration: str  # chiave di RESTORATION

    @property
    def unavailability_h(self) -> float:
        return self.failure_rate * self.duration_h


@dataclass
class LoadPointResult:
    id: str
    bus: str
    customers: int
    average_mw: float
    failure_rate: float = 0.0  # interruzioni sostenute [1/anno]
    unavailability_h: float = 0.0  # [h/anno]
    momentary_rate: float = 0.0  # interruzioni momentanee [1/anno]
    contributions: list[Contribution] = field(default_factory=list)

    @property
    def duration_h(self) -> float:
        """Durata media di un'interruzione r = U/λ [h]."""
        return self.unavailability_h / self.failure_rate if self.failure_rate > 0 else 0.0

    @property
    def ens_mwh(self) -> float:
        return self.average_mw * self.unavailability_h


@dataclass
class ElementSummary:
    """Effetto complessivo dei guasti di un elemento sui carichi."""

    element: str
    failure_rate: float
    repair_time_h: float
    customer_interruptions: float = 0.0  # [clienti·interruzioni/anno]
    customer_hours: float = 0.0  # [clienti·h/anno]
    ens_mwh: float = 0.0


@dataclass
class ReliabilityResult:
    name: str
    load_points: list[LoadPointResult]
    elements: list[ElementSummary]
    customers: int
    saifi: float
    saidi: float
    caidi: float
    asai: float
    maifi: float
    ens_mwh: float
    aens_kwh: float
    cost: Optional[float] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def asui(self) -> float:
        return 1.0 - self.asai


class _Topology:
    """Grafo bipartito nodi–rami (con le sorgenti) e organi di manovra agli estremi."""

    def __init__(self, net: Network, generators_as_sources: bool, default_switching_time_h: float):
        net.validate()
        self.generators_as_sources = generators_as_sources
        self.buses = [b.id for b in net.buses]
        self.branches: dict[str, list[str]] = {}
        self.category: dict[str, str] = {b: "buses" for b in self.buses}
        self.length_km: dict[str, float] = {}
        for ln in net.lines:
            self.branches[ln.id] = [ln.from_bus, ln.to_bus]
            self.category[ln.id] = "lines"
            self.length_km[ln.id] = ln.length_km
        for t in net.transformers:
            self.branches[t.id] = [t.hv_bus, t.lv_bus]
            self.category[t.id] = "transformers"
        for t in net.transformers3w:
            self.branches[t.id] = [t.hv_bus, t.mv_bus, t.lv_bus]
            self.category[t.id] = "transformers3w"
        self.sources: dict[str, str] = {}
        for g in net.external_grids:
            self.sources[g.id] = g.bus
            self.category[g.id] = "external_grids"
        # generatori esclusi dalle sorgenti: i loro guasti non hanno effetto
        self.ignored: set[str] = set()
        for g in net.generators:
            self.category[g.id] = "generators"
            if generators_as_sources:
                self.sources[g.id] = g.bus
            else:
                self.ignored.add(g.id)
        ids = list(self.buses) + list(self.branches) + list(self.sources)
        if len(set(ids)) != len(ids):
            raise ValueError("affidabilità: identificativi duplicati tra nodi, rami e sorgenti")

        self.devices: dict[tuple[str, str], list[_Device]] = {}
        for sw in net.switches:
            self._add_device(sw.branch, sw.bus, _Device(
                sw.id, sw.kind, sw.normally_open, sw.switching_time_h))
        earthing = {et.id for et in net.earthing_transformers}
        for pd in net.protective_devices:
            branch = pd.branch.split(":")[0]  # "<id>:hv|mv|lv" dei trasformatori a tre avvolgimenti
            if branch in earthing:  # protezione del trasformatore di messa a terra: non separa la rete
                continue
            kind = "fuse" if pd.kind == "fuse" else "breaker"
            self._add_device(branch, pd.bus, _Device(pd.id, kind, False, default_switching_time_h))

        # stato normale degli estremi: aperto se c'è un punto normalmente aperto
        self.normally_open = {end for end, devs in self.devices.items() if any(d.normally_open for d in devs)}
        # adiacenze
        self.bus_branches: dict[str, list[str]] = {b: [] for b in self.buses}
        for br, ends in self.branches.items():
            for b in ends:
                self.bus_branches[b].append(br)
        self.bus_sources: dict[str, list[str]] = {b: [] for b in self.buses}
        for s, b in self.sources.items():
            self.bus_sources[b].append(s)

    def _add_device(self, branch: str, bus: str, dev: _Device) -> None:
        if branch not in self.branches:
            raise ValueError(f"{dev.id}: ramo inesistente {branch!r}")
        if bus not in self.branches[branch]:
            raise ValueError(f"{dev.id}: il nodo {bus!r} non è un estremo del ramo {branch!r}")
        if dev.kind not in ("switch", "breaker", "fuse"):
            raise ValueError(f"{dev.id}: tipo di organo di manovra non valido {dev.kind!r} "
                             "(switch, breaker, fuse)")
        if dev.switching_time_h < 0:
            raise ValueError(f"{dev.id}: switching_time_h deve essere >= 0")
        self.devices.setdefault((branch, bus), []).append(dev)

    # --- ricerche sul grafo -------------------------------------------------------------

    def supplied_buses(self, removed: set[str], closed_extra: frozenset = frozenset()) -> set[str]:
        """Nodi collegati a una sorgente in servizio, senza gli elementi `removed`;
        gli estremi normalmente aperti sono chiusi solo se in `closed_extra`."""
        seen: set[str] = set()
        queue = deque(b for s, b in self.sources.items() if s not in removed and b not in removed)
        seen.update(queue)
        visited_branches: set[str] = set()
        while queue:
            b = queue.popleft()
            for br in self.bus_branches[b]:
                if br in removed or br in visited_branches:
                    continue
                if (br, b) in self.normally_open and (br, b) not in closed_extra:
                    continue
                visited_branches.add(br)
                for other in self.branches[br]:
                    if other in seen or other in removed:
                        continue
                    if (br, other) in self.normally_open and (br, other) not in closed_extra:
                        continue
                    seen.add(other)
                    queue.append(other)
        return seen

    def outer_supplied(self, end: tuple[str, str], zone: set[str], supplied: set[str]) -> bool:
        """Il lato dell'estremo `end` esterno alla zona è alimentato?"""
        branch, bus = end
        if branch in zone:
            return bus in supplied
        return any(b in supplied for b in self.branches[branch] if (branch, b) not in self.normally_open)

    def zone(self, element: str, stop: tuple[str, ...]) -> tuple[set[str], set[tuple[str, str]]]:
        """Elementi raggiunti dal guasto di `element` attraverso gli estremi chiusi,
        fermandosi agli estremi con un organo di tipo `stop`; restituisce anche gli
        estremi di confine (dove l'organo apre)."""
        if element in self.sources:
            return {element}, set()
        region = {element}
        boundary: set[tuple[str, str]] = set()
        queue = deque([element])
        while queue:
            x = queue.popleft()
            if x in self.branches:
                ends = [(x, b) for b in self.branches[x]]
            else:
                ends = [(br, x) for br in self.bus_branches[x]]
                for s in self.bus_sources[x]:  # la sorgente sul nodo guasto è persa
                    region.add(s)
            for end in ends:
                if end in self.normally_open:
                    continue
                other = end[1] if x in self.branches else end[0]
                if other in region:
                    continue
                if any(d.kind in stop for d in self.devices.get(end, ())):
                    boundary.add(end)
                    continue
                region.add(other)
                queue.append(other)
        return region, boundary


# elenchi della rete che non partecipano al flusso di potenza
_STUDY_LISTS = ("arc_flash", "protective_devices", "stability_events", "harmonic_sources", "harmonic_filters",
                "motor_starts", "reliability_data", "switches", "cable_ratings", "cable_sizing")
# elementi collegati a un solo nodo
_SHUNT_LISTS = ("external_grids", "generators", "motors", "static_generators", "earthing_transformers",
                "loads", "shunts")


def _configuration(net: Network, topo: _Topology, removed: set[str], closed: frozenset,
                   supplied: set[str]) -> Network:
    """Copia della rete nella configurazione di emergenza: solo i nodi alimentati,
    senza gli elementi guasti e senza i rami con un estremo aperto."""
    cfg = copy.copy(net)
    for name in _STUDY_LISTS:
        setattr(cfg, name, [])

    def open_end(br: str) -> bool:
        return any((br, b) in topo.normally_open and (br, b) not in closed for b in topo.branches[br])

    def keep_branch(br: str) -> bool:
        return br not in removed and not open_end(br) and all(b in supplied for b in topo.branches[br])

    cfg.buses = [b for b in net.buses if b.id in supplied]
    cfg.lines = [x for x in net.lines if keep_branch(x.id)]
    cfg.transformers = [x for x in net.transformers if keep_branch(x.id)]
    cfg.transformers3w = [x for x in net.transformers3w if keep_branch(x.id)]
    for name in _SHUNT_LISTS:
        setattr(cfg, name, [x for x in getattr(net, name) if x.bus in supplied and x.id not in removed])
    if not topo.generators_as_sources:  # generatori esclusi: non alimentano le isole
        cfg.generators = []
    return cfg


def _violations(cfg: Network, v_min_pu: float, max_loading_percent: float,
                base: Optional[dict[str, float]] = None) -> dict[str, float]:
    """Limiti superati nella configurazione: tensioni [pu] dei nodi e carichi [%] dei
    rami (o il motivo per cui non è risolvibile, con valore nan). Con `base` (le
    violazioni dell'esercizio normale) restano solo quelle nuove o peggiorate di
    più di 0,005 pu o di 1 punto percentuale."""
    from .loadflow import run_load_flow

    try:
        lf = run_load_flow(cfg)
    except ValueError as exc:
        return {f"flusso di potenza non risolto ({exc})": math.nan}
    if not lf.converged:
        return {"flusso di potenza non convergente": math.nan}
    out = {b.bus: b.vm_pu for b in lf.buses if b.vm_pu < v_min_pu}
    out.update({br.id: br.loading_percent for br in lf.branches
                if br.loading_percent is not None and br.loading_percent > max_loading_percent})
    if base:
        buses = {b.id for b in cfg.buses}
        out = {k: v for k, v in out.items() if k not in base
               or (v < base[k] - 0.005 if k in buses else v > base[k] + 1.0)}
    return out


def _describe(violations: dict[str, float], buses: set[str], base: Optional[dict[str, float]] = None) -> str:
    """Elenco leggibile delle violazioni, con il valore dell'esercizio normale se già fuori limite."""
    def fmt(k: str, v: float) -> str:
        return f"{v:.3f} pu" if k in buses else f"{v:.1f} %"

    return ", ".join(k if math.isnan(v) else f"{k} {fmt(k, v)}"
                     + (f" (normale {fmt(k, base[k])})" if base and k in base else "")
                     for k, v in violations.items())


def _element_data(net: Network, topo: _Topology) -> dict[str, _Element]:
    defaults: dict[str, ReliabilityData] = {}
    specific: dict[str, ReliabilityData] = {}
    for rd in net.reliability_data:
        if rd.element in _CATEGORIES:
            target = defaults
            key = _CATEGORIES[rd.element]
        else:
            if rd.element not in topo.category:
                raise ValueError(f"reliability_data: elemento inesistente {rd.element!r}")
            target = specific
            key = rd.element
        if key in target:
            raise ValueError(f"reliability_data: dati ripetuti per {rd.element!r}")
        if rd.repair_time_h < 0 or (rd.failure_rate or 0) < 0 or (rd.failure_rate_per_km or 0) < 0 \
                or rd.temporary_rate < 0:
            raise ValueError(f"reliability_data {rd.element!r}: valori negativi")
        if rd.failure_rate is not None and rd.failure_rate_per_km is not None:
            raise ValueError(f"reliability_data {rd.element!r}: indicare failure_rate oppure failure_rate_per_km")
        target[key] = rd
    elements: dict[str, _Element] = {}
    for eid, cat in topo.category.items():
        rd = specific.get(eid) or defaults.get(cat)
        if rd is None or eid in topo.ignored:
            continue
        if rd.failure_rate_per_km is not None:
            if cat != "lines":
                raise ValueError(f"reliability_data {rd.element!r}: failure_rate_per_km vale solo per le linee")
            rate = rd.failure_rate_per_km * topo.length_km[eid]
        else:
            rate = rd.failure_rate or 0.0
        if rate == 0.0 and rd.temporary_rate == 0.0:
            continue
        elements[eid] = _Element(eid, cat, rate, rd.repair_time_h, rd.temporary_rate)
    return elements


def reliability_analysis(net: Network, second_order: bool = True, generators_as_sources: bool = True,
                         cost_per_kwh: Optional[float] = None,
                         default_switching_time_h: float = 1.0, check_transfer: bool = False,
                         v_min_pu: float = 0.9, max_loading_percent: float = 100.0) -> ReliabilityResult:
    """Indici di affidabilità dei carichi e del sistema (vedi il docstring del modulo).

    check_transfer: verifica con il flusso di potenza le configurazioni di
    contro-alimentazione (tensioni >= v_min_pu, carico dei rami con corrente o
    potenza nominale <= max_loading_percent)."""
    topo = _Topology(net, generators_as_sources, default_switching_time_h)
    elements = _element_data(net, topo)
    warnings: list[str] = []

    normal = topo.supplied_buses(set())
    points: list[LoadPointResult] = []
    for ld in net.loads:
        if ld.customers < 0:
            raise ValueError(f"{ld.id}: customers deve essere >= 0")
        avg = ld.average_mw if ld.average_mw is not None else ld.p_mw * ld.count
        if ld.bus not in normal:
            warnings.append(f"{ld.id}: il nodo {ld.bus} non è alimentato in esercizio normale (escluso)")
            continue
        points.append(LoadPointResult(ld.id, ld.bus, ld.customers, avg))

    summary = {e.id: ElementSummary(e.id, e.failure_rate, e.repair_time_h) for e in elements.values()}

    def add(p: LoadPointResult, c: Contribution) -> None:
        p.contributions.append(c)
        p.failure_rate += c.failure_rate
        p.unavailability_h += c.unavailability_h

    # tempi di manovra dei punti normalmente aperti (il più lungo per estremo)
    ties: dict[tuple[str, str], float] = {}
    for end in topo.normally_open:
        ties[end] = max(d.switching_time_h for d in topo.devices[end] if d.normally_open)
    tie_times = sorted(set(ties.values()))
    checked: dict[tuple[frozenset, frozenset], dict[str, float]] = {}
    base: dict[str, float] = {}

    def transfer_violations(removed: set[str], closed: frozenset, supplied: set[str]) -> dict[str, float]:
        key = (frozenset(removed), closed)
        if key not in checked:
            checked[key] = _violations(_configuration(net, topo, removed, closed, supplied),
                                       v_min_pu, max_loading_percent, base)
        return checked[key]

    if check_transfer:
        # limiti già superati in esercizio normale: contano solo se la manovra li peggiora
        base = _violations(_configuration(net, topo, set(), frozenset(), normal), v_min_pu, max_loading_percent)
        if base:
            warnings.append("esercizio normale già fuori dai limiti della verifica di contro-alimentazione "
                            "(contano solo i peggioramenti): " + _describe(base, normal))

    for e in elements.values():
        trip_zone, trip_boundary = topo.zone(e.id, ("breaker", "fuse"))
        after_trip = topo.supplied_buses(trip_zone)
        affected = [p for p in points if p.bus not in after_trip]
        if not affected:
            continue
        for p in affected:
            if e.temporary_rate > 0:
                p.momentary_rate += e.temporary_rate
        if e.failure_rate == 0.0:
            continue
        region, iso_boundary = topo.zone(e.id, ("breaker", "fuse", "switch"))
        # manovre: apertura degli organi che separano la parte guasta (i fusibili
        # agiscono da soli) e richiusura degli interruttori scattati, cioè quelli
        # al confine della zona con una sorgente dal lato esterno
        tripped = {end for end in trip_boundary if end not in iso_boundary
                   and topo.outer_supplied(end, trip_zone, after_trip)}
        t_iso = max((d.switching_time_h for end in iso_boundary | tripped for d in topo.devices[end]
                     if d.kind != "fuse"), default=0.0)
        after_iso = topo.supplied_buses(region)
        steps = []
        for t in tie_times:
            closed = frozenset(end for end, tt in ties.items() if tt <= t)
            buses = topo.supplied_buses(region, closed)
            if check_transfer and any(p.bus in buses and p.bus not in after_iso for p in affected):
                bad = transfer_violations(region, closed, buses)
                if bad:
                    warnings.append(f"guasto di {e.id}: contro-alimentazione a {max(t_iso, t):g} h "
                                    f"non accettata: " + _describe(bad, buses | normal, base))
                    continue
            steps.append((max(t_iso, t), buses))
        s = summary[e.id]
        for p in affected:
            if p.bus in after_iso:
                duration, how = t_iso, "isolation"
            else:
                duration, how = e.repair_time_h, "repair"
                for t, buses in steps:
                    if p.bus in buses:
                        duration, how = t, "transfer"
                        break
            if e.repair_time_h < duration:
                duration, how = e.repair_time_h, "repair"
            add(p, Contribution(e.id, e.failure_rate, duration, how))
            s.customer_interruptions += p.customers * e.failure_rate
            s.customer_hours += p.customers * e.failure_rate * duration
            s.ens_mwh += p.average_mw * e.failure_rate * duration

    if second_order:
        failing = [e for e in elements.values() if e.failure_rate > 0]
        lost_alone = {e.id: {p.id for p in points if p.bus not in topo.supplied_buses({e.id})} for e in failing}
        for i, e1 in enumerate(failing):
            for e2 in failing[i + 1:]:
                supplied = topo.supplied_buses({e1.id, e2.id})
                lost = [p for p in points if p.bus not in supplied
                        and p.id not in lost_alone[e1.id] and p.id not in lost_alone[e2.id]]
                if not lost:
                    continue
                r1, r2 = e1.repair_time_h, e2.repair_time_h
                rate = e1.failure_rate * e2.failure_rate * (r1 + r2) / HOURS_PER_YEAR
                duration = r1 * r2 / (r1 + r2) if r1 + r2 > 0 else 0.0
                key = f"{e1.id}+{e2.id}"
                for p in lost:
                    add(p, Contribution(key, rate, duration, "overlap"))
                    for e in (e1, e2):  # metà del contributo a ciascun elemento
                        summary[e.id].customer_interruptions += p.customers * rate / 2
                        summary[e.id].customer_hours += p.customers * rate * duration / 2
                        summary[e.id].ens_mwh += p.average_mw * rate * duration / 2

    n = sum(p.customers for p in points)
    if n == 0:
        raise ValueError("affidabilità: nessun cliente nei carichi alimentati")
    saifi = sum(p.customers * p.failure_rate for p in points) / n
    saidi = sum(p.customers * p.unavailability_h for p in points) / n
    maifi = sum(p.customers * p.momentary_rate for p in points) / n
    ens = sum(p.ens_mwh for p in points)
    return ReliabilityResult(
        name=net.name, load_points=points,
        elements=sorted(summary.values(), key=lambda s: -s.customer_hours),
        customers=n, saifi=saifi, saidi=saidi, caidi=saidi / saifi if saifi > 0 else 0.0,
        asai=1.0 - saidi / HOURS_PER_YEAR, maifi=maifi, ens_mwh=ens, aens_kwh=ens * 1000.0 / n,
        cost=None if cost_per_kwh is None else ens * 1000.0 * cost_per_kwh, warnings=warnings)


def result_to_markdown(r: ReliabilityResult, details: bool = False) -> str:
    out = [f"# Affidabilità — {r.name}", "",
           "| Indice | Valore |", "|---|---|",
           f"| Clienti | {r.customers} |",
           f"| SAIFI [interruzioni/cliente·anno] | {r.saifi:.4f} |",
           f"| SAIDI [h/cliente·anno] | {r.saidi:.4f} |",
           f"| CAIDI [h/interruzione] | {r.caidi:.3f} |",
           f"| ASAI | {r.asai:.6f} |",
           f"| MAIFI [interruzioni momentanee/cliente·anno] | {r.maifi:.4f} |",
           f"| ENS [MWh/anno] | {r.ens_mwh:.3f} |",
           f"| AENS [kWh/cliente·anno] | {r.aens_kwh:.3f} |"]
    if r.cost is not None:
        out.append(f"| Costo delle interruzioni [/anno] | {r.cost:.2f} |")
    out += ["", "## Carichi", "",
            "| Carico | Nodo | Clienti | λ [1/anno] | r [h] | U [h/anno] | ENS [MWh/anno] | Momentanee [1/anno] |",
            "|---|---|---|---|---|---|---|---|"]
    for p in r.load_points:
        out.append(f"| {p.id} | {p.bus} | {p.customers} | {p.failure_rate:.4f} | {p.duration_h:.3f} "
                   f"| {p.unavailability_h:.4f} | {p.ens_mwh:.4f} | {p.momentary_rate:.4f} |")
    out += ["", "## Contributo degli elementi", "",
            "| Elemento | λ [1/anno] | Riparazione [h] | Clienti interrotti [1/anno] | Clienti·ore [h/anno] "
            "| ENS [MWh/anno] |", "|---|---|---|---|---|---|"]
    for s in r.elements:
        if s.customer_interruptions == 0:
            continue
        out.append(f"| {s.element} | {s.failure_rate:.4f} | {s.repair_time_h:g} | {s.customer_interruptions:.4f} "
                   f"| {s.customer_hours:.4f} | {s.ens_mwh:.4f} |")
    if details:
        for p in r.load_points:
            out += ["", f"### {p.id}", "", "| Evento | λ [1/anno] | r [h] | U [h/anno] | Ripristino |",
                    "|---|---|---|---|---|"]
            for c in p.contributions:
                out.append(f"| {c.element} | {c.failure_rate:.5f} | {c.duration_h:.3f} "
                           f"| {c.unavailability_h:.5f} | {RESTORATION[c.restoration]} |")
    if r.warnings:
        out += ["", "## Avvisi", ""] + [f"- {w}" for w in r.warnings]
    return "\n".join(out) + "\n"


def result_to_dict(r: ReliabilityResult) -> dict:
    return {
        "name": r.name, "customers": r.customers, "saifi": r.saifi, "saidi": r.saidi, "caidi": r.caidi,
        "asai": r.asai, "asui": r.asui, "maifi": r.maifi, "ens_mwh": r.ens_mwh, "aens_kwh": r.aens_kwh,
        "cost": r.cost, "warnings": r.warnings,
        "load_points": [{
            "id": p.id, "bus": p.bus, "customers": p.customers, "average_mw": p.average_mw,
            "failure_rate": p.failure_rate, "duration_h": p.duration_h, "unavailability_h": p.unavailability_h,
            "ens_mwh": p.ens_mwh, "momentary_rate": p.momentary_rate,
            "contributions": [{"element": c.element, "failure_rate": c.failure_rate, "duration_h": c.duration_h,
                               "unavailability_h": c.unavailability_h, "restoration": c.restoration}
                              for c in p.contributions],
        } for p in r.load_points],
        "elements": [vars(s).copy() for s in r.elements],
    }
