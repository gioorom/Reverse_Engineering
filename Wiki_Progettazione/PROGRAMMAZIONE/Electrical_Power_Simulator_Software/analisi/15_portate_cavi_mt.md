# 15 — Portate dei cavi MT/AT (IEC 60287)

Decimo modulo del simulatore. Calcola la portata in regime permanente di un
circuito di tre cavi unipolari con isolante estruso, secondo la IEC 60287-1-1
(perdite) e la IEC 60287-2-1 (resistenze termiche), con fattore di carico 100 %.

La IEC 60502-2 riporta nell'allegato B tabelle di portata per i cavi da
3,6/6 a 18/30 kV. Quelle tabelle sono calcolate con lo stesso metodo IEC 60287
e non sono liberamente consultabili: il modulo esegue il calcolo vero e
proprio partendo dalla costruzione del cavo e dalla posa.

- Implementazione: [`iec60909/iec60287.py`](../implementazione/iec60909/iec60287.py).
- Riga di comando: `python -m iec60909.portate_mt rete.json [--json]`.
- Dimensionamento: la voce di `cable_sizing` con `ratings` (elenco di voci di
  `cable_ratings`, una per sezione) usa queste portate al posto delle tabelle BT
  ([`14`](14_dimensionamento_cavi.md)).

## Dati

Sezione `cable_ratings`: `id`, `cable` (costruzione), `installation` (posa).

| `cable` | Significato |
|---|---|
| `conductor_material`, `area_mm2`, `conductor_diameter_mm`, `r20_ohm_per_km`, `ks`, `kp` | conduttore; R a 20 °C (default IEC 60228), coefficienti dell'effetto pelle e di prossimità (tabella 2: 1 e 1 per corda rotonda con isolante estruso) |
| `conductor_screen_mm`, `insulation_mm`, `insulation_screen_mm`, `under_screen_mm`, `under_screen_rho_t` | spessori degli strati semiconduttori, dell'isolante e dei nastri sotto lo schermo |
| `insulation_eps`, `insulation_tan_delta`, `insulation_rho_t`, `semicon_rho_t` | ε e tanδ (tabella 3: XLPE 2,5; 0,004 fino a 18/30 kV, 0,001 oltre), resistività termiche |
| `screen_kind`, `screen_material`, `screen_area_mm2`, `screen_thickness_mm`, `screen_lay_factor` | schermo a fili, a nastro o guaina tubolare (sezione π·d·t); fattore di cordatura dei fili |
| `bedding_mm`, `oversheath_mm`, rispettive resistività | letto e guaina esterna |
| `max_temperature_c`, `t1_factor`, `t3_factor` | temperatura massima del conduttore; fattori sulle resistenze termiche (default automatici, vedi sotto) |

| `installation` | Significato |
|---|---|
| `kind` | `buried` (direttamente interrati), `ducts` (in tubi interrati), `air` (in aria all'ombra) |
| `formation`, `transposed`, `spacing_mm` | `trefoil` o `flat`; trasposizione delle fasi in piano; interasse (default a contatto) |
| `depth_m`, `soil_temperature_c`, `soil_rho_t` | profondità dell'asse (trifoglio: baricentro), terreno |
| `bonding`, `eddy_both_ends` | collegamento degli schermi `both_ends`, `single_point`, `cross_bonded`; perdite parassite anche con collegamento alle due estremità (scelta del WG CIGRE B1.56) |
| `duct_inner_mm`, `duct_outer_mm`, `duct_type`, `duct_rho_t` | tubi (costanti U, V, Y della tabella 4 per i tubi in plastica) |
| `air_temperature_c`, `air_arrangement`, `air_z`, `air_e`, `air_g`, `trough_perimeter_m` | posa in aria: coefficienti Z, E, g della tabella 2 della IEC 60287-2-1 (default `trefoil` 0,96/1,25/0,20 e `flat_touching` 0,62/1,95/0,25, confermati da due fonti; per le altre disposizioni vanno indicati); canaletta chiusa non riempita |
| `other_cables_m` | posizioni (x, y) di altri cavi uguali e ugualmente caricati (mutuo riscaldamento) |
| `u0_kv`, `frequency_hz` | tensione verso terra e frequenza |

## Metodo

I = √{[Δθ − Wd·(0,5·T1 + T2 + T3 + T4)] / [R·T1 + R·(1 + λ1)·T2 + R·(1 + λ1)·(T3 + T4)]}

- **Resistenza in c.a.:** R = R'·(1 + ys + yp), con R' alla temperatura
  massima. Effetto pelle nei tre campi di xs (fino a 2,8, fino a 3,8, oltre)
  ed effetto di prossimità secondo la 2.1; in piano s è la distanza tra fasi
  adiacenti (√(s1·s2) se diverse).
- **Perdite dielettriche:** Wd = ω·C·U0²·tanδ, con C = ε/(18·ln(Di/dc)).
- **Perdite nello schermo:** λ1 = λ1' + λ1''.
  - **Circolazione (λ1')**, solo con schermi collegati alle due estremità:
    - trifoglio: Rs/R/(1 + (Rs/X)²);
    - piano trasposto: la stessa formula con X1;
    - piano senza trasposizione: formule con P, Q e Xm, diverse per il cavo
      centrale e per i due esterni.
  - **Parassite (λ1'')** per le guaine tubolari, con i termini β1, gs, λ0, Δ1
    e Δ2 per trifoglio, cavo centrale ed esterni. Con il collegamento alle due
    estremità sono ridotte dal fattore F(M, N).
- **Resistenze termiche:**
  - T1 per strati (semiconduttori e isolante);
  - T3 della guaina esterna;
  - fattori per il trifoglio interrato a contatto (IEC 60287-2-1, 4.2.4.3):
    T3 × 1,6 e, con schermo a fili e U0 ≤ 35 kV, anche T1 × 1,07
    (edizione 2023, come nel caso 4 della CIGRE TB 880);
  - T4 secondo la posa:
    - **interrati:** formula del trifoglio a contatto, altrimenti metodo
      delle immagini per il cavo considerato e il mutuo riscaldamento;
    - **in tubi:** T4' (aria nel tubo, con la temperatura media iterata),
      T4'' (parete del tubo) e T4''' (terreno);
    - **in aria:** h = Z/De^g + E e iterazione su (Δθs)^¼, con il
      riscaldamento dovuto alle perdite dielettriche. Nella canaletta chiusa
      l'aria si riscalda di ΣW/(3·p).
- **Iterazione:** sulle temperature degli schermi (da cui Rs e λ1), sulla
  temperatura media nei tubi e sul riscaldamento della canaletta. Si calcola
  la portata di ciascuno dei tre cavi e il circuito prende la minore.

## Validazione

La CIGRE TB 880 (2022), *Power cable rating examples for calculation tool
verification*, raccoglie i casi di prova per i programmi di calcolo. Il caso
introduttivo 0 usa un cavo 132 kV con conduttore Cu da 630 mm², isolante XLPE
da 15,5 mm, guaina di alluminio da 0,8 mm, posato a 1 m con terreno a 20 °C e
1 K·m/W.

| Caso | Riferimento [A] | Calcolato [A] |
|---|---|---|
| 0-1 a trifoglio interrato, perdite parassite comprese (§4.6.4, valore CIGRE) | 803,1596 | 803,1596 |
| 0-2 in tubi HDPE a contatto, perdite parassite comprese (§4.7.7, valore CIGRE) | 679,8410 | 679,8410 |
| 0-1 senza perdite parassite (§4.5) | 821,7763 | 821,7763 |
| 0-1 schermi collegati a un estremo (§4.6.3) | 886,1753 | 886,1753 |
| 0-2 senza perdite parassite (§4.7) | 682,8145 | 682,8145 |
| 0-5 in piano in canaletta, cavo limitante (§4.10) | 765,82 | 763,64 (−0,28 %) |
| 4: 33 kV, 240 mm², schermo a fili, trifoglio interrato (§8, valore CIGRE) | 537,4631 | 536,41 (−0,2 %) |

- I primi due valori sono quelli pubblicati da CIGRE. Gli altri vengono dai
  notebook che riproducono i casi della brochure
  ([frdmendoza/cbl_CIGRE_TB880](https://github.com/frdmendoza/cbl_CIGRE_TB880)).
- I casi 0-1 e 0-2 coincidono entro 10⁻⁶ A, insieme alle grandezze
  intermedie: T1, T3, T4, Wd, R in c.a., λ1 e temperatura della guaina.
- Per il caso 0-5 il notebook semplifica il riscaldamento dell'aria nella
  canaletta: 25 K costanti nel calcolo della temperatura superficiale e
  perdite del primo cavo applicate a tutti. Lo scarto sul cavo limitante è
  lo 0,28 % (0,33 % con le perdite parassite); per gli altri due cavi il
  confronto non è significativo.
- **Caso 4.**
  - Dalla brochure, nella trascrizione della suite di verifica CableSketch,
    coincidono T1 = 0,4110322351 (con il fattore 1,07), T3 = 0,1241941899
    (con 1,6), T4 = 1,8525, ys = 0,00884, yp = 0,00662 e Wd = 0,1084 W/m.
  - La guaina esterna, in tre sottostrati nella brochure, è rappresentata
    con la resistività equivalente che dà il T3 pubblicato.
  - Lo scarto sulla portata (−0,2 %) viene dalla resistenza dei fili dello
    schermo: CIGRE ne considera la cordatura, il cui passo non è nelle fonti
    aperte. Con `screen_lay_factor` si può indicare.

Le formule e le costanti sono state confrontate con più implementazioni
aperte indipendenti della norma (Alliander cable-thermal-model, DiTuS,
C4_open, CableDesign, IEC_Power_Cable_tools e i notebook TB 880). Due
eccezioni hanno una sola conferma e sono segnalate:
- il fattore 1,07 su T1 per gli schermi a fili, ricavato dal caso 4 della
  brochure;
- la reattanza X1 della formazione in piano trasposta.

## Limiti

- **Cavi:** solo unipolari con isolante estruso. Mancano i cavi tripolari,
  l'armatura (λ2) e i conduttori Milliken (perdite parassite con schermi
  collegati alle due estremità e coefficienti ks/kp da indicare a mano).
- **Posa in aria:** senza irraggiamento solare. I coefficienti Z, E, g della
  tabella 2 sono predefiniti solo per trifoglio e piano a contatto; per le
  altre disposizioni vanno indicati.
- **Tubi:** costanti U, V, Y solo per i tubi in plastica; niente blocchi di
  calcestruzzo o letti di posa con resistività diversa (fattore Gb).
- **Cross-bonding:** i tratti si suppongono perfettamente bilanciati, con
  λ1' = 0.
- **Regime:** solo portata permanente al 100 %; mancano i fattori di carico
  ciclici (IEC 60853) e il regime transitorio.
