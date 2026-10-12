# 09 — Coordinamento delle protezioni

Quarto modulo del simulatore: verifica di selettività e sensibilità delle
protezioni di massima corrente, di fase e di terra, e tracciamento delle curve
tempo-corrente (TCC), sullo stile di ETAP Star.

- Implementazione: [`iec60909/coordination.py`](../implementazione/iec60909/coordination.py).
- Riga di comando: `python -m iec60909.coordinamento rete.json [--svg cartella]
  [--ib [--tmin 0.1]] [--no-terra] [--no-carico]`.
- Esempio: [`esempi/coordinamento_cabina.json`](../implementazione/esempi/coordinamento_cabina.json).

## Dispositivi

Sezione `protective_devices` del file di rete. Ogni dispositivo è installato
all'estremo `bus` di un ramo `branch`: una linea, un trasformatore,
l'avvolgimento `<id>:hv|mv|lv` di un tre avvolgimenti oppure un trasformatore
di messa a terra (`earthing_transformers`, ramo con un solo estremo: il relè
sul suo neutro).

Il campo `protects` indica il verso protetto:
- `branch` (default): protegge il ramo, con la corrente dal nodo verso il
  ramo. È il caso di un interruttore di partenza o del relè sul primario del
  trasformatore.
- `bus`: protegge il nodo, con la corrente dal ramo verso il nodo. È il caso
  dell'interruttore generale BT in arrivo dal trasformatore o del relè sul
  neutro di un trasformatore di messa a terra.

### Grandezza misurata: protezioni di fase e di terra

Il campo `measure` vale per relè e interruttori:
- `phase` (default): la corrente di fase maggiore delle tre;
- `residual`: la corrente residua 3·I0 del ramo. È la protezione di terra
  (relè 51N/50N, funzione G degli sganciatori, relè sul neutro).

I fusibili misurano sempre la corrente di fase.

### Relè direzionali

Con `directional: true` il dispositivo interviene solo se la corrente va nel
verso protetto. Il verso si ricava come in un relè reale, polarizzato con la
tensione: l'impedenza vista dietro il dispositivo, −ΔV/I, deve stare entro
±90° dall'angolo caratteristico `characteristic_angle_deg` (default 45°).
Le grandezze usate sono quelle di sequenza:
- guasto trifase: sequenza diretta;
- guasti dissimmetrici: sequenza inversa per le protezioni di fase, sequenza
  zero per quelle di terra.

Le tensioni sono le variazioni dovute al guasto, perché il calcolo non ha
tensioni prima del guasto. Nella verifica con le correnti di carico vale il
verso della potenza attiva del flusso di potenza.

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

### Bande di tolleranza

Campi comuni a tutti i tipi:
- `current_tolerance_percent`: tutte le soglie di corrente variano di ±k %.
  Le curve dipendono solo da I/soglia, quindi con le soglie moltiplicate per
  (1 ± k) il tempo è t_nom(I/(1 ± k));
- `time_tolerance_percent` e `time_tolerance_s`: il tempo varia di
  ±max(p %·t, Δt), per esempio ±5 % o ±30 ms come nella IEC 60255-151.

Il tempo minimo usa le soglie ridotte e il tempo ridotto, il massimo le soglie
aumentate e il tempo aumentato.

### Selettività energetica tra interruttori BT

Il costruttore dichiara in tabella il limite di selettività Is tra un
interruttore a monte e uno a valle. Si indica sul dispositivo a monte:
`selectivity_limits: {"<id a valle>": Is_kA}`. Fino a Is la coppia è
selettiva anche se le curve si sovrappongono (interruttori limitatori,
selettività energetica); oltre Is non lo è. Per la selettività totale si
indica un valore pari al potere di interruzione.

## Correnti di guasto nei rami

Le correnti nei rami vengono dalla funzione `calc.fault_currents(net, nodo,
caso, zf_ohm, fault_type, breaking, tmin_s)`. Si usa il metodo della IEC 60909
con la sola sorgente equivalente c·Un/√3 nel punto di guasto. Valgono le
stesse impedenze e gli stessi fattori di correzione del calcolo di I"k.

### Reti di sequenza

1. Le correnti di sequenza nel punto di guasto sono quelle di `calculate`
   per il tipo di guasto:
   - trifase `3ph`: I1 = E/Z1;
   - bifase `2ph` (fasi b e c): I1 = −I2 = E/(Z1 + Z2);
   - monofase `1ph` (fase a): I1 = I2 = I0 = E/(Z1 + Z2 + Z0);
   - bifase a terra `2ph_e`.

   L'impedenza di guasto Z_F si somma in ogni sequenza.
2. In ogni rete di sequenza le variazioni di tensione sono ΔV_s = −Z_s,kf·I_s.
   Le correnti nei rami si ottengono dalle ammettenze dei rami registrate da
   `_Builder.build` per le sequenze 1, 2 e 0, con le stesse matrici del
   calcolo di I"k.
3. In sequenza zero compaiono anche le derivazioni verso terra. Per queste
   la corrente omopolare è quella che l'elemento assorbe dal nodo:
   - trasformatori YNd (lato YN);
   - avvolgimenti zig-zag con neutro;
   - trasformatori di messa a terra.

   I trasformatori YNyn sono rami anche in sequenza zero. Il triangolo
   interrompe la sequenza zero.

### Gruppi vettoriali

Le correnti di fase di un ramo sono Ia = I0 + I1 + I2, Ib = I0 + a²·I1 + a·I2,
Ic = I0 + a·I1 + a²·I2, nel riferimento del nodo. Le reti di sequenza non
hanno sfasamenti, quindi le componenti si ruotano con lo sfasamento del nodo
rispetto al nodo guasto, che è il riferimento (fase a).

La convenzione è quella IEC: il lato BT è in ritardo di k·30° sull'AT, con k
il numero orario. Passando dall'AT al BT la sequenza diretta ruota di −k·30°
e l'inversa di +k·30°. La sequenza zero passa solo tra avvolgimenti YN-YN: è
invertita se k/2 è dispari (gruppi 2, 6, 10).

Se il gruppo non indica il numero orario si assume:
- 11 per Dy, Yd, Yz e Zy;
- 0 negli altri casi.

Nelle maglie con sfasamenti non congruenti si dà un avviso.

### Convertitori pieni (PF)

Nel caso massimo i convertitori iniettano nel loro nodo la corrente I"k_PF di
sequenza diretta. La fase dell'iniezione è quella per cui Z_fk·I_PF è in fase
con c. La tensione nel punto di guasto prima del guasto vale così
E = c + Σ |Z_fk|·I_PF, come in `calculate`. La corrente nel punto di guasto
coincide con quella di `calculate` per tutti i tipi di guasto.

### Guasti interni ai gruppi di generazione

Per i nodi interni a un gruppo di generazione (`Network.unit_region`: nodo del
generatore e servizi ausiliari) si usa `_Builder` con `inside_unit`, come fa
`calculate`. Valgono i fattori K_G,S e K_T,S.

### Corrente di interruzione

Con `breaking=True` il guasto trifase usa la corrente di interruzione Ib al
tempo `tmin_s`. Il metodo:

1. ogni macchina con I"k_i > 2·Ir riduce la sua f.e.m. della quota
   w_i = (ΔU"_i/c)·(1 − μ_i·q_i) della formula di Ib della IEC 60909, cioè
   Ib = I"k − Σ w_i·I"k_i;
2. la riduzione entra come iniezione di corrente nel nodo della macchina, e
   la rete lineare ridistribuisce le correnti;
3. decadono solo i contributi che passano dalle macchine. Con un guasto
   franco la corrente dei rami verso la rete non cambia;
4. le riduzioni sono moltiplicate per un fattore α tale che la corrente nel
   nodo guasto sia esattamente la Ib di `calculate`. La norma somma i
   contributi in modulo, quindi α = 1 se i contributi sono in fase.

Per i guasti dissimmetrici la norma pone Ib = I"k.

### Compatibilità

Il risultato `FaultCurrents` contiene:
- `branch_ka`: corrente di sequenza diretta senza sfasamenti, uguale a prima
  per il guasto trifase (usata dall'arc flash);
- `branch_seq_ka`: componenti (I0, I1, I2);
- `branch_phase_ka`: correnti di fase (Ia, Ib, Ic);
- `bus_dv_seq_kv`: variazioni delle tensioni di sequenza;
- `fault_seq_ka`, `fault_phase_ka`: correnti nel punto di guasto;
- `inside_unit`, `warnings`.

## Livelli di guasto

| Livello | Caso | Guasto | Uso |
|---|---|---|---|
| `max` | massimo | trifase | selettività (I"k o Ib) |
| `min` | minimo | bifase | sensibilità, selettività |
| `max_1ph` | massimo | monofase a terra | selettività di fase e di terra |
| `min_1ph` | minimo | monofase a terra | sensibilità di fase e di terra |

I livelli monofase si calcolano solo nei nodi con percorso verso terra
(I"k1 > 0); `earth_faults=False` (`--no-terra`) li esclude. Il bifase usa le
reti di sequenza diretta e inversa effettive; non serve più l'ipotesi
Z1 = Z2. Per esempio, dietro un Dy un relè MT vede su una fase
(2/√3)·I"k2·n, cioè la corrente del guasto trifase riportata.

Con `current_basis="ib"` (`--ib`) il livello `max` usa la corrente di
interruzione al tempo `tmin_s`.

## Verifiche

Per ogni nodo guasto e per ogni livello:

1. **Sequenza di intervento:** corrente misurata e tempo di ogni dispositivo
   (nominale e banda). Anche un dispositivo non direzionale percorso in verso
   opposto può intervenire; per esempio la partenza di un motore vede il
   contributo del motore a un guasto a monte. Un direzionale in verso opposto
   non interviene.
2. **Principale e riserve:** si considerano solo i dispositivi percorsi nel
   verso protetto con corrente misurata non nulla. Le protezioni di terra non
   compaiono nei guasti senza corrente residua. Il verso si ricava così:
   - per i dispositivi non direzionali, dalla proiezione della corrente di
     sequenza del ramo sulla corrente di guasto della stessa sequenza;
   - per i direzionali, con la polarizzazione in tensione.

   I dispositivi sono ordinati per distanza, in numero di rami, dal lato
   protetto al nodo guasto, poi per distanza del nodo di installazione. I
   dispositivi nella stessa posizione (stesso ramo, nodo e verso, per esempio
   gli elementi di fase e di terra dello stesso interruttore) formano un unico
   gradino: tra loro non si verifica la selettività, e verso gli altri
   gradini vale il più rapido.
3. **Selettività:** per ogni coppia di gradini consecutivi si richiede
   t_riserva,min − t_principale,max ≥ CTI della riserva. I tempi sono i
   limiti delle bande di tolleranza, o le curve nominali se non ci sono
   tolleranze. Il CTI è `cti_s`, di default 0,3 s per i relè e 0,1 s per
   interruttori e fusibili.

   Se la riserva dichiara un limite di selettività Is per il principale, la
   coppia è selettiva quando la corrente nel principale non supera Is, e il
   principale interviene. Le curve in questo caso non contano.

   Con i livelli massimi (`max`, `max_1ph`) la verifica si ripete su tutto il
   campo di correnti, da 1/1000 della corrente di guasto fino a questa. Le
   correnti nei dispositivi scalano insieme, perché la rete è lineare. Così si
   trovano gli incroci delle curve a correnti inferiori a quella di guasto,
   che una verifica fatta solo al punto di guasto non vede. Con la tabella del
   costruttore il controllo non serve: le correnti inferiori sono entro Is.
4. **Sensibilità:** con i livelli minimi (`min`, `min_1ph`) la protezione
   principale deve intervenire entro `--tmax` (default 5 s) con il tempo
   massimo della banda.
5. **Correnti di carico:** se la rete ha carichi o motori, il flusso di
   potenza dà la corrente di ogni dispositivo. Questa non deve provocarne
   l'intervento, con il tempo minimo della banda. Le protezioni di terra
   vedono corrente residua nulla, perché i carichi sono equilibrati.

Le curve TCC si salvano in SVG, una per nodo guasto. Contengono:
- i dispositivi delle catene principale/riserve dei guasti trifase e monofase
  massimi, con le correnti riferite alla tensione del nodo guasto. Le
  protezioni di terra sono marcate "(3I0)";
- le bande di tolleranza, come due curve tratteggiate (tempo minimo e
  massimo);
- le linee verticali delle correnti di guasto di tutti i livelli.

## Collegamento con l'arc flash

Nella sezione `arc_flash` la protezione di un punto può essere
`{"device": "<id>"}`. In questo caso il tempo d'arco è quello del
dispositivo, calcolato per la quota della corrente d'arco che lo attraversa:
il rapporto tra la corrente nel dispositivo e I"k vale per il guasto trifase
nel nodo. Per esempio, sulle sbarre del QGBT il contributo dei motori non
passa dall'interruttore generale, che quindi vede una corrente minore e
interviene più tardi. Il rapporto ora considera anche i convertitori pieni e i
guasti interni ai gruppi di generazione.

## Esempio

Cabina 20/0,4 kV ([`esempi/coordinamento_cabina.json`](../implementazione/esempi/coordinamento_cabina.json)).

| Dispositivo | Posizione | Tarature |
|---|---|---|
| R_MT | relè sul primario del trasformatore | IEC VI, 40 A, TMS 0,55; I>> 450 A, 0,05 s |
| QF_gen | generale BT | In 1000 A, Ir 0,95, Isd 2·Ir, 0,3 s |
| QF1 | partenza verso QD1 | In 160 A, Ii 10·In |

Con il guasto trifase in QD1 la sequenza è QF1 (0,02 s), QF_gen (0,3 s), R_MT
(1,5 s): tutto selettivo.

Il trasformatore Dyn11 mette a terra il lato BT. Per questo QGBT e QD1 hanno
anche i livelli monofase, mentre il nodo MT no: la rete MT è senza dati
omopolari. Con il guasto monofase massimo in QD1 (10,5 kA):
- R_MT, lato triangolo, vede la corrente soprattutto su due fasi, al massimo
  112 A;
- come riserva interviene in 4,2 s;
- la catena resta selettiva.

Con le tarature iniziali (R_MT 25 A, Isd 4·Ir) i margini al punto di guasto
erano rispettati. Il controllo sull'intero campo di correnti ha però trovato
che la curva di R_MT passa sotto lo sganciatore L di QF_gen tra 1,4 e 3,8 kA
lato BT. Questo caso è nei test.

## Validazione

Test in [`tests/test_coordinamento.py`](../implementazione/tests/test_coordinamento.py)
e [`tests/test_coordinamento_estensioni.py`](../implementazione/tests/test_coordinamento_estensioni.py).

- Curve dei dispositivi confrontate con calcoli a mano:
  - tutte le formule IEC e IEEE;
  - soglie a tempo definito;
  - zone L, S (anche a I²t costante) e I;
  - interpolazione log-log dei fusibili;
  - bande di tolleranza su soglie e tempi.
- Correnti nei rami:
  - in una rete radiale coincidono con I"k; lato MT del trasformatore sono la
    corrente BT riportata a 20 kV;
  - nel nodo guasto, corrente dal cavo più contributo del motore uguale a
    I"k entro 1e-9.
- Correnti nei rami, guasti dissimmetrici:
  - le reti di prova sono la rete magliata (trasformatori Dyn5 e Dyn11), la
    stazione con il tre avvolgimenti YNynd5 e la cabina;
  - per i quattro tipi di guasto, caso massimo e minimo, la corrente nel punto
    di guasto è quella di `calculate` (I"k3, I"k2, I"k1, I"kE2E sulle fasi);
  - nei nodi senza sorgenti la somma delle correnti di fase dei rami è uguale
    alla corrente di guasto in tutte e tre le fasi, entro 1e-9.
- Gruppi vettoriali:
  - Dyn11, Dyn5 e Dyn con guasto monofase lato BT: lato MT due fasi con
    I·(0,4/20)/√3, la terza nulla, nessuna corrente residua (verifica nota);
  - Dy con guasto bifase lato BT: (2/√3)·I"k2·n su una fase, metà sulle altre;
  - YNyn0 e YNyn6: lato AT la sola fase guasta, riportata e invertita con il
    gruppo 6.
- Sequenza zero:
  - con un YNd, la corrente omopolare si divide tra rete e trasformatore in
    proporzione inversa alle impedenze omopolari (calcolo a mano);
  - con un trasformatore di messa a terra, tutta la corrente del guasto
    monofase passa dal suo neutro.
- Convertitori pieni: la corrente nella linea è I"k_PF e la somma nel nodo
  guasto è I"k3 di `calculate`, con il guasto nel nodo del convertitore o
  lontano. Nel caso minimo non contribuiscono.
- Guasto interno al gruppo di generazione: corrente dal trasformatore più
  contributo del generatore (con K_G,S) uguale a I"k di `calculate`.
- Corrente di interruzione:
  - la somma nel nodo guasto è la Ib di `calculate`;
  - il ramo verso la rete non cambia, quello del motore decade.
- Studio:
  - ordine principale/riserve; tempi e margini calcolati a mano;
  - correnti minime bifase;
  - livelli monofase solo dove c'è percorso verso terra;
  - relè di terra (3I0 = I"k1) e gradini con elementi di fase e di terra;
  - relè direzionali su linee in parallelo (direzionale in verso opposto non
    interviene, anche con la corrente di carico);
  - margini con le bande; selettività energetica sotto e sopra Is;
  - problemi rilevati per ogni tipo di verifica: al punto di guasto, a
    corrente ridotta, di sensibilità e con le correnti di carico.

## Limiti

- **Correnti di guasto.** Valgono le ipotesi della IEC 60909:
  - sorgente equivalente nel punto di guasto, senza correnti di carico prima
    del guasto;
  - per i relè direzionali, verso dalle sole variazioni di tensione e di
    corrente, senza tensione di memoria né quella prima del guasto;
  - nessun guasto lungo le linee (si inserisce un nodo intermedio);
  - nessun guasto evolutivo.
- **Reti a neutro isolato o compensato.** Non sono modellate, come nella
  IEC 60909: le capacità verso terra non ci sono. Le protezioni di terra di
  queste reti (direzionali di terra sulle correnti capacitive) non si possono
  verificare.
- **Polarizzazione.** È semplificata: un solo angolo caratteristico; nessuna
  polarizzazione in quadratura né con la corrente di neutro.
- **Decadimento.** Riguarda solo la corrente di interruzione Ib a un tempo
  `tmin_s`, uguale per tutto il campo di tempi delle curve. Non c'è
  l'andamento nel tempo della corrente (passaggio a Ik dei generatori) durante
  l'intervento delle riserve. Per i guasti dissimmetrici si usa I"k.
- **Bande di tolleranza.** Le soglie di corrente scalano tutte insieme; i
  fusibili non distinguono la curva di prearco da quella di interruzione
  totale.
- **Selettività energetica.** Solo come limite Is di tabella. Non c'è il
  calcolo dell'energia passante (I²t) né del picco limitato dagli interruttori
  limitatori, né la selettività di zona (ZSI).
- **Dispositivi.** Nessuna protezione differenziale, di distanza, di
  minima/massima tensione o frequenza; nessun dispositivo sui generatori,
  sulle reti esterne o sui carichi.
