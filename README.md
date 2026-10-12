# Reverse_Engineering

Repository di lavoro per reverse engineering con
[REA – Reverse Engineer Anything](https://github.com/morluto/rea), condiviso
tra il PC locale e le sessioni Claude Code nel cloud.

## Struttura

```
Wiki_Progettazione/
└── PROGRAMMAZIONE/   ← cartella di lavoro principale
.mcp.json             ← registra REA come server MCP per Claude Code
CLAUDE.md             ← istruzioni per Claude
```

## Setup sul PC (Windows)

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

Per l'analisi di binari nativi serve un motore: Ghidra (gratuito, imposta
`GHIDRA_INSTALL_DIR`), IDA o Hopper. L'analisi di JavaScript/Electron, .NET e
siti web non richiede motori esterni.

## Sincronizzazione PC ↔ GitHub ↔ cloud

- Prima di iniziare: `git pull`
- Alla fine: `git add -A && git commit -m "..." && git push`

Le sessioni cloud lavorano su un branch dedicato e aprono una pull request:
dopo il merge, sul PC basta `git pull`.
