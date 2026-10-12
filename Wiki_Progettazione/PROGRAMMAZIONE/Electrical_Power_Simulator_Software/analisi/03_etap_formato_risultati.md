# 03 — ETAP 2024: formato di ingresso e risultati degli studi di cortocircuito IEC

Scopo: capire **come ETAP memorizza dati di rete e risultati** degli studi
IEC 60909, così da poter confrontare campo per campo il nostro calcolatore
([`01_iec60909_formule.md`](01_iec60909_formule.md),
[`../implementazione/iec60909/`](../implementazione/iec60909/)) con le uscite del
demo ETAP 2024 dell'utente (vedi [`02_etap_demo_contenuto.md`](02_etap_demo_contenuto.md)).

Ogni affermazione è marcata:

- **verificato**: ricostruito numericamente dai dati (il calcolo è riportato);
- **dedotto**: interpretazione plausibile dal nome del campo, dalle etichette dei
  datablock o dai valori, ma non dimostrata.

## 0. File esaminati e metodo

| File | Tipo | Studio / caso |
|---|---|---|
| `Example-IEC/SC_909.SI2S` | SQLite | IEC 60909 "tutti i guasti" (3F, F-T, F-F, F-F-T), study case `L-G909` |
| `Example-IEC/Duty909.SI1S` | SQLite | IEC 60909 "device duty" trifase, study case `Duty909` |
| `Example-IEC/IEC-1-Phase.SI4S` | SQLite | IEC "1-phase device duty", lanciato con lo study case `Duty909` |
| `Example-New/IEC-909.SI2S` | SQLite | IEC "tutti i guasti", progetto `Example`, 60 Hz, study case `IEC - Duty`, ETAP 22.0.0C |
| `Tables/IEC-LG.sqlite`, `Tables/IEC-3ph.sqlite`, `Tables/SC3PHIEC.sqlite` | SQLite | Database modello **vuoti** (solo schema, `DBVersion` = 100058) |
| `Datablocks/IEC_SC.xml`, `Datablocks/IEC_SC Analyzer.xml` | XML | Etichette e unità dei risultati mostrati sull'unifilare |
| `Example-IEC/EXAMPLE.Scenarios.XML` | XML | Scenari: associa scenario → modo di calcolo → study case → file di uscita |
| `ExcelTemplates/.../Short Circuit Duty Analyzer Export.xls` | BIFF (xls) | Modello di esportazione |

I database sono stati aperti **in sola lettura** (`sqlite3` con `mode=ro`, `python3 -I`).
Gli script di controllo sono rimasti fuori dal repository.

Osservazioni generali sul formato:

- Ogni file di uscita è un **database SQLite autosufficiente**: contiene sia i
  risultati sia una **copia dei dati di ingresso** usati (tabelle `I*`), quindi
  per il confronto non serve il database di progetto `.MDF`.
- Tutti i numeri reali sono **float a 32 bit** (es. `0.4000000059604645` = 0,4;
  `1.100000023841858` = 1,1). Nel confronto conviene una tolleranza relativa
  ≥ 1e‑6.
- Le tabelle di dettaglio (contributi) contengono **righe separatrici**
  `FromBus = '###<<<BlankLine>>>###'` con tutti i valori a zero e un campo
  `SequenceOrder` che dà l'ordine di stampa del report: vanno filtrate.
- Curiosità: in `SCIECLL.Flag2` compare il valore intero `1065353216` =
  `0x3F800000`, cioè la rappresentazione binaria del float 1,0 scritta in una
  colonna intera (**verificato**: 0x3F800000 è 1,0f in IEEE‑754).
- `Headr.1st` = `'SAMPLE OUTPUT REPORT - DOES NOT REFLECT THE ACTUAL RESULTS'`
  in tutti e quattro i file (filigrana del demo, vedi §4). `Headr.STDCase` dà
  lo study case; `PSRev` = `24.0.0C` (Example‑IEC) e `22.0.0C` (Example‑New).

### Modi di calcolo (da `EXAMPLE.Scenarios.XML`, **verificato** con `ISCStudyCase.StudyType`)

| Scenario | `Mode` | Study case | Uscita | `StudyType` |
|---|---|---|---|---|
| `SC_909` | `STUDY_SHORTCIRCUIT IEC ALL FAULT` | `L-G909` | `SC_909.SI2S` | 7 |
| `Duty909` | `STUDY_SHORTCIRCUIT IEC DEVICE DUTY` | `Duty909` | `Duty909.SI1S` | 6 |
| `IEC-1-Phase` | `STUDY_SHORT_CIRCUIT_IEC_1PHASE_DEVICE_DUTY` | `Duty909` | `IEC-1-Phase.SI4S` | 19 |
| `SC_363` | `STUDY_SHORTCIRCUIT IEC TRANSIENT FAULT CURRENT` | `IEC363` | `SC_363.SI3S` | (file non fornito) |

Quindi l'estensione codifica il tipo di studio: **SI1S** = duty trifase IEC 60909,
**SI2S** = tutti i tipi di guasto IEC 60909, **SI3S** = IEC 61363 (transitorio),
**SI4S** = duty monofase. Lo scenarios XML **non** contiene le opzioni dello study
case (c, metodo, ecc.): quelle sono solo in `ISCStudyCase` dentro ogni uscita.

### Modello Excel

`Short Circuit Duty Analyzer Export.xls` è un BIFF valido ma il foglio
`Short Circuit Duty Analyzer` ha **0 righe e 0 colonne** (letto con `xlrd` 2.0.2):
contiene solo stili/formattazione, nessuna intestazione di colonna. Non è utile
per decodificare i campi.

### Datablock XML (etichette dei risultati)

Entrambi i file definiscono, per gli elementi `BUS`, `HVCB`, `LVCB`, `FUSE`,
`SINGLESWITCH`, campi con etichetta, unità e nome di variabile interno:

| Etichetta | Unità | `varName` | Corrisponde a (dedotto) |
|---|---|---|---|
| `I"k` | kA | `IECIkk` | `IPPk*` nelle tabelle (I"k) |
| `ip` | kA | `IECip` | `ip*` |
| `Ik` | kA | `IECIkKA` | `Ik*` |
| `Ib Sym` / `Ib asym` | kA | `IECIbSymm` / `IECIbAsymm` | `Ibsymm` / `Ibasymm` (solo dispositivi) |
| `Standard` | – | `StudyType` | `ISCStudyCase.StudyType` |

Questo conferma la convenzione di nome **`IPPk` = I"k** (nessun "picco" nel nome
nonostante le lettere "Pk"); la verifica numerica è al §3.

## 1. Tabelle per tipo di studio

Righe effettivamente popolate (le tabelle a 0 righe sono omesse; `DBVersion`
ha sempre 1 riga).

| Tabella | SI2S `SC_909` | SI1S `Duty909` | SI4S `IEC-1-Phase` | SI2S Example‑New | Scopo |
|---|---:|---:|---:|---:|---|
| `Headr` | 1 | 1 | 1 | 1 | Intestazione report (progetto, study case, versione, filigrana) |
| `Isummary` | 1 | 1 | 1 | 1 | Conteggio elementi (bus, trasformatori, macchine…) |
| `ISCStudyCase` | 1 | 1 | 1 | 1 | Opzioni dello study case (c, metodo, decadimento…) |
| `IAdjustments` | 1 | 1 | 1 | 1 | Tolleranze e correzioni di temperatura applicate |
| `IBus` | 10 | 10 | 10 | 11 | Nodi |
| `IConnect` | 10 | 10 | 10 | 11 | **Rami già ridotti a impedenze in % su 100 MVA** |
| `IUtility` | 1 | 1 | 1 | 1 | Rete esterna |
| `IXFMR2` / `IXFMR3` | 5 / 1 | 5 / 1 | 5 / 1 | 6 / 1 | Trasformatori a 2 e 3 avvolgimenti (dati di targa) |
| `Icable` | 1 | 1 | 1 | 2 | Cavi (dati per km) |
| `ISynGen` / `ISynMotor` / `IIndMachine` | 1 / 1 / 3 | 1 / 1 / 3 | 1 / 1 / 3 | 1 / 2 / 6 | Macchine |
| `ILump` | – | – | – | 3 | Carichi aggregati |
| `SCIECLGSum1` | 5 | – | 1 | 5 | Sintesi correnti per bus e tipo di guasto |
| `SCIECLGSum2` | 5 | – | 1 | 5 | Impedenze di sequenza al punto di guasto (Ω) |
| `SCIECLG` / `SCIECLL` / `SCIECLLG` | 34 ciascuna | – | 18 ciascuna | 107 ciascuna | Contributi per ramo per F‑T, F‑F, F‑F‑T (con colonne 3F) |
| `ClippingCurrent` | 5 | – | 1 | 5 | Correnti simm./asimm. a mezzo periodo e X/R per tipo di guasto |
| `SCIEC3ph` | – | 143 | – | – | Contributi per ramo, guasto trifase (fino a 3 livelli) |
| `SCIEC3phSum` | – | 25 | – | – | Duty trifase per bus e per dispositivo (making, breaking, Idc) |
| `SCIEC3phSum2` | – | 11 | – | – | Duty termico (Ith, energia I²t) per dispositivo |
| `SCIEC1phSum` / `SCIEC1phSum2` | – | – | 4 / 1 | – | Duty monofase (come `SCIEC3phSum` / `Sum2`) |
| `Alert` | 0 | 11 | 4 | 0 | Allarmi (valore calcolato vs nominale) |

Schemi modello in `Tables/` (tutti vuoti, **verificato**):

- `IEC-LG.sqlite` ha esattamente l'elenco tabelle di un **SI2S** (incl. `AutoStar*`
  e la tabella temporanea `~TMPCLP565301`).
- `IEC-3ph.sqlite` ha esattamente l'elenco tabelle di un **SI1S** (incl. le
  tabelle arc‑flash `ArcFlash`, `BusArcFlash`, `PDArcFlash`, vuote nei demo).
- `SC3PHIEC.sqlite` è lo schema del **nuovo modulo "SC3PH"** (non usato dai file
  demo): risultati per fase e per istante (`SC3PHIECResults` con `Va..Vc`, `VNeu`,
  `VPE`, `Ia..Ic`, `INeu`, `IPE`, `TimeSec`; `SC3PHIECSum1` con `Ippk/ip/Ib/Ik` e
  le varianti `…1`, `…2`; `SC3PHIECDutySum`, `SC3PHThermalDuty`,
  `SC3PHIECIBPerTimeResults`, `SC3PHIECDCResultSum` per IEC 61660 in c.c.;
  `ClippingCurrent` a 46 colonne con valori per fase A/B/C;
  `ISC3PHStudyCase` a 199 colonne). Se in futuro si confronta con questo modulo,
  i nomi dei campi cambiano ma il contenuto atteso è analogo.

## 2. Tabelle di ingresso (I\*)

Convenzioni generali (**verificate** sotto):

- Potenza di base del sistema **100 MVA**; tensione di base del nodo
  `IBus.BasekV`, che **non è sempre Un**: viene propagata attraverso i rapporti
  di trasformazione *con le prese*. Es. `Xfmr01` 33/11 kV con presa primaria
  −2,5 % → `SWBRDA.BasekV` = 11/0,975 = 11,28205 kV, e a valle di `TX5`
  `Bus6.BasekV` = 6,6/0,975 = 6,76923 kV. (Il nostro calcolatore usa invece
  base = Un e rapporti fuori nominale: nel confronto le impedenze in % vanno
  riportate alla stessa base.)
- Impedenze di macchine/trasformatori in tabelle `I<elemento>` = **dati di
  targa** (% sulla potenza nominale propria). La tabella `IConnect` contiene
  invece i rami **già convertiti in % su 100 MVA e sulla BasekV**, con i fattori
  di correzione IEC (K_T) e le tolleranze già applicati.

### `IBus`

| Campo | Significato | Stato |
|---|---|---|
| `NomlkV`, `BasekV` | Tensione nominale e di base (kV) | verificato (vedi sopra) |
| `Type` | `SWNG`, `Gen.`, `Load` | dedotto |
| `VMag`, `VAng` | Tensione iniziale (% di Un, gradi); `VAng` = −30°/−60° riflette gli sfasamenti dei trasformatori Dy | dedotto |
| `MtrMW`, `MtrMvar` | Potenza dei motori collegati (MW, Mvar) | dedotto |
| `BracPeak`, `BracAsym`, `BracSym`, `RatType` | Tenuta del quadro (kA). `EmergencySwBrd.BracPeak` = 130 = `Alert.Rated` dell'allarme "Bracing Peak" | verificato |

### `IUtility` (rete esterna)

Esempio: `MVA3ph` = 500, `X/R3ph` = 10, `MVA1Ph` = 350, `KV` = 33.

- `RPos100MVA`/`XPos100MVA` = 1,99007 / 19,9007 → |Z1| = 20,00 % = 100/500·100,
  X/R = 10. Quindi **Z1 in % su 100 MVA, *senza* il fattore c** (verificato).
- `RZero100MVA`/`XZero100MVA` = 4,5487 / 45,487 → |Z0| = 45,714 % =
  3·100/350·100 − 2·20 = 85,714 − 40 (verificato: S"k1 = 350 MVA definisce
  2·Z1 + Z0).
- Nei risultati (contributo `Network feeder` in `SCIECLG`) l'impedenza diventa
  2,18908 + j21,8908 % = **1,1 × (Z1 di IUtility)**: ETAP applica
  Z_Q = c·Un²/S"kQ come IEC 60909 eq. (1) (verificato, c = 1,1).
- `Tdc` = 0,031831 s = (X/R)/(2πf) = 10/314,16 (verificato).

### `Icable` e ramo cavo in `IConnect`

`Cable 11`: `Length` = 500, `RPos` = 0,18694, `XPos` = 0,122, `RZero` = 0,59134,
`XZero` = 0,3, `YPos` = 5,94e‑5, bus 33 kV (`Unit = 'Metric'`).

Con Z_base = 33²/100 = 10,89 Ω:

- R = 0,18694 Ω/km × 0,5 km = 0,09347 Ω → 0,09347/10,89 = **0,8583 %** =
  `IConnect.R` (0,85831) — verificato.
- X = 0,122 × 0,5 = 0,061 Ω → **0,5601 %** = `IConnect.X` — verificato.
- R0 = 0,59134 × 0,5/10,89 = **2,7151 %** = `IConnect.R0` — verificato.
- Y = 5,94e‑5 S/km × 0,5 km × 10,89 Ω × 100 = **0,03234** = `IConnect.Y` →
  l'ammettenza è in % (p.u.×100) — verificato.

Quindi `RPos/XPos/RZero/XZero` sono **Ω/km**, `YPos` **S/km**, `Length` in **m**
(sistema metrico) e `IConnect.R/X/Z/R0/X0/Z0/Y` sono **% su 100 MVA**.
Dedotto: il valore 0,18694 Ω/km per un 120 mm² Cu è compatibile con la
resistenza a 75 °C (`TempOp` = 75; R20 ≈ 0,1537 Ω/km × 1,216), e `IConnect` usa
lo stesso valore: per Ik max la IEC prescriverebbe R a 20 °C. Da confermare
(`IAdjustments.adjustCableRForTemp` = 1).

### `IXFMR2` e rami trasformatore in `IConnect` — fattore K_T

`PosZ` è in % sulla potenza `MVA`, con rapporto X/R `PosX/R`. Tutti i 5
trasformatori sono riprodotti **esattamente** (scarto < 1e‑4 %) con:

Z[% su 100 MVA] = PosZ·(1 − Tol%/100) · (100/MVA) · (U_r/U_base)² · K_T,
con K_T = 0,95·c_max/(1 + 0,6·x_T) (IEC 60909‑0 eq. 12a), x_T = reattanza
relativa *dopo* la tolleranza, c_max = quello della **tensione lato BT** del
trasformatore.

| Trafo | Dati | (U_r/U_base)² | K_T | Atteso R + jX | `IConnect` |
|---|---|---|---|---|---|
| T1, T2 11/0,4 kV | 6,25 % su 2 MVA, X/R 7,1 | 1 | 0,96179 (c = 1,05) | 41,9184 + j297,6205 | 41,9184 + j297,6205 |
| TX5 6,6/11 kV | 7,15 % su 4,5 MVA, X/R 12,14 | (6,6/6,769)² = 0,950625 | 1,00215 (c = 1,1) | 12,4265 + j150,858 | 12,4265 + j150,858 |
| Xfmr01 33/11 kV, presa −2,5 % | 8,35 % su 15 MVA, X/R 18,6 | 0,975² = 0,950625 | 0,99521 (c = 1,1) | 2,8274 + j52,5888 | 2,8274 + j52,5888 |
| Xfmr04 11/0,4 kV, `Tol%` 7,5 | 6,25 % su 2,5 MVA, X/R 10,67 | 1 | 0,96420 (c = 1,05, x_T già ridotta del 7,5 %) | 20,8059 + j221,9985 | 20,8059 + j221,9985 |

Conseguenze per il confronto:

- ETAP **applica K_T** ai trasformatori di rete; la tolleranza di impedenza
  (`IAdjustments.applyXfmrZTol` = 1) **riduce** Z del `Tol%` prima di K_T (caso
  Ik max).
- `TX5` alimenta il generatore `GenB` ma **non** è trattato come gruppo di
  generazione (K_S/K_SO): riceve K_T come un trasformatore qualsiasi e il
  generatore riceve K_G a parte (vedi `ISynGen`).
- `IConnect.R0/X0`: uguali a R/X per `Xfmr04` (Y/Y a terra) e per `Xfmr03`; pari a
  0 per i Dy (T1, T2, TX5, Xfmr01): il percorso omopolare del lato a stella va
  verso terra e non è un ramo tra due bus (dedotto).

### `IXFMR3` (`Xfmr03`) e i tre rami in `IConnect`

Dati: 33/11/11 kV, `PMVA/SMVA/TMVA` = 10/5/3, `PSPosZ` = 8 % (X/R 15),
`STPosZ` = 7 % (X/R 12), `TPPosZ` = 7 % (X/R 12), Y‑Y‑D.

`IConnect` contiene **tre righe `3W XFMR`** con lo stesso `ID` (P‑S, P‑T, S‑T):
P‑S = 6,94015 + j134,4586 %, P‑T = S‑T = 9,28342 + j103,2547 %. Sono il
**triangolo equivalente** della stella delle impedenze di avvolgimento
(verificato invertendo: stella Z_P = Z_S = 2,7155 + j40,7320,
Z_T = 3,2840 + j31,2613; da cui le somme a coppie):

- Z_P + Z_S = 5,4309 + j81,4640 → |·| = **81,645 %**, X/R = **15,000**;
- Z_P + Z_T = Z_S + Z_T = 5,9994 + j71,9933 → |·| = **72,243 %**, X/R = **12,000**.

Poiché P‑T = S‑T, le tre impedenze di coppia sono riferite **alla stessa base**,
che risulta essere la **potenza primaria `PMVA` = 10 MVA** (8 %·100/10 = 80 %,
7 %·100/10 = 70 %). I rapporti X/R sono esattamente quelli di targa. I fattori
81,645/80 = **1,0206** e 72,243/70 = **1,0320** sono i **K_T di coppia**
(verificato, vedi [`04_confronto_etap_sc909.md`](04_confronto_etap_sc909.md)):
ETAP calcola K = 0,95·1,1/(1 + 0,6·x) con x riferita alla **potenza della
coppia** (la minore dei due avvolgimenti: 5 MVA per P‑S, 3 MVA per S‑T e T‑P),
cioè x = 8 %·5/10 = 4 % → K = 1,0206 e x = 7 %·3/10 = 2,1 % → K = 1,0320.

### `ISynGen`

`GenB`: 4,06 MVA, 6,6 kV, PF 80 %, `Xdpp` = 24 %, `Xpp/R` = 24, `Ra` = 1 %.
Tutte le reattanze (`Xdpp`, `Xdp`, `Xd`, `X2`, `Xzero`, `Xl`) sono **% sulla `MVA`
della macchina**; `Tdc` = 0,07639 s = 24/(2π·50) (verificato).
`GrdOhm1` = 107,34 Ω = 6600/(√3·35,5 A) (`GNDAmp` = 35,5): resistenza di neutro
(verificato).

Nel contributo `Bus6 → SWBRDA` (guasto su `SWBRDA`) ETAP riporta
34,94 + j691,19 %. Ricostruzione (verificata, scarto < 0,01 %):
generatore (1 + j24) %·100/4,06·(6,6/6,769)² · K_G + `TX5` (12,43 + j150,86) %,
con **K_G = c_max/(1 + x"d·sin φ_rG) = 1,1/(1 + 0,24·0,6) = 0,96154**
→ 22,51 + j540,34 + 12,43 + j150,86 = 34,94 + j691,20. Quindi:

- ETAP applica **K_G** al generatore (IEC eq. 18);
- usa R dal dato `Xpp/R` (= X"d/24), **non** la R_Gf fittizia IEC (0,05/0,07·X"d)
  — dedotto che sia l'effetto di `ISCStudyCase.MachineXoverR` = 1.

### `ISynMotor`

`Syn Motor`: 2,291 MVA (`kVA`), `Xdpp` = 15,38 %, `R` = 0,4659 % = 15,38/33,01
(`Xpp/R`). Contributo su `Bus B`: 21,156 + j698,37 %. Su base 100 MVA il motore
vale 20,336 + j671,31 %; il rapporto 1,04031 coincide con
**c_max/(1 + x"d·sin φ) = 1,1/(1 + 0,1538·0,3731)** con cos φ = 0,9278 (`PF100`):
ETAP tratta il motore sincrono come un generatore e gli applica K_G (verificato).

### `IIndMachine`

`Ind M1`: 2000 kW, 11 kV, `kVA` = 2350,4, `LRC` = 453,38 %, `R` = 3,269 %,
`Xpp` = 21,813 %, `Xpp/R` = 6,673.

- |R + jX"| = 22,056 % = 100/4,5338 → impedenza a rotore bloccato
  Z_M = (1/(I_LR/I_rM))·U_rM²/S_rM in **% sui kVA del motore** (verificato).
- Contributo su `SWBRDA`: 132,21 + j882,21 % = (3,269 + j21,813)·100/2,3504 ×
  (11/11,282)² → **nessun fattore K** per i motori asincroni (verificato); `XNeg`
  del contributo (622,04 %) usa invece il campo `X2` = 15,38 % (verificato).
- `R/X` = 0,15 viene dai dati del motore; per 2000 kW, 4 poli (1 MW per coppia di
  poli) la tabella IEC darebbe R_M/X_M = 0,10: occorre usare il valore ETAP nel
  confronto (dedotto).
- `Quantity`, `MFactor` (Ind M2: 2 e 2,0; Mtr6: 2 e 0,02237): moltiplicatore di
  macchine identiche; il valore di `Mtr6` non è spiegato (dedotto/aperto).
- `Tdc` per le asincrone non è X"/R/ω (0,03817 s ≠ 6,67/314): aperto.

### `IConnect`

Colonne: `ID`, `Type` (`Cable`, `2W XFMR`, `3W XFMR`, `Tie Breakr`), `From`,
`ToSec`, `ToTer`, `R`, `X`, `Z`, `Y`, `R0`, `X0`, `Z0`, `Y0`. Tutte le impedenze
in **% su 100 MVA alla BasekV dei nodi**, con K_T e tolleranze già applicati
(verificato sopra). Interruttori di accoppiamento chiusi = ramo a impedenza 0
(`LVCB11`).

### `ISCStudyCase` (opzioni)

Confronto tra i tre study case (valori grezzi):

| Campo | `L-G909` (SI2S) | `Duty909` (SI1S/SI4S) | `IEC - Duty` (Example‑New) | Interpretazione | Stato |
|---|---|---|---|---|---|
| `Freq` | 50 | 50 | 60 | Frequenza (Hz) | verificato |
| `StudyType` | 7 | 6 (19 nel SI4S) | 7 | Tipo di studio (vedi §0) | verificato |
| `Standard` | 1 | 1 | 1 | 1 = IEC | dedotto |
| `CFact1`, `CFact2` | 1,05 | 1,05 | 1,05 | c_max BT (≤ 1 kV): i bus 0,4/0,48 kV hanno `CFactor` = 1,05 | verificato (quale dei due si riferisca a +6 %/+10 % non è determinabile) |
| `CFact3`, `Cfact4` | 1,1 | 1,1 | 1,1 | c_max MT/AT: i bus 4,16–33 kV hanno `CFactor` = 1,1 | verificato |
| `IECMethod` | 1 | 3 | 3 | Metodo IEC (forse il metodo per κ o per Ib) | **aperto**: `L-G909` (1) e `Duty909` (3) danno ip identici su tutti i bus |
| `Decay` | 1 | 1 | 1 | Decadimento AC delle macchine (μ, q) attivo | dedotto: in `Duty909` Ib < I"k per i rami con macchine |
| `SSkA` | 1 | 0 | 1 | Calcolo di Ik permanente | dedotto (Ik è comunque presente anche con 0) |
| `MachineXoverR` | 1 | 1 | 1 | X/R delle macchine dai dati invece che dai valori IEC | dedotto (vedi `ISynGen`) |
| `PreFaultMetod`, `PreFault%` | 1, 0 | 1, 0 | 1, 0 | Tensione prima del guasto = c·Un (metodo IEC) | verificato (`PreFaultNom` = 100, I"k = c·Un/(√3·Z)) |
| `MargFlag`, `Marg`, `BusMarginal` | 0, 0, 0 | 1, 90, 90 | 1, 0, 0 | Soglia allarmi "Marginal" in % | verificato: allarmi "Marginal" a 93,66 %, "Critical" > 100 % |
| `ContributionLevel` | 1 | 3 | 3 | Livelli di contributi riportati | verificato: `SCIEC3ph` riporta anche rami a 2–3 livelli dal guasto |
| `PDDuty` | 0 | 1 | 0 | Verifica dei dispositivi di protezione | verificato (righe dispositivo in `SCIEC3phSum`) |
| `IncludeLGZf`, `R_Zf`, `X_Zf`, `ZfUnit` | 0 | 0 | 0 | Impedenza di guasto verso terra | dedotto (`RFaultLocOhm` = 0) |
| `IECLVCBBreakingRating` | 1 | 0 | 1 | Potere di interruzione BT usato (Icu/Ics?) | dedotto |
| `MCCBMFMethod`, `IECLVCmaxOption`, `ZeroSeqMdl`, `UserDefinedTk`, `AdjustmentFlag` | 1,0,0,0,0 | 1,0,0,0,0 | 1,0,0,0,0 | non determinati | aperto |
| `ANSI*`, `ZSI*`, `ArcFlash*`, `AutoStar` | – | – | – | Opzioni non IEC / non usate | – |

### `IAdjustments`

Flag di tolleranza e correzione: `applyXfmrZTol` = 1 (verificato su `Xfmr04`),
`applyReactorTol` = 1, `adjustCableRForTemp` = 1, `adjustLineRForTemp` = 1;
`useGlobal*` = 0 → si usano i valori del singolo elemento (dedotto).

## 3. Tabelle dei risultati

### 3.1 `SCIECLGSum1` — sintesi per bus (SI2S, SI4S) — **kA**

Colonne: `FaultedBus`, `kVnom`, `kVBase`, `PreFaultNom` (100 %),
`PreFaultBase` (% di BasekV: 97,5 su `SWBRDA` = 11/11,282), `CFactor`, poi per
`3ph`, `LG`, `LL`, `LLG`: `IPPk*`, `ip*`, `Ib*` (solo dissimmetrici), `Ik*`.

| Campo | Significato | Stato |
|---|---|---|
| `IPPk3ph` | **I"k trifase** = c·Un/(√3·\|Z1\|) | verificato (scarto 0,000 % su 11 bus, §4) |
| `IPPkLL` | I"k2 = c·Un/\|Z1 + Z2\| | verificato |
| `IPPkLG` | I"k1 = √3·c·Un/\|Z1 + Z2 + Z0\| | verificato |
| `IPPkLLG` | **corrente di linea** del guasto bifase a terra, max(\|I_b\|, \|I_c\|) con I_b = −j·c·Un·(Z0 − a·Z2)/(Z1Z2 + Z2Z0 + Z0Z1) (IEC eq. 26) | verificato (es. `Bus B`: \|I_b\| = 6,9472 = valore ETAP, \|I_c\| = 6,8959) |
| `ip*` | corrente di cresta, κ·√2·I"k | verificato nella forma; κ vedi sotto |
| `Ik3ph` | corrente permanente trifase (< I"k vicino ai generatori: 0,81·I"k su `SWBRDA`) | dedotto |
| `IbLG/LL/LLG`, `IkLG/LL/LLG` | **uguali a I"k** del rispettivo guasto (IEC: per guasti dissimmetrici Ib = Ik = I"k) | verificato (identità esatta) |

**κ e ip.** ETAP usa **lo stesso κ per tutti i tipi di guasto** dello stesso bus
(ipLG/(√2·I"kLG) = ipLL/(√2·I"kLL) = ip3ph/(√2·I"k3ph), verificato). Tale κ
**non coincide esattamente** con κ = 1,02 + 0,98·e^(−3R/X) calcolato con l'X/R
di Z1 al punto di guasto (che è il valore memorizzato in `ClippingCurrent.XoverR3ph`):

| Bus (SC_909) | X/R (Z1) | κ da formula | κ ETAP | scarto |
|---|---:|---:|---:|---:|
| Bus B | 14,381 | 1,8155 | 1,8177 | +0,12 % |
| Bus C | 11,630 | 1,7772 | 1,7780 | +0,05 % |
| EmergencySwBrd | 10,925 | 1,7647 | 1,7649 | +0,01 % |
| SWBRDA | 11,268 | 1,7709 | 1,7731 | +0,12 % |
| Utility Bus | 10,070 | 1,7475 | 1,7482 | +0,04 % |

In Example‑New lo scarto arriva a +1,3 % (`LVBus`) e +1,8 % (`MCC1`, molti
motori). Non è il picco esatto della forma d'onda (darebbe κ più piccoli), né la
somma dei κ_i·I"k_i dei rami (Bus B: 16,781–16,788 kA contro 16,773). Lo scarto è
maggiore dove i rami hanno X/R molto diversi, compatibile con il **metodo C**
(frequenza equivalente 20 Hz / 24 Hz), che non si può ricostruire senza le
impedenze a fc (dedotto). Per il confronto: usare una tolleranza ≈ 2 % su ip,
oppure implementare il metodo C e confrontare.

### 3.2 `SCIECLGSum2` — impedenze al punto di guasto — **Ω**

`RPosOhm/XPosOhm/ZPosOhm` = Z1, `RNegOhm…` = Z2, `RZeroOhm…` = Z0 (Ω reali sul
lato a `kVnom`; per `SWBRDA` la conversione in % usa Z_base = 11,282²/100).
Verifica: `Utility Bus` R1 = 0,21263 Ω / 10,89 Ω = 1,9525 % = `RPos` della riga
`Total` di `SCIECLG` (verificato, idem X1, R0, X0 su `Bus B`).

Grandezze derivate (tutte **verificate** sui 5 bus):

- `ZLGOhm` = \|Z1 + Z2 + Z0\|/3;
- `ZLLOhm` = \|Z1 + Z2\|/√3, memorizzata ruotata: `RLLOhm + jXLLOhm` =
  j·(Z1 + Z2)/√3 (per questo `RLLOhm` è negativo);
- `ZLLGOhm` = \|Z1Z2 + Z2Z0 + Z0Z1\|/(3·\|Z2\|), cioè c·Un/(√3·ZLLG) = I"kE2E
  (corrente di terra 3I0 del guasto bifase a terra, = `ClippingCurrent.SymmLLG_3I0`);
- `EffLG`, `EffLLG` = massima tensione delle fasi sane / 100 % (es. `Bus B`:
  V_c = 105,234 % → 1,0523; `Bus C`, isolato: 190,53 % → 1,905). Include c, quindi
  non è il fattore di guasto a terra riferito a c·Un;
- `RFaultLocOhm/XFaultLocOhm` = impedenza di guasto (0 nei demo).

Bus senza percorso omopolare (`Bus C`, `EmergencySwBrd`, a valle di triangoli o
isolati): Z0 = 0 e tutti i campi LG/LLG a zero — convenzione "0 = non
calcolabile", non "impedenza nulla" (verificato: `IPPkLG` = 0, e `IPPkLLG` =
`IPPkLL`).

### 3.3 `ClippingCurrent` — correnti simmetriche/asimmetriche — **kA**

Per ogni bus guastato e tipo di guasto (`3ph`, `LG`, `LL`, `LLG`, più
`SymmLLG_3I0`/`AsymmLLG_3I0`): `Symm*` = I"k (uguale a `IPPk*` di Sum1),
`XoverR*` = X/R della relativa impedenza di guasto (per 3F è X1/R1 di Sum2,
verificato), `Asymm*` = **corrente asimmetrica efficace a mezzo periodo**:

Asymm = Symm·√(1 + 2·e^(−2π/(X/R)))

Verificato su tutti i valori 3F, F‑T e F‑F non nulli dei tre file SI2S/SI4S (t implicito = 10,000 ms
a 50 Hz; a 60 Hz la stessa formula, cioè mezzo periodo = 8,33 ms). Il nome
"clipping" suggerisce l'uso per la scelta di limitatori/fusibili (dedotto).

### 3.4 `SCIECLG`, `SCIECLL`, `SCIECLLG` — contributi per ramo

Una riga `Total` per bus guastato (`ToBus` = 'Total') seguita dai rami
(`FromBus → ToBus`), separatori `###<<<BlankLine>>>###`. Colonne principali di
`SCIECLG` (le altre due tabelle sono analoghe con suffisso `LL`/`LLG`):

| Campo | Significato | Stato |
|---|---|---|
| `Vfrom3ph` | Tensione al bus `FromBus` durante il guasto 3F (% di Un) | dedotto |
| `kASym3ph` | Contributo I"k del ramo per guasto **trifase** (kA) | verificato: la riga Total = `IPPk3ph` |
| `VaLG`, `VbLG`, `VcLG` (+ `…Ang`) | Tensioni di fase al `FromBus` durante il guasto F‑T, in % della tensione di fase nominale **incluso c** (fase sana di un bus isolato = 110·√3 = 190,5 %) | verificato |
| `IaLG`, `IbLG`, `IcLG` (+ `…Ang`), `3IoLG` | Correnti di fase e 3I0 del ramo (kA, alla tensione del ramo) | verificato per la riga Total (`IaLG` = `3IoLG` = `IPPkLG`) |
| `V0/V1/V2LG`, `I0/I1/I2LG` (+ angoli) | Componenti simmetriche (% e kA) | dedotto (I0 = I1 = I2 = I"k1/3 sul Total, verificato su `Bus B`: 2,3961 = 7,1883/3) |
| `RPos`, `XPos`, `RNeg`, `XNeg`, `RZero`, `XZero` | Per la riga **Total**: Z1/Z2/Z0 di Thevenin in **% su 100 MVA** (= Sum2 in Ω). Per i **rami sorgente**: impedenza della sorgente su 100 MVA alla BasekV, con c (rete) o K_G (macchine sincrone) già applicati. Per i rami interni: impedenza equivalente vista dal ramo | Total e sorgenti verificati; rami interni dedotto |
| `BusKV` | Tensione nominale del lato del ramo (kV) | verificato |
| `Flag1`, `Flag2` | Flag di stampa (es. sfasamento/trafo) | aperto |

Le correnti dei rami sono **alla tensione del ramo**, non riportate al bus
guastato (es. in `SCIEC3ph`: `Mtr6 → MCC1` 1,0048 kA a 0,4 kV, `MCC1 → Bus B`
0,03654 kA a 11 kV; rapporto 27,5 = 11/0,4).

### 3.5 `Duty909.SI1S` — duty trifase

**`SCIEC3ph`** (143 righe, contributi 3F fino al 3° livello): `kVNom`, `kVBase`,
`VprefaultNom/Base`, `CFactor`, `FromBus`, `ToBus` (`Total` per la somma),
`Vfrom` (%), `kAReal`, `kAImag`, `X/R`, `kAMag` (I"k del ramo, kA),
`PeakkA`, `SSkA` (sempre 0 nel demo). `X/R` = 999,9 è il valore sentinella per
contributo nullo. Riga `Total`: `kAMag` = I"k, `X/R` = X/R di Z1 (verificato).

**`SCIEC3phSum`** (25 righe): per ogni bus una riga con `DeviceID` = bus
(I"k, ip, Ik identici a `SCIECLGSum1` di `SC_909`, verificato) e una riga per
ogni dispositivo:

| Campo | Significato | Stato |
|---|---|---|
| `DeviceTD` | Ritardo minimo di apertura t_min (s) | dedotto |
| `DeviceMaking` | Potere di chiusura nominale (kA cresta). BT: = n·Icu con n = 2,1 (42 kA → 88,2) o 2,2 (65 kA → 143) come IEC 60947‑2 tab. 2 | verificato |
| `DeviceIbsymm`, `DeviceIdc`, `DeviceIbasym` | Potere di interruzione nominale simm./c.c./asimm. MT: Idc = √2·Ib,r·e^(−t/45 ms) (IEC 62271‑100, τ = 45 ms), asym = √(sym² + dc²) | verificato su tutti gli interruttori MT |
| idem per BT/fusibili | `DeviceIdc` = 0; `DeviceIbasym` = sym·√(1 + 2·e^(−2ωt/(X/R))) con X/R = 3,87 (cos φ 0,25) per LVCB11, ≈ 6,6 (cos φ ≈ 0,15) per i fusibili | verificato (LVCB11: 42·1,01717 = 42,72) / dedotto (fusibili) |
| `IPPk` | I"k che attraversa il dispositivo (può essere un contributo, es. `CB21` = contributo da `Bus3` = 7,3526) | dedotto |
| `ip` | cresta che attraversa il dispositivo | dedotto |
| `Ibsymm` | Ib simmetrica all'istante t_min (con decadimento μ/q delle macchine: `CB B1` 6,298 vs I"k 6,490) | dedotto (μ non ricostruito) |
| `Idc` | componente continua all'apertura | dedotto: l'X/R implicito (`CB B1` 15,75; `Utility Bus` 10,39) differisce da X1/R1 → probabilmente metodo C con fc/f dipendente da f·t |
| `Ibasymm` | √(Ibsymm² + Idc²) | verificato su tutte le righe |
| `Ik` | Ik permanente (solo righe bus) | dedotto |
| `Flag*` | 0 = ok, 1 = critico, 2 = marginale (es. `FlagMaking` = 2 per i quadri al 93,7 %) | dedotto |

**`SCIEC3phSum2`** (11 righe) — duty termico per dispositivo:
`Ith` = I"k·√(m + n) con **n = 1** e m = [e^(4fTk·ln(κ−1)) − 1]/(2fTk·ln(κ−1))
(IEC 60909‑0, corrente termica equivalente), verificato: `LVCB11` m = 0,03731 → Ith =
48,783·√1,03731 = 49,685 (valore ETAP 49,685); `Bus B` (Ik/I"k = 0,975, Tk = 3 s)
dà comunque n = 1,0000. `ThermalEnergy` = Ith²·Tk e `RatedThermalEnergy` =
`DeviceIthr`²·`DeviceTkr` (26,3²·3 = 2075,07): unità **kA²·s** (verificato),
anche se `Alert.Unit` scrive 'MJ'.

**`Alert`**: `Rated`, `Calculated` (stesse unità), `Deviation` =
Calculated/Rated·100 (verificato: 121,76/130 = 93,66 %), `Condition`
(`Making`, `Breaking`, `Bracing Peak`, `Thermal Energy`, `Ib symm.`,
`Ib asymm.`), `AlertType` (`Critical`/`Marginal`). Le righe sono duplicate
(stesso allarme scritto due volte).

### 3.6 `IEC-1-Phase.SI4S` — duty monofase

Lo SI4S contiene sia i risultati "tutti i guasti" per `Swbrd2` (bus 0,4 kV che
alimenta il sottosistema monofase: `SCIECLG*`, `ClippingCurrent`, con c = 1,05)
sia le tabelle monofase:

- **`SCIEC1phSum`** (stesse colonne di `SCIEC3phSum` + `CircuitNumber`):
  `Swbrd2` I"k = 40,904 kA con **`VoltageFact` = 1,1** = 1,1·0,4/(√3·\|Z1\|) con
  Z1 di `SCIECLGSum2` (verificato; il guasto trifase dello stesso bus con c = 1,05
  vale 39,0445, e 39,0445·1,1/1,05 = 40,904). Quindi il modulo monofase usa c = 1,1
  anche in BT, indipendentemente da `CFact1/2` (dedotto). `Bus1` (0,24 kV):
  I"k = Ik = 5,355 kA, ip = 10,110 kA.
- Dispositivi `Panel 1`, `Panel 2` con `DeviceTD` = 0: `Idc` = √2·I"k (nessun
  decadimento, verificato: 57,847 = √2·40,904) e `Ibasymm` = √(Ib² + Idc²) =
  70,847 (verificato); `DeviceIbasym` = √3·Ib,r (25 kA → 43,30, verificato).
- **`SCIEC1phSum2`**: come `SCIEC3phSum2` (Ith = 41,444 = 40,904·√(1 + m), m con
  κ = 1,6867, Tk = 1 s; verificato).
- Gli elementi del sottosistema monofase (pannelli, `Bus1`) **non** compaiono
  nelle tabelle `I*` (le tabelle monofase `IConnect1`, `ICap1` sono vuote):
  per questo studio i dati di ingresso non sono ricostruibili dal file (aperto).
- `Headr.STDCase` = `Duty909` (lo scenario usa quello study case).

## 4. Filigrana del demo e coerenza interna dei numeri

`Headr.1st` = `SAMPLE OUTPUT REPORT - DOES NOT REFLECT THE ACTUAL RESULTS` in tutti
i file: è la versione demo che marca i report. Si è verificato se i numeri sono
comunque coerenti fra loro.

**Verifica Ik3 = c·Un/(√3·\|Z1\|)** con `kVnom`, `CFactor` di `SCIECLGSum1` e
`ZPosOhm` (R, X) di `SCIECLGSum2`:

| File | Bus | c | Un (kV) | \|Z1\| (Ω) | I"k calcolata (kA) | `IPPk3ph` ETAP (kA) | scarto |
|---|---|---:|---:|---:|---:|---:|---:|
| SC_909 | Bus B | 1,10 | 11 | 1,07064 | 6,5250 | 6,5250 | 0,000 % |
| SC_909 | Bus C | 1,10 | 11 | 1,06117 | 6,5833 | 6,5833 | 0,000 % |
| SC_909 | EmergencySwBrd | 1,05 | 0,4 | 0,0049707 | 48,7832 | 48,7832 | 0,000 % |
| SC_909 | SWBRDA | 1,10 | 11 | 0,69948 | 9,9873 | 9,9873 | 0,000 % |
| SC_909 | Utility Bus | 1,10 | 33 | 2,15185 | 9,7394 | 9,7394 | 0,000 % |
| Example‑New | LVBus | 1,05 | 0,48 | – | 17,8953 | 17,8953 | 0,000 % |
| Example‑New | MCC1 | 1,05 | 0,48 | – | 19,3910 | 19,3910 | 0,000 % |
| Example‑New | Sub2A | 1,10 | 13,8 | – | 6,7566 | 6,7566 | 0,000 % |
| Example‑New | Sub 3 | 1,10 | 4,16 | – | 27,2707 | 27,2707 | 0,000 % |
| Example‑New | Sub3 Swgr | 1,10 | 4,16 | – | 25,2631 | 25,2631 | 0,000 % |
| SI4S | Swbrd2 | 1,05 | 0,4 | 0,0062105 | 39,0445 | 39,0445 | 0,000 % |

Con la stessa procedura risultano esatti (scarto < 0,01 %) anche I"k2, I"k1,
I"k2EE (`IPPkLLG`), I"kE2E (`SymmLLG_3I0`) e le impedenze `ZLG/ZLL/ZLLG` su tutti
gli 11 bus; le correnti asimmetriche di `ClippingCurrent` e le relazioni di
`SCIEC3phSum`/`SCIEC1phSum` (Ibasym, Ith, energia, deviazioni degli allarmi)
tornano esattamente; le impedenze dei trasformatori a 2 avvolgimenti, della rete,
del cavo e i contributi di generatore e motori si ricostruiscono dai dati di
ingresso con le regole IEC (K_T, K_G, c·Z_Q).

**Conclusione**: nonostante la filigrana, i numeri dei file demo sono
**internamente coerenti** e coerenti con i dati di ingresso memorizzati nello
stesso file; sono quindi utilizzabili come riferimento per il confronto con il
nostro calcolatore. Non si può escludere che il demo alteri i risultati in modo
coerente (es. dati di rete diversi da quelli del progetto reale), ma i risultati
sono la soluzione corretta della rete descritta dalle tabelle `I*` del file
stesso.

## 5. Indicazioni per il confronto con il nostro calcolatore

1. Costruire la rete dalle tabelle `I*` dello stesso file; per i rami conviene
   partire da `IConnect` (% su 100 MVA, BasekV) che incorpora già K_T e
   tolleranze, e confrontare separatamente la nostra conversione dati di targa →
   p.u. con i valori di `IConnect` (tabella del §2).
2. Riportare le basi: ETAP usa BasekV propagata con le prese; noi Un + rapporto
   fuori nominale. Confrontare le grandezze in Ω o in kA, non in %.
3. Applicare come ETAP: c·Z_Q alla rete; K_T con c_max del lato BT e x_T dopo la
   tolleranza; K_G a generatori **e motori sincroni**; nessun K agli asincroni;
   R delle macchine da `Xpp/R`. Il generatore con trasformatore dedicato non è
   trattato come gruppo di generazione.
4. Confrontare I"k (tutti i tipi di guasto) e le impedenze di Sum2 con
   tolleranza stretta (1e‑5); ip con tolleranza ≈ 2 % finché non si implementa il
   metodo C; Ib/Idc solo dopo aver chiarito μ, q e l'X/R usato per la c.c.
5. Punti aperti (la correzione del trasformatore a 3 avvolgimenti è risolta
   in `04`, μ e q in `06`): significato di `IECMethod`, calcolo di κ (metodo C?), μ/q per Ib,
   resistenza dei cavi a 75 °C, dati del sottosistema monofase del SI4S.
