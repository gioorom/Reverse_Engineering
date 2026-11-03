# Revit – sezione AT in BIM (via MCP)

Lo stallo è creato in **Revit 2026** con il server MCP open source
[mcp-servers-for-revit](https://github.com/mcp-servers-for-revit/mcp-servers-for-revit) v1.0.0 (licenza MIT),
usando il comando `send_code_to_revit` (codice C# eseguito dentro Revit).

## Installazione (già fatta sul PC)

- Add-in: `%AppData%\Autodesk\Revit\Addins\2026\mcp-servers-for-revit.addin` + cartella `revit_mcp_plugin\`
- Server MCP: `%LOCALAPPDATA%\mcp-server-for-revit\build\index.js` (pacchetto npm 1.0.0 con `better-sqlite3@12`,
  perché la 11 non si compila con Node 24); registrato in Claude Desktop come `mcp-server-for-revit` (`node …\index.js`).
- In Revit: scheda **revitMCP** → **Open Server** (il messaggio deve dire "Open Server": il pulsante è un interruttore).
  Il server ascolta sulla porta 8080.
- Nota: nel registro del plugin la riga "Failed to create command instance" compare anche quando il comando è
  registrato correttamente (messaggio sbagliato nel codice del plugin): non è un errore.

## Flusso

1. `python export_obj.py` – SolidCraft (headless) apre `modelli/CP_Faggiano_Sezione_AT.solidcraft` ed esporta OBJ + elenco componenti
2. `python prepara_mesh.py` – raggruppa i corpi per apparecchio, assegna categoria Revit / classe IFC / stallo / materiale,
   semplifica le mesh degli isolatori (pyfqmr) e scrive i lotti di testo (4,27 M → 1,23 M triangoli)
3. `python crea_stallo_revit.py <cartella lotti>` – via MCP: pulizia, parametri condivisi, un DirectShape per apparecchio
4. `python verifica_revit.py` – conteggi, vista 3D "CPF - Sezione AT 3D" e immagine PNG

Il passo 3 si può rilanciare: cancella prima gli elementi con `ApplicationId = CPF_Faggiano`.

## Risultato (03/11/2026)

242 elementi DirectShape: 72 Attrezzatura elettrica (TR, interruttori, sezionatori, TA, TV, scaricatori, armadi),
72 Apparecchi elettrici (isolatori, morsetti, terminali), 63 Telaio strutturale (sostegni), 31 Modelli generici
(sbarre, conduttori, piatti Cu, rinvii), 3 Fondazioni, 1 Muro. Stalli: Linea 1 e 2 (43 + 43), Trafo 1 e 2 (70 + 70),
Sistema sbarre AT (14), muro TR1-TR2 (2). Ingombro X −16975…27400, Y −5670…18070, Z −800…7275 mm.

Parametri di istanza (gruppo Dati identità): `IfcExportAs`, `IfcExportType`, `CPF_Stallo`, `CPF_Apparecchio`,
`CPF_Descrizione`; anche Commenti e Contrassegno. Materiali `CPF_*` (rame, alluminio, acciaio zincato,
acciaio verniciato, isolatore, calcestruzzo) assegnati per faccia.

Limiti: geometria a mesh (DirectShape, non famiglie parametriche); circa 8 000 triangoli più piccoli della
tolleranza di Revit (0,8 mm) sono stati scartati.

## Export IFC4 con classi (03/11/2026)

`python esporta_ifc.py <cartella>` esporta da Revit l'IFC4 della vista "CPF - Sezione AT 3D" e, con IfcOpenShell,
assegna a ogni elemento la classe IFC4 corretta (l'esportatore di Revit porta i DirectShape fuori come
IfcBuildingElementProxy e non legge IfcExportAs). `allinea_parametri_ifc.py` riporta le stesse classi nei parametri
IfcExportAs / IfcExportType del modello Revit.

File: `modelli/CP_Faggiano_Sezione_AT.ifczip` (IFC4, 95 MB non compresso). 242 elementi, tutti con geometria,
contenuti nel piano e con Pset `CPF_CP_Faggiano` (Stallo, Apparecchio, Occorrenza, Descrizione, CategoriaRevit, Impianto).

| Classe IFC4 | PredefinedType | N. |
| --- | --- | --- |
| IfcTransformer | VOLTAGE (TR 25 MVA e TV) | 8 |
| IfcTransformer | CURRENT (TA) | 12 |
| IfcProtectiveDevice | CIRCUITBREAKER (poli interruttore GL313) | 12 |
| IfcProtectiveDevice | VARISTOR (scaricatori) | 6 |
| IfcSwitchingDevice | USERDEFINED: DISCONNECTOR | 15 |
| IfcSwitchingDevice | USERDEFINED: DISCONNECTOR_WITH_EARTHING_SWITCH | 6 |
| IfcElectricDistributionBoard | SWITCHBOARD (armadi di comando) | 13 |
| IfcDiscreteAccessory | USERDEFINED: INSULATOR | 30 |
| IfcCableFitting | CONNECTOR (morsetti, terminali MT) | 42 |
| IfcCableSegment | BUSBARSEGMENT (sbarre AT, sbarre e piatti Cu MT) | 10 |
| IfcCableSegment | CONDUCTORSEGMENT (conduttori, cavi MT) | 8 |
| IfcMember | POST (sostegni) | 63 |
| IfcWall | SOLIDWALL (muro tagliafiamme) | 1 |
| IfcFooting | PAD_FOOTING / STRIP_FOOTING | 2 + 1 |
| IfcBuildingElementProxy | USERDEFINED (rinvii, tubi cavi) | 13 |

In IFC4 l'interruttore è un IfcProtectiveDevice (non IfcSwitchingDevice) e il sezionatore non ha un tipo
predefinito: si usa USERDEFINED con ObjectType.
