"""Uso: python -m iec60909.portate_mt rete.json [--json]

Portata IEC 60287 delle voci della sezione cable_ratings."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from typing import Optional

from .iec60287 import rating_of
from .io import load_network


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.portate_mt", description="Portate dei cavi MT/AT (IEC 60287)")
    parser.add_argument("rete", help="file JSON con la sezione cable_ratings")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    rows = []
    for cr in net.cable_ratings:
        c, r = rating_of(cr)
        rows.append((cr, c, r))
    if args.json:
        json.dump([{"id": cr.id, "area_mm2": c.area_mm2, **dataclasses.asdict(r)} for cr, c, r in rows],
                  sys.stdout, ensure_ascii=False)
        print()
        return 0
    out = [f"# Portate IEC 60287 — {net.name}", "",
           "| Cavo | Sezione [mm²] | Posa | I [A] | R c.a. [Ω/km] | ys | yp | Wd [W/m] | λ1 | T1 | T2 | T3 | T4 "
           "| θ schermo [°C] |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cr, c, r in rows:
        posa = f"{cr.installation.get('kind', 'buried')}, {cr.installation.get('formation', 'trefoil')}"
        out.append(f"| {cr.id} | {c.area_mm2:g} | {posa} | {r.current_a:.1f} | {r.r_ac_ohm_per_m * 1000:.5f} "
                   f"| {r.ys:.5f} | {r.yp:.5f} | {r.wd_w_per_m:.4f} | {r.lambda1:.5f} | {r.t1:.4f} | {r.t2:.4f} "
                   f"| {r.t3:.4f} | {r.t4:.4f} | {r.screen_temperature_c:.1f} |")
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
