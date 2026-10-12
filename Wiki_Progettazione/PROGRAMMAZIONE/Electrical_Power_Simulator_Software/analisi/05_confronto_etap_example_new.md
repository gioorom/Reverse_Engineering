# 05 — Confronto con ETAP: studio `Example-New/IEC-909.SI2S`

Validazione del pacchetto `iec60909` ([`../implementazione`](../implementazione)) contro
l'uscita di ETAP 2024 (PSRev 22.0.0C) dello studio di cortocircuito IEC del progetto
dimostrativo *Example* (caso di studio `IEC - Duty`).

> **Avvertenza.** La tabella `Headr` del file riporta la nota
> *"SAMPLE OUTPUT REPORT - DOES NOT REFLECT THE ACTUAL RESULTS"*: è un file della demo.
> I numeri però sono coerenti fra loro e con i dati d'ingresso (ricalcolati qui fino alla
> settima cifra), quindi lo usiamo come riferimento numerico, non come verità di campo.

Strumenti (fuori dal repository, cartella di lavoro `scratchpad/scripts-new/`):

| Script | Scopo |
|---|---|
| `dump.py`, `dumpall.py`, `tables.py` | elenco e dump delle tabelle SQLite (aperte in sola lettura) |
| `check_3w_b.py` | verifica della base MVA del trasformatore a tre avvolgimenti |
| `converti_example_new.py` | conversione ETAP → JSON `iec60909` (con opzioni per gli esperimenti) |
| `confronta_example_new.py` | confronto nodo per nodo con `SCIECLGSum1/Sum2` e `ClippingCurrent` |
| `esperimenti_example_new.py` | sensibilità: una scelta di conversione alla volta |
| `example_new_iec909.json` | rete convertita |

Il file `.SI2S` è un database SQLite; letto con
`sqlite3.connect("file:...?mode=ro", uri=True)` e `python -I`.

## 1. Caso di studio

| Campo (`ISCStudyCase`) | Valore | Interpretazione |
|---|---|---|
| `Freq` | 60 | f = 60 Hz → metodo C con fc = 24 Hz |
| `Unit` | English | lunghezze dei cavi in ft, R/X in Ω/1000 ft |
| `IECMethod` | 3 | metodo C per κ (confermato: κ coincide entro 0,005 %) |
| `CFact1`…`Cfact4` | 1,05 / 1,05 / 1,10 / 1,10 | cmax BT = 1,05 (tolleranza +6 %), cmax MT/AT = 1,10 |
| `XFMRTap` | 0 | le prese **sono** applicate: `IBus.BasekV` di Sub2A, Sub22, MCC1 è spostata del 2,5 % e `PreFaultBase` = 97,5 % |
| `MachineXoverR` | 1 | X/R delle macchine dai dati di targa (non i valori fittizi IEC) |
| `IAdjustments.applyXfmrZTol` | 1 | tolleranza di Z dei trasformatori applicata, ma `Tol%` = 0 per tutti |
| `IAdjustments.adjustCableRForTemp` | 1 | nessun effetto visibile: le R dei cavi in `IConnect` sono quelle di libreria |

## 2. Inventario degli elementi

| Tabella | N. | Elementi | Mappatura |
|---|---:|---|---|
| `IBus` | 11 | Main Bus 34,5 kV; Sub2A, Sub2B 13,8 kV; Sub 3, Sub3 Swgr 4,16 kV; Sub22, Sub23 3,45 kV; Bus1, Bus2, LVBus, MCC1 0,48 kV | `buses` (`un_kv` = `NomlkV`) |
| `IUtility` | 1 | Utility su Main Bus: 1200 MVA, X/R 45 | `external_grids` |
| `IXFMR2` | 6 | T2, T3, T4, T22, T23, XFMR 3 (tutti D/Y) | `transformers` |
| `IXFMR3` | 1 | T1 34,5/13,8/4,16 kV, 15/10/5 MVA, Y-solido / D / Y-solido | `transformers3w` |
| `Icable` | 2 | Cable2 (Sub 3 – Sub3 Swgr), Cable14 (Bus1 – Bus2, 2 conduttori/fase) | `lines` |
| `ISynGen` | 1 | Gen1 su Sub2B, 8,824 MVA | `generators` |
| `ISynMotor` | 2 | Syn1 (Sub2A, 13,2 kV), Syn2 (LVBus, 0,46 kV) | `generators` (IEC 60909-0: motori sincroni come generatori) |
| `IIndMachine` | 6 | Mtr2, Pump 1, Mtr6 (×2), Mtr4, Mtr3, Mtr5 | `motors` |
| `ILump` | 3 | LUMP1 (LVBus), LUMP2 (Sub22), LUMP5 (Sub23) | quota motori → `motors` equivalenti |
| `IConnect` | 11 | impedenze di ramo in % su 100 MVA (con K_T) | solo verifica |
| `IImp`, `IReact` | 0 | — | — |

Nessun interruttore di congiuntura (`Tie Breakr`) in `IConnect`; il convertitore li
gestirebbe fondendo i due nodi.

Risultati disponibili solo per **5 nodi guastati**: LVBus, MCC1, Sub2A, Sub 3, Sub3 Swgr.

### Interpretazione delle tabelle dei risultati (verificata)

- `SCIECLGSum1.IPPk3ph` = I"k trifase: c·Un/(√3·|Z1|) con Z1 di `SCIECLGSum2` riproduce
  il valore (LVBus: 1,05·0,48/(√3·0,016260) = 17,895 kA). `ip3ph` = picco,
  `Ik3ph` = permanente. Analogo per LG, LL, LLG.
- `IPPkLLG` è la **massima corrente di fase** del guasto bifase a terra; la corrente
  verso terra 3I0 è `ClippingCurrent.SymmLLG_3I0`.
- `SCIECLGSum2`: R/X di sequenza diretta, inversa e omopolare nel punto di guasto, in Ω.
- `IConnect` R/X/Z: % su 100 MVA alla `BasekV` del nodo, **già moltiplicate per K_T**
  (T23: 130 % · 1,0059 = 130,767 % = `IConnect.Z`).
- `IUtility.RPos100MVA`/`XPos100MVA` = 100/MVA3ph = 8,333 % **senza** c.
- `SCIECLG`: contributi di ramo e di macchina; le impedenze di macchina vi compaiono in
  % su 100 MVA, utili per verificare la mappatura dei motori (vedi § 3).

## 3. Ipotesi di mappatura (tutte verificate numericamente)

**Rete esterna.** `skq_max_mva` = MVA3ph = 1200, `rx_max` = 1/45. ETAP calcola
ZQ = c·Un²/S"kQ come la IEC (eq. 10) anche se `IUtility` riporta Z senza c: con
Skq = 1,1·1200 tutti i nodi si spostano fino a +1,2 % (§ 5). Sequenza zero:
`x0x1` = XZero/XPos = 0,5951, `r0x0` = RZero/XZero = 0,0222.

**Trasformatori a due avvolgimenti.** `ukr` = PosZ, `urr` = PosZ/√(1+(X/R)²), idem
per `uk0`/`ur0` da ZeroZ, ZeroX/R. Gruppo: `D/Y` con secondario a terra (`Solid` o
`Resistor`) → `Dyn`. Resistore di neutro: `zn_lv_ohm` = Un/(√3·I) (T2: 13,8 kV/400 A =
19,92 Ω = `SecGrdOhm1`; T3: 0,48 kV/10 A = 27,71 Ω). Per T4, T22, T23, XFMR 3 (`Solid`)
`SecGrdOhm1` = 27,71 Ω è un residuo e non va usato.

**Prese.** `Prim%Tap` = −2,5 % su T2 e XFMR 3 → `ur_hv_kv` = PrimkV·(1 + tap/100)
(33,6375 e 4,056 kV). ETAP in più varia Z con la presa: T2 ha `Minus5PercTap` = 2,1 %
→ a −2,5 % Z·(1 + 1,05 %), interpolazione lineare, applicata anche a Z0 e prima di
K_T. Verifica su `IConnect` di T2: 6,9 %·1,0105 → x_T = 6,966 %, K_T = 1,003076,
Z = 69·1,0105·1,003076·(13,8/14,1538)² = 66,486 % (ETAP 66,486 %).

**Trasformatore a tre avvolgimenti T1.** **Conclusione: PSPosZ, STPosZ, TPPosZ sono
tutte in % sulla base PMVA = 15 MVA**, e ETAP calcola K_T di ogni coppia con x
riferita alla potenza di coppia min(Sr_A, Sr_B) (10, 5, 5 MVA), come prevede la IEC.
Le tre righe `IConnect` di T1 sono il triangolo equivalente della stella (con K_T),
in % su 100 MVA: ricalcolate con questa ipotesi coincidono entro 2·10⁻⁶
(`check_3w_b.py`); nessuna combinazione di basi diverse si avvicina. Nel JSON:
`sr_hv_mv` = 10, `sr_hv_lv` = 5, `sr_mv_lv` = 5 MVA, `ukr_coppia` = uk_ETAP·Sr_coppia/15
(4,733 %, 2,4 %, 4,7 %). Gruppo `YNdyn` (primario e terziario a stella a terra franca,
secondario a triangolo); Z0 uguale a Z1 per i dati di targa.

**Cavi.** Unità inglesi: `RPos`/`XPos` in Ω/1000 ft, `Length` in ft, `No/Ph` → `parallel`.
Verifica Cable2: 0,0223·0,222/(4,16²/100) = 2,8607 % = `IConnect.R`. Nessuna correzione
di temperatura (R di libreria, riferita a 20 °C nel caso massimo).

**Generatore e motori sincroni.** `xd2_percent` = Xdpp, `x2_percent` = X2,
`cos_phi` = |PF|, `rg_ohm` = X"d[Ω]/(Xpp/R) (X/R di macchina, non R_Gf IEC). ETAP
applica K_G anche ai motori sincroni: Syn2 in `SCIECLG` ha X = 13 791,7 % su 100 MVA
= 20 %·(0,46²/0,13422)/0,002304·K_G con K_G = (0,48/0,46)·1,05/(1 + 0,2·0,436) = 1,0078.
Gen1 ha `GNDType` = 2, interpretato come neutro franco (X0 = Xzero = 12 %): **non
verificabile**, perché Sub2B non è guastato e il suo circuito omopolare è isolato dai
triangoli di T1 e T23. I motori sincroni hanno `GNDType` = 1 (neutro isolato).

**Motori asincroni.** `pr_mw` = kVA/1000 con `efficiency` = `cos_phi` = 1 (così SrM =
kVA di ETAP; equivale a HP·0,7457/(η·cosφ), `FlagHP/kW` = 2 significa HP),
`ilr_ir` = LRC/100, `rx` = 1/(Xpp/R), `x2_percent` = X2, `rx2` = R/X2 (R di sequenza
diretta), `pole_pairs` = Poles/2 per i motori MT. **Mtr6 ha `Quantity` = 2 ma ETAP ne
conta uno solo**: in `SCIECLG` il contributo di Mtr6 a MCC1 (0,887 kA) e la sua
impedenza (12 663,9 % su 100 MVA) sono quelli di un solo motore da 120 HP, e il totale
di MCC1 torna solo con `count` = 1 (con 2 si ha +4,4 %). Nel JSON si usa 1.

**Carichi concentrati.** Solo la quota motori (`MTR%`) contribuisce: motore equivalente
con SrM = kVA·MTR% (LUMP1 154 kVA, LUMP2 2100 kVA, LUMP5 350 kVA), `ilr_ir` =
100/√(Xpp² + R²), `rx` = 1/(Xpp/R). Verifica LUMP1: X = 15,365 %·0,46²/0,154 MVA =
0,2111 Ω = 9163 % su 100 MVA = `SCIECLG.XPos`. In `SCIECLG` X2 = X1 per i carichi
concentrati, come nel nostro default.

**Fattore κ.** Metodo C (`IECMethod` = 3), caso `max`, f = 60 Hz.

### Elementi non supportati dal pacchetto

Nessuno è necessario per questo studio. Restano fuori, senza effetto sui risultati:
la quota statica dei carichi concentrati (non contribuisce al guasto); la variazione di
Z con la presa e la tolleranza di Z, che non sono campi del pacchetto ma vengono
riportate dal convertitore in `ukr`/`uk0`; la corrente permanente Ik3ph, che il
pacchetto non calcola in reti con generatori (serve il metodo λ), per cui non è
confrontata.

## 4. Confronto (caso massimo, metodo C)

Valori ETAP / iec60909 (Δ %). Correnti in kA, impedenze in Ω nel punto di guasto.

| Nodo | I"k3 | ip3 | I"kLL | I"kLG | I"kLLG (fase max) | I"kE2E (3I0) | \|Z1\| | \|Z2\| | \|Z0\| |
|---|---|---|---|---|---|---|---|---|---|
| LVBus | 17,895 / 17,895 (0,000) | 45,719 / 45,719 (−0,000) | 15,497 / 15,497 (0,000) | 0,0105 / 0,0105 (0,000) | 15,499 / 15,499 (0,000) | 0,00525 / 0,00525 (0,000) | 0,016260 / 0,016260 (0,000) | 0,016263 / 0,016263 (0,000) | 83,140 / 83,140 (0,000) |
| MCC1 | 19,391 / 19,391 (0,000) | 50,006 / 50,006 (0,000) | 16,583 / 16,583 (0,000) | 18,875 / 18,875 (0,000) | 19,292 / 19,292 (0,000) | 18,842 / 18,842 (0,000) | 0,015006 / 0,015006 (0,000) | 0,015388 / 0,015388 (0,000) | 0,015863 / 0,015863 (0,000) |
| Sub2A | 6,7566 / 6,7566 (0,000) | 17,915 / 17,915 (0,000) | 5,8514 / 5,8514 (0,000) | 0,4378 / 0,4378 (0,000) | 5,9609 / 5,9609 (0,000) | 0,2196 / 0,2196 (0,000) | 1,2971 / 1,2971 (0,000) | 1,2971 / 1,2971 (0,000) | 59,828 / 59,828 (0,000) |
| Sub 3 | 27,271 / 27,271 (0,000) | 73,801 / 73,799 (−0,003) | 23,595 / 23,595 (0,000) | 27,559 / 27,559 (0,000) | 27,475 / 27,475 (0,000) | 27,905 / 27,905 (0,000) | 0,096879 / 0,096879 (0,000) | 0,097058 / 0,097058 (0,000) | 0,093665 / 0,093665 (0,000) |
| Sub3 Swgr | 25,263 / 25,263 (0,000) | 64,477 / 64,475 (−0,004) | 21,856 / 21,856 (0,000) | 24,459 / 24,459 (0,000) | 25,454 / 25,454 (0,000) | 23,734 / 23,734 (0,000) | 0,10458 / 0,10458 (0,000) | 0,10480 / 0,10480 (0,000) | 0,11492 / 0,11492 (0,000) |

Tutti gli scostamenti sono **sotto 0,005 %**; quelli di I"k e Z sono sotto 10⁻³ %
(arrotondamento dei dati `float32` di ETAP). Il residuo su ip (−0,003/−0,004 % a Sub 3
e Sub3 Swgr) viene dal κ del metodo C e resta molto sotto la precisione del metodo.

Nessuno scostamento supera l'1 %. Le cause delle differenze >1 % viste durante la
conversione sono riassunte qui sotto.

## 5. Esperimenti di sensibilità

Ogni riga cambia una sola scelta rispetto al riferimento e riporta lo scostamento
massimo da ETAP (`esperimenti_example_new.py`; K_T = 1 è forzato con un monkeypatch
a runtime, senza modificare il pacchetto).

| Variante | Scostamento massimo da ETAP |
|---|---|
| riferimento (§ 3) | < 0,005 % su tutto |
| Skq = 1,1·MVA3ph (ZQ = 100/MVA3ph, senza c) | I"k3 +1,22 % (Sub 3); ip3 +1,23 %; I"kLG +1,06 %; \|Z0\| 0,72 % |
| prese ignorate | I"k3 +1,27 % (Sub2A); I"kLG 0,24 % (MCC1) |
| prese senza variazione di Z (T2) | I"k3 +0,77 % (Sub2A) |
| Mtr6 con `Quantity` = 2 | I"k3 +4,40 % (MCC1); I"kLL 4,03 %; I"kLG 2,62 % |
| senza carichi concentrati | I"k3 −8,51 % (Sub2A) |
| senza motori asincroni | I"k3 −13,65 % (MCC1) |
| metodo κ B | ip3 10,82 % (Sub3 Swgr) |
| K_T = 1 | I"k3 3,33 % (MCC1); \|Z0\| 4,58 % (MCC1) |
| Z2 = Z1 per i motori asincroni (pacchetto prima dell'aggiunta di `x2_percent`) | I"kLL +1,27 %, I"kLLG +0,86 %, I"kLG +0,84 % a MCC1; ≤ 0,1 % altrove |

Ogni variante peggiora il confronto, quindi le scelte del § 3 sono quelle che ETAP usa
davvero: ZQ con c, prese con variazione di Z, un solo Mtr6, K_T su Z1 e Z0, metodo C,
Z2 dei motori asincroni da X2 di targa.

## 6. Conclusioni e punti aperti

- Con la mappatura del § 3 il pacchetto riproduce ETAP su tutti i 5 nodi e su tutti i
  tipi di guasto (3F, 2F, 1F-T, 2F-T con fasi e 3I0), su ip e su Z1/Z2/Z0, entro 0,005 %.
- **Base MVA del trasformatore a tre avvolgimenti:** PMVA per tutte e tre le coppie, con
  K_T calcolato sulla potenza di coppia min(Sr). Vale anche per SC_909, verificato
  indipendentemente dal coordinatore.
- **`Quantity` dei motori asincroni:** in questo file ETAP la ignora (Mtr6). Va
  verificato su altri studi prima di generalizzare; può dipendere dalla demo.
- **Neutro di Gen1 (`GNDType` = 2):** il significato non è verificabile con questo
  studio.
- Ik permanente non confrontata: il pacchetto non la calcola in presenza di generatori.
