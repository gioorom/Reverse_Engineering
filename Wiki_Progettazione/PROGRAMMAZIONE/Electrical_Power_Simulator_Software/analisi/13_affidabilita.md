# 13 — Affidabilità

Ottavo modulo del simulatore. Calcola gli indici di affidabilità dei carichi
(frequenza, durata e indisponibilità delle interruzioni) e del sistema
(IEEE 1366: SAIFI, SAIDI, CAIDI, ASAI, MAIFI; energia non fornita).

- Implementazione: [`iec60909/reliability.py`](../implementazione/iec60909/reliability.py).
- Riga di comando: `python -m iec60909.affidabilita rete.json [--dettagli] [--costo-kwh 10] [--primo-ordine] [--verifica-contro-alimentazione [--v-min 0.9] [--carico-max 100]] [--json]`.
- Esempio: [`esempi/affidabilita_dorsale.json`](../implementazione/esempi/affidabilita_dorsale.json),
  due dorsali MT da una cabina primaria, con cabine secondarie protette da
  fusibili, sezionatori a ogni nodo e un punto normalmente aperto tra le
  dorsali.

## Dati

| Sezione | Campi | Significato |
|---|---|---|
| `reliability_data` | `element`, `failure_rate` o `failure_rate_per_km`, `repair_time_h`, `temporary_rate` | guasti permanenti [1/anno], tempo di riparazione o sostituzione [h], guasti transitori [1/anno] |
| `switches` | `id`, `branch`, `bus`, `kind`, `normally_open`, `switching_time_h` | organo all'estremo `bus` del ramo: `switch` (sezionatore), `breaker` (interruttore), `fuse` (fusibile) |
| `loads` | `customers`, `average_mw` | clienti alimentati e potenza media (default p_mw·count) |

- **Elementi:** `element` è l'id di una linea, di un trasformatore (anche a
  tre avvolgimenti), di un nodo, di una rete esterna o di un generatore.
  `@lines`, `@transformers`, `@transformers3w`, `@buses`, `@external_grids`
  e `@generators` danno un default per tutta la categoria. Gli elementi
  senza dati sono considerati perfettamente affidabili.
- **Dispositivi di protezione:** quelli della sezione `protective_devices`
  ([`09`](09_coordinamento_protezioni.md)) valgono come interruttori, o come
  fusibili se di tipo `fuse`.

## Metodo

Analisi dei modi di guasto e dei loro effetti (FMEA), come nel metodo
analitico di Billinton e Allan per le reti di distribuzione. La rete è un
grafo di nodi e rami; gli organi di manovra stanno agli estremi dei rami.
Sono sorgenti le reti esterne e, se non escluse con `--senza-generatori`,
i generatori, che possono alimentare un'isola.

Per ogni guasto permanente di un elemento:

1. **Protezioni.** La zona del guasto si ricava cercando dal guasto
   attraverso gli estremi chiusi e fermandosi agli interruttori e ai
   fusibili. Tutta la zona va fuori servizio, sorgenti comprese. I carichi
   non più collegati a una sorgente sono interrotti.
2. **Sezionamento.** La parte guasta è la regione raggiunta fermandosi a
   qualunque organo di manovra. Dopo la separazione il resto della zona torna
   alimentato. Il tempo è il più lungo tra le manovre necessarie: apertura
   dei sezionatori e interruttori al confine della parte guasta, e
   richiusura degli interruttori scattati. Scattati sono quelli al confine
   della zona con una sorgente dal lato esterno. I fusibili agiscono da
   soli.
3. **Contro-alimentazione.** Si chiudono i punti normalmente aperti in ordine
   di tempo di manovra. Un carico rialimentato a quel passo ha durata
   max(sezionamento, manovra).
4. **Riparazione.** I carichi ancora interrotti aspettano la riparazione.

**Verifica della contro-alimentazione** (`check_transfer=True`,
`--verifica-contro-alimentazione`). Ogni configurazione di emergenza della
fase 3 è risolta con il flusso di potenza ([`07`](07_flusso_di_potenza.md)):

- la rete contiene solo i nodi alimentati, senza gli elementi della parte
  guasta e senza i rami con un estremo ancora aperto (un trasformatore a tre
  avvolgimenti con un avvolgimento aperto è tolto per intero);
- la manovra è respinta se una tensione scende sotto `v_min_pu` (0,9) o un
  ramo con corrente o potenza nominale (`max_i_ka`, `sn_mva`) supera
  `max_loading_percent` (100 %), oppure se il flusso non è risolvibile (per
  esempio un'isola senza nodo di saldo);
- i limiti già superati in esercizio normale contano solo se la manovra li
  peggiora di più di 0,005 pu o di 1 punto percentuale; l'avviso li elenca
  con il valore normale;
- se una manovra è respinta, i carichi che ne dipendono restano interrotti
  fino al punto normalmente aperto successivo (se la sua configurazione è
  accettata) o fino alla riparazione;
- ogni manovra respinta compare negli avvisi con le violazioni.

La verifica è a manovra intera: non c'è il distacco parziale dei carichi
per rendere accettabile la configurazione.

La durata è sempre al massimo il tempo di riparazione. Per ogni carico i
risultati sono λ = Σλ_k, U = Σλ_k·r_k e r = U/λ.

**Guasti transitori.** Sono eliminati dalla richiusura e danno
un'interruzione momentanea ai carichi interrotti nella fase 1 (MAIFI).

**Sovrapposizioni (secondo ordine).** Una coppia di elementi conta se, tolti
entrambi dalla rete in esercizio normale, separa un carico che resta
alimentato con uno solo dei due fuori servizio (insieme di taglio minimo del
secondo ordine). Vale l'approssimazione per guasti indipendenti con λ·r ≪ 1:
λ = λ1·λ2·(r1 + r2)/8760 e r = r1·r2/(r1 + r2). È il caso di trasformatori
in parallelo, doppie alimentazioni e reti magliate.

### Indici

| Indice | Definizione |
|---|---|
| SAIFI | Σ N_i·λ_i / Σ N_i [interruzioni/cliente·anno] |
| SAIDI | Σ N_i·U_i / Σ N_i [h/cliente·anno] |
| CAIDI | SAIDI/SAIFI [h] |
| ASAI | 1 − SAIDI/8760 |
| MAIFI | Σ N_i·λ_momentanee,i / Σ N_i |
| ENS | Σ L_i·U_i [MWh/anno], con L_i potenza media |
| AENS | ENS / Σ N_i [kWh/cliente·anno] |
| Costo | ENS × costo dell'energia non fornita (`--costo-kwh`) |

Per ogni elemento sono riportati anche i clienti interrotti, i clienti·ore e
l'energia non fornita causati dai suoi guasti. Per le coppie metà del
contributo va a ciascun elemento.

## Validazione

1. **Roy Billinton Test System, Bus 2.** È la rete di prova di riferimento
   per l'affidabilità della distribuzione (R. N. Allan, R. Billinton,
   I. Sjarief, L. Goel, K. S. So, *A reliability test system for
   educational purposes — basic distribution system data and results*,
   IEEE Trans. Power Systems 6(2), 1991).
   - Rete: quattro dorsali a 11 kV, 36 sezioni, 22 punti di carico e 1908
     clienti, con interruttori in cabina, sezionatori, fusibili sulle
     derivazioni e due punti normalmente aperti.
   - Dati (lunghezze, clienti, carichi, tassi e tempi) presi dalle tabelle
     2–5 dell'articolo; rete in [`tests/rbts.py`](../implementazione/tests/rbts.py)
     ed [`esempi/affidabilita_rbts_bus2.json`](../implementazione/esempi/affidabilita_rbts_bus2.json).
   - Casi verificati: caso base A (trasformatori riparati in 200 h) e caso E
     (sostituiti in 10 h), sia con linee aeree sia con cavi.
   - **Indici di sistema** (tabella 9): SAIFI, SAIDI, CAIDI, ASAI, ENS e
     AENS coincidono con tutte le cifre pubblicate. Esempio, caso A con
     linee: 0,248, 3,61 h, 14,55 h, 0,999588, 37 746 kWh/anno,
     19,78 kWh/cliente·anno.
   - **Punti di carico** (tabella 7): λ, r e U dei 22 punti entro
     l'arrotondamento dei valori pubblicati (±0,001/anno, ±0,01 h/anno).
2. **Dorsale radiale a mano.**
   - Rete: tre tratti con interruttore in testa, sezionatori, derivazioni
     protette da fusibili e punto normalmente aperto verso una seconda
     sorgente.
   - Per ogni carico λ, U e r coincidono con il calcolo a mano: riparazione
     a valle del tratto guasto, sezionamento a monte, contro-alimentazione
     a valle.
   - Coincidono anche gli indici di sistema.
   - Varianti: senza sezionatori, con un interruttore intermedio, con
     riparazione più breve della manovra.
3. **Doppia alimentazione.**
   - Rete: rete esterna e generatore sullo stesso nodo MT, poi
     trasformatore.
   - Primo ordine: interrompono solo il nodo e il trasformatore.
   - Secondo ordine: le coppie rete esterna + generatore e linea +
     generatore, con le formule esatte.
   - Senza il generatore come sorgente, rete e linea tornano in serie.
4. **Ridondanza in parallelo contro Markov e Monte Carlo.**
   - Rete: due linee in parallelo, con λ = 2/anno e r = 50 h.
   - La formula del secondo ordine dista il 2,3 % dal modello di Markov
     esatto, f = U1·U2·(μ1 + μ2), come atteso per λ·r/8760 ≈ 1 %.
   - Una simulazione sequenziale indipendente su 40 000 anni coincide con
     Markov: 0,4 % sulla frequenza e 2,4 % sull'indisponibilità.
5. **Trasformatore a tre avvolgimenti:** il guasto di un nodo resta confinato
   se c'è un interruttore e coinvolge l'intero trasformatore se manca.

**Esempio delle dorsali** (551 clienti): SAIFI 0,554, SAIDI 1,07 h,
CAIDI 1,93 h, ENS 1,29 MWh/anno.
- Il contributo maggiore è la rete esterna (0,2/anno per 1,5 h).
- Seguono i trasformatori MT/BT (48 h di riparazione) e il tratto aereo
  della dorsale B, che dà anche 2 interruzioni momentanee all'anno.

## Limiti

- **Capacità delle linee:** senza `check_transfer` la contro-alimentazione è
  solo topologica. Con la verifica, il carico considerato è quello di
  progetto (`p_mw`, `q_mvar`), non la punta del periodo del guasto; non c'è
  il distacco parziale dei carichi.
- **Organi di manovra:** perfettamente affidabili; manca il guasto
  dell'interruttore che non apre (protezione di riserva).
- **Fuori servizio programmati:** non sono considerati (manutenzione).
- **Guasti a valle:** fusibili e interruttori aprono sempre, senza mancata
  selettività ([`09`](09_coordinamento_protezioni.md) la verifica a parte).
- **Sovrapposizioni:** calcolate nella configurazione normale, senza
  contro-alimentazione; il terzo ordine è trascurato.
- **Rami in parallelo:** un ramo con `parallel` > 1 è un solo elemento.
- **Generatori:** alimentano l'isola senza controllo della potenza
  disponibile.
- **Indici:** tassi costanti (valori medi annui); niente distribuzioni di
  probabilità degli indici, che richiedono una simulazione Monte Carlo.
