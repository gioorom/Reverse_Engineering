# Reverse_Engineering

Spazio di lavoro per il reverse engineering e lo
sviluppo di software tecnico per l'ingegneria elettrica. Qui si studiano
applicazioni, file e funzionalità con strumenti di analisi
([REA](https://github.com/morluto/rea), Ghidra) e si sviluppano strumenti
propri, preferibilmente reimplementando le funzioni a partire dalle norme
tecniche pubbliche. Il repository è condiviso tra il PC Windows dell'ufficio e
le sessioni Claude Code nel cloud, e GitHub fa da punto di sincronizzazione.

## A cosa serve

- **Capire come funziona un software o un formato di file** (interoperabilità,
  documentazione, recupero di dati) usando REA e Ghidra su copie con licenza.
- **Sviluppare software tecnico proprio**, ad esempio calcoli elettrici
  secondo le norme IEC, con codice testato e documentato.
- **Tenere traccia del lavoro**: ogni progetto ha una cartella con analisi,
  evidenze, codice e test, versionata su GitHub e sempre consultabile.

## Contenuto del repository

```
Reverse_Engineering/
├── README.md                 ← questa pagina
├── CONTRIBUTING.md           ← come aprire un progetto e contribuire
├── CHANGELOG.md              ← cronologia delle modifiche
├── LICENSE                   ← licenza MIT
├── CLAUDE.md                 ← istruzioni e flusso di lavoro per Claude Code
├── .mcp.json                 ← registra REA come server MCP per Claude Code
├── .gitignore                ← esclude binari, archivi di analisi, file temporanei
├── .editorconfig             ← stile dei file (UTF-8, LF, indentazione)
├── .github/                  ← modelli per pull request e segnalazioni
├── scripts/
│   └── setup-cloud.sh        ← installa REA + Ghidra nelle sessioni cloud
└── Wiki_Progettazione/
    └── PROGRAMMAZIONE/       ← cartella di lavoro principale
        ├── README.md         ← indice dei progetti
        ├── _MODELLO_PROGETTO/← modello da copiare per ogni nuovo progetto
        └── <NomeProgetto>/   ← un progetto per cartella
            ├── README.md     ← obiettivo, target, stato, conclusioni
            ├── analisi/      ← note di analisi con evidenze
            └── implementazione/ ← codice e test
```

## Progetti

| Progetto | Descrizione | Stato |
| -------- | ----------- | ----- |
| [Electrical Power Simulator Software](Wiki_Progettazione/PROGRAMMAZIONE/Electrical_Power_Simulator_Software/) | Simulatore di reti elettriche ispirato a ETAP Power Simulator, ricostruito dalle norme tecniche pubbliche (nessuna decompilazione di software commerciale). Pacchetto Python `iec60909`: correnti di cortocircuito secondo IEC 60909-0:2016, flusso di potenza (Newton-Raphson), arc flash secondo IEEE 1584-2018 e coordinamento delle protezioni, validati con calcoli a mano, con pandapower e (cortocircuito) con gli studi della demo di ETAP. | Cortocircuito IEC 60909, flusso di potenza, arc flash IEEE 1584 e coordinamento delle protezioni implementati e testati |

L'elenco aggiornato è anche in
[`Wiki_Progettazione/PROGRAMMAZIONE/README.md`](Wiki_Progettazione/PROGRAMMAZIONE/README.md).

## Flusso di lavoro

1. **Richiesta**: si indica cosa analizzare o sviluppare (un'applicazione, un
   file, un sito, una funzionalità, un calcolo).
2. **Cartella di progetto**: si crea
   `Wiki_Progettazione/PROGRAMMAZIONE/<NomeProgetto>/` copiando
   `_MODELLO_PROGETTO/`, e si lavora solo lì.
3. **Avanzamento su GitHub**: a ogni passo significativo (analisi completata,
   conclusione, pezzo di implementazione con test) si fa commit e push, non
   solo alla fine; si aggiorna la tabella dei progetti.

I dettagli operativi per Claude Code sono in [`CLAUDE.md`](CLAUDE.md); le
convenzioni per chi contribuisce sono in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Strumenti

| Strumento | Uso | Note |
| --------- | --- | ---- |
| [REA – Reverse Engineer Anything](https://github.com/morluto/rea) | Analisi di applicazioni JavaScript/Electron, .NET, siti web e binari nativi | Pacchetto npm `rea-agents@6.4.0`, registrato come server MCP in `.mcp.json` |
| [Ghidra 12.1.4](https://github.com/NationalSecurityAgency/ghidra) | Motore per l'analisi dei binari nativi usato da REA | Richiede JDK 21 a 64 bit e la variabile `GHIDRA_INSTALL_DIR` |
| Python 3.10+ | Implementazioni e test dei progetti (es. `iec60909`) | numpy; pytest e pandapower per i test |

## Setup sul PC Windows

Requisiti: Git, Node.js 22.19+ (o 24.11+), Claude Code.

La cartella `Wiki Progettazione` sul PC deve diventare (o contenere) un clone di
questo repository. Da PowerShell:

```powershell
cd C:\Users\pietr\Workspace\02_TECNICO
git clone https://github.com/gioorom/Reverse_Engineering.git
# copia eventuali file già presenti nella vecchia cartella PROGRAMMAZIONE in:
#   Reverse_Engineering\Wiki_Progettazione\PROGRAMMAZIONE\

npm install --global rea-agents@6.4.0
rea setup --client claude_code   # registra REA e installa la skill
rea doctor                       # verifica

cd Reverse_Engineering
claude
```

Per l'analisi di binari nativi serve Ghidra 12.1.4 (gratuito):
scarica `ghidra_12.1.4_PUBLIC_20260921.zip` dalle
[release ufficiali](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build),
estrailo (es. in `C:\tools\`), installa un JDK 21 a 64 bit e imposta la
variabile d'ambiente utente:

```powershell
setx GHIDRA_INSTALL_DIR "C:\tools\ghidra_12.1.4_PUBLIC"
```

Poi riapri il terminale e verifica con `rea doctor`. L'analisi di
JavaScript/Electron, .NET e siti web non richiede motori esterni.

Per i progetti Python (es. `iec60909`) serve Python 3.10 o successivo; le
istruzioni di installazione e test sono nel README di ciascun progetto.

## Sessioni cloud

Il container delle sessioni Claude Code nel cloud è temporaneo: a ogni nuova
sessione esegui (o inserisci nello script di setup dell'ambiente)

```bash
bash scripts/setup-cloud.sh
```

Lo script è idempotente: installa `rea-agents@6.4.0` e Ghidra 12.1.4 in
`/opt/ghidra_12.1.4_PUBLIC` (verificando l'hash SHA-256 dell'archivio) e salta
i passi già fatti. Richiede un JDK 21+.

## Sincronizzazione

PC, GitHub e cloud restano allineati tramite git:

- prima di iniziare: `git pull`
- alla fine (o a ogni passo significativo):
  `git add -A && git commit -m "..." && git push`

Le sessioni cloud lavorano su un branch dedicato e aprono una pull request:
dopo il merge, sul PC basta `git pull`.

## Principi

- **Solo copie con licenza**: si analizzano esclusivamente programmi e file
  di cui si possiede una copia legittima.
- **Quadro normativo**: l'analisi rientra nei limiti della Direttiva
  2009/24/CE sulla tutela giuridica dei programmi per elaboratore, in
  particolare l'art. 5, par. 3 (osservare, studiare e sperimentare il
  funzionamento di un programma per determinarne idee e principi) e l'art. 6
  (decompilazione consentita solo se indispensabile per ottenere le
  informazioni necessarie all'interoperabilità, e nei limiti ivi previsti).
- **Nessun binario nel repository**: eseguibili, librerie, installer e archivi
  da analizzare restano fuori da git (vedi `.gitignore`); nel README del
  progetto si annotano solo provenienza e versione.
- **Prima le norme pubbliche**: quando l'obiettivo è ottenere una funzione
  (come un calcolo elettrico), si preferisce reimplementarla dalle norme
  tecniche e dalla letteratura pubblica invece di decompilare software
  commerciale, come avviene in Electrical Power Simulator Software.
- **Evidenze verificabili**: ogni conclusione rimanda alle note in `analisi/`,
  e ogni implementazione ha test che ne confrontano i risultati con
  riferimenti indipendenti.

## Licenza

Distribuito con licenza [MIT](LICENSE): il contenuto può essere usato,
modificato e redistribuito liberamente, mantenendo l'avviso di copyright.

I calcoli sono forniti "così come sono", senza garanzie (vedi la licenza):
i risultati vanno sempre verificati da un tecnico abilitato prima di essere
usati per progettazione o dimensionamento.
