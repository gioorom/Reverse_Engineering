# 01 — IEC 60909-0:2016: formule implementate

Il calcolo di cortocircuito è implementato dalle formule pubbliche della norma
IEC 60909-0:2016, senza decompilare software commerciale.

Codice: [`../implementazione/iec60909/`](../implementazione/iec60909/).

## Metodo

- **Generatore equivalente di tensione** c·Un/√3 nel punto di guasto. Tutte le
  altre sorgenti sono sostituite dalle loro impedenze interne; capacità delle
  linee, ammettenze di magnetizzazione e carichi non motori sono trascurati.
- **Metodo nodale**: per ciascuna sequenza (diretta, inversa, omopolare) si
  costruisce la matrice delle ammettenze nodali in per unità (base 100 MVA,
  tensione di base = Un del nodo). Dall'inversa si ottengono le impedenze di
  cortocircuito Z1, Z2, Z0 di ogni nodo.
- I trasformatori sono riferiti con il **rapporto nominale t_r**: un rapporto
  diverso da quello delle tensioni nominali di rete diventa un rapporto fuori
  nominale nel modello.
- Le parti di rete senza alcun collegamento verso terra (es. sequenza zero a
  valle di un avvolgimento a triangolo) hanno impedenza infinita: la corrente
  monofase vale 0.

## Fattore di tensione c (tabella 1)

| Un | cmax | cmin |
|---|---|---|
| 100 V – 1 kV, tolleranza +6 % | 1,05 | 0,95 |
| 100 V – 1 kV, tolleranza +10 % | 1,10 | 0,90 |
| > 1 kV | 1,10 | 1,00 |

## Impedenze degli elementi

| Elemento | Sequenza diretta/inversa | Sequenza zero |
|---|---|---|
| Rete esterna Q | Z_Q = c·Un²/S"kQ, X_Q = Z_Q/√(1+(R/X)²) | X0 = (X0/X1)·X_Q, R0 = (R0/X0)·X0 (se dati) |
| Trasformatore | Z_T = ukr·Ur²/Sr, R_T = uRr·Ur²/Sr, × K_T | Z0T (default = Z_T) × K_T + 3·Zn secondo il gruppo |
| Linea | (R'·k_θ + jX')·l | (R0'·k_θ + jX0')·l |
| Generatore | Z_GK = K_G·(R_Gf + jX"d) | aperta (neutro isolato) |
| Motore asincrono | Z_M = Ur²/(I_LR/I_r · Sr), Sr = Pr/(η·cosφ) | aperta |

- **Trasformatore a tre avvolgimenti**: impedenze di coppia Z_AB, Z_AC, Z_BC
  (riferite al lato AT, ciascuna con la potenza nominale della propria coppia),
  corrette con K_TAB, K_TAC, K_TBC = 0,95·cmax/(1 + 0,6·x_coppia) (solo
  correnti massime, cmax del nodo a tensione minore della coppia) e convertite
  nello schema a stella: Z_A = ½(Z_AB + Z_AC − Z_BC), Z_B = ½(Z_AB + Z_BC − Z_AC),
  Z_C = ½(Z_AC + Z_BC − Z_AB). Il centro stella è un nodo interno con tensione
  di base Ur_AT; ogni avvolgimento è un ramo con il proprio rapporto nominale.
  Sequenza zero: avvolgimento YN → ramo serie (+3·Zn); avvolgimento D →
  derivazione verso terra dal centro stella; Y senza neutro → aperto.
- **Gruppo di generazione** (generatore con trasformatore elevatore dedicato,
  `unit_transformer`): al posto di K_G e K_T un unico fattore per generatore
  e trasformatore, Z_S = K·(t_r²·Z_G + Z_THV):
  - con variatore sotto carico: K_S = (UnQ²/UrG²)·(UrTLV²/UrTHV²)·cmax /
    (1 + |x"d − x_T|·sinφrG);
  - senza variatore: K_SO = UnQ/(UrG·(1 + pG))·(UrTLV/UrTHV)·(1 − pT)·cmax /
    (1 + x"d·sinφrG), con pG campo di regolazione della tensione del
    generatore e pT presa fissa permanente del trasformatore;
  - guasto tra generatore e trasformatore (nodo del generatore):
    K_G,S = cmax/(1 + x"d·sinφrG) sul generatore e K_T,S = cmax/(1 − x_T·sinφrG)
    sul trasformatore (contributo della rete), entrambi divisi per (1 + pG)
    senza variatore. Il calcolo di questo nodo usa una matrice dedicata.
- **K_T** = 0,95·cmax/(1 + 0,6·x_T), con cmax del lato BT; applicato solo al
  calcolo delle correnti **massime** (sez. 6.3.3), anche alla sequenza zero.
- **K_G** = (Un/UrG)·cmax/(1 + x"d·sin φrG).
- **R_Gf** = 0,05·X"d (UrG > 1 kV, SrG ≥ 100 MVA), 0,07·X"d (UrG > 1 kV,
  SrG < 100 MVA), 0,15·X"d (UrG ≤ 1 kV).
- **Motori**: R/X = 0,10 (MT, Pr/p ≥ 1 MW), 0,15 (MT, Pr/p < 1 MW), 0,42 (BT).
  Esclusi dal calcolo delle correnti minime.
- **Linee, caso minimo**: R a fine guasto, k_θ = 1 + 0,004·(θe − 20 °C).
- **Gruppi vettoriali (sequenza zero)**: YNyn → ramo serie; YNd → derivazione
  lato AT; Dyn → derivazione lato BT; avvolgimento a zig-zag con neutro (ZN,
  es. Dzn, YNzn, ZNd, ZNyn) → derivazione verso terra sul suo lato con Z0 del
  trasformatore + 3·Zn, lati disaccoppiati (lo zig-zag compensa gli
  amperspire omopolari, quindi l'altro avvolgimento non riceve omopolare
  attraverso il trasformatore); in sequenza diretta e inversa lo zig-zag si
  comporta come una stella; altri gruppi (Yy, Yyn, Dd, Z senza neutro, …) →
  sequenza zero interrotta.
- **Trasformatori di messa a terra** (`earthing_transformers`, es. zig-zag su
  una rete a neutro isolato): solo in sequenza zero, derivazione Z0 + 3·Zn.
- **Convertitore pieno** (fotovoltaico, eolico full converter, accumuli;
  `kind = "PF"`): sorgente di corrente di sequenza diretta con I"k_PF
  massima data dal costruttore. Nel punto di guasto k la tensione
  equivalente diventa E = c·Un/√3 + Σ |Z(1)ik|·I"k_PF,i (somma in modulo,
  cautelativa) e tutte le correnti iniziali usano E al posto di c·Un/√3.
  - ip = √2·(κ·I"k,rete + I"k,PF): il convertitore non ha componente continua;
    anche i_DC riguarda la sola quota della rete;
  - Ib e Ik: la quota dei convertitori non decade;
  - correnti minime: contributo trascurato.
- **Eolico a doppia alimentazione** (`kind = "WD"`): impedenza
  Z_WD = √2·κ_WD·Ur/(√3·i_WDmax) con κ_WD, i_WDmax (valore istantaneo
  massimo) e R/X dati dal costruttore, in sequenza diretta e inversa; nessun
  contributo omopolare.
- I generatori eolici con generatore asincrono (WA) si rappresentano come
  motori asincroni (`motors`).

Verifica: il convertitore pieno coincide con pandapower (I"k e ip). Per WD
pandapower 3.5.6 dà un contributo circa 10 volte inferiore a quello della
formula (≈ c·i_WDmax/(√2·κ_WD)) e usa κ_WD come fattore di picco del nodo:
il modello è verificato con calcoli a mano.

### Impedenza di guasto Z_F

Guasto non franco (arco, resistenza di contatto o di terra): Z_F è in serie a
ciascuna fase guasta, quindi si somma alle impedenze di sequenza del punto di
guasto (Z1 + Z_F, Z2 + Z_F, Z0 + Z_F):

| Guasto | Formula |
|---|---|
| Trifase | I"k3 = c·Un / (√3·\|Z1 + Z_F\|) |
| Bifase isolato | I"k2 = c·Un / \|Z1 + Z2 + 2·Z_F\| |
| Monofase a terra | I"k1 = √3·c·Un / \|Z1 + Z2 + Z0 + 3·Z_F\| |
| Bifase a terra | formule del guasto franco con Z1 + Z_F, Z2 + Z_F, Z0 + Z_F |

Z_F entra anche in ip (R/X di Z1 + Z_F; nel metodo C anche X_F è riportata
alla frequenza equivalente), Ib, i_DC e Ik. È la stessa convenzione di
pandapower (identico su I"k e su ip con il metodo B; con il metodo C
pandapower non scala X_F, quindi coincide solo per Z_F resistiva). La norma
IEC 60909-0 tratta i guasti franchi: Z_F serve per valutazioni con arco o
resistenza di terra.

## Corrente di picco ip

ip = κ·√2·I"k, con κ = 1,02 + 0,98·e^(−3R/X). Lo stesso κ del trifase è usato
per bifase e monofase.

- **Metodo B**: κ dal rapporto R/X di Z1 nel punto di guasto, moltiplicato per
  1,15 e limitato a 1,8 (BT) o 2,0 (MT/AT). Cautelativo: il fattore 1,15 è
  applicato sempre.
- **Metodo C** (predefinito): frequenza equivalente fc = 20 Hz (50 Hz) o
  24 Hz (60 Hz); R/X = (Rc/Xc)·(fc/f), dove Zc è calcolata con le reattanze
  scalate di fc/f.

## Ib, Ik, Ith

- **Ib** (corrente di interruzione simmetrica, guasto trifase), formula per reti
  magliate:
  Ib = I"k − Σ (ΔU"_i/(c·Un/√3))·(1 − μ_i·q_i)·I"k_i, con I"k_i corrente
  parziale della macchina i ai suoi morsetti e ΔU"_i = X"_i·I"k_i (X" con K_G
  per i generatori). Le reti esterne non decadono; per una sola macchina la
  formula si riduce a Ib = μ·q·I"k.
  - μ = 0,84 + 0,26·e^(−0,26·r) (tmin 0,02 s); 0,71 + 0,51·e^(−0,30·r)
    (0,05 s); 0,62 + 0,72·e^(−0,32·r) (0,10 s); 0,56 + 0,94·e^(−0,38·r)
    (≥ 0,25 s), r = I"k_i/Ir_i; interpolazione lineare per tmin intermedi.
  - q (motori asincroni) = 1,03 + 0,12·ln m; 0,79 + 0,12·ln m; 0,57 + 0,12·ln m;
    0,26 + 0,10·ln m, con m = PrM/p in MW per coppia polare (0,05 MW per i
    gruppi BT senza dati); q = 1 per le macchine sincrone.
  - Macchine con r ≤ 2 non decadono (μ = q = 1), come per il criterio di
    guasto lontano dai generatori; con questa regola Ib coincide con ETAP.
  - tmin < 0,02 s (fuori dalle tabelle della norma): Ib = I"k, scelta
    cautelativa.
  - Guasti dissimmetrici: Ib2 = I"k2, Ib2E = I"k2E, Ib1 = I"k1.
- **Ik** (corrente permanente, guasto trifase):
  - reti con rete esterna o più generatori (magliate): Ik = I"k calcolata
    senza i motori asincroni;
  - guasto alimentato da un solo generatore: Ik = λ·IrG, λmax nel caso
    massimo e λmin nel caso minimo. λ può essere imposto (`lambda_max`,
    `lambda_min`, letti dalle curve della norma) oppure calcolato con il modello
    analitico da cui derivano le curve: corrente permanente E/(xd_sat + x_e),
    con x_e = c/r − x"d reattanza esterna, E = Ufmax/Ufr·|1 + j·xd_sat·(cosφ −
    j·sinφ)| per λmax (Ufmax/Ufr = 1,3 serie 1, 1,6 serie 2) ed E = 1 per λmin.
    Il modello approssima le curve grafiche della norma: per verifiche
    formali usare i valori letti dalle curve.
- **i_DC** (componente continua all'istante t = tmin):
  i_DC = √2·I"k·e^(−2π·f·t·R/X), con R/X calcolato con la frequenza
  equivalente fc = f·(fc/f) scelta in base a f·t: 0,27 (f·t < 1), 0,15 (< 2,5),
  0,092 (< 5), 0,055 (altrimenti); R/X = (Rc/Xc)·(fc/f). In una rete solo
  radiale coincide con l'R/X di Z1. Corrente di interruzione asimmetrica:
  Ib,asym = √(Ib² + i_DC²).
- **Ith** = I"k·√(m + n), con n = 1 e
  m = [e^(4·f·Tk·ln(κ−1)) − 1] / [2·f·Tk·ln(κ−1)]; per κ → 2 il limite è m = 2.

## Validazione

- Calcoli a mano: cabina 20/0,4 kV (trifase, bifase, monofase, bifase a terra,
  ip), impedenza di neutro, YNyn, caso minimo con temperatura della linea,
  rapporto fuori nominale. Scarto < 1e-9.
- pandapower 3.5.6 su rete magliata 110/20/0,4 kV: I"k trifase, bifase e
  monofase, ip (B e C) e Ith, casi massimo e minimo. Scarto < 1e-6, con due
  differenze motivate:
  1. con un generatore nella rete, pandapower lascia nella sequenza zero
     un'impedenza molto grande (~1 MΩ): scarto di 3 ppm sulla monofase;
  2. con κ = 2 (metodo B al limite) pandapower restituisce Ith = I"k (m = 0)
     invece del limite corretto m = 2.

## Limiti (non ancora implementati)

- Avvolgimenti a zig-zag nei trasformatori a tre avvolgimenti (rifiutati con
  un errore esplicito).
- Gruppi di generazione: trasformatori ausiliari e guasti sul lato dei
  servizi ausiliari.
- Fattore n della corrente termica per guasti vicini ai generatori (n = 1).
- Metodo B senza la deroga per R/X < 0,3 in tutti i rami.
