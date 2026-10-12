# Come contribuire

Questa guida spiega come aprire un nuovo progetto, come organizzare i file e
come registrare il lavoro su GitHub. Valgono anche i [Principi](README.md#principi)
del README.

## Aprire un nuovo progetto

1. Aggiorna la copia locale: `git pull`.
2. Copia il modello nella cartella di lavoro:

   ```bash
   cp -r Wiki_Progettazione/PROGRAMMAZIONE/_MODELLO_PROGETTO \
         Wiki_Progettazione/PROGRAMMAZIONE/<NomeProgetto>
   ```

   Su Windows (PowerShell):

   ```powershell
   Copy-Item -Recurse Wiki_Progettazione\PROGRAMMAZIONE\_MODELLO_PROGETTO `
                      Wiki_Progettazione\PROGRAMMAZIONE\<NomeProgetto>
   ```

3. Compila il `README.md` del progetto: obiettivo, target (applicazione,
   versione, piattaforma, dove si trova), stato e conclusioni.
4. Aggiungi una riga alla tabella "Progetti" in
   [`Wiki_Progettazione/PROGRAMMAZIONE/README.md`](Wiki_Progettazione/PROGRAMMAZIONE/README.md)
   e in quella del [README principale](README.md#progetti).
5. Fai commit e push del progetto appena aperto.

## Nomi e struttura delle cartelle

Sono accettati due stili di nome:

- **descrittivo** (preferito), es. `Electrical_Power_Simulator_Software`;
- **datato**, `AAAA-MM_nome-progetto`, es. `2026-10_ricerca-note`, come
  suggerito nel modello.

In entrambi i casi niente spazi né caratteri accentati: usa `_` o `-`.

Ogni progetto ha questa struttura:

```
<NomeProgetto>/
├── README.md          ← obiettivo, target, stato, conclusioni
├── analisi/           ← note di analisi (un file Markdown per passo)
└── implementazione/   ← codice e test
```

## Documentazione attesa

- **`analisi/`**: un file Markdown per ogni passo, numerato
  (es. `01_iec60909_formule.md`), con il comando o la fonte usata (comando REA,
  norma, articolo), gli estratti rilevanti (non dump completi), le evidenze, i
  limiti e le domande aperte.
- **`implementazione/`**: codice con un `README.md` che spiega installazione,
  uso, formato dei dati e come eseguire i test. Ogni funzione importante deve
  avere test che la confrontino con riferimenti indipendenti (calcoli a mano,
  altre implementazioni, esempi delle norme).
- **README del progetto**: tieni aggiornate la lista di stato e le
  conclusioni, con rimandi ai file in `analisi/`.

## Messaggi di commit

- In italiano, all'imperativo o alla terza persona presente, come nella
  cronologia esistente (es. `Aggiunge Ghidra 12.1.4 per l'analisi di binari nativi`).
- Oggetto breve (circa 70 caratteri al massimo), senza punto finale; se il
  commit riguarda un modulo, indicalo come prefisso
  (es. `IEC 60909: test e validazione contro pandapower`).
- Dopo una riga vuota, un corpo che spiega **perché** la modifica è stata
  fatta, non solo cosa cambia.
- Un commit per ogni passo significativo: meglio tanti commit piccoli e
  coerenti che uno solo alla fine.

## Cosa non versionare mai

- binari ed eseguibili (`*.exe`, `*.dll`, `*.so`, `*.dylib`, `*.apk`, `*.asar`…);
- installer e archivi da analizzare (`.zip`, `.msi`, `.7z`…): restano fuori dal
  repository, e nel README del progetto si annotano provenienza e versione;
- output pesanti di REA (`*.rea-evidence/`, `rea-output/`);
- credenziali, chiavi, token, password, file di licenza di software terzi;
- file generati e cache (`node_modules/`, `dist/`, `build/`, `__pycache__/`,
  `*.pyc`, `.pytest_cache/`) e file di sistema/editor.

Le regole principali sono già in [`.gitignore`](.gitignore); prima di ogni
commit controlla comunque `git status`.

## Test dei progetti Python

Dalla cartella `implementazione/` del progetto:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[test]"
python -m pytest
```

Ad esempio, per il modulo `iec60909`:

```bash
cd Wiki_Progettazione/PROGRAMMAZIONE/Electrical_Power_Simulator_Software/implementazione
pip install -e ".[test]"
python -m pytest
```

Prima di aprire una pull request tutti i test devono passare.

## Pull request e segnalazioni

- Le sessioni cloud lavorano su un branch dedicato e aprono una pull request
  usando il modello in `.github/pull_request_template.md`.
- Per proporre un nuovo progetto o segnalare un errore usa i modelli di issue
  ("Nuovo progetto", "Segnalazione di errore").

## Stile dei file

Il file [`.editorconfig`](.editorconfig) definisce codifica UTF-8, fine riga
LF e indentazione (4 spazi per Python, 2 per JSON, YAML e Markdown). La
maggior parte degli editor lo applica automaticamente.
