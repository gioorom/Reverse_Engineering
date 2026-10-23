# CP Faggiano 150/20 kV — Sezione AT

## Obiettivo

Modello 3D della sezione AT della cabina primaria Enel Distribuzione di Faggiano (sezione A-A, P-006): ogni organo è un componente separato con materiale e attributi BIM (IfcClass, Tag, Stallo), pronto per una futura integrazione con Revit.

## Dove si trova

| Cosa | Dove |
| --- | --- |
| Modello Fusion | progetto Fusion "Progetti AI" → `CP_Faggiano_Sezione_AT_A-A` (v10) |
| STEP di partenza per SolidCraft | `01_COMMESSE\CP_Faggiano_TA\Seazione AT STEP.step` |
| Modello con muro tagliafiamme | `modelli/CP_Faggiano_Sezione_AT_muro_tagliafiamme.solidcraft` e `.step` |

## Contenuto

- `analisi/scheda_impianto_CP_Faggiano.md` — griglia, organi, materiali, verifiche, punti aperti
- `analisi/muro_tagliafiamme.md` — dimensionamento e norma del muro tagliafiamme
- `analisi/stallo_AA_parametri.json` — quote e parametri dello stallo
- `implementazione/fusion/` — script nell'ordine: `fusion_stallo_AA.py`, `update_TR_matelec.py`, `fase2_stallo2_castelletto.py`, `fase3_dettaglio_materiali.py`, `fase3b_nomi_materiali.py`, `fase4_armadi_comando.py`, `fase5_sezionatore_terra.py`
- `implementazione/solidcraft/` — `sc.py` (client MCP) e `muro_tagliafiamme_solidcraft.json`

## Uso di SolidCraft via MCP

1. Avvia SolidCraft con il controllo remoto: `"C:\Program Files\SolidCraft\solidcraft.exe" --control 7878`
2. Esegui: `python sc.py muro_tagliafiamme_solidcraft.json` (apre lo STEP con `up: y`, crea parametri, muro, fondazione, materiale e attributi BIM).

## Stato

- [x] Stalli linea e trafo, sbarre, stallo 2 (Fusion)
- [x] Passanti AT e castelletti MT, materiali
- [x] Armadio di comando unico per interruttore e sezionatori
- [x] Sezionatori di linea con lame di terra
- [x] Muro tagliafiamme TR1/TR2 REI 120 (SolidCraft)
- [ ] Planimetria P-001, disegni GE, vasca olio, rete di terra (vedi punti aperti nella scheda)
