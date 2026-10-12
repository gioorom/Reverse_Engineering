# 08 — Arc flash secondo IEEE 1584-2018

Terzo modulo del simulatore: energia incidente e confine dell'arco
elettrico (arc flash boundary) secondo **IEEE 1584-2018**, per sistemi
trifase in c.a. da 208 V a 15 kV, con il **metodo di Lee** oltre 15 kV e i
metodi dell'allegato D.5 di **NFPA 70E** per la **corrente continua**.
Implementazione: [`iec60909/arcflash.py`](../implementazione/iec60909/arcflash.py)
e [`iec60909/arcflash_dc.py`](../implementazione/iec60909/arcflash_dc.py) (c.c.).
Riga di comando: `python -m iec60909.arco rete.json [--caso max|min] [--ibf iec60909|c1] [--json]`.

La corrente di cortocircuito franca Ibf di ogni punto in c.a. è la I"k
trifase calcolata dal modulo IEC 60909 sulla stessa rete (oppure una delle
varianti descritte più avanti). Il tempo d'arco viene dalla protezione
indicata per il punto.

Scelta del metodo, automatica e riportata nel risultato (`method`):

| Punto | Metodo |
|---|---|
| c.a., 0,208–15 kV | IEEE 1584-2018 (corrente piena e ridotta) |
| c.a., oltre 15 kV | Lee (un solo caso, corrente d'arco = Ibf) |
| c.c. (`system: "dc"`) | NFPA 70E D.5.1 (Doan) o D.5.2 (Stokes-Oppenlander) |

## Procedura della norma

1. **Corrente d'arco intermedia** a 600, 2700 e 14 300 V (eq. 1, tabella 1):
   Iarc,Voc = 10^(k1 + k2·lg Ibf + k3·lg G)·(k4·Ibf⁶ + … + k9·Ibf + k10).
2. **Corrente d'arco finale**:
   - Voc > 600 V: interpolazione dei tre valori intermedi (eq. 16–18);
   - Voc ≤ 600 V: eq. 25,
     Iarc = 1/√[(0,6/Voc)²·(1/Iarc,600² − (0,6² − Voc²)/(0,6²·Ibf²))].
3. **Corrente d'arco ridotta**: Iarc,min = Iarc·(1 − 0,5·VarCF) (eq. 2), con
   VarCF polinomio di sesto grado in Voc (tabella 2). Sopra 600 V la riduzione
   si applica ai tre valori intermedi.
4. **Fattore dell'involucro CF** (eq. 11–15, tabelle 6 e 7): dimensioni
   equivalenti di altezza e larghezza (EES), involucro "tipico" oppure "poco
   profondo" (BT con altezza e larghezza < 508 mm e profondità ≤ 203,2 mm);
   CF = 1 per le configurazioni all'aperto (VOA, HOA).
5. **Energia incidente** intermedia (eq. 3–6, tabelle 3–5):
   E = 12,552/50·T·10^(k1 + k2·lg G + k3·Iarc/(k4·Ibf⁷ + … + k10·Ibf)
   + k11·lg Ibf + k12·lg D + k13·lg Iarc + lg(1/CF)) [J/cm²], con T in ms;
   fino a 600 V nel terzo termine compare Iarc,600 (sempre quella piena).
   Sopra 600 V il valore finale è interpolato (eq. 19–21).
6. **Confine dell'arco** (eq. 7–10, interpolazione eq. 22–24): distanza a cui
   l'energia vale 1,2 cal/cm² (5,0208 J/cm²).
7. Il calcolo si ripete con la corrente piena e con quella ridotta, ciascuna
   con il **proprio tempo d'arco**. Si adotta il caso con energia maggiore; il
   confine è il maggiore dei due.

Configurazioni degli elettrodi: VCB (verticali in cella), VCBB (verticali in
cella con barriera isolante), HCB (orizzontali in cella), VOA e HOA (verticali e
orizzontali all'aperto).

Campo di validità, controllato prima del calcolo (4.2 della norma):

| Grandezza | Fino a 600 V | Oltre 600 V |
|---|---|---|
| Voc | 0,208–0,6 kV | 0,6–15 kV |
| Ibf | 0,5–106 kA | 0,2–65 kA |
| G | 6,35–76,2 mm | 19,05–254 mm |

Inoltre la distanza di lavoro deve essere di almeno 305 mm e la larghezza
dell'involucro di almeno 4·G.

Le tabelle 8 e 10 danno i valori tipici per classe di apparecchiatura (G,
dimensioni e distanza di lavoro). Sono disponibili con `equipment_class`, es.
`quadro_bt`, `pannello_bt`, `quadro_mt_15kv`; i dati espliciti hanno la
precedenza.

## Tempo d'arco

Per ogni punto la sezione `protection` indica:

- un tempo fisso (`time_ms`);
- oppure un relè con curva IEC 60255-151:
  t = TMS·k/((I/Is)^α − 1), con SI (0,14; 0,02), VI (13,5; 1), EI (80; 2) e
  LTI (120; 1), soglia istantanea (`inst_pickup_ka`, `inst_time_ms`) e tempo
  di apertura dell'interruttore (`breaker_time_ms`).

Il relè vede la corrente d'arco moltiplicata per `current_ratio`. Per esempio
vale 0,4/20 per un arco sulle sbarre BT eliminato dalla protezione sul lato
MT del trasformatore.

Il tempo è limitato a `max_time_ms`, 2 s per default. La norma lo indica come
valore ragionevole quando l'operatore può allontanarsi; se la protezione non
interviene si usa questo valore.

Con `{"device": id}` il punto usa un dispositivo della sezione
`protective_devices` (relè, interruttore BT o **fusibile**, curve e
interpolazione di `iec60909.coordination.trip_time_s`). Il dispositivo vede la
quota della corrente d'arco che lo attraversa: rapporto tra la corrente nel
ramo e la I"k del nodo nel guasto trifase (es. il contributo di un motore a
valle non passa nel fusibile della partenza).

## Metodo di Lee (oltre 15 kV)

Per le tensioni superiori al campo del modello la IEEE 1584-2018 rimanda al
metodo teorico di Lee (IEEE 1584-2002 eq. 8–9, NFPA 70E allegato D.2):

- E = 2,142·10⁶·V·Ibf·t/D² [J/cm²], con V in kV, Ibf in kA, t in s, D in mm
  (in cal/cm² il coefficiente è 5,12·10⁵);
- confine D_B = √(2,142·10⁶·V·Ibf·t/E_B), con E_B = 5,0208 J/cm²
  (1,2 cal/cm²).

Nota sulle unità: nelle fonti citate il coefficiente 2,142·10⁶ dà l'energia
in **J/cm²** (2,142·10⁶/4,184 = 5,12·10⁵ per le cal/cm²); usarlo per le
cal/cm² sovrastimerebbe l'energia di 4,184 volte.

Lee considera l'arco con la corrente franca (Iarc = Ibf: nessuna riduzione,
nessun fattore d'involucro né distanza tra i conduttori): il tempo d'arco è
quello della protezione alla corrente Ibf e c'è un solo caso. Il metodo è
molto cautelativo, soprattutto a grandi distanze.

## Corrente continua (NFPA 70E, allegato D.5)

Punti con `system: "dc"`: tensione `vdc_v`, corrente franca `ibf_ka` oppure
resistenza del sistema `r_system_ohm` (Ibf = Vsys/Rsys), distanza di lavoro e
protezione come per la c.a.; il nodo è facoltativo (la rete in c.c. non è
modellata).

1. **Massima potenza** (`dc_method: "doan"`, default; D.5.1, D. R. Doan,
   "Arc Flash Calculations for Exposures to DC Systems", IEEE Trans. Ind.
   Appl., 2010): la potenza dell'arco è massima quando la tensione d'arco vale
   Vsys/2, quindi Iarc = 0,5·Ibf e E = 0,01·Vsys·Iarc·Tarc/D², con E in
   cal/cm², Vsys in V, **Iarc in A**, Tarc in s, D in cm. Verifica
   dimensionale: metà della potenza Vsys·Iarc irradiata su una sfera di raggio
   D dà 0,5/(4π·4,184) = 0,0095 ≈ 0,01; con Iarc in kA l'energia risulterebbe
   1000 volte più piccola.
2. **Resistenza d'arco** (`dc_method: "stokes"`; D.5.2, R. F. Ammerman et al.,
   "DC-Arc Models and Incident-Energy Calculations", IEEE Trans. Ind. Appl.,
   2010, con il modello di A. D. Stokes e W. T. Oppenlander, 1991):
   Rarc = (20 + 0,534·G)/Iarc^0,88 [Ω; G in mm, Iarc in A]. La corrente
   d'arco è la soluzione di Iarc = Vsys/(Rsys + Rarc(Iarc)), unica perché
   Rsys·I + (20 + 0,534·G)·I^0,12 − Vsys è crescente (bisezione). Potenza
   Parc = Iarc²·Rarc = Varc·Iarc ed energia irradiata su una sfera
   E = Parc·Tarc/(4π·D²) [J/cm², D in cm], cioè 0,019·Varc·Iarc·Tarc/D² in
   cal/cm². Non si usa 0,01·Varc·Iarc·Tarc/D²: il coefficiente 0,01 di Doan
   contiene già il fattore 0,5 della massima potenza (Vsys·Iarc = 2·Parc) e
   dimezzerebbe l'energia. Con Rarc = Rsys il metodo ritrova quello di Doan
   (rapporto 1/(0,02·4π·4,184) = 0,951, verificato nei test).
3. **Arco in involucro**: le formule valgono all'aperto; per l'arco in una
   cella NFPA 70E (D.5.1, sulla base delle prove in c.a. di Wilkins sull'arco
   in una scatola) indica prudente un moltiplicatore fino a 3. Il fattore è
   `dc_enclosure_factor`: default 3 per le configurazioni in cella, 1 per VOA
   e HOA.

Il confine è la distanza a cui l'energia vale 1,2 cal/cm² (E ∝ 1/D²). Il
tempo d'arco è quello della protezione alla corrente d'arco (un dispositivo
`device` vede tutta la corrente d'arco, salvo `current_ratio`). Il risultato
riporta anche Rsys, Rarc e la tensione d'arco.

## Corrente franca Ibf

Opzione `ibf` di `arc_flash_study` (riga di comando `--ibf`):

- `iec60909` (default): I"k trifase IEC 60909 del caso richiesto (`max`, con
  cmax, o `min`, con cmin);
- `c1`: la stessa corrente riscalata a c = 1, cioè I"k/c del nodo. Con il
  metodo della sorgente equivalente I"k = c·Un/(√3·|Zk|) è proporzionale a c
  (i contributi di motori e generatori sono nell'impedenza Zk), quindi I"k/c
  è la corrente simmetrica alla tensione nominale, più vicina alla corrente
  franca "senza fattore di tensione" della prassi IEEE. Restano nelle
  impedenze i fattori di correzione K_T, K_G, K_S che contengono cmax;
- `ibf_ka` del punto: valore imposto, ha sempre la precedenza.

Il risultato indica l'origine in `ibf_source`.

## Calcolo a più intervalli

La corrente di guasto può diminuire durante l'arco (contributo dei motori che
si esaurisce, apertura di un'altra alimentazione). Il punto può indicare:

- `motor_decay_ms`: primo intervallo con la I"k completa fino a quel tempo,
  poi la I"k ricalcolata su una copia della rete **senza motori**; anche la
  quota di corrente vista dal dispositivo è ricalcolata sulla rete senza
  motori;
- `steps`: intervalli espliciti `[{"ibf_ka", "duration_ms", "current_ratio"}]`;
  l'ultimo dura fino all'eliminazione dell'arco.

Procedura, per la corrente d'arco piena e per quella ridotta:

1. correnti d'arco di ogni intervallo con la sua Ibf;
2. **tempo di eliminazione dal consumo** della protezione: nell'intervallo k
   la protezione consuma Δt_k/t(I_k), dove t(I_k) è il suo tempo di intervento
   con corrente costante I_k; l'arco è eliminato quando Σ Δt_k/t(I_k) = 1.
   Negli intervalli in cui la protezione non interviene non c'è consumo; la
   durata totale resta limitata a `max_time_ms`. Con un solo intervallo il
   risultato coincide con il tempo di intervento;
3. **energia totale = somma** delle energie degli intervalli. Sopra 600 V si
   sommano le energie intermedie a 600, 2700 e 14 300 V, si ricavano i confini
   intermedi dalle somme e poi si interpola, come in arcflash-calc
   (`multistep.py`); fino a 600 V si somma l'energia finale;
4. **confine dalla somma**: nelle eq. 3–6 l'energia dipende dalla distanza
   solo con il fattore D^k12, quindi D_B = D·(E_B/E)^(1/k12) (per un
   intervallo coincide con le eq. 7–10).

Con Lee energie e argomento del confine si sommano direttamente. Il dettaglio
degli intervalli (Ibf, Iarc, durata, energia) è nel risultato (`steps`) e in
una tabella del rapporto.

## Sotto 240 V

Per i punti con Voc < 0,24 kV il risultato contiene un avviso quando:

- i trasformatori che alimentano il nodo hanno in tutto meno di 125 kVA
  (l'arco può non autosostenersi). Sono i trasformatori con il lato
  secondario sui nodi collegati al punto da sole linee (stesso livello di
  tensione: il trasformatore sul nodo o a monte nella rete radiale);
- Ibf < 2 kA (arco sostenuto poco probabile secondo la IEEE 1584-2018).

Il calcolo viene comunque eseguito: il risultato è cautelativo e la decisione
spetta al progettista.

## Risultati

Per ogni punto sono calcolati:

- metodo, origine di Ibf, avvisi;
- corrente d'arco, tempo, energia e confine per il caso pieno e per quello
  ridotto (un solo caso con Lee e in c.c.), con il dettaglio degli
  intervalli;
- l'energia determinante in cal/cm²;
- la categoria DPI secondo NFPA 70E (1: ≤ 4, 2: ≤ 8, 3: ≤ 25, 4: ≤ 40
  cal/cm²), solo a titolo indicativo.

## Validazione

- **Esempi svolti dell'allegato D della norma:**
  - D.1, quadro 4,16 kV VCB, Ibf 15 kA, 197/223 ms;
  - D.2, quadro 480 V VCB, Ibf 45 kA, 61,3/319 ms.

  Tutti i valori intermedi e finali coincidono con le cifre pubblicate:
  correnti d'arco, dimensioni equivalenti, CF, VarCF, energie e confini.
- **Confronto con [arcflash-calc](https://github.com/LiaungYip/arcflash)** 0.1.0
  (licenza MIT), implementazione open source indipendente:
  - griglia di 864 casi: 5 configurazioni, 13 tensioni da 208 V a 15 kV, 5
    involucri (tipico, poco profondo, grande, oltre i 1244,6 mm), 3 correnti,
    caso pieno e ridotto;
  - correnti, CF ed energie coincidono entro 1e-12, i confini entro 1e-9.

  `arcflash-calc` ricava il confine invertendo l'energia, mentre
  `iec60909` usa direttamente le eq. 7–10: il confronto verifica quindi anche
  l'equivalenza delle due forme.
- I coefficienti delle tabelle 1–8 e 10 sono quelli della norma, come trascritti
  in `arcflash-calc`. Le tabelle 1–5 e 7 sono verificate dagli esempi
  dell'allegato D solo per la configurazione VCB. Per le altre configurazioni
  il riscontro è il confronto con `arcflash-calc`, che usa le stesse tabelle:
  conferma le equazioni, non la trascrizione dei coefficienti.
- **Estensioni** (`tests/test_arcflash_estensioni.py`):
  - Lee: calcoli a mano di energia e confine, anche a più intervalli, e
    scelta automatica sul nodo MT a 20 kV dell'esempio;
  - c.c.: calcoli a mano con Doan (250 V, 4 kA, 1 s, 45,72 cm: 2,39 cal/cm²
    all'aperto, 7,18 in cella), con Stokes-Oppenlander (punto fisso
    Iarc = Vsys/(Rsys + Rarc), energia Parc·T/(4πD²), confine) e coerenza dei
    due metodi alla massima potenza; punti in c.c. sulla rete con tempo fisso e
    con fusibile;
  - calcolo a più intervalli: confronto con `multistep_E_and_AFB` di
    arcflash-calc a 0,208, 0,48, 4,16 e 13,8 kV, corrente piena e ridotta
    (energie entro 1e-12, confini entro 1e-9); due intervalli uguali danno
    lo stesso risultato di un intervallo solo; consumo della protezione con
    curva VI calcolato a mano; decadimento dei motori sulle cabine d'esempio
    (Ibf ricalcolata sulla rete senza motori, energia = somma dei due
    intervalli);
  - Ibf con c = 1, Ibf imposta e opzione `--ibf` della riga di comando;
  - punto protetto da un fusibile (tempo dalla curva per punti, con la quota
    di corrente che attraversa il fusibile, caso ridotto più lento);
  - avvisi sotto 240 V con trasformatore da 100 kVA (sì) e 300 kVA (no).

## Limiti

- **Trascrizione delle tabelle**: i coefficienti delle tabelle 1–8 e 10 sono
  verificati con gli esempi dell'allegato D solo per VCB; per le altre
  configurazioni il riscontro con arcflash-calc conferma le equazioni ma non
  la trascrizione. La verifica completa richiede il testo della norma.
- **Fonti non consultate direttamente**: le formule di Lee e dell'allegato D.5
  di NFPA 70E sono riprese dalla letteratura citata, con verifiche
  dimensionali e di coerenza (energia di Lee in J/cm², Iarc in A nella formula
  di Doan, energia Parc·T/(4πD²) per Stokes-Oppenlander, fattore 3 per l'arco
  in involucro, criterio dei 2 kA sotto 240 V); vanno riscontrate sul testo
  delle edizioni in vigore.
- **Lee** è un modello teorico molto cautelativo (corrente d'arco = Ibf,
  nessun effetto dell'involucro); non c'è un modello empirico oltre 15 kV.
- **Corrente continua**: niente rete in c.c. (Ibf o Rsys sono dati del punto),
  niente sorgenti con contributo variabile nel tempo (batterie, raddrizzatori,
  condensatori) né calcolo a più intervalli; il fattore 3 per l'arco in cella
  è un'indicazione prudenziale, non un modello.
- **Ibf con c = 1**: si ottiene scalando I"k per 1/c; le impedenze restano
  quelle IEC 60909 con i fattori di correzione K_T, K_G e K_S, quindi non è la
  corrente di un'analisi IEEE "pura" (es. ANSI C37 o flusso di potenza prima
  del guasto).
- **Più intervalli**: il consumo Σ Δt_k/t(I_k) = 1 tratta il tempo di
  apertura dell'interruttore come parte della curva (approssimazione per i
  relè con tempo d'interruttore separato) e non modella la memoria termica o
  d'induzione reale del dispositivo; con `motor_decay_ms` il contributo dei
  motori scompare a gradino (niente decadimento esponenziale continuo); con
  `steps` le correnti sono imposte.
- **Sotto 240 V** il risultato è solo segnalato: la decisione se l'arco si
  autosostiene resta al progettista.
