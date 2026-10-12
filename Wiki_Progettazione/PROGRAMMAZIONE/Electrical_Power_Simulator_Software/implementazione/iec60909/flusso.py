"""Uso: python -m iec60909.flusso rete.json [--qlim] [--angoli-relativi] [--saldo-distribuito]
[--prese-fisse] [--tol 1e-8] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .io import load_network
from .loadflow import result_to_dict, result_to_markdown, run_load_flow


def main(argv: Optional[list[str]] = None) -> int:
    """Uso: python -m iec60909.flusso rete.json [--qlim] [--angoli-relativi] [--saldo-distribuito]
[--prese-fisse] [--tol 1e-8] [--json]"""

    parser = argparse.ArgumentParser(prog="iec60909.flusso", description="Flusso di potenza (Newton-Raphson)")
    parser.add_argument("rete", help="file JSON con la descrizione della rete")
    parser.add_argument("--qlim", action="store_true", help="rispetta i limiti di Q dei generatori")
    parser.add_argument("--angoli-relativi", action="store_true",
                        help="ignora gli sfasamenti dei gruppi vettoriali")
    parser.add_argument("--saldo-distribuito", action="store_true",
                        help="ripartisce lo sbilancio di P secondo slack_weight")
    parser.add_argument("--prese-fisse", action="store_true",
                        help="nessuna regolazione automatica delle prese")
    parser.add_argument("--tol", type=float, default=1e-8, help="tolleranza sugli scarti [MVA]")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    res = run_load_flow(load_network(args.rete), tol_mva=args.tol, enforce_q_lims=args.qlim,
                        phase_shift=not args.angoli_relativi, distributed_slack=args.saldo_distribuito,
                        tap_control=not args.prese_fisse)
    if args.json:
        json.dump(result_to_dict(res), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(res))
    return 0 if res.converged else 1


if __name__ == "__main__":
    raise SystemExit(main())
