"""Modello della rete: nodi ed elementi con i dati di targa."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


def _check_zero_sequence(
    owner: str, uk0: Optional[float], ur0: Optional[float], uk: float, ur: float
) -> None:
    uk0 = uk if uk0 is None else uk0
    ur0 = ur if ur0 is None else ur0
    if ur0 >= uk0:
        raise ValueError(f"{owner}: ur0 deve essere minore di uk0")


def _check_zigzag_3w(t: "Transformer3W") -> None:
    """Ogni avvolgimento zig-zag con neutro richiede la sua impedenza omopolare."""
    import re

    tokens = re.findall(r"(YN|ZN|Y|D|Z)\d*", t.vector_group.strip(), flags=re.IGNORECASE)
    for winding, token in zip(("hv", "mv", "lv"), tokens):
        if token.upper() != "ZN":
            continue
        z0 = getattr(t, f"z0_zigzag_{winding}_ohm")
        if z0 is None:
            raise ValueError(
                f"{t.id}: l'avvolgimento {winding} è a zig-zag con neutro: serve "
                f"z0_zigzag_{winding}_ohm (impedenza omopolare propria [R, X] in Ω)"
            )
        if len(z0) != 2 or z0[0] < 0 or z0[1] <= 0:
            raise ValueError(f"{t.id}: z0_zigzag_{winding}_ohm deve essere [R >= 0, X > 0]")


@dataclass
class Bus:
    id: str
    un_kv: float


@dataclass
class ExternalGrid:
    """Rete di alimentazione equivalente (Q) definita dalla potenza di cortocircuito."""

    id: str
    bus: str
    skq_max_mva: float
    rx_max: float = 0.1
    skq_min_mva: Optional[float] = None
    rx_min: Optional[float] = None
    # Sequenza zero: X0/X1 e R0/X0. Se assenti la rete non offre percorso verso terra.
    x0x1: Optional[float] = None
    r0x0: Optional[float] = None
    # Flusso di potenza: nodo di saldo con tensione e angolo imposti
    vm_pu: float = 1.0
    va_degree: float = 0.0
    # Saldo distribuito (distributed_slack): peso nella ripartizione dello
    # sbilancio di potenza attiva
    slack_weight: float = 1.0


@dataclass
class Transformer:
    """Trasformatore a due avvolgimenti."""

    id: str
    hv_bus: str
    lv_bus: str
    sr_mva: float
    ur_hv_kv: float
    ur_lv_kv: float
    ukr_percent: float
    urr_percent: float
    vector_group: str = "Dyn"
    uk0_percent: Optional[float] = None
    ur0_percent: Optional[float] = None
    zn_hv_ohm: complex = 0.0
    zn_lv_ohm: complex = 0.0
    parallel: int = 1
    # Flusso di potenza: variatore (posizione rispetto alla presa centrale,
    # passo in % e lato) e magnetizzazione (corrente a vuoto e perdite nel ferro).
    # Il calcolo di cortocircuito usa sempre il rapporto nominale.
    tap_pos: int = 0
    tap_step_percent: float = 0.0
    tap_side: str = "hv"
    i0_percent: float = 0.0
    pfe_kw: float = 0.0
    # Flusso di potenza: variatore sotto carico. Prese ammesse tap_min…tap_max
    # (None: nessun limite); con control_bus il variatore regola la tensione di
    # quel nodo a control_vm_pu ± control_band_pu (semiampiezza della banda in
    # p.u.; None: 0,75 passi) muovendo la presa di un passo alla volta.
    tap_min: Optional[int] = None
    tap_max: Optional[int] = None
    control_bus: Optional[str] = None
    control_vm_pu: float = 1.0
    control_band_pu: Optional[float] = None


@dataclass
class Transformer3W:
    """Trasformatore a tre avvolgimenti (AT, MT, BT).

    Le tensioni di cortocircuito di ogni coppia di avvolgimenti sono riferite
    alla potenza nominale di quella coppia (sr_hv_mv_mva, sr_hv_lv_mva,
    sr_mv_lv_mva). Gruppo vettoriale con tre avvolgimenti, es. "YNynd5".
    """

    id: str
    hv_bus: str
    mv_bus: str
    lv_bus: str
    ur_hv_kv: float
    ur_mv_kv: float
    ur_lv_kv: float
    sr_hv_mv_mva: float
    sr_hv_lv_mva: float
    sr_mv_lv_mva: float
    ukr_hv_mv_percent: float
    ukr_hv_lv_percent: float
    ukr_mv_lv_percent: float
    urr_hv_mv_percent: float
    urr_hv_lv_percent: float
    urr_mv_lv_percent: float
    vector_group: str = "YNynd5"
    uk0_hv_mv_percent: Optional[float] = None
    uk0_hv_lv_percent: Optional[float] = None
    uk0_mv_lv_percent: Optional[float] = None
    ur0_hv_mv_percent: Optional[float] = None
    ur0_hv_lv_percent: Optional[float] = None
    ur0_mv_lv_percent: Optional[float] = None
    zn_hv_ohm: complex = 0.0
    zn_mv_ohm: complex = 0.0
    zn_lv_ohm: complex = 0.0
    # Avvolgimenti a zig-zag con neutro (ZN): impedenza omopolare propria
    # dell'avvolgimento in Ω per fase ([R, X], lato dell'avvolgimento), dalla
    # prova del costruttore tra neutro e fasi.
    z0_zigzag_hv_ohm: Optional[tuple[float, float]] = None
    z0_zigzag_mv_ohm: Optional[tuple[float, float]] = None
    z0_zigzag_lv_ohm: Optional[tuple[float, float]] = None
    # Flusso di potenza: variatore su un avvolgimento (tap_side "hv", "mv" o
    # "lv", ai morsetti dell'avvolgimento) e magnetizzazione (corrente a vuoto
    # riferita alla potenza dell'avvolgimento AT, cioè la maggiore delle potenze
    # di coppia che lo comprendono, e perdite nel ferro), posta sul ramo AT
    # della stella equivalente. Il cortocircuito usa sempre il rapporto nominale.
    tap_pos: int = 0
    tap_step_percent: float = 0.0
    tap_side: str = "hv"
    i0_percent: float = 0.0
    pfe_kw: float = 0.0


@dataclass
class Line:
    """Linea aerea o cavo."""

    id: str
    from_bus: str
    to_bus: str
    length_km: float
    r1_ohm_per_km: float
    x1_ohm_per_km: float
    r0_ohm_per_km: Optional[float] = None
    x0_ohm_per_km: Optional[float] = None
    end_temperature_c: float = 20.0
    parallel: int = 1
    # Flusso di potenza: capacità di esercizio e corrente ammissibile (per linea)
    c_nf_per_km: float = 0.0
    max_i_ka: Optional[float] = None


@dataclass
class Generator:
    """Generatore sincrono collegato direttamente a un nodo."""

    id: str
    bus: str
    sr_mva: float
    ur_kv: float
    xd2_percent: float
    cos_phi: float = 0.8
    rg_ohm: Optional[float] = None
    # reattanza di sequenza inversa in % (default: X"d)
    x2_percent: Optional[float] = None
    # Centro stella a terra: reattanza omopolare in % e impedenza di neutro.
    # Se x0_percent è assente il generatore non conduce corrente omopolare.
    x0_percent: Optional[float] = None
    zn_ohm: complex = 0.0
    # Corrente permanente (λ): reattanza sincrona satura in %, rapporto
    # Ufmax/Ufr dell'eccitazione (1,3 serie 1; 1,6 serie 2) oppure λ imposti
    # (es. letti dalle curve della norma).
    xd_sat_percent: Optional[float] = None
    ufmax_ratio: float = 1.3
    lambda_max: Optional[float] = None
    lambda_min: Optional[float] = None
    # Gruppo di generazione (power station unit): id del trasformatore elevatore
    # dedicato (lato BT sul nodo del generatore), presenza del variatore sotto
    # carico, campo di regolazione della tensione del generatore pG e presa
    # fissa permanente del trasformatore pT (solo senza variatore). I nodi
    # alimentati dal nodo del generatore senza passare per il trasformatore del
    # gruppo (servizi ausiliari) sono calcolati come interni al gruppo.
    unit_transformer: Optional[str] = None
    oltc: bool = True
    pg_percent: float = 0.0
    pt_percent: float = 0.0
    # Flusso di potenza: potenza attiva erogata e tensione regolata (nodo PV);
    # con vm_pu = None il generatore eroga la potenza reattiva q_mvar (nodo PQ).
    # Limiti di potenza reattiva facoltativi (usati con enforce_q_lims).
    p_mw: float = 0.0
    vm_pu: Optional[float] = 1.0
    q_mvar: float = 0.0
    q_min_mvar: Optional[float] = None
    q_max_mvar: Optional[float] = None
    # Regolazione remota: il generatore regola a vm_pu la tensione di questo
    # nodo invece della propria (None: regolazione locale).
    regulated_bus: Optional[str] = None
    # Saldo distribuito (distributed_slack): peso nella ripartizione dello
    # sbilancio di potenza attiva (0: potenza attiva fissa p_mw)
    slack_weight: float = 0.0
    # Stabilità transitoria (dati sulla potenza nominale Sr): costante di
    # inerzia H [s], smorzamento D [p.u. di potenza per p.u. di velocità],
    # reattanze transitoria X'd, sincrona Xd e in quadratura Xq [%], costante
    # di tempo transitoria a vuoto T'd0 [s]; modello "classical" (fem costante
    # dietro X'd) o "one_axis" (decadimento del flusso, E'q dinamica).
    # Regolatore di tensione del primo ordine (avr_ka, avr_ta_s, limiti di Efd)
    # e regolatore di velocità con statismo (gov_droop_pu, gov_tg_s, gov_pmax_pu).
    h_s: Optional[float] = None
    d_pu: float = 0.0
    xd1_percent: Optional[float] = None
    xd_percent: Optional[float] = None
    xq_percent: Optional[float] = None
    td01_s: Optional[float] = None
    dyn_model: str = "classical"
    avr_ka: Optional[float] = None
    avr_ta_s: float = 0.05
    efd_min_pu: float = 0.0
    efd_max_pu: float = 5.0
    gov_droop_pu: Optional[float] = None
    gov_tg_s: float = 0.5
    gov_pmax_pu: float = 1.1


@dataclass
class Motor:
    """Motore asincrono (o gruppo equivalente di motori)."""

    id: str
    bus: str
    pr_mw: float
    ur_kv: float
    efficiency: float
    cos_phi: float
    ilr_ir: float
    pole_pairs: Optional[int] = None
    rx: Optional[float] = None
    count: int = 1
    # sequenza inversa da dati di targa: X2 in % su Sr = Pr/(η·cosφ) e R2/X2
    # (default: Z(2) = Z(1))
    x2_percent: Optional[float] = None
    rx2: Optional[float] = None
    # Flusso di potenza: carico a potenza costante P = loading·Pr/η, Q = P·tanφ
    loading: float = 1.0


@dataclass
class Load:
    """Carico (solo flusso di potenza), a potenza costante o dipendente dalla tensione.

    Modello ZIP separato per P e Q: P(V) = P·(z·V² + i·V + (1 − z − i)) con
    z = const_z_p_percent/100 e i = const_i_p_percent/100 (V in p.u. della
    tensione nominale del nodo); analogo per Q. Default: potenza costante.
    """

    id: str
    bus: str
    p_mw: float
    q_mvar: float = 0.0
    count: int = 1
    const_z_p_percent: float = 0.0
    const_i_p_percent: float = 0.0
    const_z_q_percent: float = 0.0
    const_i_q_percent: float = 0.0


@dataclass
class Shunt:
    """Derivazione a impedenza costante (reattori, condensatori di rifasamento).

    p_mw e q_mvar sono le potenze assorbite alla tensione nominale del nodo:
    q_mvar > 0 reattore (induttivo), q_mvar < 0 condensatori.
    """

    id: str
    bus: str
    q_mvar: float
    p_mw: float = 0.0


@dataclass
class StabilityEvent:
    """Evento della simulazione di stabilità transitoria.

    kind: "fault" (guasto trifase nel nodo `bus`, impedenza r_ohm + j·x_ohm),
    "clear_fault" (elimina il guasto nel nodo `bus`), "trip_branch" (apre il
    ramo `element`: linea, trasformatore o tre avvolgimenti), "trip_gen"
    (distacca il generatore `element`), "load" (moltiplica per `scale` i
    carichi a impedenza costante del nodo `bus`).
    """

    t_s: float
    kind: str
    bus: Optional[str] = None
    element: Optional[str] = None
    r_ohm: float = 0.0
    x_ohm: float = 0.0
    scale: float = 1.0


@dataclass
class ProtectiveDevice:
    """Dispositivo di protezione installato all'estremo `bus` del ramo `branch`.

    `protects`: "branch" (default: protegge il ramo, corrente dal nodo verso il
    ramo, es. partenza) oppure "bus" (protegge il nodo, corrente dal ramo verso
    il nodo, es. interruttore generale BT di arrivo dal trasformatore).
    Dati per tipo (`kind`): vedi `iec60909.coordination`.
    """

    id: str
    branch: str
    bus: str
    kind: str
    protects: str = "branch"
    cti_s: Optional[float] = None
    # relè (correnti primarie in A)
    curve: Optional[str] = None
    pickup_a: Optional[float] = None
    tms: float = 1.0
    stages: list = field(default_factory=list)
    breaker_time_s: float = 0.0
    # interruttore BT: In [A], Ir = ir·In, tr a 6·Ir, Isd = isd·Ir, Ii = ii·In
    in_a: Optional[float] = None
    ir: float = 1.0
    tr_s: Optional[float] = None
    isd: Optional[float] = None
    tsd_s: Optional[float] = None
    i2t_sd: bool = False
    ii: Optional[float] = None
    ti_s: float = 0.02
    # fusibile o curva per punti: [[I_A, t_s], …]
    points: list = field(default_factory=list)
    # grandezza misurata: "phase" (corrente di fase maggiore) o "residual"
    # (corrente residua 3·I0, protezione di terra)
    measure: str = "phase"
    # direzionale: interviene solo con corrente nel verso protetto; angolo
    # caratteristico dell'impedenza vista dietro il dispositivo (−ΔV/I)
    directional: bool = False
    characteristic_angle_deg: float = 45.0
    # bande di tolleranza: soglie di corrente ±%, tempi ±% (almeno ±time_tolerance_s)
    current_tolerance_percent: float = 0.0
    time_tolerance_percent: float = 0.0
    time_tolerance_s: float = 0.0
    # selettività energetica dichiarata dal costruttore con i dispositivi a
    # valle: {id del dispositivo a valle: Is [kA]}
    selectivity_limits: dict = field(default_factory=dict)


@dataclass
class ArcFlashPoint:
    """Punto di calcolo dell'arc flash (IEEE 1584-2018) su un nodo.

    `equipment_class` (facoltativa) fornisce i valori tipici delle tabelle 8 e
    10 della norma; i campi indicati esplicitamente li sostituiscono.
    `protection`: {"time_ms": …} oppure relè IEC 60255-151 {"curve": "SI"|"VI"|
    "EI"|"LTI", "pickup_ka", "tms", "inst_pickup_ka", "inst_time_ms",
    "breaker_time_ms", "max_time_ms"} oppure {"device": id} (dispositivo della
    sezione protective_devices).

    Corrente franca (c.a.): `ibf_ka` impone il valore invece della I"k IEC
    60909; `motor_decay_ms` (contributo dei motori che si esaurisce dopo quel
    tempo) oppure `steps` ([{"ibf_ka", "duration_ms", "current_ratio"}, …])
    attivano il calcolo a più intervalli.
    Corrente continua (`system: "dc"`, nodo facoltativo): tensione `vdc_v`,
    corrente franca `ibf_ka` oppure resistenza del sistema `r_system_ohm`,
    metodo `dc_method` ("doan" o "stokes") e fattore per l'arco in involucro
    `dc_enclosure_factor` (default 3 in cella, 1 per VOA/HOA).
    """

    id: str
    bus: str = ""
    configuration: str = "VCB"
    equipment_class: Optional[str] = None
    gap_mm: Optional[float] = None
    distance_mm: Optional[float] = None
    height_mm: Optional[float] = None
    width_mm: Optional[float] = None
    depth_mm: Optional[float] = None
    protection: dict = field(default_factory=dict)
    system: str = "ac"
    ibf_ka: Optional[float] = None
    motor_decay_ms: Optional[float] = None
    steps: list = field(default_factory=list)
    vdc_v: Optional[float] = None
    r_system_ohm: Optional[float] = None
    dc_method: str = "doan"
    dc_enclosure_factor: Optional[float] = None


@dataclass
class EarthingTransformer:
    """Trasformatore di messa a terra (es. zig-zag) collegato a un nodo.

    Interviene solo in sequenza zero: derivazione verso terra di impedenza
    omopolare per fase `z0_ohm` ([R, X] in Ω) più 3·`zn_ohm` (impedenza di neutro).
    """

    id: str
    bus: str
    z0_ohm: tuple[float, float]
    zn_ohm: complex = 0.0


@dataclass
class StaticGenerator:
    """Generatore statico (IEC 60909-0, 6.9).

    kind = "PF": unità con convertitore pieno (fotovoltaico, eolico full
    converter, accumuli): sorgente di corrente di sequenza diretta con
    corrente iniziale massima `ikss_ka` (valore efficace, riferito alla
    tensione del nodo), indicata dal costruttore.
    kind = "WD": eolico con generatore asincrono a doppia alimentazione:
    impedenza Z_WD = √2·κ_WD·Ur/(√3·i_WDmax), con `kappa_wd` e `i_wd_max_ka`
    (valore istantaneo massimo) dati dal costruttore e rapporto R/X `rx`.
    """

    id: str
    bus: str
    kind: str = "PF"
    ikss_ka: Optional[float] = None
    kappa_wd: Optional[float] = None
    i_wd_max_ka: Optional[float] = None
    ur_kv: Optional[float] = None
    rx: float = 0.1
    count: int = 1
    # Flusso di potenza: potenza erogata (nodo PQ)
    p_mw: float = 0.0
    q_mvar: float = 0.0


@dataclass
class Network:
    name: str = "rete"
    f_hz: float = 50.0
    lv_tolerance_percent: int = 6
    buses: list[Bus] = field(default_factory=list)
    external_grids: list[ExternalGrid] = field(default_factory=list)
    transformers: list[Transformer] = field(default_factory=list)
    transformers3w: list[Transformer3W] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    generators: list[Generator] = field(default_factory=list)
    motors: list[Motor] = field(default_factory=list)
    static_generators: list[StaticGenerator] = field(default_factory=list)
    earthing_transformers: list[EarthingTransformer] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    shunts: list[Shunt] = field(default_factory=list)
    arc_flash: list[ArcFlashPoint] = field(default_factory=list)
    protective_devices: list[ProtectiveDevice] = field(default_factory=list)
    stability_events: list[StabilityEvent] = field(default_factory=list)

    def bus_index(self) -> dict[str, int]:
        index = {b.id: i for i, b in enumerate(self.buses)}
        if len(index) != len(self.buses):
            raise ValueError("identificativi dei nodi duplicati")
        return index

    def unit_region(self, g: Generator) -> tuple[list[str], bool]:
        """Nodi all'interno del gruppo di generazione di g.

        Sono il nodo del generatore e i nodi alimentati da esso senza passare
        per il trasformatore del gruppo (servizi ausiliari: trasformatori
        ausiliari e reti a valle). Restituisce anche se la regione contiene
        altre sorgenti (reti esterne, altri generatori, generatori statici).
        """
        adj: dict[str, set[str]] = {b.id: set() for b in self.buses}

        def link(a: str, b: str) -> None:
            adj[a].add(b)
            adj[b].add(a)

        for t in self.transformers:
            if t.id != g.unit_transformer:
                link(t.hv_bus, t.lv_bus)
        for t3 in self.transformers3w:
            link(t3.hv_bus, t3.mv_bus)
            link(t3.hv_bus, t3.lv_bus)
        for ln in self.lines:
            link(ln.from_bus, ln.to_bus)
        seen = {g.bus}
        stack = [g.bus]
        while stack:
            for nxt in adj[stack.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        other = (
            any(q.bus in seen for q in self.external_grids)
            or any(o.bus in seen for o in self.generators if o is not g)
            or any(sg.bus in seen for sg in self.static_generators)
        )
        return [b.id for b in self.buses if b.id in seen], other

    def validate(self) -> None:
        index = self.bus_index()

        def check(bus_id: str, owner: str) -> None:
            if bus_id not in index:
                raise ValueError(f"{owner}: nodo inesistente {bus_id!r}")

        for g in self.external_grids:
            check(g.bus, g.id)
        for t in self.transformers:
            check(t.hv_bus, t.id)
            check(t.lv_bus, t.id)
            if t.urr_percent >= t.ukr_percent:
                raise ValueError(f"{t.id}: urr deve essere minore di ukr")
            _check_zero_sequence(t.id, t.uk0_percent, t.ur0_percent, t.ukr_percent, t.urr_percent)
        for t in self.transformers3w:
            for bus in (t.hv_bus, t.mv_bus, t.lv_bus):
                check(bus, t.id)
            for pair in ("hv_mv", "hv_lv", "mv_lv"):
                if getattr(t, f"urr_{pair}_percent") >= getattr(t, f"ukr_{pair}_percent"):
                    raise ValueError(f"{t.id}: urr_{pair} deve essere minore di ukr_{pair}")
                _check_zero_sequence(
                    f"{t.id} ({pair})",
                    getattr(t, f"uk0_{pair}_percent"),
                    getattr(t, f"ur0_{pair}_percent"),
                    getattr(t, f"ukr_{pair}_percent"),
                    getattr(t, f"urr_{pair}_percent"),
                )
            _check_zigzag_3w(t)
        for ln in self.lines:
            check(ln.from_bus, ln.id)
            check(ln.to_bus, ln.id)
            un = {b.id: b.un_kv for b in self.buses}
            if abs(un[ln.from_bus] - un[ln.to_bus]) > 1e-9:
                raise ValueError(f"{ln.id}: collega nodi con tensioni nominali diverse")
        transformers = {t.id: t for t in self.transformers}
        units: set[str] = set()
        for g in self.generators:
            check(g.bus, g.id)
            if g.regulated_bus is not None:
                check(g.regulated_bus, g.id)
            if g.unit_transformer is None:
                continue
            t = transformers.get(g.unit_transformer)
            if t is None:
                raise ValueError(f"{g.id}: trasformatore del gruppo inesistente {g.unit_transformer!r}")
            if t.lv_bus != g.bus:
                raise ValueError(f"{g.id}: il lato BT di {t.id} deve essere sul nodo del generatore")
            if t.parallel != 1:
                raise ValueError(f"{t.id}: il trasformatore di un gruppo non può avere parallel > 1")
            if t.id in units:
                raise ValueError(f"{t.id}: trasformatore assegnato a più gruppi")
            units.add(t.id)
        for m in self.motors:
            check(m.bus, m.id)
        for ld in self.loads:
            check(ld.bus, ld.id)
            for q in ("p", "q"):
                z, i = getattr(ld, f"const_z_{q}_percent"), getattr(ld, f"const_i_{q}_percent")
                if z < 0 or i < 0 or z + i > 100.0 + 1e-9:
                    raise ValueError(f"{ld.id}: quote const_z_{q} e const_i_{q} non valide (somma <= 100)")
        for sh in self.shunts:
            check(sh.bus, sh.id)
        for af in self.arc_flash:
            if af.system != "dc" or af.bus:  # i punti in c.c. possono non avere un nodo
                check(af.bus, af.id)
        for pd in self.protective_devices:
            check(pd.bus, pd.id)
        for t in self.transformers:
            if t.tap_side not in ("hv", "lv"):
                raise ValueError(f"{t.id}: tap_side deve essere 'hv' o 'lv'")
            if t.pfe_kw / 1000.0 > t.i0_percent / 100.0 * t.sr_mva + 1e-12:
                raise ValueError(f"{t.id}: pfe_kw non compatibile con i0_percent")
            if t.tap_min is not None and t.tap_max is not None and t.tap_min > t.tap_max:
                raise ValueError(f"{t.id}: tap_min maggiore di tap_max")
            if t.control_bus is not None:
                check(t.control_bus, t.id)
                if t.tap_step_percent == 0:
                    raise ValueError(f"{t.id}: la regolazione della tensione richiede tap_step_percent")
                if t.control_band_pu is not None and t.control_band_pu <= 0:
                    raise ValueError(f"{t.id}: control_band_pu deve essere positiva")
        for t in self.transformers3w:
            if t.tap_side not in ("hv", "mv", "lv"):
                raise ValueError(f"{t.id}: tap_side deve essere 'hv', 'mv' o 'lv'")
            sr_hv = max(t.sr_hv_mv_mva, t.sr_hv_lv_mva)
            if t.pfe_kw / 1000.0 > t.i0_percent / 100.0 * sr_hv + 1e-12:
                raise ValueError(f"{t.id}: pfe_kw non compatibile con i0_percent")
        for et in self.earthing_transformers:
            check(et.bus, et.id)
            if len(et.z0_ohm) != 2 or et.z0_ohm[0] < 0 or et.z0_ohm[1] <= 0:
                raise ValueError(f"{et.id}: z0_ohm deve essere [R >= 0, X > 0]")
        for sg in self.static_generators:
            check(sg.bus, sg.id)
            if sg.kind == "PF":
                if sg.ikss_ka is None or sg.ikss_ka <= 0:
                    raise ValueError(f"{sg.id}: per un generatore PF serve ikss_ka > 0")
            elif sg.kind == "WD":
                if not (sg.kappa_wd and sg.i_wd_max_ka and sg.kappa_wd > 0 and sg.i_wd_max_ka > 0):
                    raise ValueError(f"{sg.id}: per un generatore WD servono kappa_wd e i_wd_max_ka")
            else:
                raise ValueError(f"{sg.id}: tipo di generatore statico non valido {sg.kind!r} (PF o WD)")
            if sg.count < 1:
                raise ValueError(f"{sg.id}: count deve essere almeno 1")
        if not (self.external_grids or self.generators
                or any(sg.kind == "WD" for sg in self.static_generators)):
            raise ValueError("la rete non ha sorgenti (reti esterne o generatori)")
        if self.f_hz not in (50.0, 60.0):
            raise ValueError("la frequenza deve essere 50 o 60 Hz")
