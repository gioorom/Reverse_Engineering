# Changelog

Tutte le modifiche rilevanti del repository sono registrate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).
Il repository non ha ancora versioni rilasciate.

## Non rilasciato

### 2026-10-15

#### Modificato

- REA aggiornato da `rea-agents@6.4.0` a `rea-agents@6.5.0` (`.mcp.json`,
  `scripts/setup-cloud.sh`, `README.md`, `CLAUDE.md`). Requisiti invariati
  (Node 22.19+, Ghidra 12.1.4, JDK 21); `rea doctor` riconosce Ghidra.
  Modifiche incompatibili della 6.5.0 solo nella forma di alcuni risultati
  (campi che possono valere `null`, `get_call_graph`, `--filter-output`).

### 2026-10-14

#### Aggiunto

- Portate IEC 60287 dei cavi tripolari con schermi separati sulle anime e
  armatura a fili in acciaio o acciaio inossidabile: cordatura delle anime,
  perdite nell'armatura, fattore geometrico dei riempitivi, secondo le
  indicazioni della CIGRE TB 880; verifica sui casi sottomarini a 30 kV e
  220 kV (opzione `layup_on_conductor` per la cordatura sul conduttore).

- Dimensionamento dei cavi: circuiti monofase (campo `phases`), con portata a
  2 conduttori caricati e caduta di tensione fase-neutro.
- Affidabilità: verifica facoltativa delle contro-alimentazioni con il flusso
  di potenza (`check_transfer`, `--verifica-contro-alimentazione`); le
  manovre che superano la tensione minima o il carico ammesso dei rami sono
  respinte e i carichi attendono la manovra successiva o la riparazione.
- Affidabilità: mancato intervento di interruttori e fusibili
  (`stuck_probability`, `--mancato-intervento`) con intervento della
  protezione di riserva e restituzione dopo l'apertura manuale.
- Affidabilità: guasto durante la manutenzione di un altro elemento
  (`maintenance_rate`, `maintenance_time_h`), formule di Billinton–Allan.

#### Corretto

- Avviamento dei motori: legenda del grafico SVG spostata sotto il grafico,
  non più sovrapposta alle curve.
- Portate MT: interasse dell'effetto di prossimità per la formazione in
  piano (distanza tra fasi adiacenti, non moltiplicata per √2).

### 2026-10-12

#### Aggiunto

- Portate dei cavi MT/AT secondo IEC 60287 in `iec60909.iec60287`, riga di
  comando `python -m iec60909.portate_mt`: cavi unipolari descritti per
  strati, resistenza in c.a., perdite dielettriche e negli schermi (correnti
  di circolazione e parassite, trifoglio e piano con o senza trasposizione),
  posa interrata, in tubi e in aria (anche in canaletta), mutuo riscaldamento,
  portata del cavo più caldo; collegamento al dimensionamento dei cavi;
  verifica sui casi della CIGRE TB 880.
- Dimensionamento dei cavi BT in `iec60909.cables`, riga di comando
  `python -m iec60909.cavi`: portata con le tabelle dell'allegato B della
  IEC 60364-5-52 e i fattori di correzione (temperatura, terreno,
  raggruppamento), coordinamento con la protezione, caduta di tensione,
  tenuta al cortocircuito (anche del conduttore di protezione) e
  interruzione automatica nei sistemi TN con le correnti IEC 60909, conduttori
  in parallelo, applicazione delle sezioni alla rete; tabelle da trascrizioni
  pubbliche con fonti e confidenza di ogni valore; verifica con calcoli a mano
  ed esempi pubblicati. Nuova funzione `io.network_to_dict`.
- Affidabilità in `iec60909.reliability`, riga di comando
  `python -m iec60909.affidabilita`: analisi dei modi di guasto con
  intervento delle protezioni, sezionamento e contro-alimentazione dai punti
  normalmente aperti, guasti transitori, sovrapposizioni del secondo ordine,
  indici dei carichi e di sistema (SAIFI, SAIDI, CAIDI, ASAI, MAIFI, ENS,
  AENS, costo), contributo di ogni elemento; nuove sezioni `reliability_data`
  e `switches`, clienti e carico medio nei carichi; verifica sul Roy
  Billinton Test System Bus 2 (indici pubblicati), con calcoli a mano,
  Markov e Monte Carlo.
- Avviamento dei motori in `iec60909.motorstart`, riga di comando
  `python -m iec60909.avviamento`: circuito equivalente stimato dai dati di
  targa (anche con la coppia di spunto), avviamento diretto, stella-triangolo,
  autotrasformatore e soft starter con limite di corrente, flusso di potenza
  a ogni passo, caduta di tensione, tempo di avviamento, stallo, verifiche dei
  limiti, grafici; verifica con calcoli a mano e integrazione indipendente.
- Armoniche in `iec60909.harmonics`, riga di comando
  `python -m iec60909.armoniche`: sorgenti di corrente armonica con spettri
  predefiniti o propri, reti di sequenza alla frequenza h·f con gli
  sfasamenti dei trasformatori, tensioni e correnti armoniche, THD, fattore K,
  filtri accordati (anche nel flusso di potenza), scansione in frequenza,
  limiti EN 50160 e IEEE 519 (tensione e correnti al punto di consegna);
  verifica con calcoli a mano e con OpenDSS.
- Stabilità transitoria in `iec60909.stability`, riga di comando
  `python -m iec60909.stabilita`: generatori con modello classico o a un asse,
  regolatori di tensione e di velocità, rete esterna di potenza infinita,
  carichi ad ammettenza costante, eventi (guasto, eliminazione, apertura di
  rami, distacco di generatori, variazioni di carico), tempo critico di
  eliminazione, grafico degli angoli; verifica con il criterio delle aree
  uguali, con un'integrazione indipendente e con ANDES sul sistema di Kundur.
- Coordinamento delle protezioni, estensioni: correnti nei rami per guasti
  trifase, bifase, bifase a terra e monofase con gli sfasamenti dei gruppi
  vettoriali; protezioni di terra (corrente residua); relè direzionali;
  correnti di interruzione Ib (decadimento delle macchine); bande di
  tolleranza; limiti di selettività energetica dei costruttori; convertitori
  pieni e guasti interni ai gruppi di generazione nelle correnti nei rami.
- Flusso di potenza, estensioni: sfasamenti dei gruppi vettoriali; prese e
  magnetizzazione dei trasformatori a tre avvolgimenti; regolazione automatica
  delle prese; regolazione remota della tensione dei generatori; saldo
  distribuito; carichi ZIP; confronto con pandapower.
- Arc flash, estensioni: metodo di Lee oltre 15 kV; arco in corrente continua
  (Doan, Stokes-Oppenlander/Ammerman, NFPA 70E); scelta della corrente Ibf;
  calcolo a più intervalli con decadimento del contributo dei motori;
  avvisi sotto 240 V e sotto 2 kA.
- Coordinamento delle protezioni in `iec60909.coordination`, riga di comando
  `python -m iec60909.coordinamento`: relè IEC 60255-151/IEEE C37.112 con
  soglie a tempo definito, interruttori BT L-S-I, fusibili per punti;
  correnti di guasto nei rami (`fault_currents`), sequenza di intervento,
  selettività anche sull'intero campo di correnti, sensibilità, correnti di
  carico dal flusso di potenza, curve tempo-corrente in SVG; arc flash con il
  tempo di intervento dei dispositivi.
- Arc flash secondo IEEE 1584-2018 in `iec60909.arcflash`, riga di comando
  `python -m iec60909.arco`: corrente d'arco piena e ridotta, fattore
  dell'involucro, energia incidente e confine dell'arco, Ibf dal cortocircuito
  IEC 60909, tempo d'arco da tempo fisso o relè IEC 60255-151; verifica con
  gli esempi dell'allegato D e con arcflash-calc.
- Flusso di potenza (Newton-Raphson) in `iec60909.loadflow`, riga di comando
  `python -m iec60909.flusso`: reti esterne di saldo, generatori PV/PQ con
  limiti di Q, carichi, motori, generatori statici, condensatori, linee con
  capacità, trasformatori con prese e magnetizzazione, trasformatori a tre
  avvolgimenti; confronto con pandapower e soluzione in forma chiusa.
- Deroga del metodo B in `iec60909`: senza il fattore 1,15 quando tutti i
  rami hanno R/X < 0,3; confronto con pandapower.
- Fattore n della corrente termica equivalente Ith in `iec60909`
  (decadimento della componente alternata per i guasti alimentati da un solo
  generatore).
- Trasformatori dei servizi ausiliari dei gruppi di generazione in
  `iec60909`: guasti sul lato ausiliario e nelle reti a valle calcolati con
  K_G,S/K_T,S (trasformatori ausiliari con il loro K_T).
- Avvolgimenti a zig-zag nei trasformatori a due e a tre avvolgimenti e
  trasformatori di messa a terra in `iec60909`.
- Generatori statici in `iec60909`: convertitori pieni (sorgenti di corrente,
  confronto con pandapower) ed eolico a doppia alimentazione (Z_WD).
- Impedenza di guasto Z_F in `iec60909` (in serie a ogni fase guasta) per
  tutte le grandezze; opzioni `--rf`/`--xf`; confronto con pandapower.
- Componente continua i_DC (frequenza equivalente in base a f·t) e corrente
  di interruzione asimmetrica in `iec60909`; confronto con ETAP.
- Gruppi di generazione con trasformatore dedicato in `iec60909`: K_S/K_SO
  per i guasti esterni, K_G,S/K_T,S per i guasti tra generatore e
  trasformatore; confronto con pandapower.
- Ib con i fattori μ e q (formula per reti magliate, tmin a scelta) e Ik con
  la regola delle reti magliate o con λ per i guasti alimentati da un solo
  generatore; confronto con lo studio di duty di ETAP.
- Importatore degli studi di cortocircuito IEC di ETAP (`iec60909.etap`):
  conversione della rete dai database SQLite `.SI2S`/`.SI1S` e confronto dei
  risultati; lo studio SC_909 della demo di ETAP 2024 è riprodotto entro
  lo 0,025 % (lo studio IEC-909 di Example-New entro lo 0,005 % con una
  conversione dedicata).
- Generatori con sequenza inversa di targa e neutro a terra; motori con
  sequenza inversa di targa.
- Analisi della demo di ETAP 2024 e del formato dei suoi file di uscita
  (`analisi/02`–`06`).
- Test automatici su GitHub Actions (Python 3.10 e 3.13).
- Licenza MIT.
- Presentazione del repository: README riscritto, `CONTRIBUTING.md`,
  `CHANGELOG.md`, `.editorconfig`, modelli per pull request e issue in
  `.github/`.
- Progetto Electrical Power Simulator Software: calcolo delle correnti di
  cortocircuito secondo IEC 60909-0:2016 nel pacchetto Python `iec60909`
  (guasti trifase, bifase, bifase a terra e monofase; correnti massime e
  minime; ip con metodi B e C, Ib, Ik, Ith).
- Correzione: correnti di fase del guasto bifase a terra senza percorso verso
  terra (ora pari a I"k2 invece di zero).
- Verifica indipendente dei tre avvolgimenti con 20 test di calcolo a mano;
  controlli espliciti su dati omopolari incoerenti e avvolgimenti a zig-zag.
- Trasformatori a tre avvolgimenti in `iec60909` (schema a stella con
  K_TAB, K_TAC, K_TBC; sequenza zero secondo il gruppo vettoriale), con
  confronto contro pandapower e rete di esempio.
- Test di `iec60909` contro calcoli a mano e validazione contro pandapower su
  una rete magliata 110/20/0,4 kV.
- Documentazione delle formule IEC 60909, istruzioni d'uso e stato del
  progetto.
- Apertura del primo progetto (inizialmente `ETAP_Power_Simulator`).
- Ghidra 12.1.4 per l'analisi di binari nativi, installato nelle sessioni
  cloud da `scripts/setup-cloud.sh`.
- Flusso di lavoro documentato in `CLAUDE.md`.
- Modello `_MODELLO_PROGETTO/` per i progetti in `PROGRAMMAZIONE`.
- Predisposizione del repository per il reverse engineering con REA
  (`rea-agents@6.4.0` registrato come server MCP in `.mcp.json`, `.gitignore`,
  README iniziale).

#### Modificato

- Progetto rinominato da `ETAP_Power_Simulator` a
  `Electrical_Power_Simulator_Software`, per chiarire che si tratta di un
  software proprio ispirato a ETAP e non di un'analisi di ETAP.
