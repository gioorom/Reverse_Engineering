# 08 — Arc flash secondo IEEE 1584-2018

Terzo modulo del simulatore: energia incidente e confine dell'arco
elettrico (arc flash boundary) secondo **IEEE 1584-2018**, per sistemi
trifase in c.a. da 208 V a 15 kV.
Implementazione: [`iec60909/arcflash.py`](../implementazione/iec60909/arcflash.py).
Riga di comando: `python -m iec60909.arco rete.json`.

La corrente di cortocircuito franca Ibf di ogni punto è la I"k trifase
calcolata dal modulo IEC 60909 sulla stessa rete. Il tempo d'arco viene dalla
protezione indicata per il punto.

## Procedura della norma

1. **Corrente d'arco intermedia** a 600, 2700 e 14 300 V (eq. 1, tabella 1):
   Iarc,Voc = 10^(k1 + k2·lg Ibf + k3·lg G)·(k4·Ibf⁶ + … + k9·Ibf + k10).
2. **Corrente d'arco finale**:
   - Voc > 600 V: interpolazione dei tre valori intermedi (eq. 16–18);
   - Voc ≤ 600 V: eq. 25,
     Iarc = 1/√[(0,6/Voc)²·(1/Iarc,600² − (0,6² − Voc²)/(0,6²·Ibf²))].
3. **Corrente d'arco ridotta**: Iarc,min = Iarc·(1 − 0,5·VarCF) (eq. 2), con
   VarCF polinomio di sesto grado in Voc (tabella 2). Sopra 600 V la riduzione
   si applica ai tre valori intermedi.
4. **Fattore dell'involucro CF** (eq. 11–15, tabelle 6 e 7): dimensioni
   equivalenti di altezza e larghezza (EES), involucro "tipico" oppure "poco
   profondo" (BT con altezza e larghezza < 508 mm e profondità ≤ 203,2 mm);
   CF = 1 per le configurazioni all'aperto (VOA, HOA).
5. **Energia incidente** intermedia (eq. 3–6, tabelle 3–5):
   E = 12,552/50·T·10^(k1 + k2·lg G + k3·Iarc/(k4·Ibf⁷ + … + k10·Ibf)
   + k11·lg Ibf + k12·lg D + k13·lg Iarc + lg(1/CF)) [J/cm²], con T in ms;
   fino a 600 V nel terzo termine compare Iarc,600 (sempre quella piena).
   Sopra 600 V il valore finale è interpolato (eq. 19–21).
6. **Confine dell'arco** (eq. 7–10, interpolazione eq. 22–24): distanza a cui
   l'energia vale 1,2 cal/cm² (5,0208 J/cm²).
7. Il calcolo si ripete con la corrente piena e con quella ridotta, ciascuna
   con il **proprio tempo d'arco**. Si adotta il caso con energia maggiore; il
   confine è il maggiore dei due.

Configurazioni degli elettrodi: VCB (verticali in cella), VCBB (verticali in
cella con barriera isolante), HCB (orizzontali in cella), VOA e HOA (verticali e
orizzontali all'aperto).

Campo di validità, controllato prima del calcolo (4.2 della norma):

| Grandezza | Fino a 600 V | Oltre 600 V |
|---|---|---|
| Voc | 0,208–0,6 kV | 0,6–15 kV |
| Ibf | 0,5–106 kA | 0,2–65 kA |
| G | 6,35–76,2 mm | 19,05–254 mm |

Inoltre la distanza di lavoro deve essere di almeno 305 mm e la larghezza
dell'involucro di almeno 4·G.

Le tabelle 8 e 10 danno i valori tipici per classe di apparecchiatura (G,
dimensioni e distanza di lavoro). Sono disponibili con `equipment_class`, es.
`quadro_bt`, `pannello_bt`, `quadro_mt_15kv`; i dati espliciti hanno la
precedenza.

## Tempo d'arco

Per ogni punto la sezione `protection` indica:

- un tempo fisso (`time_ms`);
- oppure un relè con curva IEC 60255-151:
  t = TMS·k/((I/Is)^α − 1), con SI (0,14; 0,02), VI (13,5; 1), EI (80; 2) e
  LTI (120; 1), soglia istantanea (`inst_pickup_ka`, `inst_time_ms`) e tempo
  di apertura dell'interruttore (`breaker_time_ms`).

Il relè vede la corrente d'arco moltiplicata per `current_ratio`. Per esempio
vale 0,4/20 per un arco sulle sbarre BT eliminato dalla protezione sul lato
MT del trasformatore.

Il tempo è limitato a `max_time_ms`, 2 s per default. La norma lo indica come
valore ragionevole quando l'operatore può allontanarsi; se la protezione non
interviene si usa questo valore.

## Risultati

Per ogni punto sono calcolati:

- corrente d'arco, tempo, energia e confine per il caso pieno e per quello
  ridotto;
- l'energia determinante in cal/cm²;
- la categoria DPI secondo NFPA 70E (1: ≤ 4, 2: ≤ 8, 3: ≤ 25, 4: ≤ 40
  cal/cm²), solo a titolo indicativo.

## Validazione

- **Esempi svolti dell'allegato D della norma:**
  - D.1, quadro 4,16 kV VCB, Ibf 15 kA, 197/223 ms;
  - D.2, quadro 480 V VCB, Ibf 45 kA, 61,3/319 ms.

  Tutti i valori intermedi e finali coincidono con le cifre pubblicate:
  correnti d'arco, dimensioni equivalenti, CF, VarCF, energie e confini.
- **Confronto con [arcflash-calc](https://github.com/LiaungYip/arcflash)** 0.1.0
  (licenza MIT), implementazione open source indipendente:
  - griglia di 864 casi: 5 configurazioni, 13 tensioni da 208 V a 15 kV, 5
    involucri (tipico, poco profondo, grande, oltre i 1244,6 mm), 3 correnti,
    caso pieno e ridotto;
  - correnti, CF ed energie coincidono entro 1e-12, i confini entro 1e-9.

  `arcflash-calc` ricava il confine invertendo l'energia, mentre
  `iec60909` usa direttamente le eq. 7–10: il confronto verifica quindi anche
  l'equivalenza delle due forme.
- I coefficienti delle tabelle 1–8 e 10 sono quelli della norma, come trascritti
  in `arcflash-calc`. Le tabelle 1–5 e 7 sono verificate dagli esempi
  dell'allegato D solo per la configurazione VCB. Per le altre configurazioni
  il riscontro è il confronto con `arcflash-calc`, che usa le stesse tabelle:
  conferma le equazioni, non la trascrizione dei coefficienti.

## Limiti

- Solo c.a. trifase da 208 V a 15 kV: niente c.c. e niente metodi per tensioni
  superiori (es. Lee).
- Ibf è la I"k trifase IEC 60909, non la corrente simmetrica a regime della
  prassi IEEE.
- Tempo d'arco da una sola protezione con curva IEC 60255 o tempo fisso. Non
  sono modellati il decadimento della corrente durante l'arco (calcolo a più
  intervalli) né i fusibili.
- Sotto 240 V la norma ammette che l'arco non si autosostenga con
  trasformatori di potenza inferiore a 125 kVA: la verifica è lasciata al
  progettista.
