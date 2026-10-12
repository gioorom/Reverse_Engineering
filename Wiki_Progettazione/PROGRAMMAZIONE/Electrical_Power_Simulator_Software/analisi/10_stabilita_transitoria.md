# 10 — Stabilità transitoria

Quinto modulo del simulatore: simulazione nel tempo del comportamento
elettromeccanico dei generatori sincroni dopo un disturbo (guasto, apertura
di linee, distacco di generatori, variazioni di carico), con il verdetto di
stabilità e il tempo critico di eliminazione del guasto.

- Implementazione: [`iec60909/stability.py`](../implementazione/iec60909/stability.py).
- Riga di comando: `python -m iec60909.stabilita rete.json [--svg angoli.svg]`.
- Esempio: [`esempi/kundur_due_aree.json`](../implementazione/esempi/kundur_due_aree.json),
  il sistema di Kundur a due aree con quattro generatori.

## Modello

Grandezze in per unità, con potenza di base 100 MVA e tensione di base del
nodo. Il punto di partenza è il flusso di potenza
([`07`](07_flusso_di_potenza.md)): tensioni, potenze delle macchine, prese
regolate e sfasamenti.

| Elemento | Modello |
|---|---|
| Rete (linee, trasformatori, derivazioni) | matrice delle ammettenze del flusso di potenza; rete algebrica risolta a ogni istante |
| Carichi, motori, generatori statici | ammettenza costante, da Y = −S*/\|V\|² con S la potenza netta del nodo non dovuta alle macchine nel flusso iniziale |
| Rete esterna | nodo di potenza infinita: fem costante dietro l'impedenza di cortocircuito Zq (`skq_max_mva`, `rx_max`) |
| Generatore `classical` | fem E' costante dietro X'd |
| Generatore `one_axis` | decadimento del flusso: T'd0·dE'q/dt = Efd − E'q − (Xd − X'd)·Id, con Vd = Xq·Iq − Ra·Id e Vq = E'q − Ra·Iq − X'd·Id |
| Regolatore di tensione | TA·dEfd/dt = KA·(Vref − \|Vt\|) − Efd, con limiti di Efd |
| Regolatore di velocità | TG·dPm/dt = Pref − Δω·(Sr/Sb)/R − Pm, con limite Pmax |

L'equazione di oscillazione è scritta sulla potenza nominale Sr:
dδ/dt = ω0·Δω, 2H·dΔω/dt = Pm − Pe − D·Δω.

**Interfaccia macchina-rete.** La macchina è una fem dietro X'd. Per il
modello a un asse la fem vale E = u·(j·E'q + (Xq − X'd)·Iq), con
u = e^(j(δ − π/2)) e Iq = Im(I·u*). Poiché la rete è lineare, le Iq di tutte
le macchine sono la soluzione esatta di un sistema lineare reale. Una prima
versione con iterazione semplice divergeva quando Xq e X'd erano molto
diverse.

**Inizializzazione.** Dal flusso di potenza si ricavano:
- δ dall'angolo di V + (Ra + jXq)·I, oppure di V + (Ra + jX'd)·I nel modello
  classico;
- E'q e Efd = E'q + (Xd − X'd)·Id;
- Vref = |Vt| + Efd/KA e Pref = Pe.

Senza eventi tutte le grandezze restano costanti entro 10⁻⁸ (test).

**Integrazione.** Runge-Kutta del quarto ordine a passo fisso, con passo di
default 2 ms. Il passo viene spezzato agli istanti degli eventi.

## Eventi

Si indicano nella sezione `stability_events` del file di rete, oppure
direttamente a `simulate`.

| `kind` | Effetto |
|---|---|
| `fault` | guasto trifase nel nodo `bus`, con impedenza `r_ohm` + j`x_ohm` (franco se nulla) |
| `clear_fault` | elimina il guasto nel nodo `bus` |
| `trip_branch` | apre il ramo `element`: linea, trasformatore, o tre avvolgimenti (tutti gli avvolgimenti) |
| `trip_gen` | distacca il generatore `element` |
| `load` | moltiplica per `scale` le ammettenze di carico del nodo `bus` |

## Risultati

- **Andamenti nel tempo:**
  - angoli rotorici, assoluti e relativi (riferiti alla fem della rete
    esterna, o al centro d'inerzia se la rete esterna manca);
  - velocità, potenze elettriche, Efd e tensioni dei nodi.
- **Verdetto:** il sistema è instabile, cioè perde il passo, quando la
  differenza tra gli angoli di due macchine supera 180°. Nel confronto entra
  anche la fem della rete esterna. Il risultato riporta l'istante di
  instabilità.
- **Tempo critico di eliminazione** (`critical_clearing_time`, `--tcc NODO`):
  ricerca per bisezione, eventualmente con l'apertura di rami all'eliminazione
  (`--apri`).
- **Grafico SVG** degli angoli rotorici relativi.

## Validazione

1. **Criterio delle aree uguali.** Macchina collegata alla rete di potenza
   infinita, con guasto franco ai morsetti eliminato senza aprire linee. La
   soluzione esatta è δcr = arccos[(π − 2δ0)·sinδ0 − cosδ0] e
   tcr = √(4H(δcr − δ0)/(ω0·Pm)), cioè 0,1927 s. Il tempo critico calcolato
   coincide entro 1 ms.
2. **Integrazione indipendente** con `scipy.integrate.solve_ivp`
   (tolleranza 10⁻¹¹):
   - Modello classico, guasto a metà linea eliminato aprendo la linea. La
     potenza massima durante il guasto è ricavata con una riduzione di Kron
     indipendente. Scarto massimo 2·10⁻⁵ °. Il caso perde il passo in
     entrambi i calcoli: dopo l'apertura Pmax è minore di Pm.
   - Modello a un asse con Xq ≠ X'd e regolatore di tensione (KA = 50),
     guasto attraverso una reattanza ai morsetti. Le equazioni macchina-rete
     di potenza infinita sono scritte in forma chiusa. Scarto 5·10⁻⁹ ° sugli
     angoli e 10⁻⁸ p.u. su Efd.
3. **Regolatore di velocità.** Due macchine in isola, aumento del 10 % del
   carico. A regime Δω = (ΣPref − ΣPe)/(Σ Sr/(Sb·R) + ΣD) entro 0,1 %, con
   la stessa velocità per le due macchine.
4. **ANDES 2.0.0**, sistema di Kundur a due aree con modello classico
   (`cases/kundur/kundur.raw` + `kundur_gencls.dyr`):
   - rete convertita con [`strumenti/confronto_andes_kundur.py`](../implementazione/strumenti/confronto_andes_kundur.py);
   - guasto nel nodo 8 da 1,0 a 1,083 s e apertura di Line_8 a 2,0 s (evento
     già presente nel file di ANDES);
   - flusso di potenza uguale entro 3·10⁻⁷ p.u.;
   - angoli rotorici relativi uguali entro **0,0028°** su 5 s, anche con
     l'apertura di una linea dell'interconnessione all'eliminazione del guasto.

   Lo scarto residuo viene dai diversi metodi di integrazione: trapezi
   implicito in ANDES, Runge-Kutta qui. I valori di riferimento di ANDES sono
   in `tests/dati/kundur_andes.json`.

## Limiti

- **Generatori:** modelli classico e a un asse, senza modelli subtransitori
  (GENROU, a sei equazioni) né saturazione.
- **Regolatori:** quelli di tensione e di velocità sono del primo ordine, non
  i modelli IEEE standard (es. SEXS, IEEEST, TGOV1); manca lo stabilizzatore
  di potenza (PSS).
- **Rete esterna:** sempre di potenza infinita; non c'è un'inerzia
  equivalente.
- **Carichi e altre macchine:**
  - carichi, motori e generatori statici sono ad ammettenza costante: non ci
    sono la dinamica dei motori asincroni né il controllo dei convertitori;
  - le protezioni non intervengono in automatico durante la simulazione, ma
    i loro tempi si possono ricavare dal coordinamento
    ([`09`](09_coordinamento_protezioni.md)) e inserire come eventi.
- **Guasti:** solo trifase; i guasti dissimmetrici richiederebbero le reti
  di sequenza in simulazione.
- **Metodo:** a passo fisso. Il criterio di instabilità dei 180° è
  convenzionale.
