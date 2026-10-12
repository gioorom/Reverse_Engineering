# PROGRAMMAZIONE

Cartella di lavoro principale per le attività di programmazione e reverse
engineering con [REA](https://github.com/morluto/rea).

Questa cartella è sincronizzata tra:

- **PC locale**: `C:\Users\pietr\Workspace\02_TECNICO\Reverse_Engineering\Wiki_Progettazione\PROGRAMMAZIONE`
- **GitHub**: `gioorom/Reverse_Engineering` → `Wiki_Progettazione/PROGRAMMAZIONE/`

## Nuovo progetto

1. Copia `_MODELLO_PROGETTO/` in una nuova cartella `AAAA-MM_nome-progetto`.
2. Compila il `README.md` del progetto (obiettivo, target, stato).
3. Salva i passi di analisi in `analisi/` e il codice in `implementazione/`.

I binari, gli installer e gli archivi da analizzare restano fuori dal
repository: nel README del progetto annota solo dove si trovano e la versione.

## Progetti

| Progetto | Target | Stato |
| -------- | ------ | ----- |
| [ETAP_Power_Simulator](ETAP_Power_Simulator/) | ETAP Power Simulator (Windows) | Cortocircuito IEC 60909 reimplementato e testato |
