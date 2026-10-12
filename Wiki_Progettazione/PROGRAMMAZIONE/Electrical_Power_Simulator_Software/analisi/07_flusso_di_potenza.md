# 07 — Flusso di potenza (load flow)

Secondo modulo del simulatore: calcolo delle tensioni e dei flussi di potenza
in regime permanente sinusoidale con il metodo di **Newton-Raphson**.
Implementazione: [`iec60909/loadflow.py`](../implementazione/iec60909/loadflow.py),
riga di comando `python -m iec60909.flusso rete.json`.

Usa lo stesso file di rete del cortocircuito, con alcuni campi di esercizio
facoltativi. Una sola descrizione della rete basta per entrambi i calcoli: i
campi del flusso di potenza (prese, regolazioni, pesi, quote ZIP) non
cambiano il calcolo IEC 60909 (verificato in `test_cortocircuito_invariato`).

## Grandezze e basi

- Per unità con potenza di base 100 MVA e tensione di base uguale alla
  tensione nominale di ogni nodo; il centro stella dei trasformatori a tre
  avvolgimenti ha base pari alla tensione nominale dell'avvolgimento AT.
- Nessun fattore di correzione della IEC 60909: impedenze di targa.
- Angoli assoluti con gli sfasamenti dei gruppi vettoriali (opzione
  `phase_shift=True`, default): la tensione di un avvolgimento con numero
  orario k è in ritardo di k·30° su quella dell'avvolgimento AT (IEC 60076-1:
  Dyn5 → −150°, Dyn11 → −330° ≡ +30°, YNyn0d5 → MT 0°, BT −150°). Con
  `phase_shift=False` (`--angoli-relativi`) gli angoli sono relativi al nodo di
  saldo come se tutti i trasformatori fossero a sfasamento nullo (convenzione
  di `calculate_voltage_angles=False` di pandapower). Moduli e flussi non
  cambiano, salvo maglie chiuse tra trasformatori di sfasamento diverso.

## Modelli

| Elemento | Modello |
|---|---|
| Rete esterna | nodo di saldo, tensione `vm_pu` e angolo `va_degree` imposti; con il saldo distribuito eroga la quota `slack_weight` dello sbilancio |
| Generatore sincrono | nodo PV (`p_mw`, `vm_pu`), oppure PQ con `vm_pu = null` e `q_mvar`; limiti `q_min_mvar`, `q_max_mvar` facoltativi; regolazione remota con `regulated_bus` |
| Carico (`loads`) | ZIP: quote a impedenza, corrente e potenza costante, separate per P e Q (`count` carichi uguali) |
| Motore asincrono | potenza costante P = `loading`·Pr/η, Q = P·tan φ |
| Generatore statico | potenza costante immessa `p_mw` + j`q_mvar` |
| Derivazione (`shunts`) | ammettanza costante: P e Q assorbite alla tensione nominale (Q > 0 reattore, Q < 0 condensatori) |
| Linea | circuito a π: Z = (R + jX)·l/n, metà della capacità di esercizio C·l·n a ogni estremo |
| Trasformatore a due avvolgimenti | circuito a π con trasformatore ideale a rapporto complesso sul lato AT (vedi sotto), variatore sotto carico facoltativo |
| Trasformatore a tre avvolgimenti | stella equivalente: tre trasformatori a due avvolgimenti verso il centro stella, con presa, sfasamenti e magnetizzazione (vedi sotto) |

### Trasformatore a due avvolgimenti

- Presa: U_r,eff = U_r·(1 + `tap_pos`·`tap_step_percent`/100) sul lato
  `tap_side` (AT o BT).
- Impedenza di cortocircuito riferita alla tensione nominale efficace del lato
  BT: Z = (u_k/100)·U_rBT,eff²/S_r, R = (u_R/100)·U_rBT,eff²/S_r.
- Rapporto fuori nominale N = (U_rAT,eff/U_rBT,eff)/(U_nAT/U_nBT) e rapporto
  complesso a = N·e^(jψ), ψ = k·30° (numero orario del gruppo vettoriale, es.
  `Dyn11` → k = 11). Trasformatore ideale sul lato AT (V_AT = a·V_int,
  I_AT = I_int/a*): Y_AA = (Y_s + Y_m/2)/|a|², Y_BB = Y_s + Y_m/2,
  Y_AB = −Y_s/a*, Y_BA = −Y_s/a (matrice non simmetrica se ψ ≠ 0). A vuoto
  V_BT = V_AT·e^(−jψ)/N: la tensione BT è in ritardo di ψ.
- Magnetizzazione: |y_m| = i0/100, g_m = P_Fe/S_r (per unità del
  trasformatore), b_m = −√(|y_m|² − g_m²), divisa a metà tra i due lati.
- `parallel` trasformatori uguali: ammettanze moltiplicate.

### Trasformatore a tre avvolgimenti

Stesso modello di pandapower (`_trafo_df_from_trafo3w`): tre trasformatori a
due avvolgimenti tra i morsetti e il centro stella (base U_rAT), con le
impedenze di stella ricavate dalle impedenze di coppia (riferite alla potenza
della coppia).

- Ramo AT: trasformatore ideale ai morsetti AT con rapporto
  U_rAT,eff/U_nAT (presa sul lato `hv`), impedenza di stella riferita al
  centro stella (U_rAT nominale), nessuno sfasamento.
- Rami MT e BT: trasformatore ideale dal lato del centro stella con rapporto
  complesso (U_nW/U_rW,eff)·e^(jψ_W), impedenza di stella riferita alla
  tensione efficace dell'avvolgimento (presa sul lato `mv` o `lv`, come per il
  lato BT di un due avvolgimenti); ψ_MT e ψ_BT dai numeri orari del gruppo
  (`YNyn0d5` → 0° e 150°).
- Presa ai morsetti dell'avvolgimento `tap_side` (pandapower
  `tap_at_star_point=False`, il caso usuale).
- Magnetizzazione (`i0_percent`, `pfe_kw`) sul ramo AT, metà ai morsetti AT
  (attraverso il rapporto) e metà al centro stella: è il modello a π di
  pandapower con `trafo3w_losses="hv"` (default). La corrente a vuoto è
  riferita alla potenza dell'avvolgimento AT, cioè la maggiore delle potenze di
  coppia che lo comprendono (`sn_hv_mva` di pandapower). La scelta segue il
  riferimento di confronto: le alternative (perdite al centro stella o su
  altro lato) differiscono solo per la caduta della corrente magnetizzante
  nelle impedenze di dispersione, trascurabile rispetto alla precisione dei
  dati di targa (i0 ≈ 0,1–1 %).

## Metodo di Newton-Raphson

Incognite: angoli di tutti i nodi diversi dal nodo di saldo, moduli dei nodi
senza tensione imposta e, con il saldo distribuito, lo sbilancio Δ. Equazioni:
potenza attiva in tutti i nodi diversi dal saldo (con il saldo distribuito
anche nel nodo di saldo), potenza reattiva nei nodi senza generatori che
regolano la tensione. Scarti
ΔS = V·(Y·V)* − S_spec(|V|) − w·Δ; jacobiano dalle derivate complesse
∂S/∂|V| = diag(V)·(Y·diag(V/|V|))* + diag(I)*·diag(V/|V|) − diag(∂S_spec/∂|V|) e
∂S/∂θ = j·diag(V)·(diag(I) − Y·diag(V))*, colonna −w per Δ. Partenza piatta
sui moduli (|V| = 1 o tensione imposta) e angoli iniziali pari all'angolo del
nodo di saldo meno gli sfasamenti dei trasformatori incontrati (visita della
rete); convergenza quando tutti gli scarti sono sotto `tol_mva`
(default 1e-8 MVA).

### Carichi ZIP

P(V) = P·(z_P·V² + i_P·V + (1 − z_P − i_P)), Q(V) = Q·(z_Q·V² + i_Q·V +
(1 − z_Q − i_Q)) con z = `const_z_*_percent`/100, i = `const_i_*_percent`/100
e V in p.u. della tensione nominale del nodo (come pandapower 3). La derivata
2·z·V + i entra nella diagonale di ∂S/∂|V|: la convergenza resta quadratica.
pandapower media le quote dei carichi dello stesso nodo senza pesarle con la
potenza; qui ogni carico conserva le proprie (identico con un carico ZIP per
nodo).

### Regolazione remota della tensione

Un generatore con `regulated_bus` regola a `vm_pu` il modulo della tensione di
quel nodo: il nodo regolato ha il modulo imposto ma l'equazione della potenza
reattiva (resta PQ), il nodo del generatore ha la potenza reattiva libera ma
il modulo incognito. Il sistema resta quadrato (una equazione Q in meno, una
incognita |V| in meno). Vincoli: un nodo regolato da un solo nodo di
generazione, generatori dello stesso nodo con lo stesso nodo regolato e la
stessa tensione, nodo regolato diverso dal nodo di saldo. Con i limiti di
potenza reattiva il generatore al limite diventa PQ e il nodo regolato torna
libero.

### Limiti di potenza reattiva

`enforce_q_lims` (opzione `--qlim`): dopo la convergenza i generatori che
regolano una tensione (locale o remota) oltre i limiti diventano PQ con la
potenza reattiva al limite e il calcolo si ripete fino a nessuna violazione.

### Saldo distribuito

`distributed_slack=True` (`--saldo-distribuito`): come pandapower
`runpp(distributed_slack=True)`. Pesi `slack_weight` di reti esterne (default
1) e generatori (default 0), normalizzati a somma unitaria; il nodo di saldo
resta riferimento di tensione e angolo ma la sua potenza attiva è
un'equazione. L'incognita Δ (sbilancio: carichi + perdite − potenze impresse)
è ripartita: generatore P = `p_mw` + w·Δ, rete esterna P = w·Δ (parte da
potenza nulla). Ammesso un solo nodo di saldo; somma dei pesi positiva.
Risultato in `slack_mw`.

### Regolazione automatica delle prese

Variatore sotto carico dei trasformatori a due avvolgimenti con `control_bus`:
iterazione esterna come `pandapower.control.DiscreteTapControl`. Dopo ogni
flusso di potenza, se |V| del nodo regolato è sotto
`control_vm_pu − control_band_pu` o sopra `control_vm_pu + control_band_pu`
la presa si sposta di un passo nel verso che corregge la tensione (presa AT e
nodo regolato lato BT: presa più bassa per alzare la tensione; verso
invertito per presa BT, nodo regolato AT o passo negativo), entro
`tap_min`…`tap_max`. Tutti i trasformatori regolati si muovono insieme, un
passo per iterazione; ci si ferma quando nessuna presa si muove. Banda di
default ±0,75 passi (banda complessiva 1,5 passi, nessun pendolamento); se la
banda è più stretta di mezzo passo e lo stato delle prese si ripete il calcolo
si ferma con un avviso di pendolamento. Tensione fuori banda con la presa al
limite: avviso. Prese finali in `taps`; `tap_control=False` (`--prese-fisse`)
usa le prese di `tap_pos`.

Senza reti esterne il primo generatore PV a regolazione locale fa da nodo di
saldo (con avviso). Più generatori PV sullo stesso nodo si ripartiscono la
potenza reattiva in parti uguali; i generatori sul nodo di una rete esterna
erogano solo la potenza attiva impressa (la reattiva va alla rete).

## Risultati

- Nodi: tensione (p.u. e kV), angolo, potenze nette immesse.
- Rami: potenze ai due estremi, correnti, perdite, carico in % (linee:
  corrente rispetto a `max_i_ka`·n; trasformatori: potenza apparente
  rispetto a S_r·n; tre avvolgimenti: potenza dell'avvolgimento rispetto alla
  maggiore delle potenze di coppia che lo comprendono).
- Sorgenti: potenze della rete esterna e dei generatori.
- Prese finali dei trasformatori regolati (`taps`), sbilancio ripartito dal
  saldo distribuito (`slack_mw`).

## Validazione

- Soluzione in forma chiusa su due nodi (rete esterna, linea, carico):
  |V2|⁴ + (2(RP + XQ) − V1²)|V2|² + (R² + X²)(P² + Q²) = 0, tensione, perdite e
  potenze coincidono entro 1e-9. Con carico a impedenza costante (ZIP 100 % Z)
  la rete è lineare: V2 = V1·Zc/(Zl + Zc) entro 1e-10.
- pandapower 3.5.6 (`runpp`, modello a π dei trasformatori,
  `calculate_voltage_angles=True` con `shift_degree` = k·30° e
  `shift_mv_degree`/`shift_lv_degree` per i tre avvolgimenti) sulla rete
  [`esempi/rete_flusso_potenza.json`](../implementazione/esempi/rete_flusso_potenza.json):
  110/20/10/0,4 kV con due trasformatori in parallelo con presa, trasformatore
  BT con presa sul lato BT e magnetizzazione, trasformatore a tre avvolgimenti,
  anello MT con capacità di esercizio e linee in parallelo, generatore PV,
  motore, generatore statico, carichi e condensatori. Tensioni, angoli
  (assoluti e relativi), flussi, correnti, carichi e perdite coincidono entro
  1e-6 (di fatto all'arrotondamento), anche con i limiti di potenza reattiva e
  con il generatore PQ. Convenzione di segno di pandapower verificata:
  `shift_degree` positivo = tensione BT in ritardo, come la IEC.
- Estensioni (`tests/test_loadflow_estensioni.py`), confronto con pandapower
  (scarti massimi su |V| e angolo):
  - sfasamenti: maglia a 20 kV chiusa tra un Dyn5 e un YNd5 con a valle un
    Dyn11 (4e-16 p.u., 3e-14°); a vuoto l'angolo BT è −k·30° per k = 0…11
    (soluzione esatta);
  - tre avvolgimenti con presa su AT, MT o BT, magnetizzazione e gruppi
    YNyn0d5 / YNd11d1: tensioni, potenze, correnti e perdite dei tre
    avvolgimenti (1e-15 p.u., 6e-14°); perdite a vuoto ≈ P_Fe e i0·S_r;
  - variatore sotto carico contro `DiscreteTapControl` con la stessa banda
    (presa BT e due trasformatori in parallelo con presa AT): stessa presa
    finale, tensioni a 7e-16 p.u.; verificato anche che una presa in meno
    lascia la tensione fuori banda (passo minimo necessario), il limite delle
    prese e il pendolamento;
  - saldo distribuito contro `runpp(distributed_slack=True)` con pesi
    diversi sulla rete di prova (7e-16 p.u., 6e-14°) e sulla IEEE 14 nodi con
    cinque sorgenti pesate (entro 1e-6 su tensioni, angoli e potenze attive);
  - carichi ZIP con quote diverse per P e Q (5e-13 p.u., 4e-11°: pandapower
    converge con tolleranza propria sugli ZIP);
  - regolazione remota (pandapower non la prevede): tensione del nodo
    regolato uguale al riferimento entro 1e-12; verifica indipendente
    risolvendo la stessa rete con il generatore a regolazione locale alla
    tensione del suo nodo trovata (iec60909 e pandapower): il nodo remoto
    torna a 1,0 p.u. entro 1e-9, stessa potenza reattiva; bilancio di potenza;
    passaggio a PQ al limite di Q con regolazione attraverso un trasformatore.
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

- Regolazione automatica delle prese solo per i trasformatori a due
  avvolgimenti (il tre avvolgimenti ha presa fissa `tap_pos`) e solo a passi
  discreti con banda (nessun regolatore continuo né compensazione della
  caduta di linea, LDC).
- Presa dei tre avvolgimenti solo ai morsetti (non al centro stella) e
  magnetizzazione solo sul ramo AT; nessun variatore sfasatore (tap_step_degree).
- Saldo distribuito con un solo nodo di saldo (come pandapower, che converte
  le altre reti esterne in nodi PV); i pesi valgono per reti esterne e
  generatori sincroni, non per generatori statici o carichi.
- Regolazione remota: ogni nodo regolato da generatori di un solo nodo (nessuna
  ripartizione della potenza reattiva tra più nodi di generazione).
- Modello ZIP solo per i carichi (`loads`); motori e generatori statici a
  potenza costante.
- Non ancora confrontato con ETAP: lo studio di load flow della demo
  (`Example-IEC\LF.LF1S`) non è tra i file disponibili.
