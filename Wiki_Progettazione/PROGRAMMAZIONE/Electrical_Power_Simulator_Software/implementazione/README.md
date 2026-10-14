# iec60909 — cortocircuito, flusso di potenza, arc flash e coordinamento

Pacchetto Python di Electrical Power Simulator Software con quattro calcoli
sulla stessa descrizione della rete:

- **cortocircuito** secondo la **IEC 60909-0:2016**, scritto dalle formule
  della norma;
- **flusso di potenza** (load flow) con il metodo di Newton-Raphson;
- **arc flash** (energia incidente e confine dell'arco) secondo
  **IEEE 1584-2018**, con il metodo di Lee oltre 15 kV e i metodi
  dell'allegato D.5 di NFPA 70E in corrente continua;
- **coordinamento delle protezioni**: sequenza di intervento, selettività,
  sensibilità e curve tempo-corrente di relè, interruttori BT e fusibili,
  per guasti trifase, bifase e monofase a terra (protezioni di fase e di
  terra, anche direzionali).

Cortocircuito e flusso di potenza sono verificati contro
[pandapower](https://www.pandapower.org/), implementazione open source
indipendente, e con calcoli a mano. L'arc flash è verificato con gli esempi
svolti della norma e con [arcflash-calc](https://github.com/LiaungYip/arcflash).

## Installazione

Richiede Python 3.10+ e numpy.

```bash
cd Wiki_Progettazione/PROGRAMMAZIONE/Electrical_Power_Simulator_Software/implementazione
pip install -e .            # solo il calcolo
pip install -e ".[test]"    # anche pytest e pandapower per i test
```

## Uso

```bash
python -m iec60909 esempi/cabina_mt_bt.json              # correnti massime, Markdown
python -m iec60909 esempi/cabina_mt_bt.json --caso min   # correnti minime
python -m iec60909 rete.json --kappa B --tk 0.5 --json   # metodo B, Tk = 0,5 s, JSON
python -m iec60909 rete.json --tmin 0.05                  # Ib con tempo minimo di interruzione 50 ms
python -m iec60909 rete.json --rf 0.01 --xf 0.005         # guasto attraverso Z_F = 0,01 + j0,005 Ω
```

Da Python:

```python
from iec60909 import load_network, calculate

risultato = calculate(load_network("rete.json"), case="max", kappa_method="C", tk_s=1.0,
                      tmin_s=0.1, zf_ohm=0j)
print(risultato.bus("QGBT").ikss3_ka)
```

### Flusso di potenza

```bash
python -m iec60909.flusso esempi/rete_flusso_potenza.json          # Markdown
python -m iec60909.flusso rete.json --qlim --json                  # limiti di Q, JSON
```

```python
from iec60909 import load_network, run_load_flow

lf = run_load_flow(load_network("rete.json"), enforce_q_lims=False)
print(lf.bus("QGBT").vm_pu, lf.branch("T1").loading_percent, lf.losses_mw)
```

Risultati: nodi (`vm_pu`, `u_kv`, `va_degree`, potenze immesse), rami
(`p_from_mw`, `q_from_mvar`, `p_to_mw`, `q_to_mvar`, `i_from_ka`, `i_to_ka`,
`pl_mw`, `loading_percent`; gli avvolgimenti dei trasformatori a tre
avvolgimenti sono i rami `<id>:hv`, `<id>:mv`, `<id>:lv`), sorgenti (potenze
di reti esterne e generatori). Modelli e limiti:
[`../analisi/07_flusso_di_potenza.md`](../analisi/07_flusso_di_potenza.md).

### Arc flash

```bash
python -m iec60909.arco esempi/arc_flash_cabina.json         # Markdown
python -m iec60909.arco rete.json --json                     # JSON
python -m iec60909.arco rete.json --ibf c1                   # Ibf = I"k con c = 1
```

```python
from iec60909 import CurrentStep, Enclosure, Protection, arc_flash, arc_flash_study, dc_arc_flash, load_network

risultati = arc_flash_study(load_network("rete.json"))           # punti della sezione arc_flash
r = arc_flash(Enclosure(0.4, "VCB", gap_mm=32, distance_mm=610), ibf_ka=25.0,
              protection=Protection(time_ms=100))
print(r.e_cal_cm2, r.afb_mm, r.ppe_category)

# più intervalli: 25 kA per 30 ms (motori), poi 21 kA fino all'eliminazione
r = arc_flash(Enclosure(0.4, "VCB", gap_mm=32, distance_mm=610), None, Protection(time_ms=100),
              steps=[CurrentStep(25.0, 30.0), CurrentStep(21.0)])
# corrente continua: 250 V, 4 kA, metodo della massima potenza (Doan), arco in cella (fattore 3)
r = dc_arc_flash(250.0, 457.2, Protection(time_ms=500), ibf_ka=4.0, method="doan")
```

Metodo scelto automaticamente: IEEE 1584-2018 da 0,208 a 15 kV, Lee oltre
15 kV (corrente d'arco = Ibf, un solo caso), NFPA 70E D.5.1 (Doan) o D.5.2
(Stokes-Oppenlander) per i punti in c.c.; il risultato riporta `method`,
`ibf_source` e gli avvisi (`warnings`, es. punti sotto 240 V alimentati da
meno di 125 kVA di trasformazione). Ibf è la I"k trifase IEC 60909 del nodo
(`ibf="iec60909"`), la stessa riscalata a c = 1 (`ibf="c1"`) oppure il valore
`ibf_ka` del punto. Con `motor_decay_ms` o `steps` il calcolo è a più
intervalli: energie sommate, tempo di eliminazione dal consumo della
protezione Σ Δt_k/t(I_k) = 1. Procedura, campo di validità e limiti sono in [`../analisi/08_arc_flash_ieee1584.md`](../analisi/08_arc_flash_ieee1584.md).

### Coordinamento delle protezioni

```bash
python -m iec60909.coordinamento esempi/coordinamento_cabina.json            # Markdown
python -m iec60909.coordinamento rete.json --svg tcc --nodi QD1 --json      # curve SVG, JSON
python -m iec60909.coordinamento rete.json --ib --tmin 0.05 --no-terra      # Ib, senza guasti a terra
```

```python
from iec60909 import coordination_study, fault_currents, load_network

rete = load_network("rete.json")
studio = coordination_study(rete, max_time_s=5.0)          # anche current_basis="ib", earth_faults=False
print(studio.issues)                                      # problemi trovati
print(fault_currents(rete, "QD1").branch_ka)               # correnti nei rami (kA), guasto trifase
fc = fault_currents(rete, "QD1", fault_type="1ph")         # "3ph", "2ph", "2ph_e", "1ph"
print(fc.branch_phase_ka, fc.branch_seq_ka)                # correnti di fase e di sequenza nei rami
```

Livelli di guasto dello studio:
- trifase massimo, oppure con la corrente di interruzione Ib (`--ib`);
- bifase minimo;
- monofase massimo e minimo, nei nodi con percorso verso terra.

Le correnti nei rami vengono dalle tre reti di sequenza, con gli sfasamenti
dei gruppi vettoriali, i convertitori pieni e i guasti interni ai gruppi di
generazione. Il codice di uscita della riga di comando è 1 se ci sono
problemi. Dispositivi, verifiche e limiti:
[`../analisi/09_coordinamento_protezioni.md`](../analisi/09_coordinamento_protezioni.md).

### Stabilità transitoria

```bash
python -m iec60909.stabilita esempi/kundur_due_aree.json --tfine 5 --svg angoli.svg
python -m iec60909.stabilita rete.json --tcc B --apri L2      # tempo critico di eliminazione
```

```python
from iec60909 import StabilityEvent, critical_clearing_time, load_network, simulate

rete = load_network("rete.json")
res = simulate(rete, t_end_s=3.0, dt_s=0.002)            # eventi da stability_events
print(res.stable, res.relative_angles_deg()["G1"].max())
print(critical_clearing_time(rete, "B", [StabilityEvent(0, "trip_branch", element="L2")]))
```

Dati dinamici dei generatori: `h_s`, `d_pu`, `xd1_percent` (X'd), e per il
modello `dyn_model: "one_axis"` anche `xd_percent`, `xq_percent`, `td01_s`;
regolatore di tensione `avr_ka`, `avr_ta_s`, `efd_min_pu`, `efd_max_pu`;
regolatore di velocità `gov_droop_pu`, `gov_tg_s`, `gov_pmax_pu`. Eventi nella
sezione `stability_events`: `t_s`, `kind` (`fault`, `clear_fault`,
`trip_branch`, `trip_gen`, `load`), `bus`, `element`, `r_ohm`, `x_ohm`,
`scale`. Modelli, validazione e limiti:
[`../analisi/10_stabilita_transitoria.md`](../analisi/10_stabilita_transitoria.md).

### Armoniche

```bash
python -m iec60909.armoniche esempi/armoniche_cabina.json                  # tensioni, correnti, limiti EN 50160
python -m iec60909.armoniche rete.json --limiti ieee519 --pcc MT --ramo-pcc TR --il 30
python -m iec60909.armoniche rete.json --scansione BT --svg scansione.svg  # risonanze
```

Sezioni del file di rete: `harmonic_sources` (`id`, `bus`, `element` = carico,
motore o generatore statico da cui prendere la corrente fondamentale, oppure
`i1_a` e `angle_deg`; `spectrum` = `"6_impulsi"`, `"12_impulsi"` o
`{"5": [m %, φ °], …}`) e `harmonic_filters` (`id`, `bus`, `q_mvar`,
`tuned_order`, `quality`). Modelli, validazione e limiti:
[`../analisi/11_armoniche.md`](../analisi/11_armoniche.md).

### Avviamento dei motori

```bash
python -m iec60909.avviamento esempi/avviamento_motore.json --svg grafici   # dinamico
python -m iec60909.avviamento rete.json --statico                          # solo caduta di tensione
```

Sezione `motor_starts`: `id`, `motor` (id del motore), `method` (`dol`,
`star_delta`, `autotransformer`, `soft_starter`), `switch_speed`, `tap`, `u0`,
`ramp_s`, `current_limit`, `h_s` (inerzia di motore e carico), `a0`, `a1`, `a2`
(coppia resistente), `tlr_tr` (coppia di spunto di targa), circuito `rs`, `xs`,
`xm`, `rr`, `xr` (facoltativo), `t_max_s`, `v_min_motor_pu`, `v_min_bus_pu`,
`t_lr_max_s`. Modello, validazione e limiti:
[`../analisi/12_avviamento_motori.md`](../analisi/12_avviamento_motori.md).

### Affidabilità

```bash
python -m iec60909.affidabilita esempi/affidabilita_dorsale.json --dettagli --costo-kwh 10
python -m iec60909.affidabilita esempi/affidabilita_rbts_bus2.json --json
```

Sezioni `reliability_data` (`element`: id di ramo, nodo o sorgente, oppure
`@lines`, `@transformers`, `@transformers3w`, `@buses`, `@external_grids`,
`@generators`; `failure_rate` o `failure_rate_per_km`, `repair_time_h`,
`temporary_rate`) e `switches` (`id`, `branch`, `bus`, `kind`: `switch`,
`breaker`, `fuse`; `normally_open`, `switching_time_h`); nei `loads`
`customers` e `average_mw`. I `protective_devices` valgono come interruttori
o fusibili. Opzioni: `--primo-ordine` (senza sovrapposizioni),
`--senza-generatori`, `--manovra` (tempo di manovra dei dispositivi di
protezione), `--verifica-contro-alimentazione` con `--v-min` e
`--carico-max` (flusso di potenza sulle configurazioni di emergenza). Metodo, validazione e limiti:
[`../analisi/13_affidabilita.md`](../analisi/13_affidabilita.md).

### Dimensionamento dei cavi

```bash
python -m iec60909.cavi esempi/cavi_cabina.json
python -m iec60909.cavi rete.json --applica rete_dimensionata.json   # salva le sezioni scelte
```

Sezione `cable_sizing`: `id`, `line`, `ib_a` e `cos_phi` (default dal flusso di
potenza), `material` (`cu`, `al`), `insulation` (`pvc`, `xlpe`, `epr`),
`phases` (3 o 1), `method` (A1, A2, B1, B2, C, D1, D2, E, F, G), `loaded_conductors`,
`arrangement`, `ambient_c`, `soil_resistivity_km_w`, `grouping`, `circuits`,
`cores`, `k_extra`, `ampacity_a` (tabella propria), `sections`,
`max_parallel`, `device` o `in_a` con `i2_ratio`, `vdrop_max_percent`,
`upstream_drop_percent`, `x_ohm_per_km`, `pe_section_mm2`, `t_sc_s`,
`let_through_a2s`, `disconnection_time_s`. Portate e fattori dalla
IEC 60364-5-52 allegato B, con fonti e confidenza di ogni valore in
`strumenti/dati/iec60364_5_52.json`. Metodo, fonti, validazione e limiti:
[`../analisi/14_dimensionamento_cavi.md`](../analisi/14_dimensionamento_cavi.md).

### Portate dei cavi MT/AT (IEC 60287)

```bash
python -m iec60909.portate_mt rete.json
```

Sezione `cable_ratings`: `id`, `cable` (costruzione per strati: conduttore,
semiconduttori, isolante, schermo a fili, nastro o guaina, letto, guaina
esterna; per un tripolare `cores` = 3 con guaina sull'anima, riempitivi,
cordatura delle anime e armatura a fili `steel` o `stainless`) e `installation` (`kind` `buried`, `ducts` o `air`, `formation`
`trefoil` o `flat`, `transposed`, profondità, interasse, terreno, `bonding`,
tubi, coefficienti dell'aria, canaletta, altri cavi vicini). Nel
dimensionamento, `ratings` elenca le voci da usare come portate per sezione.
Metodo, validazione sui casi CIGRE TB 880 e limiti:
[`../analisi/15_portate_cavi_mt.md`](../analisi/15_portate_cavi_mt.md).

## Risultati per nodo (cortocircuito)

| Grandezza | Significato |
|---|---|
| `ikss3_ka`, `skss3_mva` | I"k e S"k per guasto trifase |
| `ikss2_ka` | I"k per guasto bifase isolato |
| `ikss1_ka` | I"k per guasto monofase a terra |
| `ikss2e_earth_ka` | I"kE2E, corrente verso terra nel guasto bifase a terra |
| `ikss2e_l2_ka`, `ikss2e_l3_ka` | correnti nelle fasi guaste del guasto bifase a terra |
| `kappa`, `ip3_ka`, `ip2_ka`, `ip1_ka` | fattore κ e correnti di picco (metodo B: 1,15·κ, senza 1,15 se tutti i rami hanno R/X < 0,3) |
| `ib_ka` | corrente di interruzione simmetrica Ib con i fattori μ e q (tmin da `--tmin`) |
| `idc_ka`, `ib_asym_ka` | componente continua all'istante tmin e corrente di interruzione asimmetrica |
| `ik_ka` | corrente permanente Ik (reti magliate: senza motori asincroni; un solo generatore: λ·IrG) |
| `ith_ka` | corrente termica equivalente per la durata Tk, I"k·√(m + n) (n < 1 solo per guasti alimentati da un solo generatore) |
| `z1_ohm`, `z2_ohm`, `z0_ohm` | impedenze di cortocircuito di sequenza nel nodo |

## Formato del file di rete (JSON)

Vedi `esempi/cabina_mt_bt.json`. Sezioni e campi:

- `name`, `f_hz` (50 o 60), `lv_tolerance_percent` (6 o 10: sceglie cmax/cmin in BT)
- `buses`: `id`, `un_kv`
- `external_grids`: `id`, `bus`, `skq_max_mva`, `rx_max`, `skq_min_mva`, `rx_min`,
  `x0x1` e `r0x0` (sequenza zero; se assenti la rete non dà corrente omopolare)
- `transformers`: `id`, `hv_bus`, `lv_bus`, `sr_mva`, `ur_hv_kv`, `ur_lv_kv`,
  `ukr_percent`, `urr_percent`, `vector_group` (es. `Dyn11`, `YNd5`, `YNyn0`, `Dzn0`, `ZNyn11`),
  `uk0_percent`, `ur0_percent` (default = valori diretti), `zn_hv_ohm`, `zn_lv_ohm`
  (impedenza di neutro, numero o `[R, X]`), `parallel`
- `transformers3w` (tre avvolgimenti): `id`, `hv_bus`, `mv_bus`, `lv_bus`,
  `ur_hv_kv`, `ur_mv_kv`, `ur_lv_kv`, potenze di coppia `sr_hv_mv_mva`,
  `sr_hv_lv_mva`, `sr_mv_lv_mva`, tensioni di cortocircuito di coppia
  `ukr_hv_mv_percent`, `ukr_hv_lv_percent`, `ukr_mv_lv_percent` e
  `urr_..._percent` (riferite alla potenza della coppia), facoltativi
  `uk0_..._percent`/`ur0_..._percent`, `vector_group` (es. `YNynd5`),
  `zn_hv_ohm`, `zn_mv_ohm`, `zn_lv_ohm`; per gli avvolgimenti a zig-zag con
  neutro `z0_zigzag_hv_ohm`/`_mv_`/`_lv_` (`[R, X]` omopolare propria in Ω).
  Esempio: `esempi/stazione_tre_avvolgimenti.json`
- `lines`: `id`, `from_bus`, `to_bus`, `length_km`, `r1_ohm_per_km`,
  `x1_ohm_per_km`, `r0_ohm_per_km`, `x0_ohm_per_km`, `end_temperature_c`
  (temperatura a fine guasto per il caso minimo), `parallel`
- `generators` (anche motori sincroni): `id`, `bus`, `sr_mva`, `ur_kv`,
  `xd2_percent`, `cos_phi`, `rg_ohm` (se assente: R_Gf = 0,05/0,07/0,15 · X"d),
  `x2_percent` (sequenza inversa, default X"d), `x0_percent` e `zn_ohm`
  (centro stella a terra; senza `x0_percent` il neutro è isolato); per Ik con
  un solo generatore: `xd_sat_percent` e `ufmax_ratio` (1,3 o 1,6) oppure
  `lambda_max` e `lambda_min` letti dalle curve della norma; per un gruppo di
  generazione: `unit_transformer` (id del trasformatore elevatore, lato BT sul
  nodo del generatore), `oltc` (variatore sotto carico, default vero),
  `pg_percent`, `pt_percent`; i trasformatori ausiliari sono trasformatori
  normali con il lato AT sul nodo del generatore: i nodi a valle sono
  riconosciuti come interni al gruppo
- `earthing_transformers` (messa a terra, es. zig-zag): `id`, `bus`, `z0_ohm`
  (`[R, X]` omopolare per fase), `zn_ohm`
- `static_generators`: `id`, `bus`, `kind` (`PF` convertitore pieno con
  `ikss_ka`, corrente iniziale massima riferita alla tensione del nodo; `WD`
  eolico a doppia alimentazione con `kappa_wd`, `i_wd_max_ka`, `rx`, `ur_kv`),
  `count`
- `motors`: `id`, `bus`, `pr_mw`, `ur_kv`, `efficiency`, `cos_phi`, `ilr_ir`,
  `pole_pairs` (obbligatorio per motori MT), `rx` (facoltativo), `count`,
  `x2_percent` e `rx2` (sequenza inversa da dati di targa, default Z2 = Z1)

Campi usati solo dal flusso di potenza (tutti facoltativi, esempio in
`esempi/rete_flusso_potenza.json`):

- `external_grids`: `vm_pu` (default 1), `va_degree` (default 0),
  `slack_weight` (peso nel saldo distribuito, default 1)
- `transformers`: `tap_pos`, `tap_step_percent`, `tap_side` (`hv`/`lv`),
  `i0_percent`, `pfe_kw` (il cortocircuito usa sempre il rapporto nominale);
  variatore sotto carico: `tap_min`, `tap_max`, `control_bus` (nodo regolato),
  `control_vm_pu` (tensione di riferimento, default 1), `control_band_pu`
  (semiampiezza della banda, default 0,75 passi). Lo sfasamento (k·30°, tensione
  BT in ritardo) è ricavato dal numero orario di `vector_group`
- `transformers3w`: `tap_pos`, `tap_step_percent`, `tap_side` (`hv`/`mv`/`lv`),
  `i0_percent` (riferita alla potenza dell'avvolgimento AT), `pfe_kw`;
  sfasamenti di MT e BT dai numeri orari di `vector_group` (es. `YNyn0d5`)
- `lines`: `c_nf_per_km` (capacità di esercizio), `max_i_ka` (per il carico %)
- `generators`: `p_mw`, `vm_pu` (nodo PV; `null` per un nodo PQ con
  `q_mvar`), `q_min_mvar`, `q_max_mvar`, `regulated_bus` (nodo di cui il
  generatore regola la tensione a `vm_pu`, regolazione remota), `slack_weight`
  (peso nel saldo distribuito, default 0)
- `motors`: `loading` (frazione della potenza nominale, default 1)
- `static_generators`: `p_mw`, `q_mvar`
- `loads`: `id`, `bus`, `p_mw`, `q_mvar`, `count`, quote ZIP in %
  `const_z_p_percent`, `const_i_p_percent`, `const_z_q_percent`,
  `const_i_q_percent` (impedenza e corrente costante; il resto a potenza
  costante, default 0); per l'affidabilità `customers`
  (default 1) e `average_mw` (default p_mw·count)
- `shunts`: `id`, `bus`, `q_mvar` (assorbita a tensione nominale: > 0
  reattore, < 0 condensatori), `p_mw`

Opzioni di `run_load_flow` (e della riga di comando): `enforce_q_lims`
(`--qlim`), `phase_shift=True` (`--angoli-relativi` per angoli relativi senza
sfasamenti), `distributed_slack=False` (`--saldo-distribuito`),
`tap_control=True` (`--prese-fisse` per non regolare le prese).

Sezione dell'arc flash (esempio in `esempi/arc_flash_cabina.json`):

- `arc_flash`: `id`, `bus`, `configuration` (`VCB`, `VCBB`, `HCB`, `VOA`,
  `HOA`), `equipment_class` (valori tipici delle tabelle 8 e 10: `quadro_bt`,
  `ccm_bt`, `pannello_bt`, `cassetta_di_derivazione`, `quadro_mt_5kv`,
  `quadro_mt_15kv`, …, anche `_poco_profondo`), `gap_mm`, `distance_mm`,
  `height_mm`, `width_mm`, `depth_mm` (sostituiscono i valori tipici),
  `protection`: `time_ms` fisso oppure relè IEC 60255-151 con `curve` (`SI`,
  `VI`, `EI`, `LTI`), `pickup_ka`, `tms`, `inst_pickup_ka`, `inst_time_ms`,
  `breaker_time_ms`, `current_ratio` (corrente vista dal relè / corrente
  d'arco), `max_time_ms` (default 2000), oppure `device` (id di un
  dispositivo di `protective_devices`: relè, interruttore o fusibile);
  `ibf_ka` (corrente franca imposta), `motor_decay_ms` (contributo dei motori
  esaurito dopo quel tempo: secondo intervallo con la I"k della rete senza
  motori) oppure `steps` (`[{"ibf_ka", "duration_ms", "current_ratio"}, …]`,
  l'ultimo dura fino all'eliminazione)
- punti in corrente continua: `system: "dc"`, `bus` facoltativo, `vdc_v`,
  `ibf_ka` oppure `r_system_ohm`, `dc_method` (`doan`, default, oppure
  `stokes`, che richiede `gap_mm`), `distance_mm` (o `equipment_class`),
  `dc_enclosure_factor` (default 3 in cella, 1 con `configuration` `VOA` o
  `HOA`), `protection` come sopra (un dispositivo vede tutta la corrente
  d'arco)

Sezione del coordinamento (esempio in `esempi/coordinamento_cabina.json`):

- `protective_devices`: `id`, `branch` (linea, trasformatore, `<id>:hv|mv|lv`
  o trasformatore di messa a terra), `bus` (estremo di installazione), `kind`
  (`relay`, `breaker`, `fuse`), `protects` (`branch` o `bus`), `cti_s`;
  relè: `curve` (`IEC_SI`, `IEC_VI`, `IEC_EI`, `IEC_LTI`, `IEEE_MI`,
  `IEEE_VI`, `IEEE_EI`), `pickup_a`, `tms`, `stages`
  (`[{"pickup_a", "time_s"}]`), `breaker_time_s`; interruttore BT: `in_a`,
  `ir`, `tr_s`, `isd`, `tsd_s`, `i2t_sd`, `ii`, `ti_s`; fusibile: `points`
  (`[[I_A, t_s], …]`). Campi comuni:
  - `measure`: `phase` (default) o `residual` (3·I0, protezione di terra);
  - `directional`, `characteristic_angle_deg` (default 45°);
  - bande di tolleranza: `current_tolerance_percent`,
    `time_tolerance_percent`, `time_tolerance_s`;
  - `selectivity_limits`: `{"<id a valle>": Is_kA}`, limite di selettività
    energetica dalle tabelle del costruttore

## Confronto con ETAP

Gli studi di cortocircuito IEC di ETAP sono database SQLite (`.SI2S`) che
contengono dati di rete e risultati. Il modulo `iec60909.etap` converte la rete
e confronta i risultati nodo per nodo:

```bash
python -m iec60909.etap "C:\ETAP Demo\Example-IEC\SC_909.SI2S"            # tabella di confronto
python -m iec60909.etap studio.SI2S --json rete.json                       # salva la rete convertita
```

Sullo studio di esempio `SC_909` di ETAP 2024 lo scarto massimo è 0,025 %
(dettagli in [`../analisi/04_confronto_etap_sc909.md`](../analisi/04_confronto_etap_sc909.md)).
I file di ETAP non vanno mai aggiunti al repository.

## Test

```bash
python -m pytest
```

- `tests/test_formule.py`: confronto con calcoli a mano svolti dalle formule
  della norma (tolleranza 1e-9).
- `tests/test_pandapower.py`: confronto con pandapower su una rete magliata
  110/20/0,4 kV con trasformatori in parallelo a rapporto fuori nominale,
  anello MT, generatore, motore MT e cabina BT, e su una stazione con
  trasformatore a tre avvolgimenti in cinque gruppi vettoriali (tolleranza 1e-6).
- `tests/test_loadflow.py`: flusso di potenza, soluzione in forma chiusa su due
  nodi e confronto con pandapower `runpp` (tolleranza 1e-6);
  `tests/test_loadflow_ieee14.py`: rete di prova IEEE a 14 nodi.
- `tests/test_arcflash.py`: arc flash, esempi svolti dell'allegato D della
  IEEE 1584-2018 e confronto con arcflash-calc su 864 casi;
  `tests/test_arcflash_estensioni.py`: Lee, corrente continua (calcoli a
  mano), scelta di Ibf, calcolo a più intervalli (confronto con
  arcflash-calc `multistep_E_and_AFB`), fusibili e avvisi sotto 240 V.
- `tests/test_portate_mt.py`: portate IEC 60287 sui casi della CIGRE TB 880.
- `tests/test_cavi.py`: dimensionamento dei cavi, calcoli a mano, tabelle IEC 60364-5-52,
  esempi pubblicati (motore 90 kW, lunghezze massime TN di AS/NZS 3000).
- `tests/test_affidabilita.py`: affidabilità, RBTS Bus 2 (indici pubblicati),
  calcoli a mano, secondo ordine contro Markov e Monte Carlo, verifica delle
  contro-alimentazioni con il flusso di potenza.
- `tests/test_avviamento.py`: avviamento dei motori, stima del circuito,
  caduta di tensione a mano, metodi di avviamento, integrazione indipendente.
- `tests/test_armoniche.py`: armoniche, calcoli a mano, risonanza, filtri,
  12 impulsi, armoniche omopolari, limiti, confronto con OpenDSS.
- `tests/test_stabilita.py`: stabilità transitoria, criterio delle aree
  uguali, integrazione indipendente con scipy, confronto con ANDES (Kundur).
- `tests/test_coordinamento.py`: coordinamento, curve dei dispositivi,
  correnti nei rami, verifiche di selettività, sensibilità e carico;
  `tests/test_coordinamento_estensioni.py`: correnti nei rami per i guasti
  dissimmetrici, con la somma nel nodo guasto confrontata con `calculate`
  (tolleranza 1e-9) e i gruppi vettoriali; protezioni di terra, relè
  direzionali, corrente di interruzione, bande di tolleranza, selettività
  energetica, convertitori pieni e guasti interni ai gruppi.

Dettagli delle formule, ipotesi e limiti: [`../analisi/01_iec60909_formule.md`](../analisi/01_iec60909_formule.md).
