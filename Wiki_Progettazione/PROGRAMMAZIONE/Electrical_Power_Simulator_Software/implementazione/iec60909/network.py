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


def _reject_zigzag(owner: str, vector_group: str) -> None:
    if "Z" in vector_group.upper():
        raise ValueError(f"{owner}: avvolgimenti a zig-zag non ancora supportati ({vector_group})")


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

    def bus_index(self) -> dict[str, int]:
        index = {b.id: i for i, b in enumerate(self.buses)}
        if len(index) != len(self.buses):
            raise ValueError("identificativi dei nodi duplicati")
        return index

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
            _reject_zigzag(t.id, t.vector_group)
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
            _reject_zigzag(t.id, t.vector_group)
        for ln in self.lines:
            check(ln.from_bus, ln.id)
            check(ln.to_bus, ln.id)
            un = {b.id: b.un_kv for b in self.buses}
            if abs(un[ln.from_bus] - un[ln.to_bus]) > 1e-9:
                raise ValueError(f"{ln.id}: collega nodi con tensioni nominali diverse")
        for g in self.generators:
            check(g.bus, g.id)
        for m in self.motors:
            check(m.bus, m.id)
        if not (self.external_grids or self.generators):
            raise ValueError("la rete non ha sorgenti (reti esterne o generatori)")
        if self.f_hz not in (50.0, 60.0):
            raise ValueError("la frequenza deve essere 50 o 60 Hz")
