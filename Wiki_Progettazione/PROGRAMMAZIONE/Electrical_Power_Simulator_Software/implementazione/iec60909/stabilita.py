"""Uso: python -m iec60909.stabilita rete.json [--tfine 3] [--dt 0.002] [--svg grafico.svg] [--json]
       python -m iec60909.stabilita rete.json --tcc NODO [--apri RAMO ...] [--tguasto 0.1]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .io import load_network
from .network import StabilityEvent
from .stability import angles_svg, critical_clearing_time, result_to_dict, result_to_markdown, simulate


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.stabilita", description="Stabilità transitoria")
    parser.add_argument("rete", help="file JSON con la rete, i dati dinamici e stability_events")
    parser.add_argument("--tfine", type=float, default=3.0, help="durata della simulazione [s]")
    parser.add_argument("--dt", type=float, default=0.002, help="passo di integrazione [s]")
    parser.add_argument("--limite", type=float, default=180.0, help="differenza angolare di instabilità [°]")
    parser.add_argument("--svg", help="file SVG con gli angoli rotorici")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    parser.add_argument("--tcc", metavar="NODO", help="calcola il tempo critico di eliminazione del guasto nel nodo")
    parser.add_argument("--apri", nargs="*", default=[], help="rami aperti all'eliminazione del guasto (con --tcc)")
    parser.add_argument("--tguasto", type=float, default=0.1, help="istante del guasto (con --tcc) [s]")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    if args.tcc:
        clear = [StabilityEvent(0.0, "trip_branch", element=b) for b in args.apri]
        tcc = critical_clearing_time(net, args.tcc, clear, args.tguasto, t_end_s=args.tfine, dt_s=args.dt)
        if tcc is None:
            print(f"Guasto in {args.tcc}: stabile anche con eliminazione dopo 1 s")
        else:
            print(f"Guasto in {args.tcc}: tempo critico di eliminazione {tcc * 1000:.0f} ms")
        return 0
    res = simulate(net, args.tfine, args.dt, angle_limit_deg=args.limite)
    if args.svg:
        with open(args.svg, "w", encoding="utf-8") as fh:
            fh.write(angles_svg(res, f"Stabilità transitoria — {net.name}"))
    if args.json:
        json.dump(result_to_dict(res), sys.stdout, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(res))
    return 0 if res.stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
