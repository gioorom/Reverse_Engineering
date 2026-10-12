"""Uso: python -m iec60909.cavi rete.json [--applica rete_dimensionata.json] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .cables import apply_sizing, cable_sizing_study, results_to_dict, results_to_markdown
from .io import load_network, network_to_dict


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.cavi", description="Dimensionamento dei cavi")
    parser.add_argument("rete", help="file JSON con la rete e la sezione cable_sizing")
    parser.add_argument("--applica", help="salva la rete con le linee aggiornate alle sezioni scelte")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    results = cable_sizing_study(net)
    if args.applica:
        out = apply_sizing(net, results)
        with open(args.applica, "w", encoding="utf-8") as fh:
            json.dump(network_to_dict(out), fh, ensure_ascii=False, indent=2)
    if args.json:
        json.dump(results_to_dict(results), sys.stdout, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(results_to_markdown(results, net.name))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
