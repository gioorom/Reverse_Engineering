# ETAP Power Simulator

## Obiettivo

Reimplementare il calcolo di cortocircuito secondo IEC 60909-0:2016 (modulo
Short Circuit IEC di ETAP) partendo dalle formule della norma, senza
decompilare ETAP.

## Target

| Campo          | Valore |
| -------------- | ------ |
| Applicazione   | ETAP Power Simulator (Operation Technology, Inc. / ETAP) |
| Pagina         | https://etap.com/power-simulator |
| Versione       | da definire |
| Piattaforma    | Windows (applicazione desktop) |
| Tipo           | da verificare (.NET e/o nativo) |
| Licenza        | commerciale, in abbonamento |
| Dove si trova  | da definire (installazione con licenza sul PC dell'utente?) |

Descrizione pubblica: piattaforma per modellare, analizzare e simulare reti
elettriche (load flow, cortocircuito, coordinamento delle protezioni,
arc flash, affidabilità, power quality). Interoperabilità dichiarata con
AVEVA, Autodesk ed Excel.

## Note

- `etap.com` non è raggiungibile dalle sessioni cloud (bloccato dalla policy di
  rete): l'analisi richiede che il materiale arrivi da un'installazione locale.
- ETAP è software commerciale: l'analisi va fatta su una copia con licenza
  valida e nel rispetto dei termini della licenza e della normativa
  (Dir. 2009/24/CE, artt. 5.3 e 6: studio del funzionamento e decompilazione
  ai soli fini di interoperabilità).

## Stato

- [x] Target identificato
- [x] Obiettivo definito: cortocircuito IEC 60909 dalle norme
- [x] Formule e ipotesi documentate ([`analisi/01_iec60909_formule.md`](analisi/01_iec60909_formule.md))
- [x] Implementazione ([`implementazione/`](implementazione/))
- [x] Test: calcoli a mano e confronto con pandapower
- [ ] Confronto con i risultati di ETAP su una rete reale
- [ ] Estensioni: power station unit, trasformatori a 3 avvolgimenti, μ/q/λ

## Conclusioni

Il calcolo IEC 60909-0 è implementato nel pacchetto Python `iec60909`:
guasti trifase, bifase, bifase a terra e monofase, correnti massime e minime,
ip (metodi B e C), Ib, Ik, Ith. I risultati coincidono con pandapower entro
1 ppm (le due differenze residue sono motivate in `analisi/`).

Prossimo passo consigliato: calcolare la stessa rete con ETAP e con
`iec60909` e confrontare i risultati.
