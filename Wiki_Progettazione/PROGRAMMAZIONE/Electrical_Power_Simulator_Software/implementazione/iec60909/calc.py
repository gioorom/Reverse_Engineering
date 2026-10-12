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
from .network import Generator, Motor, Network, StaticGenerator, Transformer, Transformer3W

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
    # componente continua all'istante tmin e corrente di interruzione asimmetrica
    idc_ka: float = 0.0
    ib_asym_ka: float = 0.0

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
    tmin_s: float = 0.1
    zf_ohm: complex = 0j

    def bus(self, bus_id: str) -> BusResult:
        for b in self.buses:
            if b.bus == bus_id:
                return b
        raise KeyError(bus_id)


def _parse_vector_group(group: str) -> tuple[str, str]:
    g = group.strip().rstrip("0123456789")
    upper = g.upper()
    for hv in ("YN", "ZN", "Y", "D", "Z"):
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

    def __init__(
        self, net: Network, case: str, warnings: list[str], inside_unit: Optional[str] = None
    ):
        self.net = net
        self.case = case
        self.warnings = warnings
        # generatore del gruppo nel cui interno (nodo del generatore) si calcola il guasto
        self.inside_unit = inside_unit
        self.idx = net.bus_index()
        self.un = {b.id: b.un_kv for b in net.buses}
        # Nodo interno (centro stella) di ogni trasformatore a tre avvolgimenti,
        # con tensione di base pari alla tensione nominale dell'avvolgimento AT.
        for t in net.transformers3w:
            self.idx[_star_node(t)] = len(self.idx)
            self.un[_star_node(t)] = t.ur_hv_kv
        # gruppi di generazione: fattore del trasformatore (per id trafo) e del
        # generatore (per id generatore)
        self.unit_k: dict[str, float] = {}
        self.unit_k_gen: dict[str, float] = {}
        transformers = {t.id: t for t in net.transformers}
        for g in net.generators:
            if g.unit_transformer is None:
                continue
            t = transformers[g.unit_transformer]
            k_out, k_g_in, k_t_in = factors.power_station_factors(
                un_q_kv=self.un[t.hv_bus],
                ur_g_kv=g.ur_kv,
                ur_t_hv_kv=t.ur_hv_kv,
                ur_t_lv_kv=t.ur_lv_kv,
                c_max_q=self.c_max(t.hv_bus),
                c_max_g=self.c_max(g.bus),
                xd2_pu=g.xd2_percent / 100.0,
                xt_pu=math.sqrt(t.ukr_percent**2 - t.urr_percent**2) / 100.0,
                cos_phi=g.cos_phi,
                oltc=g.oltc,
                pg=g.pg_percent / 100.0,
                pt=g.pt_percent / 100.0,
            )
            inside = g.id == inside_unit
            self.unit_k[t.id] = k_t_in if inside else k_out
            self.unit_k_gen[g.id] = k_g_in if inside else k_out

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
        if t.id in self.unit_k:
            # trasformatore di un gruppo di generazione: K_S/K_SO o K_T,S invece di K_T
            kt = self.unit_k[t.id]
        elif self.case == "max":
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

    def generator_z(self, g: Generator, seq: int) -> complex:
        """Impedenza del generatore in p.u. (sequenza 1, 2 o 0 senza neutro)."""
        xd = g.xd2_percent / 100.0 * g.ur_kv**2 / g.sr_mva
        rg = g.rg_ohm if g.rg_ohm is not None else factors.generator_rx(g.ur_kv, g.sr_mva) * xd
        if g.id in self.unit_k_gen:
            kg = self.unit_k_gen[g.id]  # gruppo di generazione: K_S/K_SO o K_G,S
        else:
            kg = factors.generator_kg(
                self.un[g.bus], g.ur_kv, self.c_max(g.bus), g.xd2_percent / 100.0, g.cos_phi
            )
        x = xd
        if seq == 2 and g.x2_percent is not None:
            # reattanza di sequenza inversa di targa, es. X(2) = (X"d + X"q)/2
            x = g.x2_percent / 100.0 * g.ur_kv**2 / g.sr_mva
        elif seq == 0:
            x = (g.x0_percent or 0.0) / 100.0 * g.ur_kv**2 / g.sr_mva
        return kg * complex(rg, x) / self.zbase(g.bus)

    @staticmethod
    def motor_sr_mva(m: Motor) -> float:
        return m.pr_mw / (m.efficiency * m.cos_phi)

    def motor_z(self, m: Motor, seq: int) -> complex:
        """Impedenza del motore asincrono (o del gruppo) in p.u., sequenza 1 o 2."""
        srm = self.motor_sr_mva(m)
        zm = m.ur_kv**2 / (m.ilr_ir * srm) / m.count
        rx = m.rx if m.rx is not None else factors.motor_rx(m.ur_kv, m.pr_mw, m.pole_pairs)
        xm = zm / math.sqrt(1.0 + rx**2)
        if seq == 2 and m.x2_percent is not None:
            # sequenza inversa da dati di targa (default: Z(2) = Z(1))
            xm = m.x2_percent / 100.0 * m.ur_kv**2 / srm / m.count
            rx = m.rx2 if m.rx2 is not None else rx
        return complex(rx * xm, xm) / self.zbase(m.bus)

    def wd_z(self, sg: StaticGenerator) -> complex:
        """Impedenza dell'eolico a doppia alimentazione Z_WD = √2·κ_WD·Ur/(√3·i_WDmax), in p.u."""
        ur = sg.ur_kv if sg.ur_kv is not None else self.un[sg.bus]
        z = math.sqrt(2.0) * sg.kappa_wd * ur / (math.sqrt(3.0) * sg.i_wd_max_ka) / sg.count
        x = z / math.sqrt(1.0 + sg.rx**2)
        return complex(sg.rx * x, x) / self.zbase(sg.bus)

    def pf_sources(self) -> list[tuple[int, float]]:
        """Sorgenti di corrente dei convertitori pieni: (nodo, I"k_PF in p.u.).

        Escluse dal calcolo delle correnti minime.
        """
        if self.case != "max":
            return []
        out = []
        for sg in self.net.static_generators:
            if sg.kind == "PF":
                ibase = S_BASE_MVA / (math.sqrt(3.0) * self.un[sg.bus])
                out.append((self.idx[sg.bus], sg.ikss_ka * sg.count / ibase))
        return out

    def rated_current_pu(self, bus: str, sr_mva: float, ur_kv: float) -> float:
        """Corrente nominale di una macchina in p.u. della base del nodo."""
        return sr_mva * self.un[bus] / (S_BASE_MVA * ur_kv)

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
        if seq == 1 and x_scale == 1.0 and motors:
            self.max_rx = 0.0  # R/X massimo dei rami (deroga del metodo B)

        def scale(z: complex) -> complex:
            if seq == 1 and x_scale == 1.0 and motors:
                rx = z.real / z.imag if z.imag > 0 else math.inf
                self.max_rx = max(self.max_rx, rx)
            return complex(z.real, z.imag * x_scale)

        # rami della sequenza (correnti nei rami): (nome, nodo i, nodo j, ammettenza,
        # rapporto); le derivazioni con nome (es. trasformatore YNd in sequenza
        # zero) hanno nodo j None e corrente dal nodo i verso l'elemento
        if not hasattr(self, "seq_branches"):
            self.seq_branches: dict[int, list[tuple[str, str, Optional[str], complex, float]]] = {}
        self.seq_branches[seq] = []

        def shunt(bus: str, z: complex, name: str = "") -> None:
            yy = 1.0 / scale(z)
            if name:
                self.seq_branches[seq].append((name, bus, None, yy, 1.0))
            y[self.idx[bus], self.idx[bus]] += yy
            grounded[self.idx[bus]] = True

        if seq == 1:
            self.branches: list[tuple[str, str, str, complex, float]] = []

        def branch(i_bus: str, j_bus: str, z: complex, ratio: float = 1.0, name: str = "") -> None:
            yy = 1.0 / scale(z)
            if seq == 1:
                self.branches.append((name, i_bus, j_bus, yy, ratio))
            if name:
                self.seq_branches[seq].append((name, i_bus, j_bus, yy, ratio))
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
                branch(t.hv_bus, t.lv_bus, z1 / t.parallel, ratio, t.id)
                continue
            hv, lv = _parse_vector_group(t.vector_group)
            zn_hv = 3.0 * complex(t.zn_hv_ohm) / self.zbase(t.hv_bus)
            zn_lv = 3.0 * complex(t.zn_lv_ohm) / self.zbase(t.lv_bus)
            if "ZN" in (hv, lv):
                # Avvolgimento a zig-zag con neutro: la corrente omopolare si chiude
                # nelle due metà dell'avvolgimento stesso, quindi è una derivazione
                # verso terra sul suo nodo (Z0 del trasformatore + 3·Zn) e i due lati
                # sono disaccoppiati in sequenza zero.
                if hv == "ZN":
                    shunt(t.hv_bus, (z0 * ratio**2 + zn_hv) / t.parallel, t.id)
                if lv == "ZN":
                    shunt(t.lv_bus, (z0 + zn_lv) / t.parallel, t.id)
            elif hv == "YN" and lv == "YN":
                branch(t.hv_bus, t.lv_bus, (z0 + zn_lv + zn_hv / ratio**2) / t.parallel, ratio, t.id)
            elif hv == "YN" and lv == "D":
                shunt(t.hv_bus, (z0 * ratio**2 + zn_hv) / t.parallel, t.id)
            elif hv == "D" and lv == "YN":
                shunt(t.lv_bus, (z0 + zn_lv) / t.parallel, t.id)
            # Altri gruppi (Yy, Yyn, YNy, Dd, Dy, Yd, Z senza neutro, ...): sequenza
            # zero interrotta.

        if seq == 0:
            # trasformatori di messa a terra (zig-zag o YNd dedicati)
            for et in self.net.earthing_transformers:
                shunt(et.bus, (complex(*et.z0_ohm) + 3.0 * complex(et.zn_ohm)) / self.zbase(et.bus), et.id)

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
                    branch(star, bus, z_w, ratio, f"{t.id}:{w}")
                elif connections[w] == "YN":
                    zn = 3.0 * complex(getattr(t, f"zn_{w}_ohm")) / self.zbase(bus)
                    branch(star, bus, z_w + zn, ratio, f"{t.id}:{w}")
                elif connections[w] == "D":
                    # il triangolo chiude la corrente omopolare: derivazione dal centro stella
                    shunt(star, z_star[w] / self.zbase(star))
                elif connections[w] == "ZN":
                    # zig-zag con neutro: la corrente omopolare si chiude nell'avvolgimento
                    # stesso, staccato dal centro stella (lati disaccoppiati)
                    z0_zz = complex(*getattr(t, f"z0_zigzag_{w}_ohm"))
                    zn = 3.0 * complex(getattr(t, f"zn_{w}_ohm"))
                    shunt(bus, (z0_zz + zn) / self.zbase(bus), f"{t.id}:{w}")
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
            branch(ln.from_bus, ln.to_bus, z / self.zbase(ln.from_bus), name=ln.id)

        if seq == 0:
            for g in self.net.generators:
                if g.x0_percent is None:
                    continue  # neutro isolato
                # K_G si applica all'impedenza omopolare della macchina, non a quella di neutro
                shunt(g.bus, self.generator_z(g, 0) + 3.0 * complex(g.zn_ohm) / self.zbase(g.bus))
        if seq in (1, 2):
            for g in self.net.generators:
                shunt(g.bus, self.generator_z(g, seq))
            if motors and self.case == "max":
                for m in self.net.motors:
                    shunt(m.bus, self.motor_z(m, seq))
            # eolico a doppia alimentazione: impedenza in sequenza diretta e inversa
            for sg in self.net.static_generators:
                if sg.kind == "WD":
                    shunt(sg.bus, self.wd_z(sg))
        return y, grounded


def _diag_z(system: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Impedenze nodali Z_ii; infinite per le parti di rete senza collegamento verso terra."""
    return np.diag(_full_z(system)).copy()


def _full_z(system: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Matrice delle impedenze nodali; infinita tra parti di rete non collegate."""
    y, grounded = system
    n = y.shape[0]
    z = np.full((n, n), complex(math.inf, math.inf))
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
            z[sub] = np.linalg.inv(y[sub])
    return z


def calculate(
    net: Network,
    case: str = "max",
    kappa_method: str = "C",
    tk_s: float = 1.0,
    tmin_s: float = 0.1,
    zf_ohm: complex = 0j,
) -> StudyResult:
    """Calcola le correnti di cortocircuito in tutti i nodi della rete.

    case: "max" (correnti massime) o "min" (correnti minime: cmin, niente
    motori, niente K_T, resistenze delle linee alla temperatura di fine guasto).
    kappa_method: "B" (impedenza nel punto di guasto, fattore 1,15) o "C"
    (frequenza equivalente fc = 20 Hz a 50 Hz, 24 Hz a 60 Hz).
    tk_s: durata del cortocircuito per la corrente termica equivalente Ith.
    tmin_s: tempo minimo di interruzione per Ib (fattori μ e q; valori
    tabellati 0,02 / 0,05 / 0,10 / ≥ 0,25 s, interpolazione lineare).
    zf_ohm: impedenza di guasto Z_F (Ω) in serie a ciascuna fase guasta: si
    somma a Z1, Z2 e Z0 nel punto di guasto, quindi Z1 + Z_F (trifase),
    Z1 + Z2 + 2·Z_F (bifase), Z1 + Z2 + Z0 + 3·Z_F (monofase).
    """
    zf_ohm = complex(zf_ohm)
    if zf_ohm.real < 0.0:
        raise ValueError("la resistenza di guasto non può essere negativa")
    net.validate()
    kappa_method = kappa_method.upper()
    if kappa_method not in ("B", "C"):
        raise ValueError("kappa_method deve essere 'B' o 'C'")
    result = _calculate(net, case, kappa_method, tk_s, tmin_s, None, zf_ohm)
    # Guasti all'interno dei gruppi di generazione (nodo del generatore e
    # servizi ausiliari a valle dei trasformatori ausiliari): fattori K_G,S e
    # K_T,S invece di K_S/K_SO; i trasformatori ausiliari restano con il loro K_T.
    for g in net.generators:
        if g.unit_transformer is None:
            continue
        region, other_sources = net.unit_region(g)
        if other_sources:
            region = [g.bus]
            result.warnings.append(
                f"{g.id}: i servizi ausiliari sono collegati ad altre sorgenti, "
                "solo il nodo del generatore è calcolato come interno al gruppo"
            )
        inside = _calculate(net, case, kappa_method, tk_s, tmin_s, g.id, zf_ohm)
        for bus_id in region:
            k = next(i for i, r in enumerate(result.buses) if r.bus == bus_id)
            result.buses[k] = inside.bus(bus_id)
        result.warnings += [w for w in inside.warnings if w not in result.warnings]
    return result


def _calculate(
    net: Network,
    case: str,
    kappa_method: str,
    tk_s: float,
    tmin_s: float,
    inside_unit: Optional[str],
    zf_ohm: complex = 0j,
) -> StudyResult:
    warnings: list[str] = []
    b = _Builder(net, case, warnings, inside_unit)

    z1_full = _full_z(b.build(1))
    rx_rami = b.max_rx
    if zf_ohm:
        # l'impedenza di guasto è in serie al percorso della corrente: conta come ramo
        rx_rami = max(rx_rami, zf_ohm.real / zf_ohm.imag if zf_ohm.imag > 0 else math.inf)
    z1 = np.diag(z1_full).copy()
    isolated = [net.buses[i].id for i in np.nonzero(~np.isfinite(z1[: len(net.buses)]))[0]]
    if isolated:
        raise ValueError(f"nodi non collegati ad alcuna sorgente: {isolated}")
    z2 = _diag_z(b.build(2))
    z0 = _diag_z(b.build(0))
    if kappa_method == "C":
        fc = 20.0 if net.f_hz == 50.0 else 24.0
        zc = _diag_z(b.build(1, x_scale=fc / net.f_hz))
    # componente continua all'istante tmin: R/X con la frequenza equivalente
    # fc = f·(fc/f), con fc/f scelto in base a f·t (metodo C della norma)
    fc_dc = factors.dc_frequency_ratio(net.f_hz * tmin_s)
    zdc = _diag_z(b.build(1, x_scale=fc_dc))
    machines = _machines(b, warnings)
    zf_pu = [zf_ohm / b.zbase(bus.id) for bus in net.buses]
    steady = _steady_state(net, b, warnings, zf_pu)
    single_fed = not net.external_grids and len(net.generators) == 1
    pf = b.pf_sources()
    zs_full = _full_z(b.build(1, motors=False)) if pf else None

    results = []
    for i, bus in enumerate(net.buses):
        c = b.c_case(bus.id)
        zb = b.zbase(bus.id)
        ibase = S_BASE_MVA / (math.sqrt(3.0) * bus.un_kv)
        zf = zf_pu[i]
        # impedenza di guasto in serie a ogni fase guasta: entra in tutte le sequenze
        z1i, z2i, z0i = z1[i] + zf, z2[i] + zf, z0[i] + zf
        zero_open = not cmath.isfinite(z0i)

        def scaled(z: complex, k: float) -> complex:
            return complex(z.real, z.imag * k)

        # Convertitori pieni (sorgenti di corrente di sequenza diretta): aumentano la
        # tensione equivalente nel punto di guasto, E = c + Σ |Z_ik|·I"k_PF,k
        # (somma in modulo, cautelativa). La quota c/E delle correnti è della rete.
        e_pf = sum(abs(z1_full[k, i]) * i_pf for k, i_pf in pf if cmath.isfinite(z1_full[k, i]))
        e = c + e_pf
        share = c / e

        ik3 = e / abs(z1i) * ibase
        ik2 = math.sqrt(3.0) * e / abs(z1i + z2i) * ibase
        if zero_open:
            # senza percorso verso terra il guasto bifase a terra equivale al bifase isolato
            ik1 = ike = 0.0
            ikl2 = ikl3 = ik2
        else:
            ik1 = 3.0 * e / abs(z1i + z2i + z0i) * ibase
            den = z1i * z2i + z1i * z0i + z2i * z0i
            ike = 3.0 * e * abs(z2i) / abs(den) * ibase
            i1 = e / (z1i + z2i * z0i / (z2i + z0i))
            i2 = -i1 * z0i / (z2i + z0i)
            i0 = -i1 * z2i / (z2i + z0i)
            ikl2 = abs(i0 + _A**2 * i1 + _A * i2) * ibase
            ikl3 = abs(i0 + _A * i1 + _A**2 * i2) * ibase

        if kappa_method == "C":
            zci = zc[i] + scaled(zf, fc / net.f_hz)
            k = factors.kappa(zci.real / zci.imag * fc / net.f_hz)
        else:
            k_limit = 1.8 if bus.un_kv <= factors.LV_LIMIT_KV else 2.0
            # deroga: con R/X < 0,3 in tutti i rami il fattore 1,15 non serve
            k_b = 1.0 if rx_rami < 0.3 else 1.15
            k = min(k_b * factors.kappa(z1i.real / z1i.imag), k_limit)
        # picco: κ solo sulla quota della rete, i convertitori non hanno componente continua
        peak = math.sqrt(2.0) * (k * share + (1.0 - share))
        ip3 = peak * ik3
        m = factors.thermal_m(k, net.f_hz, tk_s)
        i_pf3 = e_pf / abs(z1i) * ibase  # quota dei convertitori, senza decadimento
        ib = _breaking_current(i, c, z1_full, machines, tmin_s, zf) * ibase + i_pf3
        zdci = zdc[i] + scaled(zf, fc_dc)
        idc = factors.dc_component(ik3 * share, net.f_hz, tmin_s, zdci.real / zdci.imag * fc_dc)
        ik = None if steady[i] is None else steady[i] * ibase
        if ik is not None and zs_full is not None:
            zss = zs_full[i, i] + zf
            ik += sum(
                abs(zs_full[kk, i]) * i_pf for kk, i_pf in pf if cmath.isfinite(zs_full[kk, i])
            ) / abs(zss) * ibase
        # Fattore n: decadimento della componente alternata (guasti vicini ai
        # generatori) solo quando Ik deriva da λ (guasto alimentato da un solo
        # generatore); nelle reti magliate Ik è la stima cautelativa della norma
        # e si usa n = 1.
        n = factors.thermal_n(ik3 / ik, tk_s) if single_fed and ik else 1.0
        ith = ik3 * math.sqrt(m + n)

        results.append(
            BusResult(
                bus=bus.id,
                un_kv=bus.un_kv,
                c=c,
                z1_ohm=z1[i] * zb,
                z2_ohm=z2[i] * zb,
                z0_ohm=None if zero_open else z0[i] * zb,
                ikss3_ka=ik3,
                skss3_mva=math.sqrt(3.0) * bus.un_kv * ik3,
                ikss2_ka=ik2,
                ikss1_ka=ik1,
                ikss2e_earth_ka=ike,
                ikss2e_l2_ka=ikl2,
                ikss2e_l3_ka=ikl3,
                kappa=k,
                ip3_ka=ip3,
                ip2_ka=peak * ik2,
                ip1_ka=peak * ik1,
                ib_ka=ib,
                ik_ka=ik,
                ith_ka=ith,
                idc_ka=idc,
                ib_asym_ka=math.hypot(ib, idc),
            )
        )
    return StudyResult(net.name, case, kappa_method, tk_s, results, warnings, tmin_s, zf_ohm)


@dataclass
class _Machine:
    """Macchina rotante vista dal calcolo di Ib."""

    bus: int
    z: complex  # impedenza subtransitoria in p.u. (con K_G per i generatori)
    ir: float  # corrente nominale in p.u.
    mw_per_pole_pair: Optional[float]  # solo motori asincroni (fattore q)


def _machines(b: _Builder, warnings: list[str]) -> list[_Machine]:
    out = []
    for g in b.net.generators:
        out.append(_Machine(b.idx[g.bus], b.generator_z(g, 1), b.rated_current_pu(g.bus, g.sr_mva, g.ur_kv), None))
    if b.case == "max":
        for m in b.net.motors:
            if m.pole_pairs is not None:
                mpp = m.pr_mw / m.pole_pairs
            else:
                # gruppi di motori BT senza dati: PrM/p = 0,05 MW
                mpp = 0.05
                msg = f"{m.id}: coppie polari non indicate, per q si usa PrM/p = 0,05 MW"
                if msg not in warnings:
                    warnings.append(msg)
            sr = b.motor_sr_mva(m) * m.count
            out.append(_Machine(b.idx[m.bus], b.motor_z(m, 1), b.rated_current_pu(m.bus, sr, m.ur_kv), mpp))
    return out


def _breaking_current(
    f: int, c: float, z_full: np.ndarray, machines: list[_Machine], tmin_s: float, zf: complex = 0j
) -> float:
    """Corrente di interruzione simmetrica Ib (p.u.) per guasto trifase nel nodo f.

    Ib = I"k − Σ (ΔU"_i/(c·Un/√3))·(1 − μ_i·q_i)·I"k_i, con I"k_i corrente
    parziale della macchina i e ΔU"_i = X"_i·I"k_i la caduta ai suoi
    morsetti (q = 1 per le macchine sincrone). Per un guasto alimentato da una
    sola macchina si riduce a Ib = μ·q·I"k. Le macchine con I"k_i ≤ 2·Ir non
    decadono (μ = q = 1); per tmin < 0,02 s Ib = I"k.
    """
    zff = z_full[f, f] + zf  # con impedenza di guasto
    ib = c / abs(zff)
    if tmin_s < factors.T_MIN_IB:
        # sotto 0,02 s la norma non dà μ e q: nessun decadimento (cautelativo)
        return ib
    for mach in machines:
        zkf = z_full[mach.bus, f]
        if not cmath.isfinite(zkf):
            continue
        i_m = c * abs(zkf / zff) / abs(mach.z)
        ratio = i_m / mach.ir
        if ratio <= 2.0:
            continue  # macchina lontana dal guasto: nessun decadimento (μ = q = 1)
        mu = factors.decay_mu(ratio, tmin_s)
        q = 1.0 if mach.mw_per_pole_pair is None else factors.decay_q(mach.mw_per_pole_pair, tmin_s)
        ib -= (mach.z.imag * i_m / c) * (1.0 - mu * q) * i_m
    return ib


def _steady_state(
    net: Network, b: _Builder, warnings: list[str], zf: list[complex]
) -> list[Optional[float]]:
    """Corrente permanente Ik (p.u.) per guasto trifase in ogni nodo.

    Guasto alimentato da un solo generatore (nessuna rete esterna, un solo
    generatore): Ik = λ·IrG, con λmax (caso max) o λmin (caso min).
    Negli altri casi (reti magliate o con più sorgenti): Ik = I"k calcolata
    senza i motori asincroni.
    """
    n = len(net.buses)
    system = b.build(1, motors=False)
    if net.external_grids or len(net.generators) != 1:
        z = _diag_z(system)
        return [b.c_case(bus.id) / abs(z[i] + zf[i]) for i, bus in enumerate(net.buses)]
    g = net.generators[0]
    z_full = _full_z(system)
    gi = b.idx[g.bus]
    zg = b.generator_z(g, 1)
    ir = b.rated_current_pu(g.bus, g.sr_mva, g.ur_kv)
    out: list[Optional[float]] = []
    for i, bus in enumerate(net.buses):
        c = b.c_case(bus.id)
        ratio = c * abs(z_full[gi, i] / (z_full[i, i] + zf[i])) / abs(zg) / ir
        if g.lambda_max is not None and g.lambda_min is not None:
            lam_max, lam_min = g.lambda_max, g.lambda_min
        elif g.xd_sat_percent is not None:
            # reattanza subtransitoria corretta (K_G) in p.u. del generatore e stesso c
            # usato per I"kG/IrG: con guasto ai morsetti la reattanza esterna è nulla
            lam_max, lam_min = factors.generator_lambda(
                ratio, g.xd_sat_percent / 100.0, abs(zg) * ir, g.cos_phi, g.ufmax_ratio, c,
            )
        else:
            msg = f"{g.id}: per Ik servono xd_sat_percent oppure lambda_max e lambda_min"
            if msg not in warnings:
                warnings.append(msg)
            out.append(None)
            continue
        out.append((lam_max if b.case == "max" else lam_min) * ir)
    return out


FAULT_TYPES = ("3ph", "2ph", "2ph_e", "1ph")


@dataclass
class FaultCurrents:
    """Correnti iniziali (o di interruzione) per un guasto in un nodo (metodo della IEC 60909).

    Tipi di guasto (`fault_type`): "3ph" trifase, "2ph" bifase isolato tra le
    fasi b e c, "2ph_e" bifase a terra (b, c e terra), "1ph" monofase a terra
    della fase a. La fase a del nodo guasto è il riferimento delle fasi.

    - `ikss_ka`: corrente complessa nel punto di guasto (kA): per il trifase la
      corrente della fase a, per gli altri guasti la corrente della fase guasta
      di modulo massimo (monofase: I"k1; bifase: I"k2).
    - `branch_ka[(ramo, nodo)]`: corrente complessa (kA, alla tensione del nodo)
      di sequenza diretta che dal nodo entra nel ramo, senza gli sfasamenti dei
      gruppi vettoriali; per il guasto trifase è la corrente di fase. Per i
      trasformatori a tre avvolgimenti i rami sono `<id>:hv`, `<id>:mv`,
      `<id>:lv` (dal centro stella al nodo).
    - `branch_seq_ka[(ramo, nodo)]`: componenti (I0, I1, I2) nel riferimento
      delle reti di sequenza (senza sfasamenti); comprende le derivazioni
      verso terra della sequenza zero (trasformatori YNd, zig-zag e di messa a
      terra: corrente omopolare che l'elemento assorbe dal nodo).
    - `branch_phase_ka[(ramo, nodo)]`: correnti di fase (Ia, Ib, Ic) nel
      riferimento del nodo, con gli sfasamenti dei gruppi vettoriali.
    - `bus_dv_seq_kv[nodo]`: variazioni delle tensioni stellate di sequenza
      (ΔV0, ΔV1, ΔV2) in kV, nel riferimento delle reti di sequenza (servono
      ai relè direzionali).
    - `bus_shift_deg[nodo]`: sfasamento della sequenza diretta del nodo
      rispetto al nodo guasto (gradi).
    """

    bus: str
    ikss_ka: complex
    branch_ka: dict[tuple[str, str], complex]
    fault_type: str = "3ph"
    fault_seq_ka: tuple[complex, complex, complex] = (0j, 0j, 0j)
    fault_phase_ka: tuple[complex, complex, complex] = (0j, 0j, 0j)
    branch_seq_ka: dict[tuple[str, str], tuple[complex, complex, complex]] = field(default_factory=dict)
    branch_phase_ka: dict[tuple[str, str], tuple[complex, complex, complex]] = field(default_factory=dict)
    bus_dv_seq_kv: dict[str, tuple[complex, complex, complex]] = field(default_factory=dict)
    bus_shift_deg: dict[str, float] = field(default_factory=dict)
    inside_unit: Optional[str] = None
    breaking: bool = False
    warnings: list[str] = field(default_factory=list)

    def phase_ka(self, branch: str, bus: str) -> float:
        """Modulo della corrente di fase maggiore nel ramo (kA)."""
        return max(abs(i) for i in self.branch_phase_ka.get((branch, bus), (0j, 0j, 0j)))

    def residual_ka(self, branch: str, bus: str) -> float:
        """Modulo della corrente residua 3·I0 nel ramo (kA)."""
        return 3.0 * abs(self.branch_seq_ka.get((branch, bus), (0j, 0j, 0j))[0])


def unit_of_bus(net: Network, bus: str) -> Optional[str]:
    """Generatore del gruppo di generazione al cui interno si trova il nodo (come `calculate`)."""
    found = None
    for g in net.generators:
        if g.unit_transformer is None:
            continue
        region, other_sources = net.unit_region(g)
        if other_sources:
            region = [g.bus]
        if bus in region:
            found = g.id
    return found


def _clock(group: str, kinds: tuple[str, str]) -> int:
    """Numero orario finale del gruppo; se manca: 11 per Dy, Yd, Yz, Zy, 0 altrimenti."""
    m = re.search(r"(\d+)\s*$", group.strip())
    if m:
        return int(m.group(1)) % 12
    letters = {k[0].upper() for k in kinds}  # Y, D o Z
    return 11 if letters in ({"D", "Y"}, {"Y", "Z"}) else 0


def _zero_shift(k: int) -> float:
    """Sfasamento della sequenza zero tra avvolgimenti a stella: 180° se k/2 è dispari."""
    return 180.0 if k % 2 == 0 and (k // 2) % 2 == 1 else 0.0


def _vector_shifts(net: Network) -> dict[str, tuple[float, float]]:
    """Sfasamento (gradi) introdotto da ogni ramo dal primo al secondo nodo.

    Per ramo: (sequenza diretta, sequenza zero). Convenzione IEC: il lato BT
    è in ritardo di k·30° sull'AT (k numero orario), quindi la sequenza diretta
    ruota di −k·30° e l'inversa di +k·30° passando dall'AT al BT. In sequenza
    zero (solo avvolgimenti YN-YN) lo sfasamento è 0° o 180° (k/2 dispari:
    polarità invertita).
    """
    out: dict[str, tuple[float, float]] = {}
    for t in net.transformers:
        k = _clock(t.vector_group, _parse_vector_group(t.vector_group))
        out[t.id] = (-30.0 * k, _zero_shift(k))
    for t3 in net.transformers3w:
        tokens = re.findall(r"(YN|ZN|Y|D|Z)(\d*)", t3.vector_group.strip(), flags=re.IGNORECASE)
        hv_kind = tokens[0][0].upper()
        k_hv = int(tokens[0][1]) % 12 if tokens[0][1] else 0
        out[f"{t3.id}:hv"] = (0.0, 0.0)  # il centro stella ha il riferimento dell'AT
        for w, (kind, num) in zip(("mv", "lv"), tokens[1:]):
            k = int(num) % 12 if num else _clock("", (hv_kind, kind.upper()))
            k = (k - k_hv) % 12
            out[f"{t3.id}:{w}"] = (-30.0 * k, _zero_shift(k))
    return out


def _node_shifts(
    start: str,
    branches: list[tuple[str, str, Optional[str], complex, float]],
    shifts: dict[str, float],
    warnings: list[str],
) -> dict[str, float]:
    """Sfasamento di ogni nodo rispetto a `start` (visita dei rami a due estremi)."""
    adj: dict[str, list[tuple[str, float, str]]] = {}
    for name, i, j, _, _ in branches:
        if j is None:
            continue
        d = shifts.get(name, 0.0)
        adj.setdefault(i, []).append((j, d, name))
        adj.setdefault(j, []).append((i, -d, name))
    out = {start: 0.0}
    stack = [start]
    while stack:
        a = stack.pop()
        for nb, d, name in adj.get(a, []):
            s = (out[a] + d) % 360.0
            if nb not in out:
                out[nb] = s
                stack.append(nb)
            elif abs((out[nb] - s + 180.0) % 360.0 - 180.0) > 1e-6:
                msg = f"{name}: sfasamenti dei gruppi vettoriali non congruenti nella maglia"
                if msg not in warnings:
                    warnings.append(msg)
    return out


def _decay_injections(
    b: _Builder, f: int, c: float, z: np.ndarray, zf: complex, tmin_s: float, warnings: list[str]
) -> np.ndarray:
    """Iniezioni di corrente che riducono le f.e.m. delle macchine che decadono (calcolo di Ib).

    Per ogni macchina con I"k_i > 2·Ir la f.e.m. si riduce di c·w_i, con
    w_i = (ΔU"_i/c)·(1 − μ_i·q_i) come nella formula di Ib della IEC 60909:
    la corrente nel punto di guasto diminuisce di w_i·I"k_i.
    """
    inj = np.zeros(z.shape[0], dtype=complex)
    if tmin_s < factors.T_MIN_IB:
        return inj
    zff = z[f, f] + zf
    for mach in _machines(b, warnings):
        zkf = z[mach.bus, f]
        if not cmath.isfinite(zkf):
            continue
        i_m = c * abs(zkf / zff) / abs(mach.z)
        ratio = i_m / mach.ir
        if ratio <= 2.0:
            continue
        mu = factors.decay_mu(ratio, tmin_s)
        q = 1.0 if mach.mw_per_pole_pair is None else factors.decay_q(mach.mw_per_pole_pair, tmin_s)
        w = (mach.z.imag * i_m / c) * (1.0 - mu * q)
        inj[mach.bus] -= w * c / mach.z
    return inj


def fault_currents(
    net: Network,
    fault_bus: str,
    case: str = "max",
    zf_ohm: complex = 0j,
    fault_type: str = "3ph",
    breaking: bool = False,
    tmin_s: float = 0.1,
) -> FaultCurrents:
    """Correnti nei rami per un guasto nel nodo `fault_bus`.

    Sovrapposizione, in ciascuna rete di sequenza, della sola sorgente
    equivalente c·Un/√3 nel punto di guasto (variazioni di tensione
    ΔV = −Z_kf·I_f); stesse impedenze e fattori di correzione del calcolo di
    I"k, compreso il guasto interno a un gruppo di generazione (`_Builder` con
    `inside_unit`, come in `calculate`). Le correnti di sequenza nel punto di
    guasto sono quelle di `calculate` per il tipo di guasto `fault_type`.

    Convertitori pieni (PF, solo caso massimo): iniettano nel loro nodo la
    corrente I"k_PF, con la fase per cui Z_fk·I_PF è in fase con c; la
    tensione nel punto di guasto prima del guasto vale così
    E = c + Σ |Z_fk|·I_PF, come in `calculate`.

    `breaking=True` (solo guasto trifase): corrente di interruzione Ib al
    tempo `tmin_s`. Ogni macchina che decade (I"k_i > 2·Ir) riduce la sua
    f.e.m. della quota w_i = (ΔU"_i/c)·(1 − μ_i·q_i) della IEC 60909 (Ib =
    I"k − Σ w_i·I"k_i); la rete lineare ridistribuisce le correnti nei rami,
    quindi decadono solo i contributi che passano dalle macchine. Le riduzioni
    sono moltiplicate per un fattore α (1 se i contributi sono in fase) tale
    che la corrente nel nodo guasto sia la Ib di `calculate`, che somma i
    contributi in modulo. Per i guasti dissimmetrici la norma assume Ib = I"k.
    """
    if fault_type not in FAULT_TYPES:
        raise ValueError(f"tipo di guasto non valido {fault_type!r} {FAULT_TYPES}")
    net.validate()
    warnings: list[str] = []
    inside = unit_of_bus(net, fault_bus)
    b = _Builder(net, case, warnings, inside)
    z1 = _full_z(b.build(1))
    z2 = _full_z(b.build(2))
    z0 = _full_z(b.build(0))
    f = b.idx[fault_bus]
    zf = complex(zf_ohm) / b.zbase(fault_bus)
    c = b.c_case(fault_bus)
    z1_fin = np.where(np.isfinite(z1), z1, 0.0)

    # iniezioni di sequenza diretta dei convertitori pieni, in fase con c nel nodo guasto
    inj = np.zeros(z1.shape[0], dtype=complex)
    e = c
    for k, i_pf in b.pf_sources():
        if cmath.isfinite(z1[k, f]) and abs(z1[k, f]) > 0.0:
            inj[k] += i_pf * cmath.exp(-1j * cmath.phase(z1[f, k]))
            e += abs(z1[k, f]) * i_pf

    z1i, z2i, z0i = z1[f, f] + zf, z2[f, f] + zf, z0[f, f] + zf
    zero_open = not cmath.isfinite(z0i)
    i0 = i2 = 0j
    if fault_type == "3ph":
        i1 = e / z1i
        if breaking:
            ib = _breaking_current(f, c, z1, _machines(b, warnings), tmin_s, zf) + (e - c) / abs(z1i)
            decay = _decay_injections(b, f, c, z1, zf, tmin_s, warnings)
            # I_f(α) = A − α·B: α scala le riduzioni delle f.e.m. in modo che |I_f| = Ib
            # (α = 1 se i contributi delle macchine sono in fase, come assume la norma)
            big_b = -(z1_fin[f] @ decay) / z1i
            alpha = 1.0
            if abs(big_b) > 0.0:
                p = (i1 * big_b.conjugate()).real
                disc = p**2 - abs(big_b) ** 2 * (abs(i1) ** 2 - ib**2)
                if disc >= 0.0:
                    roots = [(p - math.sqrt(disc)) / abs(big_b) ** 2, (p + math.sqrt(disc)) / abs(big_b) ** 2]
                    alpha = min(roots, key=lambda r: abs(r - 1.0))
                else:
                    alpha = p / abs(big_b) ** 2
            inj += alpha * decay
            i1 = i1 - alpha * big_b
    elif fault_type == "2ph" or (fault_type == "2ph_e" and zero_open):
        i1 = e / (z1i + z2i)
        i2 = -i1
    elif fault_type == "1ph":
        if zero_open:
            i1 = 0j  # nessun percorso verso terra: nessuna corrente di guasto
            inj[:] = 0.0
        else:
            i1 = e / (z1i + z2i + z0i)
        i2 = i0 = i1
    else:  # bifase a terra
        i1 = e / (z1i + z2i * z0i / (z2i + z0i))
        i2 = -i1 * z0i / (z2i + z0i)
        i0 = -i1 * z2i / (z2i + z0i)

    def col(z: np.ndarray) -> np.ndarray:
        return np.where(np.isfinite(z[:, f]), z[:, f], 0.0)

    dv = {1: z1_fin @ inj - col(z1) * i1, 2: -col(z2) * i2, 0: -col(z0) * i0}

    def ibase(bus: str) -> float:
        return S_BASE_MVA / (math.sqrt(3.0) * b.un[bus])

    seq: dict[tuple[str, str], list[complex]] = {}
    for s in (1, 2, 0):
        v = dv[s]
        for name, i_bus, j_bus, yy, ratio in b.seq_branches[s]:
            vi = v[b.idx[i_bus]]
            if j_bus is None:  # derivazione verso terra
                seq.setdefault((name, i_bus), [0j, 0j, 0j])[s] += yy * vi * ibase(i_bus)
                continue
            vj = v[b.idx[j_bus]]
            seq.setdefault((name, i_bus), [0j, 0j, 0j])[s] += (yy / ratio**2 * vi - yy / ratio * vj) * ibase(i_bus)
            seq.setdefault((name, j_bus), [0j, 0j, 0j])[s] += (yy * vj - yy / ratio * vi) * ibase(j_bus)

    # sfasamenti dei gruppi vettoriali rispetto al nodo guasto
    shifts = _vector_shifts(net)
    sh1 = _node_shifts(fault_bus, b.seq_branches[1], {k: v[0] for k, v in shifts.items()}, warnings)
    sh0 = _node_shifts(fault_bus, b.seq_branches[0], {k: v[1] for k, v in shifts.items()}, warnings)

    def phases(bus: str, c0: complex, c1: complex, c2: complex) -> tuple[complex, complex, complex]:
        r1 = cmath.exp(1j * math.radians(sh1.get(bus, 0.0)))
        r0 = cmath.exp(1j * math.radians(sh0.get(bus, 0.0)))
        a0, a1, a2 = c0 * r0, c1 * r1, c2 * r1.conjugate()
        return (a0 + a1 + a2, a0 + _A**2 * a1 + _A * a2, a0 + _A * a1 + _A**2 * a2)

    ib_f = ibase(fault_bus)
    f_seq = (i0 * ib_f, i1 * ib_f, i2 * ib_f)
    f_ph = phases(fault_bus, *f_seq)
    if fault_type == "3ph":
        ikss = f_seq[1]
    elif fault_type == "1ph":
        ikss = f_ph[0]
    else:
        ikss = max(f_ph[1:], key=abs)
    branch_seq = {k: (v[0], v[1], v[2]) for k, v in seq.items()}
    keys1 = {(nm, x) for nm, i, j, _, _ in b.seq_branches[1] for x in (i, j)}
    buses = [bus.id for bus in net.buses]
    return FaultCurrents(
        bus=fault_bus,
        ikss_ka=ikss,
        branch_ka={k: v[1] for k, v in branch_seq.items() if k in keys1},
        fault_type=fault_type,
        fault_seq_ka=f_seq,
        fault_phase_ka=f_ph,
        branch_seq_ka=branch_seq,
        branch_phase_ka={k: phases(k[1], *v) for k, v in branch_seq.items()},
        bus_dv_seq_kv={
            bus: (dv[0][b.idx[bus]] * b.un[bus] / math.sqrt(3.0),
                  dv[1][b.idx[bus]] * b.un[bus] / math.sqrt(3.0),
                  dv[2][b.idx[bus]] * b.un[bus] / math.sqrt(3.0))
            for bus in buses
        },
        bus_shift_deg={bus: sh1.get(bus, 0.0) for bus in buses},
        inside_unit=inside,
        breaking=breaking and fault_type == "3ph",
        warnings=warnings,
    )
