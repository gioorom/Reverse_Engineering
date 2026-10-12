"""Lettura della rete da JSON e scrittura dei risultati."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from .calc import StudyResult
from .network import (
    Bus,
    EarthingTransformer,
    ExternalGrid,
    Generator,
    Line,
    Motor,
    Network,
    StaticGenerator,
    Transformer,
    Transformer3W,
)

_SECTIONS = {
    "buses": Bus,
    "external_grids": ExternalGrid,
    "transformers": Transformer,
    "transformers3w": Transformer3W,
    "lines": Line,
    "generators": Generator,
    "motors": Motor,
    "static_generators": StaticGenerator,
    "earthing_transformers": EarthingTransformer,
}


def _complex(value: Any) -> complex:
    if isinstance(value, (list, tuple)):
        return complex(value[0], value[1])
    return complex(value)


def _build(cls: type, data: dict[str, Any]) -> Any:
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ValueError(f"{cls.__name__}: campi sconosciuti {sorted(unknown)}")
    kwargs = dict(data)
    for key in ("z0_zigzag_hv_ohm", "z0_zigzag_mv_ohm", "z0_zigzag_lv_ohm", "z0_ohm"):
        if kwargs.get(key) is not None:
            kwargs[key] = tuple(kwargs[key])
    for key in ("zn_hv_ohm", "zn_mv_ohm", "zn_lv_ohm", "zn_ohm"):
        if key in kwargs:
            kwargs[key] = _complex(kwargs[key])
    return cls(**kwargs)


def network_from_dict(data: dict[str, Any]) -> Network:
    net = Network(
        name=data.get("name", "rete"),
        f_hz=float(data.get("f_hz", 50.0)),
        lv_tolerance_percent=int(data.get("lv_tolerance_percent", 6)),
    )
    unknown = set(data) - set(_SECTIONS) - {"name", "f_hz", "lv_tolerance_percent"}
    if unknown:
        raise ValueError(f"sezioni sconosciute nel file: {sorted(unknown)}")
    for key, cls in _SECTIONS.items():
        setattr(net, key, [_build(cls, item) for item in data.get(key, [])])
    return net


def load_network(path: str | Path) -> Network:
    with open(path, encoding="utf-8") as fh:
        return network_from_dict(json.load(fh))


def result_to_dict(result: StudyResult) -> dict[str, Any]:
    def conv(value: Any) -> Any:
        if isinstance(value, complex):
            return [value.real, value.imag]
        return value

    return {
        "network": result.network,
        "case": result.case,
        "kappa_method": result.kappa_method,
        "tk_s": result.tk_s,
        "tmin_s": result.tmin_s,
        "zf_ohm": [result.zf_ohm.real, result.zf_ohm.imag],
        "warnings": result.warnings,
        "buses": [
            {k: conv(v) for k, v in dataclasses.asdict(b).items()} for b in result.buses
        ],
    }


def _fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def result_to_markdown(result: StudyResult) -> str:
    caso = "massime" if result.case == "max" else "minime"
    lines = [
        f"# Cortocircuito IEC 60909-0 — {result.network}",
        "",
        f"Correnti {caso}, fattore di picco con metodo {result.kappa_method}, "
        f"Tk = {result.tk_s:g} s, tmin = {result.tmin_s:g} s"
        + (f", Z_F = {result.zf_ohm.real:g} + j{result.zf_ohm.imag:g} Ω" if result.zf_ohm else "")
        + ". Correnti in kA, impedenze di rete in Ω.",
        "",
        "| Nodo | Un [kV] | c | Zk1 [Ω] | R/X | I\"k3 | S\"k3 [MVA] | ip3 | Ib | i_DC | Ib asim "
        "| Ik | Ith | I\"k2 | I\"k1 | I\"kE2E |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for b in result.buses:
        lines.append(
            f"| {b.bus} | {b.un_kv:g} | {b.c:.2f} | {abs(b.z1_ohm):.5f} | {b.r_over_x:.3f} "
            f"| {_fmt(b.ikss3_ka)} | {_fmt(b.skss3_mva, 1)} | {_fmt(b.ip3_ka)} | {_fmt(b.ib_ka)} "
            f"| {_fmt(b.idc_ka)} | {_fmt(b.ib_asym_ka)} "
            f"| {_fmt(b.ik_ka)} | {_fmt(b.ith_ka)} | {_fmt(b.ikss2_ka)} | {_fmt(b.ikss1_ka)} "
            f"| {_fmt(b.ikss2e_earth_ka)} |"
        )
    if result.warnings:
        lines += ["", "## Avvertenze", ""] + [f"- {w}" for w in result.warnings]
    return "\n".join(lines) + "\n"
