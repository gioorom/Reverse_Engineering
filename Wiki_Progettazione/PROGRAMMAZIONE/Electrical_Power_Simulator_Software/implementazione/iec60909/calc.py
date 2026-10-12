"""Calcolo delle correnti di cortocircuito secondo IEC 60909-0:2016.

Metodo del generatore equivalente di tensione c·Un/√3 nel punto di guasto,
applicato con il metodo nodale (matrice delle impedenze nodali) alle reti di
sequenza diretta, inversa e omopolare. I calcoli interni sono in per unità con
potenza di base S_BASE e tensione di base pari alla tensione nominale Un di
ciascun nodo.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import factors
from .network import Network, Transformer, Transformer3W

S_BASE_MVA = 100.0
_A = cmath.exp(2j * math.pi / 3)


@dataclass
class BusResult:
    bus: str
    un_kv: float
    c: float
    z1_ohm: complex
    z2_ohm: complex
    z0_ohm: Optional[complex]
    ikss3_ka: float
    skss3_mva: float
    ikss2_ka: float
    ikss1_ka: float
    ikss2e_earth_ka: float
    ikss2e_l2_ka: float
    ikss2e_l3_ka: float
    kappa: float
    ip3_ka: float
    ip2_ka: float
    ip1_ka: float
    ib_ka: float
    ik_ka: Optional[float]
    ith_ka: float

    @property
    def r_over_x(self) -> float:
        return self.z1_ohm.real / self.z1_ohm.imag


@dataclass
class StudyResult:
    network: str
    case: str
    kappa_method: str
    tk_s: float
    buses: list[BusResult]
    warnings: list[str] = field(default_factory=list)

    def bus(self, bus_id: str) -> BusResult:
        for b in self.buses:
            if b.bus == bus_id:
                return b
        raise KeyError(bus_id)


def _parse_vector_group(group: str) -> tuple[str, str]:
    g = group.strip().rstrip("0123456789")
    upper = g.upper()
    for hv in ("YN", "Y", "D", "Z"):
        if upper.startswith(hv):
            lv = upper[len(hv):]
            if lv in ("YN", "Y", "D", "ZN", "Z"):
                return hv, lv
    raise ValueError(f"gruppo vettoriale non riconosciuto: {group!r}")


def _parse_vector_group_3w(group: str) -> tuple[str, str, str]:
    tokens = re.findall(r"(YN|ZN|Y|D|Z)\d*", group.strip(), flags=re.IGNORECASE)
    if len(tokens) != 3 or not re.fullmatch(r"((YN|ZN|Y|D|Z)\d*){3}", group.strip(), re.IGNORECASE):
        raise ValueError(f"gruppo vettoriale a tre avvolgimenti non riconosciuto: {group!r}")
    return tuple(t.upper() for t in tokens)  # type: ignore[return-value]


def _star_node(t: Transformer3W) -> str:
    return f"{t.id}::stella"


class _Builder:
    """Costruisce le matrici delle ammettenze nodali di una sequenza."""

    def __init__(self, net: Network, case: str, warnings: list[str]):
        self.net = net
        self.case = case
        self.warnings = warnings
        self.idx = net.bus_index()
        self.un = {b.id: b.un_kv for b in net.buses}
        # Nodo interno (centro stella) di ogni trasformatore a tre avvolgimenti,
        # con tensione di base pari alla tensione nominale dell'avvolgimento AT.
        for t in net.transformers3w:
            self.idx[_star_node(t)] = len(self.idx)
            self.un[_star_node(t)] = t.ur_hv_kv

    def zbase(self, bus_id: str) -> float:
        return self.un[bus_id] ** 2 / S_BASE_MVA

    def c_max(self, bus_id: str) -> float:
        return factors.voltage_factor(self.un[bus_id], "max", self.net.lv_tolerance_percent)

    def c_case(self, bus_id: str) -> float:
        return factors.voltage_factor(self.un[bus_id], self.case, self.net.lv_tolerance_percent)

    # --- elementi ------------------------------------------------------------

    def _transformer_data(self, t: Transformer) -> tuple[complex, complex, float]:
        """Impedenze di sequenza diretta e omopolare (p.u. lato BT) e rapporto fuori nominale."""
        zr = t.ur_lv_kv**2 / t.sr_mva
        zk = t.ukr_percent / 100.0 * zr
        rk = t.urr_percent / 100.0 * zr
        xk = math.sqrt(zk**2 - rk**2)
        kt = 1.0
        if self.case == "max":
            x_t = math.sqrt(t.ukr_percent**2 - t.urr_percent**2) / 100.0
            kt = factors.transformer_kt(self.c_max(t.lv_bus), x_t)
        z1 = kt * complex(rk, xk) / self.zbase(t.lv_bus)
        uk0 = t.uk0_percent if t.uk0_percent is not None else t.ukr_percent
        ur0 = t.ur0_percent if t.ur0_percent is not None else t.urr_percent
        z0k = uk0 / 100.0 * zr
        r0k = ur0 / 100.0 * zr
        z0 = kt * complex(r0k, math.sqrt(z0k**2 - r0k**2)) / self.zbase(t.lv_bus)
        ratio = (t.ur_hv_kv / t.ur_lv_kv) / (self.un[t.hv_bus] / self.un[t.lv_bus])
        return z1, z0, ratio

    def _transformer3w_star(self, t: Transformer3W, zero: bool) -> dict[str, complex]:
        """Impedenze degli avvolgimenti dello schema a stella, in Ω riferiti al lato AT.

        Le impedenze di coppia Z_AB, Z_AC, Z_BC sono corrette con K_TAB, K_TAC,
        K_TBC (solo correnti massime) e poi trasformate nello schema a stella.
        """
        pairs = {"hv_mv": t.mv_bus, "hv_lv": t.lv_bus, "mv_lv": t.lv_bus}
        z_pair = {}
        for pair, lower_bus in pairs.items():
            sr = getattr(t, f"sr_{pair}_mva")
            uk = getattr(t, f"ukr_{pair}_percent")
            ur = getattr(t, f"urr_{pair}_percent")
            kt = 1.0
            if self.case == "max":
                kt = factors.transformer_kt(self.c_max(lower_bus), math.sqrt(uk**2 - ur**2) / 100.0)
            if zero:
                uk0 = getattr(t, f"uk0_{pair}_percent")
                ur0 = getattr(t, f"ur0_{pair}_percent")
                uk = uk0 if uk0 is not None else uk
                ur = ur0 if ur0 is not None else ur
            zr = t.ur_hv_kv**2 / sr
            z_pair[pair] = kt * complex(ur / 100.0 * zr, math.sqrt(uk**2 - ur**2) / 100.0 * zr)
        hm, hl, ml = z_pair["hv_mv"], z_pair["hv_lv"], z_pair["mv_lv"]
        return {
            "hv": 0.5 * (hm + hl - ml),
            "mv": 0.5 * (hm + ml - hl),
            "lv": 0.5 * (hl + ml - hm),
        }

    def build(
        self, seq: int, x_scale: float = 1.0, motors: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """Matrice Y in p.u. e nodi con collegamento verso terra (elementi in derivazione).

        ``x_scale`` scala le reattanze (metodo C, fc/f).
        """
        n = len(self.idx)
        y = np.zeros((n, n), dtype=complex)
        grounded = np.zeros(n, dtype=bool)

        def scale(z: complex) -> complex:
            return complex(z.real, z.imag * x_scale)

        def shunt(bus: str, z: complex) -> None:
            y[self.idx[bus], self.idx[bus]] += 1.0 / scale(z)
            grounded[self.idx[bus]] = True

        def branch(i_bus: str, j_bus: str, z: complex, ratio: float = 1.0) -> None:
            yy = 1.0 / scale(z)
            i, j = self.idx[i_bus], self.idx[j_bus]
            y[i, i] += yy / ratio**2
            y[j, j] += yy
            y[i, j] -= yy / ratio
            y[j, i] -= yy / ratio

        for g in self.net.external_grids:
            if self.case == "max":
                skq, rx = g.skq_max_mva, g.rx_max
            else:
                skq = g.skq_min_mva if g.skq_min_mva is not None else g.skq_max_mva
                rx = g.rx_min if g.rx_min is not None else g.rx_max
            zq = self.c_case(g.bus) * S_BASE_MVA / skq
            xq = zq / math.sqrt(1.0 + rx**2)
            z1 = complex(rx * xq, xq)
            if seq in (1, 2):
                shunt(g.bus, z1)
            elif g.x0x1 is not None:
                x0 = g.x0x1 * xq
                r0x0 = g.r0x0 if g.r0x0 is not None else rx
                shunt(g.bus, complex(r0x0 * x0, x0))

        for t in self.net.transformers:
            z1, z0, ratio = self._transformer_data(t)
            if seq in (1, 2):
                branch(t.hv_bus, t.lv_bus, z1 / t.parallel, ratio)
                continue
            hv, lv = _parse_vector_group(t.vector_group)
            zn_hv = 3.0 * complex(t.zn_hv_ohm) / self.zbase(t.hv_bus)
            zn_lv = 3.0 * complex(t.zn_lv_ohm) / self.zbase(t.lv_bus)
            if hv == "YN" and lv == "YN":
                branch(t.hv_bus, t.lv_bus, (z0 + zn_lv + zn_hv / ratio**2) / t.parallel, ratio)
            elif hv == "YN" and lv == "D":
                shunt(t.hv_bus, (z0 * ratio**2 + zn_hv) / t.parallel)
            elif hv == "D" and lv == "YN":
                shunt(t.lv_bus, (z0 + zn_lv) / t.parallel)
            # Altri gruppi (Yy, Yyn, YNy, Dd, Dy, Yd, ...): sequenza zero interrotta.

        for t in self.net.transformers3w:
            star = _star_node(t)
            windings = {"hv": t.hv_bus, "mv": t.mv_bus, "lv": t.lv_bus}
            z_star = self._transformer3w_star(t, zero=seq == 0)
            connections = dict(zip(windings, _parse_vector_group_3w(t.vector_group)))
            for w, bus in windings.items():
                ur_w = getattr(t, f"ur_{w}_kv")
                # impedenza dell'avvolgimento riportata al suo lato e rapporto fuori nominale
                z_w = z_star[w] * (ur_w / t.ur_hv_kv) ** 2 / self.zbase(bus)
                ratio = self.un[bus] / ur_w
                if seq in (1, 2):
                    branch(star, bus, z_w, ratio)
                elif connections[w] == "YN":
                    zn = 3.0 * complex(getattr(t, f"zn_{w}_ohm")) / self.zbase(bus)
                    branch(star, bus, z_w + zn, ratio)
                elif connections[w] == "D":
                    # il triangolo chiude la corrente omopolare: derivazione dal centro stella
                    shunt(star, z_star[w] / self.zbase(star))
                # Y o Z senza neutro: avvolgimento aperto in sequenza zero

        for ln in self.net.lines:
            k_theta = 1.0
            if self.case == "min":
                k_theta = 1.0 + 0.004 * (ln.end_temperature_c - 20.0)
            if seq in (1, 2):
                r, x = ln.r1_ohm_per_km, ln.x1_ohm_per_km
            else:
                if ln.r0_ohm_per_km is None or ln.x0_ohm_per_km is None:
                    msg = f"{ln.id}: dati di sequenza zero mancanti, linea aperta in sequenza zero"
                    if msg not in self.warnings:
                        self.warnings.append(msg)
                    continue
                r, x = ln.r0_ohm_per_km, ln.x0_ohm_per_km
            z = complex(r * k_theta, x) * ln.length_km / ln.parallel
            branch(ln.from_bus, ln.to_bus, z / self.zbase(ln.from_bus))

        if seq in (1, 2):
            for g in self.net.generators:
                xd = g.xd2_percent / 100.0 * g.ur_kv**2 / g.sr_mva
                rg = g.rg_ohm if g.rg_ohm is not None else factors.generator_rx(g.ur_kv, g.sr_mva) * xd
                kg = factors.generator_kg(
                    self.un[g.bus], g.ur_kv, self.c_max(g.bus), g.xd2_percent / 100.0, g.cos_phi
                )
                shunt(g.bus, kg * complex(rg, xd) / self.zbase(g.bus))
            if motors and self.case == "max":
                for m in self.net.motors:
                    srm = m.pr_mw / (m.efficiency * m.cos_phi)
                    zm = m.ur_kv**2 / (m.ilr_ir * srm) / m.count
                    rx = m.rx if m.rx is not None else factors.motor_rx(m.ur_kv, m.pr_mw, m.pole_pairs)
                    xm = zm / math.sqrt(1.0 + rx**2)
                    shunt(m.bus, complex(rx * xm, xm) / self.zbase(m.bus))
        return y, grounded


def _diag_z(system: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Impedenze nodali Z_ii; infinite per le parti di rete senza collegamento verso terra."""
    y, grounded = system
    n = y.shape[0]
    z = np.full(n, complex(math.inf, math.inf))
    seen = np.zeros(n, dtype=bool)
    for start in range(n):
        if seen[start]:
            continue
        component, stack = [], [start]
        seen[start] = True
        while stack:
            i = stack.pop()
            component.append(i)
            for j in np.nonzero(y[i])[0]:
                if not seen[j]:
                    seen[j] = True
                    stack.append(j)
        if grounded[component].any():
            sub = np.ix_(component, component)
            z[component] = np.diag(np.linalg.inv(y[sub]))
    return z


def calculate(
    net: Network,
    case: str = "max",
    kappa_method: str = "C",
    tk_s: float = 1.0,
) -> StudyResult:
    """Calcola le correnti di cortocircuito in tutti i nodi della rete.

    case: "max" (correnti massime) o "min" (correnti minime: cmin, niente
    motori, niente K_T, resistenze delle linee alla temperatura di fine guasto).
    kappa_method: "B" (impedenza nel punto di guasto, fattore 1,15) o "C"
    (frequenza equivalente fc = 20 Hz a 50 Hz, 24 Hz a 60 Hz).
    tk_s: durata del cortocircuito per la corrente termica equivalente Ith.
    """
    net.validate()
    kappa_method = kappa_method.upper()
    if kappa_method not in ("B", "C"):
        raise ValueError("kappa_method deve essere 'B' o 'C'")
    warnings: list[str] = []
    b = _Builder(net, case, warnings)

    z1 = _diag_z(b.build(1))
    isolated = [net.buses[i].id for i in np.nonzero(~np.isfinite(z1[: len(net.buses)]))[0]]
    if isolated:
        raise ValueError(f"nodi non collegati ad alcuna sorgente: {isolated}")
    z2 = _diag_z(b.build(2))
    z0 = _diag_z(b.build(0))
    if kappa_method == "C":
        fc = 20.0 if net.f_hz == 50.0 else 24.0
        zc = _diag_z(b.build(1, x_scale=fc / net.f_hz))
        rx_c = zc.real / zc.imag * fc / net.f_hz
    # Corrente permanente Ik: senza contributo dei motori; calcolata solo per reti
    # "lontane dai generatori" (nessun generatore sincrono).
    z1_steady = _diag_z(b.build(1, motors=False)) if not net.generators else None
    if net.generators:
        warnings.append("rete con generatori: Ik permanente non calcolata (serve il metodo λ)")
    if net.motors or net.generators:
        warnings.append("Ib calcolata come Ib = I\"k (stima cautelativa, μ = q = 1)")

    results = []
    for i, bus in enumerate(net.buses):
        c = b.c_case(bus.id)
        zb = b.zbase(bus.id)
        ibase = S_BASE_MVA / (math.sqrt(3.0) * bus.un_kv)
        z1i, z2i, z0i = z1[i], z2[i], z0[i]
        zero_open = not cmath.isfinite(z0i)

        ik3 = c / abs(z1i) * ibase
        ik2 = math.sqrt(3.0) * c / abs(z1i + z2i) * ibase
        if zero_open:
            ik1 = ike = ikl2 = ikl3 = 0.0
        else:
            ik1 = 3.0 * c / abs(z1i + z2i + z0i) * ibase
            den = z1i * z2i + z1i * z0i + z2i * z0i
            ike = 3.0 * c * abs(z2i) / abs(den) * ibase
            i1 = c / (z1i + z2i * z0i / (z2i + z0i))
            i2 = -i1 * z0i / (z2i + z0i)
            i0 = -i1 * z2i / (z2i + z0i)
            ikl2 = abs(i0 + _A**2 * i1 + _A * i2) * ibase
            ikl3 = abs(i0 + _A * i1 + _A**2 * i2) * ibase

        if kappa_method == "C":
            k = factors.kappa(rx_c[i])
        else:
            k_limit = 1.8 if bus.un_kv <= factors.LV_LIMIT_KV else 2.0
            k = min(1.15 * factors.kappa(z1i.real / z1i.imag), k_limit)
        ip3 = k * math.sqrt(2.0) * ik3
        m = factors.thermal_m(k, net.f_hz, tk_s)
        ith = ik3 * math.sqrt(m + 1.0)
        ik = None
        if z1_steady is not None:
            ik = c / abs(z1_steady[i]) * ibase

        results.append(
            BusResult(
                bus=bus.id,
                un_kv=bus.un_kv,
                c=c,
                z1_ohm=z1i * zb,
                z2_ohm=z2i * zb,
                z0_ohm=None if zero_open else z0i * zb,
                ikss3_ka=ik3,
                skss3_mva=math.sqrt(3.0) * bus.un_kv * ik3,
                ikss2_ka=ik2,
                ikss1_ka=ik1,
                ikss2e_earth_ka=ike,
                ikss2e_l2_ka=ikl2,
                ikss2e_l3_ka=ikl3,
                kappa=k,
                ip3_ka=ip3,
                ip2_ka=k * math.sqrt(2.0) * ik2,
                ip1_ka=k * math.sqrt(2.0) * ik1,
                ib_ka=ik3,
                ik_ka=ik,
                ith_ka=ith,
            )
        )
    return StudyResult(net.name, case, kappa_method, tk_s, results, warnings)
