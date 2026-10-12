"""Modello della rete: nodi ed elementi con i dati di targa."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class Network:
    name: str = "rete"
    f_hz: float = 50.0
    lv_tolerance_percent: int = 6
    buses: list[Bus] = field(default_factory=list)
    external_grids: list[ExternalGrid] = field(default_factory=list)
    transformers: list[Transformer] = field(default_factory=list)
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
