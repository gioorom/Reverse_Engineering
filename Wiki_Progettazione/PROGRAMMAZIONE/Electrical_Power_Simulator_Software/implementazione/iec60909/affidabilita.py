"""Uso: python -m iec60909.affidabilita rete.json [--primo-ordine] [--senza-generatori] [--costo-kwh 10] [--mancato-intervento 0.01] [--verifica-contro-alimentazione] [--dettagli] [--json]"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .io import load_network
from .reliability import reliability_analysis, result_to_dict, result_to_markdown


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="iec60909.affidabilita", description="Affidabilità della rete")
    parser.add_argument("rete", help="file JSON con la rete e le sezioni reliability_data e switches")
    parser.add_argument("--primo-ordine", action="store_true", help="senza le sovrapposizioni di due guasti")
    parser.add_argument("--senza-generatori", action="store_true",
                        help="i generatori non alimentano la rete in isola (solo le reti esterne)")
    parser.add_argument("--costo-kwh", type=float, help="costo dell'energia non fornita [per kWh]")
    parser.add_argument("--manovra", type=float, default=1.0,
                        help="tempo di manovra dei dispositivi di protective_devices [h]")
    parser.add_argument("--mancato-intervento", type=float, default=0.0,
                        help="probabilità che un interruttore non apra sul guasto (protezione di riserva)")
    parser.add_argument("--verifica-contro-alimentazione", action="store_true",
                        help="verifica con il flusso di potenza le configurazioni di contro-alimentazione")
    parser.add_argument("--v-min", type=float, default=0.9, help="tensione minima ammessa [pu]")
    parser.add_argument("--carico-max", type=float, default=100.0, help="carico massimo dei rami [%%]")
    parser.add_argument("--dettagli", action="store_true", help="eventi per ogni carico")
    parser.add_argument("--json", action="store_true", help="output JSON invece di Markdown")
    args = parser.parse_args(argv)
    net = load_network(args.rete)
    r = reliability_analysis(net, second_order=not args.primo_ordine,
                             generators_as_sources=not args.senza_generatori,
                             cost_per_kwh=args.costo_kwh, default_switching_time_h=args.manovra,
                             stuck_probability=args.mancato_intervento,
                             check_transfer=args.verifica_contro_alimentazione, v_min_pu=args.v_min,
                             max_loading_percent=args.carico_max)
    if args.json:
        json.dump(result_to_dict(r), sys.stdout, ensure_ascii=False)
        print()
    else:
        sys.stdout.write(result_to_markdown(r, args.dettagli))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
