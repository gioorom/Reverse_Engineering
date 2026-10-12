"""Uso: python -m iec60909.arco rete.json [--caso max|min] [--ibf iec60909|c1] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .arcflash import IBF_SOURCES, arc_flash_study, results_to_dict, results_to_markdown
from .io import load_network


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.arco", description="Arc flash secondo IEEE 1584-2018 (Lee oltre 15 kV, NFPA 70E in c.c.)")
    parser.add_argument("rete", help="file JSON con la rete e la sezione arc_flash")
    parser.add_argument("--caso", choices=("max", "min"), default="max",
                        help="caso di cortocircuito IEC 60909 per Ibf")
    parser.add_argument("--ibf", choices=tuple(IBF_SOURCES), default="iec60909",
                        help="corrente franca: I\"k IEC 60909 (default) oppure I\"k riscalata a c = 1 (c1); "
                             "il valore ibf_ka del punto ha la precedenza")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    results = arc_flash_study(net, args.caso, ibf=args.ibf)
    if args.json:
        json.dump(results_to_dict(results), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(results_to_markdown(results, net.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
