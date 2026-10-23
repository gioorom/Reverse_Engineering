# CABINE PRIMARIE ENEL DISTRIBUZIONE

Progettazione elettromeccanica di cabine primarie AT/MT secondo gli standard Enel Distribuzione: modelli 3D degli stalli (Autodesk Fusion, SolidCraft), schede impianto, verifiche delle distanze e note normative. Un impianto per cartella.

## Struttura di un impianto

- `analisi/` — schede impianto, note normative, verifiche
- `implementazione/fusion/` — script Python per Autodesk Fusion (mm, parametri in testa)
- `implementazione/solidcraft/` — comandi MCP di SolidCraft (JSON) e client `sc.py`
- `modelli/` — modelli CAD esportati (.step, .solidcraft)
- `immagini/` — viste del modello

## Impianti

| Impianto | Contenuto | Stato |
| --- | --- | --- |
| [CP Faggiano 150/20 kV](CP_Faggiano_150-20kV/) | Sezione AT: 2 stalli linea, 2 stalli trafo Matelec, sbarre, castelletti MT, armadi di comando, sezionatori con lame di terra, muro tagliafiamme | Modello Fusion v10; in SolidCraft muro tagliafiamme centrale e castelletti MT lato esterno |
