//! Modello delle prove sui relè di protezione.
//!
//! Questa libreria non parla con lo strumento e non legge né scrive file:
//! dalle tarature di una funzione protettiva calcola i punti di prova (le
//! grandezze secondarie da iniettare e l'esito atteso), valuta i risultati
//! misurati e compone il report.

pub mod curves;
pub mod functions;
pub mod phasor;
pub mod project;
pub mod report;
pub mod shot;
pub mod transformers;
