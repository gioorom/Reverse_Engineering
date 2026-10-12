"""Uso: python -m iec60909.avviamento rete.json [--statico] [--dt 0.01] [--svg cartella] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .io import load_network
from .motorstart import motor_start_study, results_to_dict, results_to_markdown, start_svg


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.avviamento", description="Avviamento dei motori")
    parser.add_argument("rete", help="file JSON con la rete e la sezione motor_starts")
    parser.add_argument("--statico", action="store_true", help="solo l'istante di avviamento (rotore bloccato)")
    parser.add_argument("--dt", type=float, default=0.01, help="passo di integrazione [s]")
    parser.add_argument("--svg", help="cartella per i grafici (uno per avviamento)")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    results = motor_start_study(net, args.dt, args.statico)
    if args.svg and not args.statico:
        out = Path(args.svg)
        out.mkdir(parents=True, exist_ok=True)
        for r in results:
            (out / f"avviamento_{r.id}.svg").write_text(start_svg(r), encoding="utf-8")
    if args.json:
        json.dump(results_to_dict(results), sys.stdout, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(results_to_markdown(results, net.name))
    return 1 if any(r.issues for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
