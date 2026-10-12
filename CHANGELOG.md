# Changelog

Tutte le modifiche rilevanti del repository sono registrate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).
Il repository non ha ancora versioni rilasciate.

## Non rilasciato

### 2026-10-12

#### Aggiunto

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
