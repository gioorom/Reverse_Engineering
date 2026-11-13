# ProvaRelè

Programma in Rust per le prove sui relè di protezione con la cassetta OMICRON
CMC 356: un modulo per funzione ANSI, pochi dati da inserire, report alla fine.

**Stato:** il programma calcola i punti di prova, valuta i risultati e produce
il report. Non comanda ancora lo strumento: le grandezze si impostano sulla
cassetta e gli esiti misurati si inseriscono a mano.

## Struttura

| Cartella  | Contenuto |
| --------- | --------- |
| `core/`   | Libreria `prova-rele-core`: tarature, punti di prova, esiti attesi, valutazione, report. Non legge file e non parla con lo strumento. |
| `app/`    | Programma `prova-rele`: la finestra (libreria grafica egui). |
| `esempi/` | `cabina_mt.json`, una prova di esempio da aprire nel programma. |
| `.vscode/`| Comandi e debug già pronti per Visual Studio Code. |

## Aprire il progetto in Visual Studio Code (Windows)

Una volta sola:

1. Installa Rust: `winget install Rustlang.Rustup`.
2. Installa gli strumenti di compilazione Microsoft, se non c'è già Visual
   Studio con il carico di lavoro "Sviluppo di applicazioni desktop con C++":
   `winget install Microsoft.VisualStudio.2022.BuildTools`, poi nel programma
   d'installazione scegli quel carico di lavoro.
3. In Visual Studio Code apri la cartella `implementazione` (questa, non la
   radice del repository) e accetta le estensioni consigliate.

Poi, dal menu **Terminale › Esegui attività**:

| Attività | Che cosa fa |
| -------- | ----------- |
| Avvia ProvaRelè | compila e apre il programma (anche con Ctrl+Maiusc+B) |
| Avvia ProvaRelè con la prova di esempio | lo apre su `esempi/cabina_mt.json` |
| Esegui i test | esegue i test della libreria |
| Compila il programma finale (release) | crea `target\release\prova-rele.exe` |

Con F5 il programma parte nel debugger.

Gli stessi comandi da terminale:

```
cargo run -p prova-rele
cargo test --workspace
cargo build --release -p prova-rele
```

A ogni caricamento su GitHub i test girano su Windows e il programma
compilato si scarica dalla pagina **Actions** del repository, esecuzione
"ProvaRelè", voce **Artifacts**.

## Come si usa

1. **Dati della prova**: relè, montante, impianto, località, Commissioning
   Engineer, data; rapporti di TA (con il verso), TO e TV; funzioni presenti
   nel relè.
2. Per ogni funzione spuntata compare un **modulo** nell'elenco a sinistra.
   Nel modulo si inseriscono le tarature (in valori primari o secondari) e,
   se servono, rapporti di TA e TV diversi da quelli generali.
3. Il modulo elenca le **prove**: per ognuna le grandezze secondarie da
   iniettare e l'esito atteso (tempo di intervento con la sua finestra, o
   nessun intervento). Accanto si inserisce l'esito misurato e il programma
   dà subito superata o non superata.
4. **Report**: riepilogo degli esiti ed esportazione in una pagina HTML, in
   forma estesa (tarature, grandezze iniettate, risultati) o sintetica (solo
   risultati). Dal browser si stampa o si salva in PDF.

La prova si salva in un file `.json` e si riapre in seguito.

## Che cosa prova ogni modulo

| ANSI | Prove |
| ---- | ----- |
| 50, 51 | Per ogni tipo di guasto scelto, la corrente ai multipli della soglia: sotto non interviene, sopra interviene nel tempo della caratteristica (tempo definito, curve IEC 60255-151 e IEEE C37.112). |
| 51N | Come sopra con la corrente residua: sul TO (uscita I 4) se presente, altrimenti su L1. |
| 46 | Terna di sola sequenza inversa ai multipli della soglia. |
| 67, 67N | Soglia al centro del settore di intervento; ai due limiti del settore, dentro e fuori; direzione opposta. |
| 27, 59 | Terna di tensioni ai multipli della soglia, concatenata o di fase. |
| 59N | Tensione residua 3V0 ai multipli della soglia: centro stella spostato sulle tre fasi e stessa tensione sull'uscita V 4. |
| 81 | Per ogni soglia di minima o massima frequenza, una prova da ciascuna parte. |
| 21L | Per ogni anello di guasto (L1-E, L1-L2, L1-L2-L3) e ogni zona, un punto dentro e uno fuori dalla portata, lungo l'angolo di linea, a corrente costante. |
| 87T, 87G | Soglia iniettando da un solo lato; poi, a ogni corrente di stabilizzazione scelta, un punto sotto e uno sopra la caratteristica a due pendenze. |
| 87L | Soglia e tempo da un solo estremo. |

Uscite dello strumento: `V L1`, `V L2`, `V L3` tensioni di fase, `V 4`
tensione residua; `I L1`, `I L2`, `I L3` correnti di fase (lato 1 delle
differenziali); `I 4`, `I 5`, `I 6` lato 2 delle differenziali, `I 4` anche
per il TO.

## Convenzioni e limiti

- **Tolleranze.** Dentro la banda di tolleranza della soglia l'esito non è
  definito: i multipli che vi cadono sono esclusi, con un avviso. Sul tempo
  vale la maggiore tra la tolleranza percentuale e quella minima in
  millisecondi. Per le curve inverse la finestra di tempo comprende l'effetto
  della tolleranza sulla corrente.
- **Angoli delle direzionali.** Il settore è espresso come ritardo della
  corrente sulla tensione di riferimento: la tensione di fase per la 67, la
  tensione residua 3V0 per la 67N. Il segno della tensione residua cambia da
  un costruttore all'altro e va verificato sul manuale del relè.
- **Verso del TA.** Con i TA rivolti verso le sbarre le correnti di fase sono
  iniettate ruotate di 180°.
- **Distanza.** Le zone sono verificate solo lungo l'angolo di linea: la
  forma della caratteristica (mho o poligonale) fuori da quell'angolo non è
  provata.
- **Differenziali.** Prove trifase simmetriche. La caratteristica è a due
  pendenze con tre formule possibili per la corrente di stabilizzazione; se
  il relè ne usa un'altra i punti vanno ricalcolati. La seconda soglia
  (Idiff>>) e il blocco per armoniche non sono provati.
- **87L.** La caratteristica di stabilizzazione richiede due cassette
  sincronizzate ai due estremi e non è prevista.
- **Limiti delle uscite.** Il programma avvisa quando una prova supera
  300 V o 32 A per uscita, valori di targa della CMC 356 da confermare sullo
  strumento.
- **Tarature predefinite.** I valori proposti alla prima apertura sono solo
  un punto di partenza, non tarature consigliate.

## Verifiche fatte

- 57 test automatici sulla libreria (`cargo test --workspace`): curve
  confrontate con i valori tabulati delle norme, impedenze viste dal relè
  nei tre anelli di guasto, punti delle differenziali, conversioni tra
  primario e secondario, esiti, report, apertura della prova di esempio.
- Il programma è stato avviato su Linux e le pagine sono state controllate a
  vista con la prova di esempio.
- Non verificato: le finestre "Apri", "Salva" ed "Esporta" (su Linux senza
  ambiente grafico non si aprono) e l'esecuzione su Windows.
- Nessun confronto è stato ancora fatto con Test Universe né con un relè
  reale: prima di usarlo in una messa in servizio i punti di prova vanno
  confrontati con quelli di Test Universe.
