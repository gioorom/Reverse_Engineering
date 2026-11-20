# Istruzioni per Claude

Lingua di lavoro: italiano.

## Flusso di lavoro

1. L'utente fornisce qualcosa da analizzare (applicazione, file, sito, funzionalità).
2. Crea una sottocartella dedicata in `Wiki_Progettazione/PROGRAMMAZIONE/`
   (nome: il programma, es. `Wiki_Progettazione/PROGRAMMAZIONE/NomeProgramma/`)
   partendo da `_MODELLO_PROGETTO/`, e lavora solo lì.
3. Mentre lavori, carica i progressi su GitHub (`gioorom/Reverse_Engineering`):
   commit e push a ogni passo significativo (analisi completata, conclusione,
   pezzo di implementazione), non solo alla fine.
4. Aggiorna la tabella "Progetti" in `Wiki_Progettazione/PROGRAMMAZIONE/README.md`.

## Strumenti

- Reverse engineering: REA (`rea-agents`), registrato come server MCP in
  `.mcp.json`. Se gli strumenti MCP non sono disponibili usa la CLI `rea`
  (o `npx -y rea-agents@6.10.1 <comando>`).
- Binari nativi: Ghidra 12.2 con JDK 25 (REA legge il JDK da `JAVA_HOME`).
  In una sessione cloud, se `rea doctor` non trova Ghidra o `rea` manca,
  esegui prima `bash scripts/setup-cloud.sh` e imposta
  `GHIDRA_INSTALL_DIR=/opt/ghidra_12.2_PUBLIC` e
  `JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64`. Il server MCP avviato con la
  sessione eredita il JDK 21 dell'ambiente: per i binari nativi usa la CLI
  `rea` con quelle variabili.
- Non versionare binari, eseguibili, installer o archivi da analizzare
  (vedi `.gitignore`): tienili fuori dal repository (in una sessione cloud,
  nella scratchpad) e documenta nel README del progetto da dove provengono e
  la versione.
