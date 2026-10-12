# PROGRAMMAZIONE

Cartella di lavoro principale del repository: contiene un progetto per
cartella, di reverse engineering (con [REA](https://github.com/morluto/rea) e
Ghidra) o di sviluppo di software tecnico a partire dalle norme pubbliche.
Presentazione generale, strumenti e principi sono nel
[README principale](../../README.md).

Questa cartella è sincronizzata tra:

- **PC locale**: `C:\Users\pietr\Workspace\02_TECNICO\Reverse_Engineering\Wiki_Progettazione\PROGRAMMAZIONE`
- **GitHub**: `gioorom/Reverse_Engineering` → `Wiki_Progettazione/PROGRAMMAZIONE/`

## Nuovo progetto

1. Copia `_MODELLO_PROGETTO/` in una nuova cartella con un nome descrittivo
   senza spazi (es. `Electrical_Power_Simulator_Software`) oppure nella forma
   `AAAA-MM_nome-progetto`.
2. Compila il `README.md` del progetto (obiettivo, target, stato).
3. Salva i passi di analisi in `analisi/` e il codice con i test in
   `implementazione/`.
4. Aggiungi il progetto alla tabella qui sotto e fai commit e push a ogni
   passo significativo.

I dettagli sono in [`CONTRIBUTING.md`](../../CONTRIBUTING.md). I binari, gli
installer e gli archivi da analizzare restano fuori dal repository: nel README
del progetto annota solo dove si trovano e la versione.

## Progetti

| Progetto | Target | Stato |
| -------- | ------ | ----- |
| [Electrical Power Simulator Software](Electrical_Power_Simulator_Software/) | Simulatore reti elettriche (ispirato a ETAP) | Cortocircuito IEC 60909 implementato e testato |
