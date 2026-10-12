"""Uso: python -m iec60909.armoniche rete.json [--limiti en50160|ieee519] [--senza-carichi]
       [--pcc NODO --ramo-pcc RAMO --il A] [--scansione NODO --svg grafico.svg] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .harmonics import frequency_scan, harmonic_analysis, result_to_dict, result_to_markdown, scan_svg
from .io import load_network


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.armoniche", description="Analisi armonica")
    parser.add_argument("rete", help="file JSON con la rete e la sezione harmonic_sources")
    parser.add_argument("--limiti", choices=("en50160", "ieee519"), default="en50160")
    parser.add_argument("--senza-carichi", action="store_true", help="esclude i carichi R-L dal modello")
    parser.add_argument("--pelle", action="store_true", help="resistenze proporzionali a √h")
    parser.add_argument("--pcc", help="nodo del punto di consegna (limiti di corrente IEEE 519)")
    parser.add_argument("--ramo-pcc", help="ramo che alimenta il punto di consegna")
    parser.add_argument("--il", type=float, help="massima corrente di carico IL al punto di consegna [A]")
    parser.add_argument("--scansione", metavar="NODO", help="scansione in frequenza dell'impedenza del nodo")
    parser.add_argument("--hmax", type=float, default=50.0, help="ordine massimo della scansione")
    parser.add_argument("--svg", help="file SVG della scansione in frequenza")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    if args.scansione:
        scan = frequency_scan(net, args.scansione, args.hmax, include_loads=not args.senza_carichi)
        if args.svg:
            with open(args.svg, "w", encoding="utf-8") as fh:
                fh.write(scan_svg(scan, net.f_hz))
        print(f"Scansione in frequenza del nodo {args.scansione}: risonanze parallelo")
        for h, z in scan.resonances:
            print(f"- ordine {h:.2f} ({h * net.f_hz:.0f} Hz): |Z| = {z:.4g} Ω")
        if not net.harmonic_sources:
            return 0
    res = harmonic_analysis(net, not args.senza_carichi, args.pelle, args.limiti, args.pcc, args.ramo_pcc, args.il)
    if args.json:
        json.dump(result_to_dict(res), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(res))
    violazioni = any(b.limit_violations for b in res.buses) or bool(res.pcc and res.pcc.get("violations"))
    return 1 if violazioni else 0


if __name__ == "__main__":
    raise SystemExit(main())
