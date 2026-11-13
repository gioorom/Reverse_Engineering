# Test Universe / CMC 356

## Obiettivo

Software in Rust per comandare la cassetta prova relè OMICRON CMC 356 e
provare le funzioni protettive di un relè, più semplice e diretto di
OMICRON Test Universe: un modulo per funzione protettiva, pochi dati da
inserire, nessun ambiente dispersivo.

Test Universe viene studiato con REA per capire come il PC parla con la
cassetta (ricerca, connessione, comando delle uscite, lettura degli ingressi
binari) e come sono fatti i suoi report, allo scopo di far funzionare il
nuovo software con lo stesso strumento.

## Target

| Campo          | Valore |
| -------------- | ------ |
| Applicazione   | OMICRON Test Universe |
| Versione       | da annotare (non ancora letta) |
| Piattaforma    | Windows |
| Tipo           | da determinare (nativo e/o .NET) |
| Dove si trova  | `C:\Program Files (x86)\OMICRON\Test Universe` sul PC di lavoro (il binario NON va nel repository) |
| Strumento      | OMICRON CMC 356 |

## Requisiti

### Dati della prova

- nome del relè;
- montante provato;
- nome dell'impianto;
- località;
- nome del Commissioning Engineer;
- funzioni ANSI presenti nel relè (quelle da provare);
- rapporto e verso del TA;
- rapporto dell'eventuale TO (toroide omopolare);
- rapporto del TV.

### Moduli di prova

Un modulo per funzione; in ogni modulo si impostano i rapporti di TA e TV.

| ANSI | Funzione |
| ---- | -------- |
| 50   | Massima corrente istantanea |
| 51   | Massima corrente a tempo |
| 51N  | Massima corrente omopolare a tempo |
| 67   | Massima corrente direzionale |
| 67N  | Massima corrente direzionale di terra |
| 46   | Sequenza inversa (squilibrio) |
| 27   | Minima tensione |
| 59   | Massima tensione |
| 59N  | Massima tensione omopolare |
| 81   | Frequenza |
| 21L  | Distanza di linea |
| 87L  | Differenziale di linea |
| 87T  | Differenziale di trasformatore |
| 87G  | Differenziale di generatore |

### Strumento e report

- connessione alla CMC 356;
- report gestiti come in Test Universe.

## Vincoli

- **Sicurezza.** La CMC 356 eroga tensioni e correnti pericolose. Ogni
  comando verso le uscite va prima verificato senza carico e confrontato con
  Test Universe; finché questo confronto non è fatto, il software non va
  usato per prove di messa in servizio.
- **Licenze.** Nessun aggiramento delle protezioni o dei controlli di licenza
  di Test Universe o dello strumento. Prima di decompilare va verificato che
  cosa consente la licenza d'uso installata.
- **Via ufficiale.** OMICRON vende CM Engine, un'interfaccia di
  programmazione per comandare le CMC da software proprio. Da verificare se
  la licenza della CMC 356 la comprende: in quel caso è la strada da
  preferire rispetto alla ricostruzione del protocollo.
- **Binari.** Programmi, librerie e installer di OMICRON restano fuori dal
  repository.

## Piano di analisi

1. Inventario della cartella d'installazione: versione, eseguibili, librerie,
   tipo (nativo o .NET), presenza di CM Engine.
2. Connessione: come Test Universe trova la CMC in rete e apre il
   collegamento.
3. Comandi: come si impostano ampiezza, fase e frequenza delle uscite, come
   si avvia e si ferma l'erogazione, come si leggono ingressi binari e tempi
   d'intervento.
4. Report: formato dei file di prova e dei report.
5. Verifica sullo strumento, a uscite scollegate, di ogni comando ricostruito.

## Stato

- [ ] Target identificato e versione annotata
- [ ] Analisi con REA (`analisi/`)
- [ ] Conclusioni con evidenze
- [ ] Implementazione (`implementazione/`)
- [ ] Test

L'analisi non è ancora iniziata: la cartella d'installazione è sul PC di
lavoro e va analizzata da una sessione di Claude Code avviata su quel PC, dove
REA e Ghidra sono già installati.

## Domande aperte

- La CMC 356 ha la licenza CM Engine?
- La 87L si prova da un solo estremo, o servono due cassette sincronizzate?
- Interfaccia: applicazione desktop per Windows soltanto?

## Conclusioni

Nessuna, per ora.
