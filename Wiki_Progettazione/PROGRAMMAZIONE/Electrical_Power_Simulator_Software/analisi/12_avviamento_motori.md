# 12 — Avviamento dei motori

Settimo modulo del simulatore. Calcola la caduta di tensione all'avviamento
di un motore asincrono e la simulazione dell'accelerazione, con i metodi di
avviamento diretto, stella-triangolo, con autotrasformatore e con soft
starter.

- Implementazione: [`iec60909/motorstart.py`](../implementazione/iec60909/motorstart.py).
- Riga di comando: `python -m iec60909.avviamento rete.json [--statico] [--svg cartella]`.
- Esempio: [`esempi/avviamento_motore.json`](../implementazione/esempi/avviamento_motore.json),
  la cabina 20/0,4 kV con il motore da 75 kW in fondo al cavo, avviato in
  tre modi.

## Motore

Il motore è rappresentato con un circuito equivalente a gabbia singola. Le
grandezze sono in per unità sulla potenza apparente nominale
Sr = Pr/(η·cosφ) e sulla tensione nominale Ur:

- Z(s) = Rs + jXs + jXm ∥ (Rr/s + jXr);
- coppia Te = |Ir|²·Rr/s, con coppia di base Sr/ω di sincronismo;
- equazione meccanica 2H·dω/dt = Te − T_L(ω).

La coppia resistente è T_L = T_r·(a0 + a1·ω + a2·ω²), dove T_r è la coppia
nominale all'albero. Il default a0 = 0,1, a2 = 0,9 rappresenta pompe e
ventilatori.

### Stima del circuito dai dati di targa

Se i parametri rs, xs, xm, rr, xr non sono indicati, vengono stimati con
Newton imponendo Xs = Xr.

| Condizione | Equazioni |
|---|---|
| Rotore bloccato | \|Z(1)\| = 1/(Ilr/Ir), con R/X dato (`rx` del motore) o convenzionale IEC 60909 (0,42 BT; 0,1–0,15 MT) |
| Punto nominale | Z(s_r) = 1∠φ: corrente nominale con il cosφ di targa a tensione nominale |
| Rendimento | Pall'albero = η·Pass |

Le incognite sono Rs, Rr, Xs, Xm e lo scorrimento nominale s_r.

Nei motori MT con R/X convenzionale basso le perdite nel rame non bastano a
dare il rendimento di targa. In quel caso si assume **Rs = Rr** e la
differenza viene attribuita alle perdite meccaniche e nel ferro. Queste sono
rappresentate come una coppia resistente costante a motore in moto, così il
rendimento all'albero torna esatto.

Con la **coppia di spunto di targa** `tlr_tr` (Tavv/Tn) questa condizione
sostituisce quella sull'R/X a rotore bloccato. È consigliata: con la gabbia
singola e R/X = 0,1 la coppia di spunto dei motori MT risulta di 0,3–0,5
volte la nominale, contro 0,7–1 dei motori reali a barre profonde.

## Rete e metodi di avviamento

A ogni passo si risolve il flusso di potenza ([`07`](07_flusso_di_potenza.md)):
- il motore in avviamento è un'ammettenza che dipende dallo scorrimento;
- gli altri carichi e motori sono a potenza costante;
- prima dell'avviamento il motore è fermo, cioè assente.

L'avviatore è un trasformatore ideale di rapporto u tra rete e motore.

| Metodo | u | Ammettenza vista dalla rete | Note |
|---|---|---|---|
| diretto | 1 | Y | |
| stella-triangolo | 1/√3 fino a `switch_speed` | u²·Y | corrente e coppia 1/3; alla commutazione corrente transitoria |
| autotrasformatore | presa `tap` fino a `switch_speed` | u²·Y | corrente di linea u², coppia u² |
| soft starter | rampa da `u0` in `ramp_s`, ridotta per non superare `current_limit` × Ir | u·Y | la corrente di linea è quella del motore |

Integrazione con il metodo di Heun (trapezi esplicito) a passo fisso, con
passo di default 10 ms. L'avviamento è concluso quando la velocità raggiunge
1 − 2·s_r.

## Verifiche e risultati

- **Correnti:** corrente di linea iniziale e massima (in A e in multipli di
  Ir); la massima conta per stella-triangolo e autotrasformatore alla
  commutazione.
- **Tensioni:** tensione minima della rete nel punto di allacciamento,
  confrontata con `v_min_motor_pu`, di default 0,8; tensione al motore a
  valle dell'avviatore, solo informativa; tensioni minime negli altri nodi,
  confrontate con `v_min_bus_pu`, di default 0,9.
- **Tempi:** tempo di avviamento, confrontato con il tempo ammesso a rotore
  bloccato `t_lr_max_s`; stallo se la velocità di fine avviamento non viene
  raggiunta entro `t_max_s`.
- **Grafico SVG** di velocità, corrente e tensione al motore.
- **Calcolo statico** (`--statico`): solo l'istante di avviamento, con il
  rotore bloccato.

## Validazione

1. **Stima del circuito.** Per cinque motori (BT e MT, con e senza coppia di
   spunto) sono riprodotti esattamente, entro 10⁻⁸, corrente nominale, cosφ,
   rendimento all'albero, |Z(1)| = 1/(Ilr/Ir) e, se indicati, l'R/X a rotore
   bloccato o la coppia di spunto.
2. **Caduta di tensione a mano.** Rete rigida, linea e motore:
   V_M = Zm/(Zm + Z_linea) e corrente Un/(√3·|Zm + Z_linea|), entro 10⁻⁹.
3. **Metodi di avviamento.** Su una rete rigida la corrente di linea vale
   Ilr (diretto), Ilr/3 (stella-triangolo), tap²·Ilr (autotrasformatore) e
   u0·Ilr (soft starter). Sull'esempio della cabina, a parità di tensione,
   la corrente in stella è 1/3 di quella diretta entro 10⁻⁹.
4. **Accelerazione contro un'integrazione indipendente** (`scipy`,
   tolleranza 10⁻¹⁰) con la stessa rete in forma chiusa.
   - Velocità: scarto 4·10⁻⁴ p.u. con passo 10 ms e 1,3·10⁻⁵ con 2 ms.
   - Tempo di avviamento: scarto entro un passo.
5. **Altri test:**
   - soft starter: il limite di corrente è rispettato e raggiunto;
   - stallo con coppia resistente oltre quella di spunto;
   - segnalazioni dei limiti di tensione e di tempo;
   - corrente che risale alla commutazione stella-triangolo.

**Esempio della cabina** (motore da 75 kW, 0,4 kV, coppia di spunto 2,2):

| Metodo | I max [×Ir] | U di rete al motore min [p.u.] | Tempo di avviamento [s] |
|---|---|---|---|
| diretto | 6,34 | 0,905 | 0,62 |
| stella-triangolo | ~2,2 in stella, picco alla commutazione | 0,952 | 2,12 |
| soft starter (limite 3,5 × Ir) | 3,32 | 0,941 | 3,22 |

## Limiti

- **Motore:**
  - circuito a gabbia singola, senza doppia gabbia o barre profonde, ma
    con la coppia di spunto di targa imponibile;
  - niente saturazione né transitori elettromagnetici: il modello è
    quasi-stazionario e il picco asimmetrico all'inserzione non è
    calcolato;
  - le perdite meccaniche e nel ferro sono modellate come coppia costante.
- **Rete:** gli altri motori sono carichi a potenza costante, senza la loro
  dinamica (es. riaccelerazione dopo un buco di tensione); i generatori della
  rete non hanno dinamica (per quella vedi [`10`](10_stabilita_transitoria.md)).
- **Avviatori:** il soft starter è una pura riduzione di tensione alla
  fondamentale, senza le armoniche dei tiristori; gli avviamenti con
  inverter non sono modellati.
- **Scenari:** un avviamento alla volta, senza avviamenti in sequenza.
