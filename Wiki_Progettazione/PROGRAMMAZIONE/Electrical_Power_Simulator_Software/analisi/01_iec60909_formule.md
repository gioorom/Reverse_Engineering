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
- **K_T** = 0,95·cmax/(1 + 0,6·x_T), con cmax del lato BT; applicato solo al
  calcolo delle correnti **massime** (sez. 6.3.3), anche alla sequenza zero.
- **K_G** = (Un/UrG)·cmax/(1 + x"d·sin φrG).
- **R_Gf** = 0,05·X"d (UrG > 1 kV, SrG ≥ 100 MVA), 0,07·X"d (UrG > 1 kV,
  SrG < 100 MVA), 0,15·X"d (UrG ≤ 1 kV).
- **Motori**: R/X = 0,10 (MT, Pr/p ≥ 1 MW), 0,15 (MT, Pr/p < 1 MW), 0,42 (BT).
  Esclusi dal calcolo delle correnti minime.
- **Linee, caso minimo**: R a fine guasto, k_θ = 1 + 0,004·(θe − 20 °C).
- **Gruppi vettoriali (sequenza zero)**: YNyn → ramo serie; YNd → derivazione
  lato AT; Dyn → derivazione lato BT; altri gruppi → sequenza zero interrotta.

## Correnti di guasto

| Guasto | Formula |
|---|---|
| Trifase | I"k3 = c·Un / (√3·\|Z1\|) |
| Bifase isolato | I"k2 = c·Un / \|Z1 + Z2\| |
| Monofase a terra | I"k1 = √3·c·Un / \|Z1 + Z2 + Z0\| |
| Bifase a terra (verso terra) | I"kE2E = √3·c·Un·\|Z2\| / \|Z1·Z2 + Z1·Z0 + Z2·Z0\| |

Le correnti nelle fasi guaste del bifase a terra sono calcolate con le
componenti simmetriche.

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

- **Ib** = I"k: stima cautelativa ammessa per le reti magliate (μ = q = 1).
- **Ik**: calcolata come I"k senza motori, solo se non ci sono generatori
  sincroni (reti lontane dai generatori).
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

- Avvolgimenti a zig-zag (rifiutati con un errore esplicito).
- Gruppi di generazione con trasformatore (power station unit, K_S/K_SO),
  generatori con neutro a terra.
- Ib con i fattori μ e q, Ik con il metodo λ per reti vicine ai generatori.
- Componente continua i_DC, impedenza di guasto, contributo di inverter/eolico.
- Metodo B senza la deroga per R/X < 0,3 in tutti i rami.
