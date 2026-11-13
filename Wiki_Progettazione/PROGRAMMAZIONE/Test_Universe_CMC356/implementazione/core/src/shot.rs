//! Punto di prova: grandezze da iniettare, esito atteso, esito misurato.

use serde::{Deserialize, Serialize};

use crate::phasor::Phasor;

/// Limiti delle uscite della CMC 356 (4 tensioni da 300 V, 6 correnti da 32 A).
/// Valori di targa da confermare sullo strumento.
pub const MAX_OUTPUT_VOLTAGE_V: f64 = 300.0;
pub const MAX_OUTPUT_CURRENT_A: f64 = 32.0;

pub const VOLTAGE_LABELS: [&str; 4] = ["V L1", "V L2", "V L3", "V 4"];
pub const CURRENT_LABELS: [&str; 6] = ["I L1", "I L2", "I L3", "I 4", "I 5", "I 6"];

/// Grandezze secondarie ai morsetti dello strumento.
#[derive(Debug, Clone, PartialEq)]
pub struct Outputs {
    /// V L1, V L2, V L3 (fase-neutro) e V 4 (tensione residua).
    pub voltages: [Phasor; 4],
    /// I L1, I L2, I L3 (terna A) e I 4, I 5, I 6 (terna B: secondo lato
    /// delle differenziali; I 4 anche per il TO).
    pub currents: [Phasor; 6],
    pub frequency_hz: f64,
}

impl Outputs {
    pub fn new(frequency_hz: f64) -> Self {
        Outputs {
            voltages: [Phasor::ZERO; 4],
            currents: [Phasor::ZERO; 6],
            frequency_hz,
        }
    }

    pub fn set_phase_voltages(&mut self, v: [Phasor; 3]) {
        self.voltages[..3].copy_from_slice(&v);
    }

    pub fn set_phase_currents(&mut self, i: [Phasor; 3]) {
        self.currents[..3].copy_from_slice(&i);
    }

    pub fn set_second_side_currents(&mut self, i: [Phasor; 3]) {
        self.currents[3..].copy_from_slice(&i);
    }

    /// Le uscite diverse da zero, una per riga.
    pub fn describe(&self) -> String {
        let mut lines = Vec::new();
        for (label, v) in VOLTAGE_LABELS.iter().zip(self.voltages) {
            if !v.is_zero() {
                lines.push(format!("{label}: {:.2} V / {:.1}°", v.magnitude, v.angle_deg));
            }
        }
        for (label, i) in CURRENT_LABELS.iter().zip(self.currents) {
            if !i.is_zero() {
                lines.push(format!("{label}: {:.3} A / {:.1}°", i.magnitude, i.angle_deg));
            }
        }
        lines.push(format!("f: {:.3} Hz", self.frequency_hz));
        lines.join("\n")
    }

    pub fn limit_warnings(&self) -> Vec<String> {
        let mut warnings = Vec::new();
        for (label, v) in VOLTAGE_LABELS.iter().zip(self.voltages) {
            if v.magnitude > MAX_OUTPUT_VOLTAGE_V {
                warnings.push(format!(
                    "{label} = {:.1} V supera il limite di {MAX_OUTPUT_VOLTAGE_V:.0} V dell'uscita",
                    v.magnitude
                ));
            }
        }
        for (label, i) in CURRENT_LABELS.iter().zip(self.currents) {
            if i.magnitude > MAX_OUTPUT_CURRENT_A {
                warnings.push(format!(
                    "{label} = {:.2} A supera il limite di {MAX_OUTPUT_CURRENT_A:.0} A dell'uscita",
                    i.magnitude
                ));
            }
        }
        warnings
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Expected {
    /// Intervento entro la finestra di tempo, in secondi.
    Trip { nominal_s: f64, min_s: f64, max_s: f64 },
    NoTrip,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum Measured {
    Trip { time_s: f64 },
    NoTrip,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    NotTested,
    Passed,
    Failed,
}

pub fn assess(expected: &Expected, measured: Option<&Measured>) -> Verdict {
    match (expected, measured) {
        (_, None) => Verdict::NotTested,
        (Expected::NoTrip, Some(Measured::NoTrip)) => Verdict::Passed,
        (Expected::Trip { min_s, max_s, .. }, Some(Measured::Trip { time_s }))
            if time_s >= min_s && time_s <= max_s =>
        {
            Verdict::Passed
        }
        _ => Verdict::Failed,
    }
}

/// Esito complessivo: fallito se una prova è fallita, superato solo se tutte
/// sono state eseguite e superate.
pub fn overall(verdicts: impl IntoIterator<Item = Verdict>) -> Verdict {
    let mut any = false;
    let mut all_passed = true;
    for v in verdicts {
        any = true;
        match v {
            Verdict::Failed => return Verdict::Failed,
            Verdict::NotTested => all_passed = false,
            Verdict::Passed => {}
        }
    }
    if any && all_passed {
        Verdict::Passed
    } else {
        Verdict::NotTested
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Shot {
    pub description: String,
    pub outputs: Outputs,
    pub expected: Expected,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Tolerances {
    /// Tolleranza sulla grandezza di soglia (corrente, tensione, impedenza), in %.
    pub quantity_pct: f64,
    /// Tolleranza sul tempo: la maggiore tra la quota percentuale e quella assoluta.
    pub time_pct: f64,
    pub time_abs_s: f64,
}

impl Default for Tolerances {
    fn default() -> Self {
        Tolerances { quantity_pct: 5.0, time_pct: 5.0, time_abs_s: 0.04 }
    }
}

impl Tolerances {
    pub fn quantity(&self) -> f64 {
        self.quantity_pct / 100.0
    }

    pub fn time_margin(&self, time_s: f64) -> f64 {
        (time_s * self.time_pct / 100.0).max(self.time_abs_s)
    }

    /// Intervento atteso a tempo definito.
    pub fn trip_at(&self, delay_s: f64) -> Expected {
        let margin = self.time_margin(delay_s);
        Expected::Trip {
            nominal_s: delay_s,
            min_s: (delay_s - margin).max(0.0),
            max_s: delay_s + margin,
        }
    }

    /// Esito atteso di una prova a soglia. `ratio` è la grandezza iniettata
    /// divisa per la soglia; `over` vale per le funzioni di massima, false
    /// per quelle di minima. Dentro la banda di tolleranza della soglia
    /// l'esito non è definito.
    pub fn threshold(&self, ratio: f64, over: bool, delay_s: f64) -> Option<Expected> {
        let q = self.quantity();
        let beyond = if over { ratio >= 1.0 + q } else { ratio <= 1.0 - q };
        let short = if over { ratio <= 1.0 - q } else { ratio >= 1.0 + q };
        if beyond {
            Some(self.trip_at(delay_s))
        } else if short {
            Some(Expected::NoTrip)
        } else {
            None
        }
    }
}

/// Elenco dei punti di prova di un modulo, con gli avvisi.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct ShotPlan {
    pub shots: Vec<Shot>,
    pub warnings: Vec<String>,
}

impl ShotPlan {
    /// Aggiunge il punto, o un avviso se l'esito atteso non è definito.
    pub fn push(&mut self, description: String, outputs: Outputs, expected: Option<Expected>) {
        match expected {
            Some(expected) => self.shots.push(Shot { description, outputs, expected }),
            None => self.warnings.push(format!(
                "{description}: dentro la banda di tolleranza della soglia, prova esclusa"
            )),
        }
    }

    pub fn warn(&mut self, message: impl Into<String>) {
        let message = message.into();
        if !self.warnings.contains(&message) {
            self.warnings.push(message);
        }
    }

    /// Aggiunge gli avvisi sui limiti delle uscite dello strumento.
    pub fn check_limits(&mut self) {
        let messages: Vec<String> = self
            .shots
            .iter()
            .flat_map(|s| {
                s.outputs
                    .limit_warnings()
                    .into_iter()
                    .map(move |w| format!("{}: {w}", s.description))
            })
            .collect();
        for m in messages {
            self.warn(m);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trip_inside_the_window_passes() {
        let e = Tolerances::default().trip_at(1.0);
        assert_eq!(assess(&e, Some(&Measured::Trip { time_s: 1.04 })), Verdict::Passed);
        assert_eq!(assess(&e, Some(&Measured::Trip { time_s: 1.06 })), Verdict::Failed);
        assert_eq!(assess(&e, Some(&Measured::NoTrip)), Verdict::Failed);
        assert_eq!(assess(&e, None), Verdict::NotTested);
    }

    #[test]
    fn unexpected_trip_fails() {
        let m = Measured::Trip { time_s: 0.1 };
        assert_eq!(assess(&Expected::NoTrip, Some(&m)), Verdict::Failed);
        assert_eq!(assess(&Expected::NoTrip, Some(&Measured::NoTrip)), Verdict::Passed);
    }

    #[test]
    fn absolute_time_tolerance_wins_on_short_delays() {
        let Expected::Trip { min_s, max_s, .. } = Tolerances::default().trip_at(0.0) else {
            panic!("atteso un intervento");
        };
        assert_eq!(min_s, 0.0);
        assert!((max_s - 0.04).abs() < 1e-12);
    }

    #[test]
    fn threshold_band_is_undefined() {
        let t = Tolerances::default();
        assert!(matches!(t.threshold(1.1, true, 0.5), Some(Expected::Trip { .. })));
        assert_eq!(t.threshold(0.9, true, 0.5), Some(Expected::NoTrip));
        assert_eq!(t.threshold(1.02, true, 0.5), None);
        assert!(matches!(t.threshold(0.9, false, 0.5), Some(Expected::Trip { .. })));
        assert_eq!(t.threshold(1.1, false, 0.5), Some(Expected::NoTrip));
    }

    #[test]
    fn overall_needs_every_shot() {
        use Verdict::*;
        assert_eq!(overall([Passed, Passed]), Passed);
        assert_eq!(overall([Passed, NotTested]), NotTested);
        assert_eq!(overall([Passed, NotTested, Failed]), Failed);
        assert_eq!(overall([]), NotTested);
    }

    #[test]
    fn outputs_over_the_instrument_limits_are_reported() {
        let mut o = Outputs::new(50.0);
        o.currents[0] = Phasor::new(40.0, 0.0);
        o.voltages[3] = Phasor::new(310.0, 0.0);
        assert_eq!(o.limit_warnings().len(), 2);
    }
}
