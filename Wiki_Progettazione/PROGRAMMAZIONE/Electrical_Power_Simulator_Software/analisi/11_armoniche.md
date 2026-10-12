# 11 — Armoniche

Sesto modulo del simulatore: propagazione delle correnti armoniche dei carichi
non lineari (convertitori, azionamenti, raddrizzatori), tensioni armoniche e
THD nei nodi, correnti armoniche nei rami, scansione in frequenza per
individuare le risonanze, filtri accordati e verifica dei limiti EN 50160 e
IEEE 519.

- Implementazione: [`iec60909/harmonics.py`](../implementazione/iec60909/harmonics.py).
- Riga di comando: `python -m iec60909.armoniche rete.json [--scansione NODO --svg z.svg]`.
- Esempio: [`esempi/armoniche_cabina.json`](../implementazione/esempi/armoniche_cabina.json),
  cabina 20/0,4 kV con rifasamento e convertitore a 6 impulsi.

## Metodo

La rete è lineare, quindi vale la sovrapposizione degli effetti, e il sistema
trifase è equilibrato.

- **Fondamentale:** viene dal flusso di potenza ([`07`](07_flusso_di_potenza.md)).
- **Correnti armoniche delle sorgenti:** ogni sorgente assorbe
  I_h = I1·m_h/100 ∠ (h·θ1 + φ_h), dove I1 e θ1 sono la corrente fondamentale
  dell'elemento collegato (carico, motore o generatore statico) oppure i valori
  dati con `i1_a` e `angle_deg`, e m_h, φ_h vengono dallo spettro.
- **Spettri predefiniti:** convertitori ideali a 6 impulsi (6k ± 1, 1/h) e a
  12 impulsi (12k ± 1, 1/h). In alternativa si possono indicare valori propri.
- **Sequenza dell'armonica:** h = 3k + 1 è diretta, h = 3k − 1 inversa,
  h = 3k omopolare.
- **Calcolo per ogni ordine:** V_h = Z_h·I_h, con Z_h la rete della sequenza
  corrispondente alla frequenza h·f. Le correnti nei rami si ricavano dalle
  tensioni.

### Modelli alla frequenza h·f

| Elemento | Sequenze diretta e inversa | Sequenza zero |
|---|---|---|
| Linea | R (o R·√h con `--pelle`) + jX·h, capacità B·h | r0 + jx0·h se indicate, altrimenti aperta (avviso) |
| Trasformatore | R + jX·h, rapporto con presa, sfasamento +k·30° (diretta) e −k·30° (inversa) | secondo i collegamenti, come nel cortocircuito (YNyn, YNd, Dyn, zig-zag) |
| Rete esterna | R + jX·h da skq_max e rx_max | da x0x1 e r0x0 |
| Generatore | R + jX₂·h | R + jX₀·h + 3·Zn |
| Motore | impedenza a rotore bloccato R + jX·h | — |
| Carico | R e L in parallelo: Y = (P − jQ/h)/Un² (potenza a tensione nominale) | — |
| Condensatori / reattori | B·h / X·h | — |
| Filtro accordato | R + j(h·X_L − X_C/h) | — |

**Sfasamenti.** Un trasformatore Dy sposta le grandezze di sequenza diretta di
+30° e quelle di sequenza inversa di −30°, qualunque sia l'ordine
dell'armonica. Unito alla rotazione h·θ1 delle correnti, questo spiega la
cancellazione di 5ª e 7ª nei convertitori a 12 impulsi.

**Filtri accordati** (`harmonic_filters`): la potenza reattiva Q alla
fondamentale e l'ordine di accordo h_t danno
X_C = (Un²/Q)·h_t²/(h_t² − 1) e X_L = X_C/h_t². La resistenza
R = h_t·X_L/qualità deriva dal fattore di qualità. Il filtro entra anche nel
flusso di potenza, con la sua ammettenza alla fondamentale. La funzione
`design_single_tuned_filter` restituisce C, L e R per fase.

## Risultati

- **Nodi:** tensione armonica di ogni ordine in % della nominale, THD
  riferito alla tensione fondamentale.
- **Rami:** corrente fondamentale e armoniche a entrambi gli estremi, THD,
  valore efficace e fattore K, dato da Σ(I_h·h)²/ΣI_h², fondamentale
  compresa.
- **Limiti di tensione:**
  - `en50160`, il default, che coincide con IEC 61000-2-2: 2ª 2 %, 3ª 5 %,
    4ª 1 %, 5ª 6 %, 6ª–24ª pari 0,5 %, 7ª 5 %, 9ª 1,5 %, 11ª 3,5 %, 13ª 3 %,
    15ª e 21ª 0,5 %, 17ª 2 %, 19ª, 23ª e 25ª 1,5 %; THD fino alla 40ª pari
    all'8 %;
  - `ieee519`, dalla tabella 1 della IEEE 519-2014 in base al livello di
    tensione.
- **Limiti di corrente IEEE 519 al punto di consegna** (`--pcc NODO
  --ramo-pcc RAMO --il A`): Isc è la I"k3 massima IEC 60909 del nodo, e dal
  rapporto Isc/IL si ricavano i limiti delle singole armoniche e del TDD
  (tabelle 2–4).
- **Scansione in frequenza:** |Z(h)| vista da un nodo e massimi locali, cioè
  le risonanze parallelo, con grafico SVG.

## Validazione

1. **Calcoli a mano.**
   - Nodo con rete esterna e condensatori:
     V_h = (I1/h)·|Zq(h) ∥ Zc(h)|, entro 10⁻⁹, anche con i carichi R-L in
     parallelo.
   - Risonanza senza resistenze: la scansione trova h = √(Sk/Qc) = 10 entro
     0,002.
   - Filtro: impedenza puramente resistiva all'accordo, frequenza
     1/(2π√(LC)) = h_t·f e potenza reattiva alla fondamentale.
2. **Convertitori a 12 impulsi.** Due convertitori uguali alimentati da
   trasformatori YNyn0 e Dyn11. Sulla MT 5ª, 7ª, 17ª e 19ª si annullano
   (< 10⁻⁹ %), mentre 11ª e 13ª sono uguali al caso con due YNyn0.
3. **Armoniche omopolari.** La 3ª armonica lato BT di un Dyn non passa sulla
   MT (corrente nulla); con un YNyn0 passa.
4. **OpenDSS** (DSS C-API 0.14.5, modalità armoniche).
   - Rete: cabina con trasformatore YNyn0, Dyn11 o Dyn1, cavo con capacità,
     rifasamento e carico lineare.
   - Due sorgenti: 6 impulsi, e uno spettro con angoli propri su un altro
     nodo.
   - In OpenDSS i carichi sono modellati con `%SeriesRL=0` (R-L in parallelo)
     e la frequenza base è 50 Hz.
   - Le tensioni armoniche di tutti i nodi e di tutti gli ordini fino al 49°
     coincidono entro **6·10⁻⁵** in valore relativo, per tutti e tre i gruppi
     vettoriali. Due sorgenti con angoli diversi confermano la stessa
     convenzione di fase (h·θ1 + φ_h).
   - OpenDSS impone 1 p.u. alla fem dietro l'impedenza della sorgente: nel
     confronto la rete esterna ha la stessa tensione fondamentale.
   - Lo scarto residuo è massimo vicino alla risonanza (7ª–11ª). Ho escluso
     come cause la frequenza base, la tensione fondamentale, la tensione a
     cui si valutano i carichi (alla tensione effettiva lo scarto sale allo
     0,9 %) e la capacità `ppm_antifloat` dei trasformatori: resta una piccola
     differenza nei modelli interni.
   - Lo script è [`strumenti/confronto_opendss_armoniche.py`](../implementazione/strumenti/confronto_opendss_armoniche.py)
     e i valori di riferimento sono in `tests/dati/armoniche_opendss.json`.

**Esempio della cabina.** La scansione trova una risonanza parallelo
all'ordine 8,2 (409 Hz) tra il rifasamento da 250 kvar e la rete vista dalle
sbarre BT. Per questo la 7ª supera il 5 % della EN 50160. Sostituendo il
rifasamento con filtri accordati a 4,7 e 6,7 (100 kvar ciascuno) le sbarre BT
rientrano nei limiti. In fondo al cavo resta la 19ª poco sopra l'1,5 %
(test).

## Limiti

- **Sistema equilibrato:** niente squilibri, sorgenti monofase né
  interarmoniche; le armoniche triple si propagano solo come sequenza zero
  equilibrata.
- **Sorgenti armoniche:** generatori di corrente ideali, senza
  l'interazione tra la tensione distorta e il convertitore.
- **Modelli a frequenza costante:** il modello dei carichi è uno solo (R-L in
  parallelo, tipo CIGRE 1), l'effetto pelle si limita alla scelta √h e
  mancano modelli dipendenti dalla frequenza per linee lunghe (parametri
  distribuiti).
- **Limiti di norma:** la EN 50160 non dà limiti per le singole armoniche
  oltre la 25ª; i limiti IEEE 519 per la corrente si applicano al solo punto
  di consegna indicato.
