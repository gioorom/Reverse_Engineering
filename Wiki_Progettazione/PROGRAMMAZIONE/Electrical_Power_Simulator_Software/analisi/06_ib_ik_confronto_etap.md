# 06 — Ib e Ik (μ, q, λ): implementazione e confronto con ETAP

Corrente di interruzione simmetrica Ib e corrente permanente Ik secondo
IEC 60909-0:2016, confrontate con lo studio di "duty" `Duty909.SI1S` del
progetto `Example-IEC` della demo di ETAP 2024 (stessa rete di
[`04_confronto_etap_sc909.md`](04_confronto_etap_sc909.md)).

Formule implementate: [`01_iec60909_formule.md`](01_iec60909_formule.md),
sezione "Ib, Ik, Ith". Strumento: `python -m iec60909.etap Duty909.SI1S`.

## Ib

ETAP riporta Ib per ogni dispositivo di interruzione, con il suo tempo minimo
di interruzione t_min (`DeviceTD`). Il confronto è possibile per i dispositivi
che vedono l'intera corrente di guasto del nodo; per gli altri ETAP sottrae il
contributo del ramo protetto, che `iec60909` non calcola ancora.

| Nodo | Dispositivo | t_min [s] | Ib ETAP [kA] | Ib iec60909 [kA] | Scarto |
|---|---|---|---|---|---|
| Bus C | CB32 | 0,052 | 6,5304 | 6,5305 | +0,003 % |
| Bus C | CB C1 | 0,055 | 6,5294 | 6,5296 | +0,002 % |
| EmergencySwBrd | LVCB11 | 0,025 | 48,7832 | 48,7832 | 0,000 % |
| Swbrd2 | LVCB2 | 0,25 | 39,0445 | 39,0445 | 0,000 % |
| Bus C | Fuse C1 | 0,01 | 6,5624 | 6,5833 | +0,318 % |
| MCC1 | Fuse2 | 0,01 | 39,4981 | 39,8763 | +0,958 % |

Due regole, ricavate dal confronto, rendono i risultati coincidenti:

1. **Macchine lontane dal guasto**: una macchina il cui contributo non supera
   2 volte la corrente nominale non decade (μ = q = 1). La norma lo prevede
   esplicitamente per μ; senza estenderlo a q, i motori asincroni lontani
   riducevano Ib di circa lo 0,17 % rispetto a ETAP.
2. **t_min < 0,02 s** (fusibili): la norma non tabella μ e q sotto 0,02 s.
   `iec60909` usa Ib = I"k (nessun decadimento, scelta cautelativa); ETAP
   applica un decadimento intermedio (simile a un'estrapolazione lineare, che
   darebbe +0,03/+0,04 %). Lo scarto è dalla parte della sicurezza.

## Ik

| Nodo | Un [kV] | Ik ETAP [kA] | Ik iec60909 [kA] | Scarto |
|---|---|---|---|---|
| EmergencySwBrd / LV Bus | 0,4 | 48,613 | 48,613 | 0,000 % |
| MCC1 | 0,4 | 38,844 | 38,844 | 0,000 % |
| Swbrd2 | 0,4 | 38,936 | 38,936 | 0,000 % |
| Bus C | 11 | 6,486 | 6,503 | +0,26 % |
| SWBRDA | 11 | 8,115 | 8,143 | +0,35 % |
| Bus3 | 33 | 8,960 | 8,984 | +0,27 % |
| Utility Bus | 33 | 9,227 | 9,252 | +0,27 % |
| Bus B | 11 | 6,361 | 6,431 | +1,09 % |

`iec60909` applica la regola della norma per le reti magliate: Ik = I"k
calcolata senza i motori asincroni, con le macchine sincrone alla reattanza
subtransitoria. Ai nodi BT coincide con ETAP. Ai nodi MT ETAP riduce
ulteriormente il contributo delle macchine sincrone (generatore e motore
sincrono, che a Bus B è collegato direttamente: da qui lo scarto maggiore).

Ipotesi verificate e scartate per riprodurre ETAP ai nodi MT:

| Ipotesi sul contributo delle macchine sincrone | Scarto |
|---|---|
| Reattanza subtransitoria (regola della norma) | da +0,26 % a +1,09 % |
| Reattanza transitoria X'd | da −1,2 % a −3,1 % |
| Reattanza sincrona Xd | da −3,6 % a −9,8 % |
| Macchine sincrone escluse | da −0,4 % a −11,9 % |

Il metodo di ETAP è quindi un modello proprio, intermedio tra
subtransitorio e transitorio, che i file dello studio non permettono di
ricostruire (la colonna dei contributi a regime per ramo è vuota). Il valore
di `iec60909` è cautelativo rispetto a ETAP.

## λ

Per un guasto alimentato da un solo generatore Ik = λ·IrG. La norma fornisce
λmax e λmin solo come curve grafiche. `iec60909` permette di imporre i valori
letti dalle curve (`lambda_max`, `lambda_min`) oppure li calcola con il
modello analitico da cui le curve derivano (vedi `01`). La rete di esempio di
ETAP non contiene guasti alimentati da un solo generatore, quindi λ non ha un
riscontro con ETAP: è verificato solo con calcoli a mano.
