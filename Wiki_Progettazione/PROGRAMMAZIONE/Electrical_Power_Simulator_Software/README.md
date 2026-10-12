# Electrical Power Simulator Software

## Obiettivo

Software di simulazione delle reti elettriche ispirato alle funzioni di
ETAP Power Simulator, sviluppato in proprio a partire dalle norme tecniche
pubbliche (nessuna decompilazione di software commerciale).

Moduli: calcolo delle correnti di cortocircuito secondo IEC 60909-0:2016 e
flusso di potenza (Newton-Raphson).

## Riferimento di ispirazione

| Campo        | Valore |
| ------------ | ------ |
| Prodotto     | ETAP Power Simulator (Operation Technology, Inc. / ETAP) |
| Pagina       | https://etap.com/power-simulator |
| Funzioni     | load flow, cortocircuito, coordinamento protezioni, arc flash, affidabilità, power quality |
| Installato   | no: le funzioni sono reimplementate dalle norme, non da ETAP |

## Moduli

| Modulo | Norma | Stato |
| ------ | ----- | ----- |
| Cortocircuito ([`implementazione/`](implementazione/)) | IEC 60909-0:2016 | implementato e testato |
| Flusso di potenza ([`analisi/07`](analisi/07_flusso_di_potenza.md)) | Newton-Raphson | implementato e testato (pandapower, forma chiusa) |

## Stato

- [x] Obiettivo definito: simulatore proprio basato sulle norme
- [x] Cortocircuito IEC 60909: formule documentate ([`analisi/01_iec60909_formule.md`](analisi/01_iec60909_formule.md))
- [x] Cortocircuito IEC 60909: implementazione e test (calcoli a mano, confronto con pandapower)
- [x] Cortocircuito: gruppi di generazione con servizi ausiliari, fattori μ/q/λ, componente continua, generatori statici, zig-zag
- [x] Flusso di potenza (Newton-Raphson): implementazione e test
- [ ] Altri moduli (es. arc flash IEEE 1584, coordinamento delle protezioni)

## Conclusioni

Il calcolo IEC 60909-0 è implementato nel pacchetto Python `iec60909`:
guasti trifase, bifase, bifase a terra e monofase, correnti massime e minime,
ip (metodi B e C), Ib, Ik, Ith. I risultati coincidono con pandapower,
implementazione open source indipendente della stessa norma, entro 1 ppm
(le differenze residue sono motivate in `analisi/`).
