# Changelog

Tutte le modifiche rilevanti del repository sono registrate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).
Il repository non ha ancora versioni rilasciate.

## Non rilasciato

### 2026-10-12

#### Aggiunto

- Presentazione del repository: README riscritto, `CONTRIBUTING.md`,
  `CHANGELOG.md`, `.editorconfig`, modelli per pull request e issue in
  `.github/`.
- Progetto Electrical Power Simulator Software: calcolo delle correnti di
  cortocircuito secondo IEC 60909-0:2016 nel pacchetto Python `iec60909`
  (guasti trifase, bifase, bifase a terra e monofase; correnti massime e
  minime; ip con metodi B e C, Ib, Ik, Ith).
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
