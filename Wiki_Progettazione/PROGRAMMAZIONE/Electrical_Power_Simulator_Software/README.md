# Electrical Power Simulator Software

## Obiettivo

Software di simulazione delle reti elettriche ispirato alle funzioni di
ETAP Power Simulator, sviluppato in proprio a partire dalle norme tecniche
pubbliche (nessuna decompilazione di software commerciale).

Primo modulo: calcolo delle correnti di cortocircuito secondo
IEC 60909-0:2016.

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

## Stato

- [x] Obiettivo definito: simulatore proprio basato sulle norme
- [x] Cortocircuito IEC 60909: formule documentate ([`analisi/01_iec60909_formule.md`](analisi/01_iec60909_formule.md))
- [x] Cortocircuito IEC 60909: implementazione e test (calcoli a mano, confronto con pandapower)
- [x] Cortocircuito: gruppi di generazione con servizi ausiliari, fattori μ/q/λ, componente continua, generatori statici, zig-zag
- [ ] Altri moduli (es. load flow, arc flash IEEE 1584)

## Conclusioni

Il calcolo IEC 60909-0 è implementato nel pacchetto Python `iec60909`:
guasti trifase, bifase, bifase a terra e monofase, correnti massime e minime,
ip (metodi B e C), Ib, Ik, Ith. I risultati coincidono con pandapower,
implementazione open source indipendente della stessa norma, entro 1 ppm
(le differenze residue sono motivate in `analisi/`).
