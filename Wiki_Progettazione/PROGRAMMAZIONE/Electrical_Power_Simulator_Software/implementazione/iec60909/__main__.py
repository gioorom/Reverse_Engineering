"""Uso: python -m iec60909 rete.json [--caso max|min] [--kappa B|C] [--tk 1] [--tmin 0.1] [--json]"""

from __future__ import annotations

import argparse
import json
import sys

from .calc import calculate
from .io import load_network, result_to_dict, result_to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="iec60909", description="Correnti di cortocircuito secondo IEC 60909-0:2016"
    )
    parser.add_argument("rete", help="file JSON con la descrizione della rete")
    parser.add_argument("--caso", choices=("max", "min"), default="max")
    parser.add_argument("--kappa", choices=("B", "C"), default="C", help="metodo per ip")
    parser.add_argument("--tk", type=float, default=1.0, help="durata del guasto per Ith [s]")
    parser.add_argument(
        "--tmin", type=float, default=0.1, help="tempo minimo di interruzione per Ib [s]"
    )
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)

    result = calculate(load_network(args.rete), args.caso, args.kappa, args.tk, args.tmin)
    if args.json:
        json.dump(result_to_dict(result), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
