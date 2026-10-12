# 02 — Contenuto della cartella demo ETAP (`C:\ETAP Demo`)

Analisi del solo **elenco file** (colonne `FullName`, `Length`) esportato dal PC
dell'utente. Nessun file è stato aperto: tutto ciò che segue sul *contenuto* dei
file è dedotto dal nome, dall'estensione o dalla dimensione ed è segnalato come
tale ("dal nome si deduce"). Scopo: individuare materiale per **validare** il
nostro calcolatore IEC 60909-0:2016
([`01_iec60909_formule.md`](01_iec60909_formule.md)) contro ETAP.

## 1. Panoramica

| Voce | Valore |
|---|---|
| Radice | `C:\ETAP Demo` |
| File | 13.134 |
| Cartelle | 838 |
| Dimensione totale | 7.683.361.915 byte (≈ 7,16 GiB) |
| di cui crash dump `Etap64Dump.0.0.0.0.dmp` | 3.105.990.611 byte (≈ 2,9 GiB) |
| di cui eseguibili/DLL/installer (`.exe .dll .msi .msu .ocx`) | ≈ 2,27 GB |

### Cartelle di primo livello (ordinate per dimensione)

| Cartella | File | Byte | Contenuto (dal nome si deduce) |
|---|---:|---:|---|
| *(radice)* | 371 | 4.393.303.033 | `etaps64.exe`, ~290 DLL, motori di calcolo (`sciec3p.exe`, `sciec1p.exe`, `sciectr.exe`, `scansi*.exe`, `lf*.exe`, `ts.exe`…), help `etaps.chm`, `etap_overview.pdf`, crash dump |
| `Other` | 88 | 1.387.514.372 | Prerequisiti/installer (.NET, VC++ redist, Access DB Engine, SQL LocalDB, MongoDB Compass, DB Browser for SQLite…) |
| `Formats2400` | 1.930 | 1.133.646.893 | Modelli di report (`.rpt`, Crystal Reports) per ogni modulo di calcolo, più template Excel/Python |
| `Example-ANSI` | 68 | 237.608.556 | Progetto di esempio ANSI con uscite di studio |
| `Example-IEC` | 67 | 153.352.166 | **Progetto di esempio IEC con uscite di studio** |
| `Tables` | 122 | 105.267.182 | Database modello (`.mdb` + `.sqlite`) per le uscite di ogni modulo (es. `IEC-3ph`, `IEC-LG`, `SC3PHIEC`) |
| `Lib` | 5 | 93.852.773 | Libreria dati componenti (`DemoLib.lib`, `LibChanges_2024-118.lib`) |
| `Example-New` | 65 | 53.785.186 | Secondo progetto di esempio (ANSI + IEC + GOST) |
| `Symbols` / `SymbolsXaml` / `ToolBoxImages` / `Themes` | 6.430 | ≈ 50,5 MB | Grafica dei simboli unifilari |
| `Templates` | 84 | 26.233.225 | Reti tipo in XML, versioni `ANSI\` e `IEC\` (42 ciascuna) |
| `ExcelTemplates` | 48 | 14.755.827 | Template di esportazione Excel |
| `Convert` | 3.580 | 14.199.446 | Script di conversione/aggiornamento database (`.CVT`, `.RCD`) |
| `Datablocks` | 15 | 8.309.428 | Definizioni XML dei "datablock" dei risultati (es. `IEC_SC.xml`) |
| `Filters`, `pvdt40`, `x64`, `x86`, `WAREHOUSE`, `Rules`, `Clean .ini…` | — | ≈ 11 MB | Filtri import/export, controlli ActiveX, DLL SQLite, varie |

### Indizi sulla versione di ETAP (tutte **deduzioni**)

- Cartella `Formats2400` e file `WAREHOUSE\etapwh2400.wh`: dal nome si deduce
  la versione **24.0.0 (ETAP 2024)**.
- `Lib\MergeLib\LibChanges_2024-118.lib`: libreria aggiornata nel 2024.
- `Convert\SQL\032024.CVT`: dal nome, uno script di conversione datato 03/2024.
- Prerequisiti in `Other\`: `aspnetcore-runtime-6.0.27`, `dotnet-runtime-6.0.28`,
  `OpenSSLSetup-3_0_13`, `vc_redist_2022` — tutti rilasci di inizio 2024, coerenti
  con ETAP 2024.
- I backup dei progetti si chiamano `Example-32304.*`: il numero potrebbe essere
  una build/versione, ma il significato non è determinabile dall'elenco.
- Curiosità: `mfcmdbe.dll` ha la stessa dimensione esatta di
  `Example-IEC\Example.MDF` (38.862.848 byte) e `mfcmdb.dll` / `mfcpso.dll` di
  `Example-ANSI\EXAMPLE.MDF` / `.PSO`; si può supporre che siano copie modello del
  database di progetto, ma è solo un'ipotesi.

### Formato dei file di progetto e di uscita (deduzioni)

- Progetto = `*.OTI` (file di progetto, ~34 KB) + `*.MDF`/`*_log.ldf` (database
  **SQL Server/LocalDB** con i dati di rete, ~35–39 MB) + `*.PSO` (dal nome, la
  grafica dell'unifilare). Il backup è `*.bak` (backup SQL Server).
- Uscite di studio = un file per caso di calcolo, con estensione che indica il
  modulo, es. `.SI2S`, `.SA2S`. La famiglia `SI1`…`SI4` è IEC, `SA1`…`SA4` è ANSI
  (cfr. le cartelle `Convert\RCD\SI1..SI4`, `SA1..SA4`). Dai nomi dei file di
  esempio si ricava la corrispondenza:
  - `.SI2S` → cortocircuito IEC 60909 (es. `SC_909.SI2S`, `IEC-909.SI2S`)
  - `.SI1S` → duty IEC (es. `Duty909.SI1S`, `IEC-Duty.SI1S`)
  - `.SI3S` → IEC 61363 (es. `IEC-363.SI3S`)
  - `.SI4S` → cortocircuito monofase IEC (es. `IEC-1-Phase.SI4S`)
- La "S" finale e la presenza di `OtiSQLCEToSQLite.exe`, di `Tables\*.sqlite`
  accanto a `Tables\*.mdb` e di `DB.Browser.for.SQLite-win64.msi` fanno supporre
  che le uscite siano **database SQLite** (o SQL CE). Se è così, sarebbero
  leggibili direttamente con `sqlite3` di Python senza ETAP. **Da verificare**
  sul primo file ricevuto (intestazione `SQLite format 3`).
- I report "stampabili" non sono salvati come PDF/testo: vengono generati al
  volo da Crystal Reports (`psrept.exe`, `etrep64.dll`) usando i modelli
  `Formats2400\...\*.rpt` sui dati del file di uscita. **Nella cartella non ci
  sono report già esportati (nessun PDF/XLS/CSV di risultati).**

## 2. Cartelle di esempio

### 2.1 `Example-IEC` — 67 file, 153.352.166 byte

Contiene **un solo progetto** (`Example`) e, nella stessa cartella, le uscite di
tutti i casi di studio eseguiti. Raggruppamento per tipo di studio (dal nome si
deduce):

#### Progetto (file principali) — 13 file, 47.725.738 byte

| File | Byte |
|---|---:|
| `Example.OTI` | 34.816 |
| `Example.MDF` | 38.862.848 |
| `Example_log.ldf` | 4.325.376 |
| `Example.PSO` | 4.421.120 |
| `EXAMPLE.Scenarios.XML` | 30.683 |
| `EXAMPLE.Macros.XML` | 3.622 |
| `classification.xml` | 136 |
| `~OTI_ETAP#last.scenarios.xml` | 1.361 |
| `~OTI_ETAP#temp_ArcFlash.scenarios.xml` | 1.434 |
| `~OTI_ETAP#temp_Scenario1.scenarios.xml` | 1.361 |
| `Area Reports.txt` | 2.003 |
| `BatterySOC.csv` | 18 |
| `ProfileLibrary.sqlite` | 40.960 |

#### Cortocircuito IEC (uscite di studio) — 8 file, 2.069.852 byte

| File | Byte |
|---|---:|
| `SC_909.SI2S` | 311.296 |
| `Duty909.SI1S` | 258.048 |
| `IEC-1-Phase.SI4S` | 286.720 |
| `SC_363.SI1S` | 258.048 |
| `SC_363.sip` | 30.044 |
| `STAR_SM.ST2S` | 385.024 |
| `STAR_SQOP.ST2S` | 385.024 |
| `DCSC.DS1S` | 155.648 |

#### Arc flash — 5 file, 1.011.712 byte

| File | Byte |
|---|---:|
| `ArcFlash.IAFS` | 290.816 |
| `AFSQOP.IAFS` | 253.952 |
| `DCAF-MAXPOWER.DA1S` | 155.648 |
| `DCAF-PAUKERT.DA1S` | 155.648 |
| `DCAF-STOKES.DA1S` | 155.648 |

#### Load flow e affini — 6 file, 1.294.336 byte

| File | Byte |
|---|---:|
| `LF.LF1S` | 212.992 |
| `UBLF.UL1S` | 471.040 |
| `OPF.OP1S` | 196.608 |
| `DCLF.DL1S` | 131.072 |
| `EXAMPLE.LA1S` | 73.728 |
| `CA.CA2S` | 208.896 |

#### Armoniche — 7 file, 2.019.344 byte

| File | Byte |
|---|---:|
| `HALoadFlow.HA1S` | 266.240 |
| `HALoadFlow.hfp` | 151.984 |
| `HALoadFlow.hfpdb` | 323.584 |
| `HA_FreqScan.HA1S` | 475.136 |
| `HA_FreqScan.fsp` | 80.464 |
| `HA_FreqScan.fspdb` | 602.112 |
| `HA_FreqScan.hfp` | 119.824 |

#### Avviamento motori — 8 file, 1.916.928 byte

| File | Byte |
|---|---:|
| `M1_Starting.MS1S` | 225.280 |
| `M1_Starting.mapt` | 110.064 |
| `M1_Starting.msb` | 37.392 |
| `M1_Starting.mspdb` | 634.880 |
| `Static.MS1S` | 225.280 |
| `Static.mapt` | 110.064 |
| `Static.msb` | 37.392 |
| `Static.mspdb` | 536.576 |

#### Stabilità transitoria — 3 file, 2.738.448 byte

| File | Byte |
|---|---:|
| `TS.TS1S` | 307.200 |
| `TS.tsp` | 731.408 |
| `TS.tspdb` | 1.699.840 |

#### Batterie DC — 6 file, 1.062.160 byte

| File | Byte |
|---|---:|
| `DCBS.DB1S` | 360.448 |
| `DCBS.dbp` | 23.176 |
| `DCBS.dbpdb` | 147.456 |
| `Discharge.DB1S` | 360.448 |
| `Discharge.dbp` | 23.176 |
| `Discharge.dbpdb` | 147.456 |

#### Affidabilità / protezioni — 5 file, 403.376 byte

| File | Byte |
|---|---:|
| `RA.RA1S` | 94.208 |
| `RA.rap` | 10.640 |
| `RA.rapdb` | 73.728 |
| `OCP.CA1S` | 217.088 |
| `OCP.CAP` | 7.712 |

#### BACKUP — 6 file, 93.110.272 byte

| File | Byte |
|---|---:|
| `BACKUP\Example-32304.bak` | 37.651.968 |
| `BACKUP\Example-32304.oti` | 36.352 |
| `BACKUP\Example-32304.pso` | 12.395.008 |
| `BACKUP\Example~~.bak` | 38.569.472 |
| `BACKUP\Example~~.oti` | 36.352 |
| `BACKUP\Example~~.pso` | 4.421.120 |
Note su `Example-IEC` (deduzioni):

- `SC_909.SI2S` è, dal nome, l'uscita di uno studio di cortocircuito IEC 60909
  sulla rete `Example`: è il **candidato principale per il confronto**.
- `Duty909.SI1S`: dal nome, verifica dei poteri di interruzione (duty) con
  metodo 60909 — contiene presumibilmente anche ip, Ib, Ik.
- `IEC-1-Phase.SI4S`: dal nome, cortocircuito su sistema monofase IEC.
- `SC_363.SI1S` / `SC_363.sip`: dal nome IEC 61363 (navale), non 60909 —
  l'estensione `.SI1S` è inattesa per un 61363; non approfondire.
- `STAR_SM.ST2S`, `STAR_SQOP.ST2S`: coordinamento protezioni (ETAP Star), che
  calcola internamente correnti di guasto ma non è un report 60909.
- `EXAMPLE.Scenarios.XML` (30 KB): dal nome, l'elenco degli scenari (casi di
  studio, configurazione, file di uscita) — utile per sapere **con quali opzioni**
  è stato generato `SC_909.SI2S` (c max/min, motori, ecc.).
- `BACKUP\`: copie di sicurezza del database; non servono.

### 2.2 `Example-ANSI` — 68 file, 237.608.556 byte (sintesi)

Stesso schema di `Example-IEC` ma per la norma ANSI/IEEE C37: progetto
`EXAMPLE.OTI` + `EXAMPLE.MDF` (37,8 MB) + `EXAMPLE.PSO` (33,5 MB), uscite
`ANSI-Max.SA2S`, `ANSI-MIN.SA2S`, `ANSI-4Cyc.SA2S`, `ANSI-Duty.SA1S`,
`ANSI-1-Phase.SA4S`, arc flash, load flow, armoniche, motor starting, TS, ecc.
Unico file IEC: `IEC-363.sipdb` (32 KB, IEC 61363). Contiene anche
`Phase-1.log` (13 KB) e `EXAMPLE.oli` (4 KB). **Non utile per il 60909**
(metodo ANSI diverso).

### 2.3 `Example-New` — 65 file, 53.785.186 byte (sintesi)

Progetto `EXAMPLE` con database `EXAMPLE.MDF` (33,6 MB) ma `EXAMPLE.PSO` di soli
1.536 byte (dal nome e dalla dimensione: grafica quasi vuota). Contiene uscite
**sia ANSI sia IEC sia GOST**, tra cui:

| File | Byte | Dal nome si deduce |
|---|---:|---|
| `Example-New\IEC-909.SI2S` | 356.352 | cortocircuito IEC 60909 |
| `Example-New\IEC-Duty.SI1S` | 286.720 | duty IEC |
| `Example-New\IEC-1-Phase.SI4S` | 286.720 | cortocircuito monofase IEC |
| `Example-New\IEC-363.SI3S` | 585.728 | IEC 61363 |
| `Example-New\IECArcFlash.IAFS` | 327.680 | arc flash IEC |
| `Example-New\GOST.SG1S` | 544.768 | cortocircuito GOST |
| `Example-New\ETAPDumpInfo.txt` | 8.930 | informazioni su un crash: **può contenere dati della macchina, non condividere senza averlo letto** |

È un secondo caso di confronto 60909 indipendente da `Example-IEC`; non si sa se
la rete sia la stessa.

## 3. File potenzialmente utili per la validazione IEC 60909

Classifica dal più utile. Tutti i percorsi sono relativi a `C:\ETAP Demo\`.

### (a) File di risultati confrontabili con i nostri

| # | Percorso | Byte | Perché |
|---|---|---:|---|
| 1 | `Example-IEC\SC_909.SI2S` | 311.296 | Uscita di cortocircuito IEC 60909 della rete di esempio IEC: Ik", ip, Ib, Ik per nodo (presunto). Se è SQLite si legge con Python. |
| 2 | `Example-New\IEC-909.SI2S` | 356.352 | Secondo caso 60909 su un'altra rete, utile come conferma. |
| 3 | `Example-IEC\Duty909.SI1S` | 258.048 | Duty IEC: valori di ip/Ib confrontabili con i nostri κ e μ. |
| 4 | `Example-IEC\IEC-1-Phase.SI4S` | 286.720 | Guasti su sistemi monofase (minore priorità). |
| 5 | `Example-New\IEC-Duty.SI1S` | 286.720 | Duty IEC sul secondo progetto. |

Senza ETAP completo non sappiamo se il demo permetta di aprire i report: se lo
consente, un **export in PDF/Excel** del report di cortocircuito (Report Manager)
sarebbe il formato più comodo da confrontare.

### (b) File di progetto/dati con i dati di rete

| # | Percorso | Byte | Perché |
|---|---|---:|---|
| 6 | `Example-IEC\EXAMPLE.Scenarios.XML` | 30.683 | Scenari e opzioni di studio (dal nome): serve per riprodurre le stesse ipotesi. |
| 7 | `Example-IEC\Example.OTI` | 34.816 | File di progetto (impostazioni, norme, unità). |
| 8 | `Example-IEC\Area Reports.txt` | 2.003 | Testo, contenuto non noto; piccolo. |
| 9 | `Templates\IEC\IEEE Test Systems\IEEE 14 BUS.xml` | 583.755 | Rete di test IEEE 14 nodi in **XML** in versione IEC: mostra il formato dati di ETAP ed è una rete nota in letteratura. Non contiene risultati. |
| 10 | `Templates\IEC\Radial\Radial Circuit 1.xml` | 60.424 | Rete radiale piccola in XML: caso semplice per un primo confronto di formato. |
| 11 | `Example-IEC\Example.MDF` (+ `Example_log.ldf`) | 38.862.848 (+ 4.325.376) | Tutti i dati di rete del progetto IEC (database SQL Server). Indispensabile per ricostruire la rete in modo esatto, ma pesante e da leggere con SQL Server LocalDB. Chiedere in un secondo momento, zippato. |
| 12 | `Example-IEC\Example.PSO` | 4.421.120 | Grafica dell'unifilare (dal nome); utile solo per capire la topologia. |

### (c) Documentazione dei formati e del metodo

| # | Percorso | Byte | Perché |
|---|---|---:|---|
| 13 | `Tables\SC3PHIEC.sqlite` | 462.848 | Dal nome, schema del database di uscita del cortocircuito IEC (trifase/sistemi squilibrati): nomi di tabelle e campi dei risultati. |
| 14 | `Tables\IEC-3ph.sqlite` | 241.664 | Dal nome, schema delle uscite IEC trifase. |
| 15 | `Tables\IEC-LG.sqlite` | 286.720 | Dal nome, schema delle uscite IEC fase-terra. |
| 16 | `Datablocks\IEC_SC.xml` | 12.861 | Definizione XML dei campi di risultato del cortocircuito IEC mostrati sull'unifilare. |
| 17 | `Datablocks\IEC_SC Analyzer.xml` | 22.213 | Come sopra, per il "Short Circuit Analyzer". |
| 18 | `ExcelTemplates\ShortCircuitDutyAnalyzer\Short Circuit Duty Analyzer Export.xls` | 20.992 | Modello di esportazione Excel dei risultati di cortocircuito: elenco delle colonne. |
| 19 | `Formats2400\IEC 3-Phase SC\Result\Short-Circuit Report.rpt` | 51.200 | Modello Crystal Reports del report 60909: contiene i nomi dei campi ma è binario. Bassa priorità. |
| 20 | `Formats2400\IEC 3Ph-UBSys SC 60909\...` | 41 file, 3,67 MB | Modelli di report 60909 per guasti 3Ph, LG, LL, LLG, simultanei. Solo se servono i nomi dei campi. |
| 21 | `etaps.chm` | 317.757.254 | Help completo di ETAP: dal nome si deduce che documenti anche il modulo di cortocircuito IEC (metodo, opzioni, significato dei campi). Troppo grande da caricare: estrarre solo le pagine che citano 60909 (vedi §5). |
| 22 | `etap_overview.pdf` | 4.797.603 | Dal nome, panoramica commerciale; probabilmente poco tecnica. |
| 23 | `Tables\Transformer Duty Classes for ANSI and IEC.xlsx` | 20.670 | Tabella classi trasformatori; marginale. |

Altre cartelle `Formats2400\IEC *` (1-Phase SC, 363 SC, Unbalanced SC, STAR,
Sequence of Operation, Arc Flash) contengono solo modelli `.rpt`; la cartella
`Formats2400\IEC DC-UBSys SC 61660` contiene un template Excel e due script
Python per i report DC (IEC 61660), fuori ambito.

## 4. Cosa NON serve / non va caricato

- **`Etap64Dump.0.0.0.0.dmp` (3.105.990.611 byte)**: crash dump di memoria di
  ETAP. Può contenere contenuti sensibili della memoria (percorsi, nomi utente,
  dati di licenza, frammenti di documenti aperti). **Non va condiviso né
  caricato.** Lo stesso vale, finché non è stato letto, per
  `Example-New\ETAPDumpInfo.txt`.
- Eseguibili e DLL della radice (`etaps64.exe` 145 MB, motori di calcolo
  `sciec3p.exe`, `sciec1p.exe`, `sciectr.exe`, ~293 DLL): non servono e il
  nostro approccio non prevede di decompilarli.
- Installer e prerequisiti in `Other\` (≈ 1,39 GB): .NET, VC++, Access DB
  Engine in 9 lingue, SQL LocalDB, MongoDB Compass, ecc.
- `etapsqlenglishmodel.bak`, `etapsqlmetricmodel.bak` (~33 MB l'uno): dal nome,
  database modello vuoti.
- `Symbols`, `SymbolsXaml`, `ToolBoxImages`, `Themes`, `Convert`, `Filters`,
  `pvdt40`, `x64`, `x86`: grafica, conversioni di database, componenti.
- `Example-ANSI\` e le uscite ANSI di `Example-New\`: metodo ANSI, non 60909.
- Cartelle `BACKUP\` dei progetti e i grandi modelli arc flash in
  `Formats2400\*Arc Flash` (≈ 1,0 GB in totale).
- `Lib\*.lib` (94 MB): libreria componenti; utile solo per dati di catalogo.

## 5. Prossimi passi proposti

### Primo invio (≈ 3,0 MB in totale, 15 file)

| Percorso (`C:\ETAP Demo\...`) | Byte |
|---|---:|
| `Example-IEC\SC_909.SI2S` | 311.296 |
| `Example-IEC\Duty909.SI1S` | 258.048 |
| `Example-IEC\IEC-1-Phase.SI4S` | 286.720 |
| `Example-IEC\Example.OTI` | 34.816 |
| `Example-IEC\EXAMPLE.Scenarios.XML` | 30.683 |
| `Example-IEC\Area Reports.txt` | 2.003 |
| `Example-New\IEC-909.SI2S` | 356.352 |
| `Tables\SC3PHIEC.sqlite` | 462.848 |
| `Tables\IEC-3ph.sqlite` | 241.664 |
| `Tables\IEC-LG.sqlite` | 286.720 |
| `Datablocks\IEC_SC.xml` | 12.861 |
| `Datablocks\IEC_SC Analyzer.xml` | 22.213 |
| `ExcelTemplates\ShortCircuitDutyAnalyzer\Short Circuit Duty Analyzer Export.xls` | 20.992 |
| `Templates\IEC\IEEE Test Systems\IEEE 14 BUS.xml` | 583.755 |
| `Templates\IEC\Radial\Radial Circuit 1.xml` | 60.424 |
| **Totale** | **2.971.395** |

Comandi PowerShell (copiano solo questi file, mantenendo le sottocartelle, e
creano uno zip da caricare):

```powershell
$src = 'C:\ETAP Demo'
$dst = "$env:USERPROFILE\Desktop\etap_validazione"
$files = @(
  'Example-IEC\SC_909.SI2S',
  'Example-IEC\Duty909.SI1S',
  'Example-IEC\IEC-1-Phase.SI4S',
  'Example-IEC\Example.OTI',
  'Example-IEC\EXAMPLE.Scenarios.XML',
  'Example-IEC\Area Reports.txt',
  'Example-New\IEC-909.SI2S',
  'Tables\SC3PHIEC.sqlite',
  'Tables\IEC-3ph.sqlite',
  'Tables\IEC-LG.sqlite',
  'Datablocks\IEC_SC.xml',
  'Datablocks\IEC_SC Analyzer.xml',
  'ExcelTemplates\ShortCircuitDutyAnalyzer\Short Circuit Duty Analyzer Export.xls',
  'Templates\IEC\IEEE Test Systems\IEEE 14 BUS.xml',
  'Templates\IEC\Radial\Radial Circuit 1.xml'
)
foreach ($f in $files) {
  $target = Join-Path $dst $f
  New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
  Copy-Item -LiteralPath (Join-Path $src $f) -Destination $target
}
Compress-Archive -Path "$dst\*" -DestinationPath "$dst.zip" -Force
Get-Item "$dst.zip" | Select-Object FullName, Length
```

Se ETAP demo è aperto, chiuderlo prima della copia (i file di uscita potrebbero
essere bloccati).

### Al ricevimento

1. Verificare il formato dei `.SI2S`/`.SI1S` (intestazione `SQLite format 3`?) e,
   se SQLite, elencare tabelle e colonne con `python -I` + `sqlite3`.
2. Con `EXAMPLE.Scenarios.XML` individuare le opzioni dello studio `SC_909`
   (c max/min, contributo motori, metodo ip) e impostarle uguali nel nostro
   calcolatore.
3. Confrontare nodo per nodo Ik", ip, Ib, Ik.

### Secondo invio (solo se servono i dati di rete completi)

Il database del progetto IEC, zippato (≈ 43 MB non compressi):

```powershell
Compress-Archive -LiteralPath 'C:\ETAP Demo\Example-IEC\Example.MDF','C:\ETAP Demo\Example-IEC\Example_log.ldf','C:\ETAP Demo\Example-IEC\Example.PSO' `
  -DestinationPath "$env:USERPROFILE\Desktop\etap_example_iec_db.zip" -Force
```

In alternativa, se il demo lo consente: aprire `Example-IEC\Example.OTI` in ETAP,
eseguire/aprire lo studio `SC_909` ed **esportare il report di cortocircuito in
PDF o Excel**, oppure esportare la rete in XML; sono formati più leggeri e
leggibili del `.MDF`.

### Pagine dell'help sul metodo (facoltativo)

`etaps.chm` è troppo grande (318 MB). Si può decompilare in locale e copiare solo
le pagine che citano la norma:

```powershell
$out = "$env:USERPROFILE\Desktop\etaps_chm"
hh.exe -decompile $out 'C:\ETAP Demo\etaps.chm'
Start-Sleep -Seconds 60   # hh.exe ritorna subito: attendere la fine dell'estrazione
$hit = "$env:USERPROFILE\Desktop\etap_help_60909"
New-Item -ItemType Directory -Force -Path $hit | Out-Null
Get-ChildItem $out -Recurse -Include *.htm,*.html |
  Select-String -Pattern '60909' -List |
  ForEach-Object { Copy-Item -LiteralPath $_.Path -Destination $hit }
Get-ChildItem $hit | Measure-Object Length -Sum
```

Caricare la cartella `etap_help_60909` (senza immagini) solo se è di dimensione
ragionevole; altrimenti inviarne l'elenco dei nomi file per scegliere.
