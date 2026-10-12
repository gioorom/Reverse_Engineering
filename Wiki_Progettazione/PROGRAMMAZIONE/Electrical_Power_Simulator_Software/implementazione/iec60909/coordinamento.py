"""Uso: python -m iec60909.coordinamento rete.json [--nodi A B] [--tmax 5] [--svg cartella] [--json]
[--ib [--tmin 0.1]] [--no-terra] [--no-carico]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .coordination import LEVEL_LABELS, coordination_study, result_to_dict, result_to_markdown, tcc_svg
from .io import load_network


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.coordinamento", description="Coordinamento delle protezioni")
    parser.add_argument("rete", help="file JSON con la rete e la sezione protective_devices")
    parser.add_argument("--nodi", nargs="*", help="nodi guasti (default: tutti)")
    parser.add_argument("--tmax", type=float, default=5.0, help="tempo massimo della protezione principale [s]")
    parser.add_argument("--no-carico", action="store_true", help="salta la verifica con le correnti di carico")
    parser.add_argument("--no-terra", action="store_true", help="salta i guasti monofase a terra")
    parser.add_argument("--ib", action="store_true",
                        help="guasto trifase massimo con la corrente di interruzione Ib invece di I\"k")
    parser.add_argument("--tmin", type=float, default=0.1, help="tempo minimo di interruzione per Ib [s]")
    parser.add_argument("--svg", help="cartella in cui scrivere le curve tempo-corrente (una per nodo guasto)")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    res = coordination_study(net, args.nodi, args.tmax, not args.no_carico, not args.no_terra,
                             "ib" if args.ib else "ik", args.tmin)
    if args.svg:
        out = Path(args.svg)
        out.mkdir(parents=True, exist_ok=True)
        un = {b.id: b.un_kv for b in net.buses}
        for f in res.faults:
            if f.level != "max":
                continue
            cases = [g for g in res.faults if g.bus == f.bus]
            # catene principale/riserve dei guasti trifase e monofase massimi
            devices: list[str] = []
            for g in cases:
                if g.level in ("max", "max_1ph"):
                    chain = sorted((o for o in g.operations if o.order is not None), key=lambda o: o.order)
                    devices += [o.device for o in chain if o.device not in devices]
            if not devices:
                continue
            marks = {LEVEL_LABELS[g.level]: g.ik_ka for g in cases}
            svg = tcc_svg(net, devices, un[f.bus], marks, f"Guasto in {f.bus}")
            (out / f"tcc_{f.bus}.svg").write_text(svg, encoding="utf-8")
    if args.json:
        json.dump(result_to_dict(res), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(res))
    return 1 if res.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
