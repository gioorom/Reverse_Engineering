# 09 — Coordinamento delle protezioni

Quarto modulo del simulatore: verifica di selettività e sensibilità delle
protezioni di massima corrente e tracciamento delle curve tempo-corrente
(TCC), sullo stile di ETAP Star.

- Implementazione: [`iec60909/coordination.py`](../implementazione/iec60909/coordination.py).
- Riga di comando: `python -m iec60909.coordinamento rete.json [--svg cartella]`.
- Esempio: [`esempi/coordinamento_cabina.json`](../implementazione/esempi/coordinamento_cabina.json).

## Dispositivi

Sezione `protective_devices` del file di rete. Ogni dispositivo è installato
all'estremo `bus` di un ramo `branch`: una linea, un trasformatore o
l'avvolgimento `<id>:hv|mv|lv` di un tre avvolgimenti.

Il campo `protects` indica il verso protetto:
- `branch` (default): protegge il ramo, con la corrente dal nodo verso il
  ramo. È il caso di un interruttore di partenza o del relè sul primario del
  trasformatore.
- `bus`: protegge il nodo, con la corrente dal ramo verso il nodo. È il caso
  dell'interruttore generale BT in arrivo dal trasformatore.

### Relè di massima corrente

Il tipo è `relay`. Le correnti sono primarie, in A.

- Curve a tempo inverso:
  - IEC 60255-151: t = TMS·A/(M^p − 1), con `IEC_SI` (0,14; 0,02), `IEC_VI`
    (13,5; 1), `IEC_EI` (80; 2) e `IEC_LTI` (120; 1);
  - IEEE C37.112: t = TD·(A/(M^p − 1) + B), con `IEEE_MI` (0,0515; 0,02;
    0,114), `IEEE_VI` (19,61; 2; 0,491) e `IEEE_EI` (28,2; 2; 0,1217).
- M = I/`pickup_a`; con M ≤ 1 il relè non interviene.
- Soglie a tempo definito `stages` (`pickup_a`, `time_s`): vale il tempo minore.
- Al tempo del relè si aggiunge il tempo di apertura dell'interruttore
  (`breaker_time_s`).

### Interruttore BT con sganciatore L-S-I

Il tipo è `breaker`. Le tarature:
- `in_a`: corrente nominale In;
- `ir`: soglia del lungo ritardo, in multipli di In (Ir = ir·In);
- `tr_s`: tempo del lungo ritardo a 6·Ir;
- `isd`: soglia del corto ritardo, in multipli di Ir;
- `tsd_s`: tempo del corto ritardo;
- `i2t_sd`: corto ritardo a I²t costante;
- `ii`: soglia dell'istantaneo, in multipli di In;
- `ti_s`: tempo dell'istantaneo.

Le zone sono in sequenza e ognuna vale fino alla soglia della successiva:
- **L**, oltre 1,05·Ir: t = tr·36/(I/Ir)², cioè I²t costante;
- **S**, da Isd: tsd, oppure con `i2t_sd` tsd·(10·Ir/I)² fino a 10·Ir; non
  supera la curva L;
- **I**, da Ii: ti.

### Fusibile o curva per punti

Il tipo è `fuse`. Si indicano i punti `points` [[I_A, t_s], …]; tra un punto e
l'altro l'interpolazione è lineare in scala log-log. Sotto il primo punto il
dispositivo non interviene; oltre l'ultimo vale il tempo dell'ultimo punto.
Va usata la curva del tempo totale di interruzione.

## Correnti di guasto nei rami

Le correnti nei rami vengono dalla nuova funzione `calc.fault_currents`. Si
usa il metodo della IEC 60909 con la sola sorgente equivalente c·Un/√3 nel
punto di guasto: le variazioni di tensione sono ΔV = −Z_kf·I"k e le correnti
nei rami si ottengono dalle ammettenze dei rami. Valgono le stesse impedenze e
gli stessi fattori di correzione del calcolo di I"k; la somma delle correnti
nel nodo guasto è uguale a I"k.

- **Corrente massima:** guasto trifase, caso massimo (motori inclusi).
- **Corrente minima:** correnti del guasto trifase nel caso minimo,
  moltiplicate per I"k2/I"k3 del nodo. È il guasto bifase, esatto se le reti
  di sequenza diretta e inversa coincidono.

## Verifiche

Per ogni nodo guasto, con la corrente massima e con quella minima:

1. **Sequenza di intervento:** corrente e tempo di ogni dispositivo. Anche un
   dispositivo percorso in verso opposto può intervenire; per esempio la
   partenza di un motore vede il contributo del motore a un guasto a monte.
2. **Principale e riserve:** si considerano solo i dispositivi percorsi nel
   verso protetto. Sono ordinati per distanza, in numero di rami, dal lato
   protetto del dispositivo al nodo guasto, poi per distanza del nodo di
   installazione.
3. **Selettività:** per ogni coppia consecutiva principale/riserva si richiede
   t_riserva − t_principale ≥ CTI della riserva. Il CTI è `cti_s`, di default
   0,3 s per i relè e 0,1 s per interruttori e fusibili.

   Con la corrente massima la verifica si ripete su tutto il campo di
   correnti, da 1/1000 della corrente di guasto fino a questa. Le correnti
   nei due dispositivi scalano insieme, perché la rete è lineare. Così si
   trovano gli incroci delle curve a correnti inferiori a quella di guasto,
   che una verifica fatta solo al punto di guasto non vede.
4. **Sensibilità:** con la corrente minima la protezione principale deve
   intervenire entro `--tmax`, di default 5 s.
5. **Correnti di carico:** se la rete ha carichi o motori, il flusso di
   potenza dà la corrente di ogni dispositivo, che non deve provocarne
   l'intervento.

Le curve TCC si salvano in SVG, una per nodo guasto: contengono i dispositivi
della catena principale/riserve, con le correnti riferite alla tensione del
nodo guasto e le linee verticali di I"k3 max e I"k2 min.

## Collegamento con l'arc flash

Nella sezione `arc_flash` la protezione di un punto può essere
`{"device": "<id>"}`. In questo caso il tempo d'arco è quello del
dispositivo, calcolato per la quota della corrente d'arco che lo attraversa:
il rapporto tra la corrente nel dispositivo e I"k vale per il guasto trifase
nel nodo. Per esempio, sulle sbarre del QGBT il contributo dei motori non
passa dall'interruttore generale, che quindi vede una corrente minore e
interviene più tardi.

## Esempio

Cabina 20/0,4 kV ([`esempi/coordinamento_cabina.json`](../implementazione/esempi/coordinamento_cabina.json)).

| Dispositivo | Posizione | Tarature |
|---|---|---|
| R_MT | relè sul primario del trasformatore | IEC VI, 40 A, TMS 0,55; I>> 450 A, 0,05 s |
| QF_gen | generale BT | In 1000 A, Ir 0,95, Isd 2·Ir, 0,3 s |
| QF1 | partenza verso QD1 | In 160 A, Ii 10·In |

Con il guasto in QD1 la sequenza è QF1 (0,02 s), QF_gen (0,3 s), R_MT
(1,5 s): tutto selettivo.

Con le tarature iniziali (R_MT 25 A, Isd 4·Ir) i margini al punto di guasto
erano rispettati. Il controllo sull'intero campo di correnti ha però trovato
che la curva di R_MT passa sotto lo sganciatore L di QF_gen tra 1,4 e 3,8 kA
lato BT. Questo caso è nei test.

## Validazione

- Curve dei dispositivi confrontate con calcoli a mano:
  - tutte le formule IEC e IEEE;
  - soglie a tempo definito;
  - zone L, S (anche a I²t costante) e I;
  - interpolazione log-log dei fusibili.
- Correnti nei rami:
  - in una rete radiale coincidono con I"k;
  - lato MT del trasformatore sono la corrente BT riportata a 20 kV;
  - nel nodo guasto, corrente dal cavo più contributo del motore uguale a
    I"k entro 1e-9.
- Studio dell'esempio:
  - ordine principale/riserve;
  - tempi e margini calcolati a mano;
  - corrente minima bifase;
  - problemi rilevati per ogni tipo di verifica: al punto di guasto, a
    corrente ridotta, di sensibilità e con le correnti di carico.

## Limiti

- Solo guasti trifase e bifase (protezioni di fase): non ci sono protezioni
  di terra né guasti monofase.
- Nessun relè direzionale: il verso serve solo a ordinare principale e
  riserve. Le reti magliate con più alimentazioni vanno verificate con
  attenzione.
- Correnti iniziali I"k, senza decadimento nel tempo: la scelta è cautelativa
  per la selettività, meno per i tempi delle riserve vicine ai generatori.
- Le bande di tolleranza dei dispositivi e la selettività energetica tra
  interruttori BT limitatori non sono modellate.
- Non sono considerati i contributi dei convertitori pieni (PF) alle correnti
  nei rami, né il calcolo dedicato dei guasti interni ai gruppi di
  generazione.
