"""Uso: python -m iec60909.coordinamento rete.json [--nodi A B] [--tmax 5] [--svg cartella] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .coordination import coordination_study, result_to_dict, result_to_markdown, tcc_svg
from .io import load_network


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.coordinamento", description="Coordinamento delle protezioni")
    parser.add_argument("rete", help="file JSON con la rete e la sezione protective_devices")
    parser.add_argument("--nodi", nargs="*", help="nodi guasti (default: tutti)")
    parser.add_argument("--tmax", type=float, default=5.0, help="tempo massimo della protezione principale [s]")
    parser.add_argument("--no-carico", action="store_true", help="salta la verifica con le correnti di carico")
    parser.add_argument("--svg", help="cartella in cui scrivere le curve tempo-corrente (una per nodo guasto)")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    res = coordination_study(net, args.nodi, args.tmax, not args.no_carico)
    if args.svg:
        out = Path(args.svg)
        out.mkdir(parents=True, exist_ok=True)
        un = {b.id: b.un_kv for b in net.buses}
        for f in res.faults:
            if f.level != "max":
                continue
            chain = sorted((o for o in f.operations if o.order is not None), key=lambda o: o.order)
            if not chain:
                continue
            fmin = res.fault(f.bus, "min")
            svg = tcc_svg(net, [o.device for o in chain], un[f.bus],
                          {"I\"k3 max": f.ik_ka, "I\"k2 min": fmin.ik_ka}, f"Guasto in {f.bus}")
            (out / f"tcc_{f.bus}.svg").write_text(svg, encoding="utf-8")
    if args.json:
        json.dump(result_to_dict(res), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(res))
    return 1 if res.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
