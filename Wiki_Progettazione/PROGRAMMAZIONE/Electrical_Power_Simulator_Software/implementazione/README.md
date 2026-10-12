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
```

Da Python:

```python
from iec60909 import load_network, calculate

risultato = calculate(load_network("rete.json"), case="max", kappa_method="C", tk_s=1.0)
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
| `ib_ka` | corrente di interruzione simmetrica (Ib = I"k, cautelativa) |
| `ik_ka` | corrente permanente (solo reti senza generatori sincroni) |
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
- `lines`: `id`, `from_bus`, `to_bus`, `length_km`, `r1_ohm_per_km`,
  `x1_ohm_per_km`, `r0_ohm_per_km`, `x0_ohm_per_km`, `end_temperature_c`
  (temperatura a fine guasto per il caso minimo), `parallel`
- `generators`: `id`, `bus`, `sr_mva`, `ur_kv`, `xd2_percent`, `cos_phi`, `rg_ohm`
  (se assente: R_Gf = 0,05/0,07/0,15 · X"d)
- `motors`: `id`, `bus`, `pr_mw`, `ur_kv`, `efficiency`, `cos_phi`, `ilr_ir`,
  `pole_pairs` (obbligatorio per motori MT), `rx` (facoltativo), `count`

## Test

```bash
python -m pytest
```

- `tests/test_formule.py`: confronto con calcoli a mano svolti dalle formule
  della norma (tolleranza 1e-9).
- `tests/test_pandapower.py`: confronto con pandapower su una rete magliata
  110/20/0,4 kV con trasformatori in parallelo a rapporto fuori nominale,
  anello MT, generatore, motore MT e cabina BT (tolleranza 1e-6).

Dettagli delle formule, ipotesi e limiti: [`../analisi/01_iec60909_formule.md`](../analisi/01_iec60909_formule.md).
