# 14 — Dimensionamento dei cavi

Nono modulo del simulatore. Sceglie la sezione dei cavi BT in base a:
- portata, con i fattori di correzione;
- coordinamento con la protezione;
- caduta di tensione;
- tenuta al cortocircuito;
- interruzione automatica nei sistemi TN.

Norme di riferimento: IEC 60364-5-52, IEC 60364-4-43, IEC 60364-4-41, IEC 60364-5-54 e IEC 60228.

- Implementazione: [`iec60909/cables.py`](../implementazione/iec60909/cables.py),
  tabelle in [`iec60909/cable_tables.py`](../implementazione/iec60909/cable_tables.py).
- Riga di comando: `python -m iec60909.cavi rete.json [--applica rete_dimensionata.json] [--json]`.
- Esempio: [`esempi/cavi_cabina.json`](../implementazione/esempi/cavi_cabina.json).
  - Rete: cabina 20/0,4 kV da 630 kVA con tre partenze.
  - Partenza verso un quadro: cavo multipolare su passerella perforata, insieme ad altri due circuiti, a 35 °C.
  - Partenza verso un motore: cavo in tubo interrato.
  - Circuito luce: protetto da un MCB, in tubo insieme ad altri tre circuiti.

## Dati

Sezione `cable_sizing`, una voce per linea; la linea è alimentata dal suo nodo `from_bus`.

| Campo | Significato |
|---|---|
| `line` | linea da dimensionare |
| `ib_a`, `cos_phi` | corrente di impiego e fattore di potenza (default: dal flusso di potenza, [`07`](07_flusso_di_potenza.md)) |
| `material`, `insulation` | `cu`/`al`; `pvc` (70 °C) o `xlpe`/`epr` (90 °C) |
| `phases` | 3 (trifase, default) o 1 (fase-neutro a U0 = Un/√3; richiede `ib_a`) |
| `method`, `loaded_conductors`, `arrangement` | metodo di installazione di riferimento (A1, A2, B1, B2, C, D1, D2, E, F, G); conduttori caricati (default 3 in trifase, 2 in monofase); per F e G con 3 conduttori: `trefoil`/`flat`, `horizontal`/`vertical` |
| `ambient_c`, `soil_resistivity_km_w` | temperatura dell'aria (o del terreno per D1/D2) e resistività termica del terreno |
| `grouping`, `circuits`, `cores` | raggruppamento: disposizione B.52.17 in aria (`bunched`, `single_layer_wall_floor`, `single_layer_under_ceiling`, `single_layer_perforated_tray`, `single_layer_ladder_cleats`), distanza B.52.18 per D2 (`touching`, `one_cable_diameter`, `0.125_m`, `0.25_m`, `0.5_m`) o B.52.19 per D1 (`touching`, `0.25_m`, `0.5_m`, `1.0_m`, con `cores` `multi`/`single`) |
| `k_extra` | ulteriore fattore (es. passerelle B.52.20/21, non tabellate) |
| `ampacity_a`, `max_temperature_c` | tabella di portata propria {mm²: A} al posto della IEC (es. cavi MT da catalogo) e temperatura massima del conduttore |
| `sections`, `max_parallel` | sezioni ammesse e numero massimo di conduttori in parallelo |
| `device` o `in_a`, `i2_ratio` | protezione di `protective_devices` ([`09`](09_coordinamento_protezioni.md)) o corrente nominale; I2/In (default 1,30 interruttori IEC 60947-2, 1,6 fusibili gG; 1,45 per gli MCB IEC 60898-1) |
| `vdrop_max_percent`, `upstream_drop_percent` | caduta massima (default 4 %) e caduta a monte |
| `x_ohm_per_km`, `pe_section_mm2` | reattanza (default 0,08 Ω/km) e sezione del conduttore di protezione (default tabella 54.2) |
| `t_sc_s`, `let_through_a2s` | durata del cortocircuito imposta (al posto della curva) e I²t passante del costruttore |
| `disconnection_time_s` | tempo massimo di interruzione nei sistemi TN (0,4 s circuiti terminali a 230 V, 5 s distribuzione) |

## Metodo

Si cerca il minor numero di conduttori in parallelo e, a parità, la sezione
più piccola che supera tutte le verifiche.

1. **Portata.**
   - Iz = n·I0·k, con I0 dalle tabelle dell'allegato B della IEC 60364-5-52:
     B.52.2–B.52.5 per i metodi A1–D2, B.52.10–B.52.13 per E, F e G.
   - k è il prodotto dei fattori di correzione:
     - B.52.14 per l'aria e B.52.15 per il terreno; B.52.16 per la resistività
       (D1 in tubo, D2 direttamente interrato);
     - B.52.17, B.52.18 e B.52.19 per il raggruppamento.
   - Le temperature e le resistività intermedie si interpolano linearmente.
   - Per un numero di circuiti non tabellato si usa il numero successivo, a
     favore della sicurezza. Nelle file singole oltre 9 circuiti non c'è
     ulteriore riduzione.
2. **Coordinamento con la protezione (IEC 60364-4-43, 433.1):** Ib ≤ In ≤ Iz e I2 ≤ 1,45·Iz.
3. **Caduta di tensione:**
   - ΔU% = √3·Ib·L·(R·cosφ + X·sinφ)/(n·Un)·100 in trifase e
     2·Ib·L·(R·cosφ + X·sinφ)/(n·U0)·100 in monofase (andata e ritorno), più
     la caduta a monte.
   - R è il valore IEC 60228 a 20 °C portato alla temperatura di esercizio
     θ = θa + (θz − θa)·(Ib/Iz)².
4. **Cortocircuito (IEC 60364-4-43, 434.5.2).** Deve valere I²t ≤ k²·S².
   - t è il tempo di intervento della protezione, dalla sua curva con la
     banda di tolleranza superiore.
   - Sotto 0,1 s, se indicato, si usa l'I²t passante del costruttore.
   - La verifica si fa due volte:
     - alla corrente massima all'inizio della linea (I"k trifase o monofase
       massima IEC 60909);
     - alla corrente di guasto a terra minima alla fine.
   - Vale anche per il conduttore di protezione.
   - k viene dalla tabella 43A: 115/76 PVC fino a 300 mm², 103/68 oltre, 143/94 XLPE/EPR.
5. **Interruzione automatica (IEC 60364-4-41).** La corrente di guasto a terra
   minima alla fine della linea deve far intervenire la protezione entro
   `disconnection_time_s`.
   - La corrente si calcola dalle impedenze di sequenza IEC 60909 (caso
     minimo, cmin) nel nodo di partenza più quelle del cavo candidato.
   - Per il cavo: Z1 = Z2 = Zf, Z0 = Zf + 3·Zpe, con le resistenze alla
     temperatura massima di esercizio. Si ottiene
     Ik1 = √3·c·Un/|Z1 + Z2 + Z0 + 3·(Zf + Zpe)|.
6. **Applicazione (`--applica`).**
   - Salva la rete con le linee aggiornate: `parallel`, R a 20 °C, X,
     R0 = R + 3·Rpe, X0 = 4·X e `max_i_ka` = Iz.
   - Sulla rete salvata si possono rifare il flusso di potenza e il
     cortocircuito.

Sono disponibili anche i metodi convenzionali, comodi per i calcoli rapidi:
- `voltage_drop_percent`: caduta di tensione con R e X date;
- `min_section_short_circuit`: S = I·√t/k;
- `max_length_tn`: Lmax = 0,8·U0·Sph·Spe/(Ia·ρ·(Sph + Spe)), con
  ρ = 22,5 mΩ·mm²/m (Cu) e 36 mΩ·mm²/m (Al), 80 % di U0 all'origine.

## Tabelle e fonti

La IEC 60364-5-52 non è liberamente consultabile. Le tabelle vengono da
trascrizioni pubbliche delle edizioni nazionali identiche:
- GOST R 50571.5.52-2011, adozione russa IDT della IEC 60364-5-52:2009;
- riproduzione online TiSoft della IEC 60364-5-52:2009;
- KS C IEC 60364-5-52, edizione coreana;
- NBR 5410:2004, norma brasiliana derivata dall'edizione IEC 1999, usata
  solo come conferma.

Non c'è un solo valore inventato o interpolato. Il file
[`strumenti/dati/iec60364_5_52.json`](../implementazione/strumenti/dati/iec60364_5_52.json)
riporta per ogni valore le fonti e il livello di confidenza:
- `cross_checked`: almeno due fonti indipendenti concordano;
- `single_source`: una sola fonte basata sull'edizione 2009;
- `nbr5410_only`: valore presente solo nella NBR 5410;
- `conflict_resolved`: fonti in disaccordo, con la scelta motivata.

Il modulo [`_tabelle_iec60364.py`](../implementazione/iec60909/_tabelle_iec60364.py)
è generato da quel file con
[`strumenti/genera_tabelle_cavi.py`](../implementazione/strumenti/genera_tabelle_cavi.py).

| Tabelle | Fonti | Confidenza |
|---|---|---|
| B.52.2–B.52.5 (A1–D2, Cu e Al) | GOST, TiSoft, KEC (XLPE Cu), NBR 5410 | due o più fonti; 2 conflitti risolti (Al PVC C 2,5 mm²: 18,5 A; Al XLPE D1 300 mm²: 286 A) |
| B.52.10–B.52.13 colonne E, F a trifoglio e G orizzontale | GOST, TiSoft, KS C IEC, NBR 5410 | due o più fonti, salvo alcune celle a fonte unica |
| B.52.10–B.52.12 F in piano e G verticale | NBR 5410 (KEC per XLPE Cu F in piano) | da verificare |
| B.52.14–B.52.19 | GOST, TiSoft, KS C IEC | due o più fonti, salvo B.52.19 parte B (fonte unica) |
| IEC 60228 classe 2 | tre fonti coincidenti | due o più fonti |
| Tabella 43A | quattro fonti; PVC > 300 mm² una sola | due o più fonti / fonte unica |

Quando la sezione scelta usa un valore che non ha almeno due conferme, il
risultato riporta un **avviso** con il livello di confidenza. Su 82 colonne di
portata, 90 valori sono in questa situazione: 68 solo NBR 5410, 20 a fonte
unica, 2 conflitti. Le lacune sono:
- B.52.13 F in piano e G verticale;
- B.52.20 e B.52.21 per passerelle e mensole: si usa `k_extra`;
- le colonne per isolamento minerale.

## Validazione

1. **Calcoli a mano su tabella propria** (indipendenti dalle tabelle IEC):
   - scelta per portata e protezione, incluso il fusibile con I2 = 1,6·In,
     che sposta la sezione;
   - caduta di tensione con R alla temperatura di esercizio (10⁻¹²);
   - conduttori in parallelo;
   - sezione del PE;
   - corrente di guasto a terra a fine linea contro l'anello calcolato a mano
     dalle impedenze IEC 60909 (10⁻¹²);
   - mancato intervento entro 0,4 s su una linea lunga.
2. **Tabelle.** Portate di riferimento (es. 95 mm² Cu nei metodi A1–G), fattori
   B.52.14–B.52.19, resistenze IEC 60228 e k. Su queste tabelle, con 40 °C e 3
   circuiti raggruppati, la sezione scelta è 120 mm² come nel calcolo a mano.
3. **Esempio pubblicato, motore 90 kW** (Power Projects India, *Cable sizing
   calculation – low voltage*): Ib 163,67 A, caduta 2,03 % in marcia e 7,10 %
   all'avviamento, sezione minima al cortocircuito 88,455 mm². Tutti
   riprodotti.
4. **Lunghezze massime nei sistemi TN** (AS/NZS 3000:2018 tabella B1, stessa
   formula del metodo convenzionale della guida Schneider): 12 righe da
   1,5 a 70 mm² per MCB B, C, D (36 valori), riprodotte al metro.
5. **Energia passante.** Con un MCB a 10 ms il calcolo I²·t richiederebbe
   16 mm² per un circuito da 25 A; con l'I²t del costruttore basta la sezione
   data dalla portata.
6. **Esempio della cabina:** sezioni 185, 120 e 10 mm²; con le sezioni
   applicate il flusso di potenza converge.

## Limiti

- **Bassa tensione:** le tabelle sono quelle della IEC 60364-5-52. Per i cavi
  MT serve la tabella del costruttore (`ampacity_a`): le tabelle della
  IEC 60502-2 e il metodo IEC 60287 non sono implementati.
- **Passerelle:** i fattori B.52.20/B.52.21 non sono inclusi (fonti parziali)
  e vanno dati con `k_extra`.
- **Circuiti monofase:** la corrente di impiego va indicata (il flusso di
  potenza è trifase equilibrato); il neutro è considerato caricato come la
  fase, senza le armoniche.
- **Effetto pelle:** la resistenza è in corrente continua, senza l'effetto
  pelle e di prossimità, trascurabile fino a circa 240 mm².
- **Guasto a terra:** si suppone la linea radiale, alimentata dal suo nodo di
  partenza.
- **Tabella 54.2:** il PE ha lo stesso materiale delle fasi.
- **Protezioni:** l'energia passante per tempi sotto 0,1 s va data dal
  costruttore; senza quel dato il calcolo I²·t è cautelativo.
- **Verifica delle tabelle:** i valori segnati con confidenza ridotta e i due
  conflitti risolti vanno controllati su una copia della norma con licenza.
