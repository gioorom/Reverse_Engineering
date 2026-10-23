# Muro tagliafiamme TR1 / TR2 — CP Faggiano 150/20 kV

## Dati di partenza

| Dato | Valore | Fonte |
| --- | --- | --- |
| Trasformatore | Matelec, olio minerale circa 16,1 t (≈ 18 300 l) | datasheet Matelec |
| Assi trasformatori | TR1 a Y 0, TR2 a Y +12 400 | modello Fusion |
| Plinti TR | 6400 × 8000 × 650, distanza netta 4400 | modello |
| Ingombro radiatori | fino a ±2540 da asse TR | modello SolidCraft (misura) |
| Sommità conservatore / terminale AT | +4590 / +4740 | modello SolidCraft (misura) |
| Castelletti MT | TR1 (Rosso) a Y −5200, TR2 (Verde) a Y +17 600: entrambi sul lato esterno | modello SolidCraft |
| Orientamento | spalle ai TR guardando la linea: TR Rosso = TR1 a sinistra, TR Verde = TR2 a destra (Y +) | utente |

## Norma

CEI EN 61936-1, par. 8.7.2 (trasformatori all'aperto): con 2 000 l ≤ V < 20 000 l la distanza G1 tra trasformatori senza separazione è 5 m. La distanza netta tra i radiatori di TR1 e TR2 è circa 7,3 m, quindi il muro **non è obbligatorio**; lo si adotta per proteggere il castelletto MT e i cavi del TR2, che si trovano a meno di 5 m dal TR1, e per uniformità agli standard Enel.

Quando c'è un muro di separazione, la norma chiede:

- resistenza al fuoco almeno EI 60 → adottato **REI 120** (anche portante);
- altezza almeno pari alla sommità del conservatore → **5000 ≥ 4740** ✔;
- larghezza tale da coprire l'ingombro del trasformatore → muro X 20000…27400, cioè circa 1 m oltre radiatori e terminale AT per lato ✔.

Spessore: EN 1992-1-2, tab. 5.4 (pareti REI 120 in c.a.: ≥ 160 mm) → adottati **300 mm** per stabilità a sbalzo (H = 5 m) e per l'esposizione all'aperto (XC4, copriferro 35 mm).

## Verifiche geometriche (dal modello)

- Muro centrato fra i plinti: Y 6050…6350 (asse 6200), fondazione Y 5700…6700
- 2050 mm dal plinto TR1 (bordo a 4000) e 2050 mm dal plinto TR2 (bordo a 8400) ✔
- Fra i due trafo ci sono solo i plinti: i castelletti MT sono entrambi sul lato esterno ✔
- Nessuna sovrapposizione con plinti, castelletti o conduttori ✔

## Da fare

- Calcolo strutturale (vento, sisma secondo NTC 2018) per armature e fondazione.
- Vasca di raccolta olio e drenaggio (CEI EN 61936-1, par. 8.7.3).
