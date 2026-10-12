# 07 — Flusso di potenza (load flow)

Secondo modulo del simulatore: calcolo delle tensioni e dei flussi di potenza
in regime permanente sinusoidale con il metodo di **Newton-Raphson**.
Implementazione: [`iec60909/loadflow.py`](../implementazione/iec60909/loadflow.py),
riga di comando `python -m iec60909.flusso rete.json`.

Usa lo stesso file di rete del cortocircuito, con alcuni campi di esercizio
facoltativi. Una sola descrizione della rete basta per entrambi i calcoli.

## Grandezze e basi

- Per unità con potenza di base 100 MVA e tensione di base uguale alla
  tensione nominale di ogni nodo; il centro stella dei trasformatori a tre
  avvolgimenti ha base pari alla tensione nominale dell'avvolgimento AT.
- Nessun fattore di correzione della IEC 60909: impedenze di targa.
- Gli sfasamenti dei gruppi vettoriali non sono considerati: gli angoli sono
  relativi al nodo di saldo come se tutti i trasformatori fossero a sfasamento
  nullo (convenzione di `calculate_voltage_angles=False` di pandapower).

## Modelli

| Elemento | Modello |
|---|---|
| Rete esterna | nodo di saldo, tensione `vm_pu` e angolo `va_degree` imposti |
| Generatore sincrono | nodo PV (`p_mw`, `vm_pu`), oppure PQ con `vm_pu = null` e `q_mvar`; limiti `q_min_mvar`, `q_max_mvar` facoltativi |
| Carico (`loads`) | potenza costante P + jQ (`count` carichi uguali) |
| Motore asincrono | potenza costante P = `loading`·Pr/η, Q = P·tan φ |
| Generatore statico | potenza costante immessa `p_mw` + j`q_mvar` |
| Derivazione (`shunts`) | ammettanza costante: P e Q assorbite alla tensione nominale (Q > 0 reattore, Q < 0 condensatori) |
| Linea | circuito a π: Z = (R + jX)·l/n, metà della capacità di esercizio C·l·n a ogni estremo |
| Trasformatore a due avvolgimenti | circuito a π con trasformatore ideale sul lato AT (vedi sotto) |
| Trasformatore a tre avvolgimenti | stella equivalente delle impedenze di coppia (riferite alla potenza della coppia), rapporto nominale di ogni avvolgimento |

### Trasformatore a due avvolgimenti

- Presa: U_r,eff = U_r·(1 + `tap_pos`·`tap_step_percent`/100) sul lato
  `tap_side` (AT o BT).
- Impedenza di cortocircuito riferita alla tensione nominale efficace del lato
  BT: Z = (u_k/100)·U_rBT,eff²/S_r, R = (u_R/100)·U_rBT,eff²/S_r.
- Rapporto fuori nominale N = (U_rAT,eff/U_rBT,eff)/(U_nAT/U_nBT); il
  trasformatore ideale è sul lato AT: Y_AA = (Y_s + Y_m/2)/N²,
  Y_BB = Y_s + Y_m/2, Y_AB = Y_BA = −Y_s/N.
- Magnetizzazione: |y_m| = i0/100, g_m = P_Fe/S_r (per unità del
  trasformatore), b_m = −√(|y_m|² − g_m²), divisa a metà tra i due lati.
- `parallel` trasformatori uguali: ammettanze moltiplicate.

## Metodo di Newton-Raphson

Incognite: angoli dei nodi PV e PQ, moduli dei nodi PQ. Scarti di potenza
ΔS = V·(Y·V)* − S_spec; jacobiano dalle derivate complesse
∂S/∂|V| = diag(V)·(Y·diag(V/|V|))* + diag(I)*·diag(V/|V|) e
∂S/∂θ = j·diag(V)·(diag(I) − Y·diag(V))*. Partenza piatta (|V| = 1 o
tensione imposta, angoli nulli), convergenza quando tutti gli scarti sono
sotto `tol_mva` (default 1e-8 MVA).

Limiti di potenza reattiva (`enforce_q_lims`, opzione `--qlim`): dopo la
convergenza i generatori PV oltre i limiti diventano nodi PQ con la potenza
reattiva al limite e il calcolo si ripete fino a nessuna violazione.

Senza reti esterne il primo generatore PV fa da nodo di saldo (con avviso).
Più generatori PV sullo stesso nodo si ripartiscono la potenza reattiva in
parti uguali; i generatori sul nodo di una rete esterna erogano solo la
potenza attiva impressa (la reattiva va alla rete).

## Risultati

- Nodi: tensione (p.u. e kV), angolo, potenze nette immesse.
- Rami: potenze ai due estremi, correnti, perdite, carico in % (linee:
  corrente rispetto a `max_i_ka`·n; trasformatori: potenza apparente
  rispetto a S_r·n; tre avvolgimenti: potenza dell'avvolgimento rispetto alla
  maggiore delle potenze di coppia che lo comprendono).
- Sorgenti: potenze della rete esterna e dei generatori.

## Validazione

- Soluzione in forma chiusa su due nodi (rete esterna, linea, carico):
  |V2|⁴ + (2(RP + XQ) − V1²)|V2|² + (R² + X²)(P² + Q²) = 0, tensione, perdite e
  potenze coincidono entro 1e-9.
- pandapower 3.5.6 (`runpp`, modello a π dei trasformatori) sulla rete
  [`esempi/rete_flusso_potenza.json`](../implementazione/esempi/rete_flusso_potenza.json):
  110/20/10/0,4 kV con due trasformatori in parallelo con presa, trasformatore
  BT con presa sul lato BT e magnetizzazione, trasformatore a tre avvolgimenti,
  anello MT con capacità di esercizio e linee in parallelo, generatore PV,
  motore, generatore statico, carichi e condensatori. Tensioni, angoli,
  flussi, correnti, carichi e perdite coincidono entro 1e-6 (di fatto
  all'arrotondamento), anche con i limiti di potenza reattiva e con il
  generatore PQ.
- Rete di prova IEEE a 14 nodi (`tests/test_loadflow_ieee14.py`, dati da
  `pandapower.networks.case14()`, 60 Hz, trasformatori a rapporto fuori
  nominale): coincide con pandapower entro 1e-13 su moduli e angoli, anche con
  i limiti di potenza reattiva attivi, e con la soluzione pubblicata (MATPOWER:
  moduli a 3 decimali, angoli a 2 decimali, perdite 13,393 MW). La soluzione
  storica del file IEEE CDF differisce leggermente da quella esatta dei suoi
  dati (es. nodo 4: 1,019 contro 1,0177): si usano i valori di MATPOWER.

Durante il confronto è emerso che in pandapower 3.x il variatore va creato con
`tap_changer_type="Ratio"`: senza, le prese sono ignorate (scarto dell'1–3 %
sulle tensioni).

## Limiti

- Sfasamenti dei gruppi vettoriali non considerati (angoli relativi).
- Trasformatori a tre avvolgimenti senza prese e senza magnetizzazione.
- Nessuna regolazione automatica delle prese né regolazione remota della
  tensione; un solo nodo di saldo per ogni rete esterna (nessun saldo
  distribuito).
- Carichi solo a potenza costante (nessun modello ZIP o dipendente dalla
  tensione).
- Non ancora confrontato con ETAP: lo studio di load flow della demo
  (`Example-IEC\LF.LF1S`) non è tra i file disponibili.
