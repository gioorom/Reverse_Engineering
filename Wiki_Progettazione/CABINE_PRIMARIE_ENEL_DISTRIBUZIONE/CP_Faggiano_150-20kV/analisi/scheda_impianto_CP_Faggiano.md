# Scheda impianto — CP 150/20 kV Faggiano, sezione AT (2 stalli linea + 2 stalli trafo)

Modello Fusion: **Progetti AI / CP_Faggiano_Sezione_AT_A-A** (v4). Script, da eseguire in sequenza: `fusion_stallo_AA.py` (stallo 1) → `update_TR_matelec.py` (trasformatore Matelec) → `fase2_stallo2_castelletto.py` (stallo 2, sbarre, castelletti MT) → `fase3_dettaglio_materiali.py` (passanti di dettaglio, castelletto a profili reali, materiali) → `fase3b_nomi_materiali.py` → `fase4_armadi_comando.py` (armadi di comando unici e rinvii) → `fase5_sezionatore_terra.py` (sezionatore di terra STA di dettaglio). Parametri: `stallo_AA_parametri.json` + blocchi `TR_MAT` / `P2` in testa agli script.
LOD 200-300. Unità mm. Assi: X lungo lo stallo (linea → trafo), Y lungo le sbarre, Z verticale. Origine: asse 7 (sostegno sbarre), quota piazzale ±0.00 = 28 m s.l.m.

**Legenda fonte:** ✔ = dato del costruttore o della tabella · 📐 = misurato in scala 1:50 dalla P-006 (±30 mm) · ❓ = stimato, **da confermare**

## 1. Griglia e quote (P-006)

| Grandezza | Valore | Fonte |
|---|---|---|
| Catena assi A-A (1→9) | 4.75 · 2.50 · 3.50 · 2.50 · 4.00 · 4.20 · 4.20 · 4.00 · 2.50 · 3.00 · 5.50 · 4.50 m | ✔ P-006 |
| X assi rispetto a 7 | TV2 −16.70 · QS3 −14.20 · TA4 −10.70 · QF5 −8.20 · QSB6 −4.20 · **7** 0 · QSB6' +4.20 · QF5' +8.20 · TA4' +10.70 · FV8 +13.70 · IS7' +19.20 · TR9 +23.70 | ✔ |
| Interfase stallo / sbarre | 2.20 m | ✔ P-006 B-B, C-041 |
| Portale sbarre → 6' (B-B) | 4.20 m; tratto sbarre B-B: 4.20 · 6.20 · 6.20 · 4.20 | ✔ |
| Sbarre tubo Al 100/90 (LC1050/60) | +7.20 | ✔ |
| Derivazioni / sezionatori | +4.70 | ✔ |
| Interruttore attacchi | +4.50 inferiore · +6.25 superiore | ✔ |
| TA attacchi P1-P2 | +5.30 | ✔ |
| Collegamento scaricatore → isolatori 7' | +6.70 | ✔ |
| Piano posa sostegni / plinto TR | +0.20 / +0.65 | ✔ |

## 2. Organi e famiglie (un componente ciascuno)

| Sigla | Componente Fusion | Apparecchio | Dati principali | Fonte |
|---|---|---|---|---|
| QF5, QF5' | INT_GL313_POLO + SOST_INT_GL313 + ARM_MANOVRA_FK3-1 | GE GL313F3/4031P (150186, uni) e GL313F1/4031P (150187) — 170 kV, 2000 A, 40 kA, SF6, comando FK3-1 | Ur 170 kV, LIWL 750 kV, massa 1631 / 1325 kg | ✔ E-002 |
| | | Geometria polo e struttura | isolatore supporto 1400, carter Ø420, camera 1600, supporto 2850 (piano 3.05) | 📐 |
| QS3 | SEZ_S3CT_TERRA + SOST_SEZ_S3C + ARM_CMM ×2 | GE S3CT doppia interruzione laterale + lame di terra, 170 kV 1250 A | interasse colonne 1120, colonne 1450, telaio a +3.00 | ✔ tipo M-009 · 📐 geometria |
| QSB6, QSB6' | SEZ_S3C + SOST_SEZ_S3C + ARM_CMM | GE S3C | come sopra, senza lame di terra | ✔ tipo · 📐 geometria |
| TA4, TA4' | TA_DY34 + SOST_DY43_TA | TA 170 kV (tab. DY34) | base a +3.35, testa Ø560 | 📐 / ❓ manca il datasheet |
| TV2 | TV_DY46-2 + SOST_DY43_TV | TV 170 kV (tab. DY46/2) | base a +2.25, attacco +4.83 | 📐 / ❓ M-019 è un rapporto di prova, senza ingombri |
| FV8 | SCAR_SBKC138-SMII + SOST_DY43_SC_H4940 + MORS_LM1085 | Tridelta SBKC 138/SM-II CQX 4500 | H 1337, Hges 1513, alette Ø205/153, base Ø260, codolo Ø40×93, 42 kg; sostegno Ø168.3×6.3 H 4940 | ✔ E-007, C-036 |
| IS7 (sbarre) | ISO_DJ1003 + SOST_LS6096-2_H5350 + MORS_LM1041 | Isolatore portante DJ1003 | H 1500, 16+15 alette Ø235/200, flange Ø235 / Ø160, PCD 200 / 127 | ✔ Bonomi S050645 |
| IS7' | ISO_DJ1003 + SOST_LS6096-1_H4850 + MORS_LM1034-1 | idem | colonna Ø219.1×5.9, trave 2×UPN100 L 4700, piastra 550×550×15 | ✔ C-041, LM1034 |
| SB | SBARRA_AL100-90 | Tubo Al Ø100/90 | tratto modellato Y −4.5 → +5.2 m | ✔ sezione · ❓ estensione |
| TR9 | TR_MATELEC_25MVA + FOND_TR | **Matelec** TP18781E01N rev.5, 25 MVA ONAN 150/20.8 kV, variatore sotto carico | 6405×3600; base 5205×2400; cassa larga 1934; coperchio +2450. Passanti AT CLC-TS 50458 (Um 170 kV, LI 750 kV) inclinati di 30°, terminale a +4090 e a 1709 dall'asse, interasse 1650. Passanti MT (2n-2u-2v-2w) a passo 370. Massa 58.8 t | ✔ Matelec (radiatori, conservatore, altezza base ❓) |
| CMT | SOST_PORTATERMINALI_MT + ISO_MT_C8-125 ×9 + SBARRE_MT_CU100x10 + TERM_CAVO_MT ×12 | Castelletto portaterminali MT | montanti 2×UPN180 H 4450, interasse 2600; testa P19 a +4.580; mensole porta-terminali a +4.218; P11 a +3.740; P9 a +3.008; telaio porta-isolatori 1420×748 a +4.180; mensole reggicavo su 3 livelli; 4 cavi per fase | ✔ C-045, E-020 · ❓ isolatori C8-125 e terminali |
| — | COND_LINEA / COND_DERIV_SBARRE / COND_TRAFO | Collegamenti LM1050/11 | Ø40, percorsi a spezzata | 📐 / ❓ tipo conduttore |

Ogni occorrenza ha l'attributo `BIM/Tag` (es. `QF5-L1`). Ogni componente ha `BIM/IfcClass` e `BIM/Fonte`.

## 2b. Impianto completo

- **Stallo 2** (linea + trafo): seconda istanza degli assiemi STALLO_LINEA e STALLO_TRAFO, traslata di +12.40 m in Y, con attributo `BIM/Stallo` = 1 / 2. Basta modificare un componente perché la modifica valga per entrambi gli stalli.
- **Sistema sbarre**: due semisbarre Ø100/90, da Y −4.50 a +4.85 e da +7.55 a +16.90. Due portali LS6096/2, a Y −4.20 e +16.60. Sezionatore longitudinale 6'' (S3C) a Y +6.20, lama lungo le sbarre a +7.20, su sostegno alto H 5350. Quote dalla P-006 B-B (4.20 · 6.20 · 6.20 · 4.20).
- **Castelletto MT**: uno per trafo, sul lato dei passanti MT, a 2.6 m dal carrello. Collegamenti: passanti MT → isolatori del telaio → sbarre di testa. Cavi MT in discesa lungo i montanti.


## 2c. Dettaglio passanti trasformatore e castelletto (fase 3)

**Passanti AT** — Hitachi Energy GSA 170-OA 1600/0 (distinta Matelec, voce 54), conformi CLC/TS 50458, Um 170 kV, LI 750 kV.

| Elemento | Quote | Materiale | Fonte |
|---|---|---|---|
| Flangia | Ø335 × 25, 12 fori Ø16 su PCD 290 | lega Al A356 | ✔ Matelec f.4 |
| Cono di montaggio + presa capacitiva | Ø260→230, h 115 | lega Al | ❓ |
| Isolatore composito | tronco Ø180, 24 alette Ø325 + 23 alette Ø285, manicotti Ø200 | gomma siliconica | ❓ conteggio alette dal disegno |
| Testa | Ø230 × 30 + testa terminale Ø160 × 50 | lega Al | ❓ |
| Codolo | Ø40 × 80 | rame | ✔ Matelec f.4 |
| Lunghezza lato aria | 1700 mm, inclinazione 30°, terminale a +4090 e a 1709 dall'asse | — | ✔ Matelec f.2-3 |
| Torretta TA | Ø450 × 300 lungo l'asse, flangia Ø520 | acciaio verniciato | ❓ |

**Passanti MT** — Cedaspe SBC 24-1250 (2n-2u-2v-2w, passo 370): porcellana, flangia Ø230, codolo M30 con bandiera in rame (❓ ingombri).

**Castelletto C-045**:
- Profili reali EN 10279: montanti 2×UPN180 ad ali contrapposte, ingombro 250×180.
- Calastrelli P5 (piatti 80) alle quote del disegno.
- Piastra P1 500×500×10 con 4 fori Ø22 (interasse 410), fazzoletti P2 trapezoidali 500/250×150, nervature P3.
- Testa P19 UPN100 L 940.
- Mensole P18 L80×5 L 940 a ±330 dall'asse dei montanti, con bracci P17.
- Traverse P11 UPN120 (+3.740) e P9 UPN80 (+3.008), L 2780.
- Telaio porta-isolatori: bracci P14, montanti P15, diagonali P12, trave P16 UPN80 a +4.180.
- I terminali cavo sono spostati sulle mensole P18; i cavi scendono a lato delle mensole reggicavo.

## 2d. Materiali assegnati

| Elementi | Materiale Fusion |
|---|---|
| Sostegni, portali, castelletti, telai sezionatori, casse TA/TV | Acciaio, Galvanizzato (zincatura a caldo CEI 7-6) |
| Sbarre AT tubo 100/90 | Alluminio 6061 (lega Al per sbarre) |
| Conduttori AT LM1050/11 | Alluminio |
| Morsetteria LM, carter interruttori, teste TA/TV, base scaricatori, flange passanti | Alluminio A356 T6 (lega da fonderia) |
| Sbarre MT Cu 100×10, collegamenti MT, codoli e bandiere dei passanti, contatti dei sezionatori, capicorda | Rame |
| Isolatori DJ1003, involucro scaricatori, passanti AT compositi, terminali cavo | Gomma, Silicone (grigio) |
| Colonne sezionatori, camere e isolatori interruttori, isolatori TA/TV, passanti MT, isolatori C8-125 | Porcellana |
| Cassa, radiatori, conservatore del trasformatore | Acciaio, finitura verniciata, grigio scuro |
| Armadi di comando (FK3, CMM, CSC, ausiliari) | Acciaio inox AISI 304 |
| Cavi MT | Gomma, nero |
| Plinto trasformatore | aspetto Calcestruzzo (la libreria non ha un materiale fisico per il calcestruzzo) |

❓ Porcellana o composito per colonne sezionatori, interruttori e TA/TV: dipende dalla fornitura. Si cambia con una sola regola nello script.


## 2e. Armadi di comando e rinvii (fase 4)

C'è un solo armadio di comando per ogni apparecchio tripolare: i 3 armadi per polo sono stati eliminati.

| Apparecchio | Armadio | Ingombro W×H×P | Posizione | Fonte |
|---|---|---|---|---|
| Interruttore GL313 (QF5, QF5') | ARM_COMANDO_INT_GL313 | 700 × 850 × 450 | struttura del **polo centrale**, 2 staffe + 4 barre M16, base a +0.80. Cavidotti corrugati Ø63 verso i poli laterali | ✔ D1301 §6.7 (montaggio) · ❓ ingombro misurato su P-006 |
| Sezionatori S3C (QSB6, QSB6', QSL6'') | ARM_CMM | 545 × 598 × 463, 70 kg, inox IP54 | sul polo centrale, base a +0.90 | ✔ D1060 fig.11 |
| Sezionatore di linea S3CT (QS3) | ARM_CMM (lama) + ARM_CMM_DBST (lame di terra) | 656 × 698 × 463, 80 kg (DBST) | ai due lati del polo centrale | ✔ D1060 fig.14 |

Ogni armadio ha: cassa, tetto sporgente, porta frontale con cerniere e maniglia lucchettabile, oblò, targa aperto/chiuso, aeratore, piastra ingresso cavi in alluminio con pressacavi in ottone, golfari e staffe di fissaggio. Sui CMM ci sono anche la morsa dell'albero d'uscita (a 114 dal retro) e la sede della manovella di emergenza.

**Rinvii sezionatori** (RINVIO_*): albero di trasmissione verticale Ø50 dall'armadio al polo, tirante di rinvio, tirante interpolare Ø48 sui 3 poli e leve di polo. Per le lame di terra del QS3 il tirante interpolare è all'altezza delle cerniere. ❓ Percorso dei rinvii schematico (disegni d'installazione DIN-49135/49138 non disponibili).


## 2f. Sezionatore di linea con lame di terra (fase 5)

I sezionatori di linea QS3, in entrambi gli stalli linea, sono il tipo **GE S3CT con sezionatore di messa a terra serie STA** sul lato linea (D1210-AA-IT figg. 1.2, 3.3, 6.1, 6.6).

| Elemento (rif. GE) | Modello | Materiale |
|---|---|---|
| Braccio mobile 6.1 | tubo rettangolare 80×60, L 1565 (❓ ~0,7 A da fig. 3.3), incernierato all'estremo lato linea del telaio, parallelo al telaio a 215 dall'asse; disegnato **APERTO** (orizzontale) | lega Al |
| Supporto 6.4, albero di cerniera, bulloni a U 6.6 | all'estremo del telaio | acciaio zincato |
| Aste di contatto 6.2 + guida 6.10 | testa del braccio | rame |
| Conduttore flessibile 6.9 | dal braccio al telaio (a terra) | rame |
| Contatto fisso di terra 6.20 | sul contatto principale della colonna lato linea, sbalzo 215, altezza 145 | rame |
| Asta orizzontale 4.2 + leva 4.7 | coassiale alle cerniere dei 3 poli, comandata dal CMM con DBST tramite albero verticale e tirante | acciaio zincato |

Chiudendo, il braccio ruota di 90° e la sua testa raggiunge il contatto fisso a circa +1,685 sopra la base del sezionatore (assoluta circa +4,69), coerente con il contatto a +4,70.

## 2g. Muro tagliafiamme TR1/TR2 (fase 6, SolidCraft)

Realizzato in SolidCraft 0.20 via MCP sul modello STEP della sezione AT (aperto con `up: y`, quindi X, Y, Z del sito con Z in alto). Script: `implementazione/solidcraft/muro_tagliafiamme_solidcraft.json`; dettagli in `analisi/muro_tagliafiamme.md`.

| Elemento | Posizione (sito, mm) | Dimensioni (mm) | Materiale |
| --- | --- | --- | --- |
| MURO_TAGLIAFIAMME_REI120 (IfcWall) | X 20000…27400, Y 4700…5000, Z 0…5000 | 7400 × 300 × 5000 | c.a. C30/37 XC4, B450C, copriferro 35 |
| FONDAZIONE_MURO_TAGLIAFIAMME (IfcFooting) | X 20000…27400, Y 4350…5350, Z −800…0 | 7400 × 1000 × 800 | c.a. C25/30 XC2 |

Parametri SolidCraft: `MT_L`, `MT_S`, `MT_H`, `MT_X0`, `MT_Y0`, `MT_FB`, `MT_FH`.

## 3. Verifiche eseguite (verificatore)

- Il modello in vista frontale ricalca il profilo A-A: posizioni, sequenza e quote di attacco coincidono.
- La catena altimetrica dei sostegni torna con i dati del costruttore:
  - C-041 H 4850 + DJ1003 1500 + LM1034 150 + 200 = **+6.70** ✔
  - C-041 H 5350 + 1500 + 150 + 200 = **+7.20** ✔
  - C-036 H 4940 + SBKC 1513 − 110 + LM1085 150 + 200 ≈ **+6.69** ✔
- Interfase 2200 mm, maggiore della distanza minima N = 1500 mm per Um 170 kV / LIWL 750 kV (CEI EN 61936-1, tab. 1) ✔
- Basi isolatori a massa tutte ≥ +2.25 m (minimo 2250 mm); la più bassa è il TV a +2.95 ✔
- Parti attive ≥ +4.50 m, maggiori di N + 2250 = 3750 mm ✔ (terminale AT Matelec a +4.74 ✔)
- MT 24 kV (LI 125 kV, N = 220 mm): passo fasi 370 mm ✔; risalite incrociate 250 mm sopra le sbarre di testa ✔
- Ingombri: castelletto a 300 mm dal plinto TR; plinti TR1/TR2 distanziati 4.4 m; nessuna compenetrazione visibile tra stalli 1 e 2

- **Fase 3, analisi di interferenza Fusion**: castelletto ↔ plinto TR, castelletto ↔ TR, portale 7' ↔ TR, isolatori ↔ TR, sbarre MT ↔ TR: **0 interferenze** ✔
- **Distanza terminale AT ↔ radiatori: ⚠ 1270 mm.** Terminale a +4090 e a 1709 mm dall'asse, sulla verticale dei radiatori lato AT. Matelec traccia attorno al terminale un raggio di rispetto **R1300**. Il valore resta sotto quel raggio, ma dipende dalla sommità dei radiatori, che nel modello è stimata a +2820 dal piano di posa. Va confermata l'altezza dei radiatori dal costruttore.
- Distanze di isolamento verso massa misurate sull'intero stallo: ≥ 1.5 m (tranne il punto sopra) ✔

## 4. Decisioni prese e punti aperti

**Decise (22/10/2026):**
- Il trasformatore è il **Matelec**.
- Lo standard di Guagnano (scaricatore, C-036, C-041, DJ1003) **vale anche per Faggiano**.
- I datasheet di **TA, TV e la tabella LM1041 non sono disponibili**: la loro geometria resta misurata in scala dalla P-006 ed è marcata ❓ nel modello.

**Ancora aperti:**
1. Disegni d'installazione GE di interruttore (D1301) e sezionatore (DIN-49135/49138): geometria ancora misurata in scala.
2. Planimetria **P-001**: posizione reale degli stalli lungo le sbarre e degli estremi delle sbarre. Stallo 2 e sezionatore longitudinale sono ricostruiti dal profilo B-B.
3. Isolatori MT C8-125 e terminali cavo MT: ingombri stimati.
4. Il terminale AT Matelec risulta a +4.74, la P-006 lo disegna a circa +5.0: il profilo è probabilmente tracciato su un trafo tipo.
5. Muro tagliafiamme: armatura, giunti e vasca di raccolta olio non modellati; spessore e classe da confermare con il calcolo strutturale (vento, sisma NTC 2018).
6. Non modellati: tralicci capolinea / portali d'arrivo linea, fondazioni (eccetto plinto TR), cavidotti, rete di terra, recinzione, edificio comandi.
