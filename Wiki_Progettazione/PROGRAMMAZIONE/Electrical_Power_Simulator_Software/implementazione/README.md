# iec60909 — calcolo delle correnti di cortocircuito

Reimplementazione del calcolo di cortocircuito della **IEC 60909-0:2016**
per Electrical Power Simulator Software, scritta dalle formule
della norma e verificata contro [pandapower](https://www.pandapower.org/),
un'implementazione open source indipendente della stessa norma.

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
```

Da Python:

```python
from iec60909 import load_network, calculate

risultato = calculate(load_network("rete.json"), case="max", kappa_method="C", tk_s=1.0, tmin_s=0.1)
print(risultato.bus("QGBT").ikss3_ka)
```

## Risultati per nodo

| Grandezza | Significato |
|---|---|
| `ikss3_ka`, `skss3_mva` | I"k e S"k per guasto trifase |
| `ikss2_ka` | I"k per guasto bifase isolato |
| `ikss1_ka` | I"k per guasto monofase a terra |
| `ikss2e_earth_ka` | I"kE2E, corrente verso terra nel guasto bifase a terra |
| `ikss2e_l2_ka`, `ikss2e_l3_ka` | correnti nelle fasi guaste del guasto bifase a terra |
| `kappa`, `ip3_ka`, `ip2_ka`, `ip1_ka` | fattore κ e correnti di picco |
| `ib_ka` | corrente di interruzione simmetrica Ib con i fattori μ e q (tmin da `--tmin`) |
| `idc_ka`, `ib_asym_ka` | componente continua all'istante tmin e corrente di interruzione asimmetrica |
| `ik_ka` | corrente permanente Ik (reti magliate: senza motori asincroni; un solo generatore: λ·IrG) |
| `ith_ka` | corrente termica equivalente per la durata Tk |
| `z1_ohm`, `z2_ohm`, `z0_ohm` | impedenze di cortocircuito di sequenza nel nodo |

## Formato del file di rete (JSON)

Vedi `esempi/cabina_mt_bt.json`. Sezioni e campi:

- `name`, `f_hz` (50 o 60), `lv_tolerance_percent` (6 o 10: sceglie cmax/cmin in BT)
- `buses`: `id`, `un_kv`
- `external_grids`: `id`, `bus`, `skq_max_mva`, `rx_max`, `skq_min_mva`, `rx_min`,
  `x0x1` e `r0x0` (sequenza zero; se assenti la rete non dà corrente omopolare)
- `transformers`: `id`, `hv_bus`, `lv_bus`, `sr_mva`, `ur_hv_kv`, `ur_lv_kv`,
  `ukr_percent`, `urr_percent`, `vector_group` (es. `Dyn11`, `YNd5`, `YNyn0`),
  `uk0_percent`, `ur0_percent` (default = valori diretti), `zn_hv_ohm`, `zn_lv_ohm`
  (impedenza di neutro, numero o `[R, X]`), `parallel`
- `transformers3w` (tre avvolgimenti): `id`, `hv_bus`, `mv_bus`, `lv_bus`,
  `ur_hv_kv`, `ur_mv_kv`, `ur_lv_kv`, potenze di coppia `sr_hv_mv_mva`,
  `sr_hv_lv_mva`, `sr_mv_lv_mva`, tensioni di cortocircuito di coppia
  `ukr_hv_mv_percent`, `ukr_hv_lv_percent`, `ukr_mv_lv_percent` e
  `urr_..._percent` (riferite alla potenza della coppia), facoltativi
  `uk0_..._percent`/`ur0_..._percent`, `vector_group` (es. `YNynd5`),
  `zn_hv_ohm`, `zn_mv_ohm`, `zn_lv_ohm`. Esempio: `esempi/stazione_tre_avvolgimenti.json`
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
  `pg_percent`, `pt_percent`
- `motors`: `id`, `bus`, `pr_mw`, `ur_kv`, `efficiency`, `cos_phi`, `ilr_ir`,
  `pole_pairs` (obbligatorio per motori MT), `rx` (facoltativo), `count`,
  `x2_percent` e `rx2` (sequenza inversa da dati di targa, default Z2 = Z1)

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

Dettagli delle formule, ipotesi e limiti: [`../analisi/01_iec60909_formule.md`](../analisi/01_iec60909_formule.md).
