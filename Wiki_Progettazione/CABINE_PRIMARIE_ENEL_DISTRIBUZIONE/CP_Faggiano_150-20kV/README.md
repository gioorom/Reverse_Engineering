# CP Faggiano 150/20 kV — Sezione AT

## Obiettivo

Modello 3D della sezione AT della cabina primaria Enel Distribuzione di Faggiano (sezione A-A, P-006): ogni organo è un componente separato con materiale e attributi BIM (IfcClass, Tag, Stallo), pronto per una futura integrazione con Revit.

## Dove si trova

| Cosa | Dove |
| --- | --- |
| Modello Fusion | progetto Fusion "Progetti AI" → `CP_Faggiano_Sezione_AT_A-A` (v10) |
| STEP di partenza per SolidCraft | `01_COMMESSE\CP_Faggiano_TA\Seazione AT STEP.step` |
| Modello SolidCraft finale | `modelli/CP_Faggiano_Sezione_AT.solidcraft` e `.step` |
| Base per la ricostruzione | `modelli/CP_Faggiano_Sezione_AT_base_SolidCraft.step` (castelletti già sul lato esterno) |

## Contenuto

- `analisi/scheda_impianto_CP_Faggiano.md` — griglia, organi, materiali, verifiche, punti aperti
- `analisi/muro_tagliafiamme.md` — dimensionamento e norma del muro tagliafiamme
- `analisi/stallo_AA_parametri.json` — quote e parametri dello stallo
- `implementazione/fusion/` — script nell'ordine: `fusion_stallo_AA.py`, `update_TR_matelec.py`, `fase2_stallo2_castelletto.py`, `fase3_dettaglio_materiali.py`, `fase3b_nomi_materiali.py`, `fase4_armadi_comando.py`, `fase5_sezionatore_terra.py`
- `implementazione/solidcraft/` — `scl.py` e `sc.py` (client MCP), `muro_tagliafiamme_solidcraft.json`, `tr2_specchio.py`, `build_finale.py`

## Uso di SolidCraft via MCP

1. Avvia SolidCraft con il controllo remoto: `"C:\Program Files\SolidCraft\solidcraft.exe" --control 7878`
2. Esegui: `python sc.py muro_tagliafiamme_solidcraft.json` (apre lo STEP con `up: y`, crea parametri, muro, fondazione, materiale e attributi BIM).
3. Esegui: `python tr2_specchio.py` (porta il castelletto MT del TR2 sul lato esterno e centra il muro), poi esporta lo STEP.
4. Modello finale: `python build_finale.py modelli\CP_Faggiano_Sezione_AT_base_SolidCraft.step modelli` (armadi TR a sinistra, muro parametrico, attributi BIM, salvataggio e verifica dopo la riapertura).

Nota: SolidCraft 0.20 non riapre correttamente le operazioni (copia, specchio) fatte su corpi di componenti annidati in uno STEP importato; per questo il modello finale parte da uno STEP senza storia.

## Stato

- [x] Stalli linea e trafo, sbarre, stallo 2 (Fusion)
- [x] Passanti AT e castelletti MT, materiali
- [x] Armadio di comando unico per interruttore e sezionatori
- [x] Sezionatori di linea con lame di terra
- [x] Muro tagliafiamme TR1/TR2 REI 120, centrale (SolidCraft)
- [x] Castelletto MT del TR2 (Verde) sul lato esterno (SolidCraft, `tr2_specchio.py`)
- [x] Armadi dei TR sulla sinistra di entrambi i trafo (SolidCraft, `build_finale.py`)
- [ ] Il modello Fusion ha ancora il castelletto del TR2 sul lato interno
- [ ] Planimetria P-001, disegni GE, vasca olio, rete di terra (vedi punti aperti nella scheda)
