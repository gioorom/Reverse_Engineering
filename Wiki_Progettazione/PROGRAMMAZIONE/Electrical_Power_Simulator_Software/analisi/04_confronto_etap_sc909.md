# 04 — Confronto con ETAP 2024: studio IEC 60909 `SC_909` (Example-IEC)

Confronto dei risultati di `iec60909` con lo studio di cortocircuito IEC 60909
`L-G909` del progetto di esempio `Example-IEC` della demo di ETAP 2024
(`SC_909.SI2S`). I file di ETAP non sono nel repository: sono stati letti in
sola lettura nella sessione di lavoro.

**Esito:** dopo aver allineato le convenzioni sui dati, `iec60909` riproduce
ETAP su tutti i 5 nodi guasti e per tutti i tipi di guasto con scarto massimo
**0,025 %** (corrente di picco a Bus B). Le correnti iniziali e le impedenze
coincidono entro 0,001 %.

Strumento usato: `python -m iec60909.etap SC_909.SI2S` (modulo
[`iec60909/etap.py`](../implementazione/iec60909/etap.py)).

## Il file di uscita di ETAP

Il file `.SI2S` è un database **SQLite** che contiene sia i dati di rete usati
dal calcolo (tabelle `I*`: `IBus`, `IUtility`, `IXFMR2`, `IXFMR3`, `Icable`,
`IConnect`, `ISynGen`, `ISynMotor`, `IIndMachine`, `ISCStudyCase`,
`IAdjustments`) sia i risultati (`SCIECLGSum1`: correnti; `SCIECLGSum2`:
impedenze di sequenza nel punto di guasto; `ClippingCurrent`: correnti
simmetriche, asimmetriche e 3I0). Il formato completo è descritto in
[`03_etap_formato_risultati.md`](03_etap_formato_risultati.md).

L'intestazione riporta "SAMPLE OUTPUT REPORT - DOES NOT REFLECT THE ACTUAL
RESULTS" (dicitura della versione demo). I valori sono comunque il risultato di
un calcolo vero: sono riprodotti esattamente dalle formule della norma.

## La rete

Rete 33/11/6,6/0,4 kV, 50 Hz, 10 nodi (5 guastati nello studio):

- rete esterna 33 kV, S"kQ = 500 MVA, X/R = 10, con dati di sequenza zero;
- trasformatore a tre avvolgimenti 33/11/11 kV YNynd (10/5/3 MVA);
- trasformatori a due avvolgimenti: 33/11 kV Dyn con presa −2,5 %, 11/0,4 kV
  Dyn, 11/0,4 kV YNyn con tolleranza 7,5 %, 6,6/11 kV Dy (gruppo generatore);
- cavo 33 kV 500 m;
- generatore sincrono 6,6 kV 4,06 MVA (neutro a terra tramite resistenza);
- motore sincrono 11 kV 2,29 MVA (neutro a terra tramite resistenza 100 A);
- motori asincroni 11 kV e 0,4 kV;
- congiuntore BT chiuso tra due quadri.

Opzioni dello studio: IEC 60909, c = 1,10 (MT) e 1,05 (BT), contributo dei
motori incluso.

## Come si è arrivati alla coincidenza

| Passo | Scarto massimo | Cosa è emerso |
|---|---|---|
| 1. Prima conversione | 100 % (bifase a terra, Bus C); 3,4 % (bifase, SWBRDA) | Guasto trifase già esatto (I"k, ip, Z1, Z0) |
| 2. Colonna `IPPkLLG` | 0,66 % | In ETAP è la corrente di **fase** del guasto bifase a terra; la corrente verso terra 3I0 è in `ClippingCurrent` |
| 3. Correzione in `iec60909` | — | Senza percorso verso terra le correnti di fase del bifase a terra valgono I"k2 (prima: 0) |
| 4. Sequenza inversa delle macchine | 0,28 % | ETAP usa la reattanza X2 di targa invece di X" |
| 5. R dei motori in sequenza inversa | 0,12 % | Per i motori asincroni ETAP usa R2 = R1 con X2 di targa |
| 6. Neutro del motore sincrono a terra | **0,025 %** | Z0 = K_G·(R + jX0) + 3·Rn, con Rn = Un/(√3·100 A) |

Le funzioni aggiunte a `iec60909` per i passi 3–6 sono generali (sequenza
inversa di targa per generatori e motori, neutro dei generatori a terra) e
coperte da test con calcoli a mano.

## Convenzioni di ETAP ricavate dai dati

- **Prese dei trasformatori**: applicate alle tensioni nominali
  (es. 33 kV · 0,975 = 32,175 kV). Senza prese lo scarto su SWBRDA sale
  all'1,1 %.
- **Tolleranza dei trasformatori** (`IAdjustments.applyXfmrZTol`): l'impedenza
  è ridotta della tolleranza (6,25 % · 0,925) prima di applicare K_T.
- **K_T** dei trasformatori a due avvolgimenti: cmax del lato BT, come in
  `iec60909` (verificato sull'impedenza salvata in `IConnect`).
- **Trasformatore a tre avvolgimenti**: le tre impedenze di coppia sono in %
  sulla potenza del primario (10 MVA); K_T di ogni coppia calcolato sulla
  potenza della coppia (la minore delle due: 5 o 3 MVA), con cmax = 1,10.
  `IConnect` contiene l'equivalente a triangolo della stella.
- **Macchine sincrone (anche i motori)**: K_G secondo la norma, ma con il
  rapporto X/R di targa invece di R_Gf convenzionale.
- **Motori asincroni**: Z_M da LRC sulla potenza apparente nominale; R/X dai
  dati di targa (`Xpp/R`) anziché i valori convenzionali della norma.

## Risultati

Correnti in kA, scarto = iec60909 / ETAP − 1.

| Nodo | Un [kV] | I"k3 ETAP | I"k3 | ip3 ETAP | ip3 | I"k2 | I"k1 | I"kE2E (3I0) | Scarto max |
|---|---|---|---|---|---|---|---|---|---|
| Utility Bus | 33 | 9,739 | 9,739 | 24,079 | 24,079 | 8,500 | 8,384 | 7,260 | 0,000 % |
| Bus B | 11 | 6,525 | 6,525 | 16,773 | 16,769 | 5,656 | 7,188 | 7,985 | 0,025 % |
| Bus C | 11 | 6,583 | 6,583 | 16,553 | 16,552 | 5,709 | 0 | 0 | 0,006 % |
| SWBRDA | 11 | 9,987 | 9,987 | 25,043 | 25,043 | 8,954 | 10,369 | 10,035 | 0,000 % |
| EmergencySwBrd | 0,4 | 48,783 | 48,783 | 121,760 | 121,758 | 42,264 | 0 | 0 | 0,002 % |

Bus C (terziario a triangolo) ed EmergencySwBrd (a valle di un YNyn alimentato
dal terziario) non hanno percorso verso terra: correnti monofase nulle in
entrambi i programmi.

## Residuo

L'unico scarto residuo (≤ 0,025 %) riguarda la corrente di picco con il metodo
C ai nodi con macchine sincrone vicine: dipende probabilmente da come ETAP
tratta la resistenza delle macchine alla frequenza equivalente fc. Non ha
rilevanza pratica.

## Non confrontato

- Ib (interruzione) e Ik (permanente) con generatori: richiedono i fattori μ,
  q e λ, non ancora implementati (lo studio `Duty909.SI1S` li contiene e potrà
  servire per validarli).
- Contributi dei singoli rami (`SCIECLG`, `SCIECLL`, `SCIECLLG`).
