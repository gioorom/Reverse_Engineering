//! Differenziale di trasformatore (87T), di generatore (87G) e di linea (87L).
//!
//! Le correnti sono espresse in per unità della corrente di riferimento di
//! ciascun lato. Il lato 1 usa la terna I L1..L3 e il TA del modulo, il lato
//! 2 la terna I 4..I 6 e il proprio TA. Le prove sono trifase simmetriche,
//! quindi la compensazione omopolare del relè non entra in gioco.

use serde::{Deserialize, Serialize};

use crate::functions::overcurrent::tolerance_rows;
use crate::phasor::three_phase;
use crate::shot::{Expected, Outputs, ShotPlan, Tolerances};
use crate::transformers::{Ratio, Transformers};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DifferentialKind {
    Transformer,
    Generator,
    Line,
}

/// Come il relè calcola la corrente di stabilizzazione dalle correnti dei due lati.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BiasFormula {
    /// |I1| + |I2|
    Sum,
    /// (|I1| + |I2|) / 2
    HalfSum,
    /// max(|I1|, |I2|)
    Max,
}

impl BiasFormula {
    pub const ALL: [BiasFormula; 3] = [BiasFormula::Sum, BiasFormula::HalfSum, BiasFormula::Max];

    pub fn label(self) -> &'static str {
        match self {
            BiasFormula::Sum => "|I1| + |I2|",
            BiasFormula::HalfSum => "(|I1| + |I2|) / 2",
            BiasFormula::Max => "max(|I1|, |I2|)",
        }
    }

    pub fn bias(self, i1: f64, i2: f64) -> f64 {
        match self {
            BiasFormula::Sum => i1 + i2,
            BiasFormula::HalfSum => (i1 + i2) / 2.0,
            BiasFormula::Max => i1.max(i2),
        }
    }

    /// Correnti passanti dei due lati (I1 ≥ I2) che danno la corrente
    /// differenziale `d` e la stabilizzazione `b`. `None` se non esistono.
    pub fn through_currents(self, d: f64, b: f64) -> Option<(f64, f64)> {
        let (i1, i2) = match self {
            BiasFormula::Sum => ((b + d) / 2.0, (b - d) / 2.0),
            BiasFormula::HalfSum => (b + d / 2.0, b - d / 2.0),
            BiasFormula::Max => (b, b - d),
        };
        (i2 >= 0.0).then_some((i1, i2))
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DifferentialSettings {
    /// Trasformatore: potenza nominale e tensioni dei due lati.
    pub rated_power_mva: f64,
    pub voltage1_kv: f64,
    pub voltage2_kv: f64,
    /// Indice orario del gruppo vettoriale (0..11): il lato 2 ritarda di
    /// indice × 30° sul lato 1.
    pub clock_number: u8,
    /// Generatore e linea: corrente di riferimento in ampere primari.
    pub rated_current_a: f64,
    /// TA del lato 2.
    pub ct2: Ratio,
    /// Soglia differenziale in per unità.
    pub pickup_pu: f64,
    pub knee1_pu: f64,
    pub slope1_pct: f64,
    pub knee2_pu: f64,
    pub slope2_pct: f64,
    pub delay_s: f64,
    pub bias_formula: BiasFormula,
    /// Correnti di stabilizzazione a cui provare la caratteristica.
    pub bias_points_pu: Vec<f64>,
    /// Ogni punto è provato a (1 − margine) e (1 + margine) della caratteristica.
    pub margin_pct: f64,
    pub tolerances: Tolerances,
}

impl Default for DifferentialSettings {
    fn default() -> Self {
        DifferentialSettings {
            rated_power_mva: 25.0,
            voltage1_kv: 132.0,
            voltage2_kv: 20.0,
            clock_number: 11,
            rated_current_a: 300.0,
            ct2: Ratio::new(1000.0, 5.0),
            pickup_pu: 0.2,
            knee1_pu: 0.5,
            slope1_pct: 25.0,
            knee2_pu: 2.5,
            slope2_pct: 50.0,
            delay_s: 0.03,
            bias_formula: BiasFormula::HalfSum,
            bias_points_pu: vec![1.0, 2.0, 4.0],
            margin_pct: 10.0,
            tolerances: Tolerances::default(),
        }
    }
}

impl DifferentialSettings {
    /// Corrente differenziale di intervento alla stabilizzazione `bias`.
    pub fn characteristic(&self, bias: f64) -> f64 {
        let s1 = self.slope1_pct / 100.0;
        let s2 = self.slope2_pct / 100.0;
        if bias <= self.knee1_pu {
            self.pickup_pu
        } else if bias <= self.knee2_pu {
            self.pickup_pu + s1 * (bias - self.knee1_pu)
        } else {
            self.pickup_pu + s1 * (self.knee2_pu - self.knee1_pu) + s2 * (bias - self.knee2_pu)
        }
    }

    /// Correnti di riferimento primarie dei due lati.
    pub fn reference_currents(&self, kind: DifferentialKind) -> (f64, f64) {
        match kind {
            DifferentialKind::Transformer => {
                let i = |kv: f64| self.rated_power_mva * 1000.0 / (3f64.sqrt() * kv);
                (i(self.voltage1_kv), i(self.voltage2_kv))
            }
            _ => (self.rated_current_a, self.rated_current_a),
        }
    }

    /// Soglia vista iniettando da un solo lato: la corrente differenziale che
    /// incontra la caratteristica alla stabilizzazione che essa stessa produce.
    pub fn single_side_pickup(&self) -> Option<f64> {
        let g = |d: f64| d - self.characteristic(self.bias_formula.bias(d, 0.0));
        let (mut low, mut high) = (0.0, 50.0);
        if g(high) < 0.0 {
            return None;
        }
        for _ in 0..60 {
            let mid = (low + high) / 2.0;
            if g(mid) < 0.0 {
                low = mid;
            } else {
                high = mid;
            }
        }
        Some(high)
    }
}

pub fn plan(
    kind: DifferentialKind,
    s: &DifferentialSettings,
    tr: &Transformers,
    frequency_hz: f64,
) -> ShotPlan {
    let mut plan = ShotPlan::default();
    let (ref1, ref2) = s.reference_currents(kind);
    let ref1_sec = ref1 / tr.ct.value();
    let ref2_sec = ref2 / s.ct2.value();
    let margin = s.margin_pct / 100.0;
    if margin <= s.tolerances.quantity() {
        plan.warn("Il margine di prova non supera la tolleranza sulla corrente");
    }
    // corrente passante: entra dal lato 1 ed esce dal lato 2, sfasata del gruppo
    let shift2 = match kind {
        DifferentialKind::Transformer => 180.0 - 30.0 * f64::from(s.clock_number),
        _ => 180.0,
    };
    let outputs = |i1: f64, i2: f64| {
        let mut o = Outputs::new(frequency_hz);
        o.set_phase_currents(three_phase(i1 * ref1_sec, 0.0));
        o.set_second_side_currents(three_phase(i2 * ref2_sec, shift2));
        o
    };
    let sides = [(1.0 - margin, "sotto", Expected::NoTrip), (1.0 + margin, "sopra", s.tolerances.trip_at(s.delay_s))];

    let single = match kind {
        DifferentialKind::Line => Some(s.pickup_pu),
        _ => s.single_side_pickup(),
    };
    match single {
        Some(d0) => {
            for (factor, side, expected) in sides {
                let d = d0 * factor;
                plan.push(
                    format!("Soglia dal lato 1: {side}, Id = {d:.3} p.u."),
                    outputs(d, 0.0),
                    Some(expected),
                );
            }
        }
        None => plan.warn("La caratteristica non è raggiungibile iniettando da un solo lato"),
    }
    if kind == DifferentialKind::Line {
        return plan;
    }

    for &bias in &s.bias_points_pu {
        let on_curve = s.characteristic(bias);
        for (factor, side, expected) in sides {
            let d = on_curve * factor;
            let description =
                format!("Caratteristica a Is = {bias:.2} p.u.: {side}, Id = {d:.3} p.u.");
            match s.bias_formula.through_currents(d, bias) {
                Some((i1, i2)) => plan.push(description, outputs(i1, i2), Some(expected)),
                None => plan.warn(format!(
                    "{description}: punto non ottenibile con questa stabilizzazione"
                )),
            }
        }
    }
    plan
}

pub fn summary(kind: DifferentialKind, s: &DifferentialSettings) -> Vec<(String, String)> {
    let mut rows = Vec::new();
    let (ref1, ref2) = s.reference_currents(kind);
    match kind {
        DifferentialKind::Transformer => {
            rows.push(("Potenza nominale".to_string(), format!("{} MVA", s.rated_power_mva)));
            rows.push(("Tensioni".to_string(), format!("{} / {} kV", s.voltage1_kv, s.voltage2_kv)));
            rows.push(("Indice orario".to_string(), format!("{}", s.clock_number)));
            rows.push((
                "Correnti di riferimento".to_string(),
                format!("{ref1:.1} A / {ref2:.1} A primari"),
            ));
        }
        _ => rows.push(("Corrente di riferimento".to_string(), format!("{ref1} A primari"))),
    }
    rows.push(("Soglia differenziale".to_string(), format!("{} p.u.", s.pickup_pu)));
    if kind != DifferentialKind::Line {
        rows.push(("TA lato 2".to_string(), format!("{} / {} A", s.ct2.primary, s.ct2.secondary)));
        rows.push((
            "Prima pendenza".to_string(),
            format!("{} % da {} p.u.", s.slope1_pct, s.knee1_pu),
        ));
        rows.push((
            "Seconda pendenza".to_string(),
            format!("{} % da {} p.u.", s.slope2_pct, s.knee2_pu),
        ));
        rows.push(("Stabilizzazione".to_string(), s.bias_formula.label().to_string()));
    }
    rows.push(("Tempo".to_string(), format!("{} s", s.delay_s)));
    rows.push(("Margine di prova".to_string(), format!("{} %", s.margin_pct)));
    rows.extend(tolerance_rows(&s.tolerances, "corrente"));
    rows
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn characteristic_has_two_slopes() {
        let s = DifferentialSettings::default();
        assert_eq!(s.characteristic(0.3), 0.2);
        assert!((s.characteristic(1.5) - 0.45).abs() < 1e-12);
        assert!((s.characteristic(4.0) - (0.2 + 0.5 + 0.75)).abs() < 1e-12);
    }

    #[test]
    fn through_currents_reproduce_the_requested_point() {
        for formula in BiasFormula::ALL {
            let (i1, i2) = formula.through_currents(0.4, 2.0).unwrap();
            assert!((i1 - i2 - 0.4).abs() < 1e-12);
            assert!((formula.bias(i1, i2) - 2.0).abs() < 1e-12);
        }
        assert_eq!(BiasFormula::Sum.through_currents(3.0, 2.0), None);
    }

    #[test]
    fn single_side_pickup_lies_on_the_characteristic() {
        let mut s = DifferentialSettings::default();
        // con la semisomma la stabilizzazione è Id/2 = 0.1 < 0.5: vale la soglia
        assert!((s.single_side_pickup().unwrap() - 0.2).abs() < 1e-9);
        // con la somma e il ginocchio a 0.1: d = 0.2 + 0.25·(d − 0.1)
        s.bias_formula = BiasFormula::Sum;
        s.knee1_pu = 0.1;
        let d = s.single_side_pickup().unwrap();
        assert!((d - 0.175 / 0.75).abs() < 1e-9);
    }

    #[test]
    fn transformer_currents_use_each_side_reference() {
        let s = DifferentialSettings::default();
        let tr = Transformers::default();
        let p = plan(DifferentialKind::Transformer, &s, &tr, 50.0);
        // 2 prove di soglia e 2 per ognuno dei 3 punti di stabilizzazione
        assert_eq!(p.shots.len(), 8);
        // lato 1: 25 MVA a 132 kV = 109.35 A, con TA 300/5 = 1.8225 A per unità
        let ref1 = 25000.0 / (3f64.sqrt() * 132.0) / 60.0;
        assert!((p.shots[1].outputs.currents[0].magnitude - 0.22 * ref1).abs() < 1e-9);
        assert!(p.shots[1].outputs.currents[3].is_zero());
        // punto a Is = 1: caratteristica 0.325, sopra del 10 % = 0.3575
        let o = &p.shots[3].outputs;
        let ref2 = 25000.0 / (3f64.sqrt() * 20.0) / 200.0;
        let i1 = o.currents[0].magnitude / ref1;
        let i2 = o.currents[3].magnitude / ref2;
        assert!((i1 - i2 - 0.3575).abs() < 1e-9);
        assert!(((i1 + i2) / 2.0 - 1.0).abs() < 1e-9);
        // Dyn11: il lato 2 esce a 180° − 330°
        assert!((o.currents[3].angle_deg + 150.0).abs() < 1e-9);
        assert!(matches!(p.shots[3].expected, Expected::Trip { .. }));
        assert_eq!(p.shots[2].expected, Expected::NoTrip);
    }

    #[test]
    fn line_differential_is_tested_from_one_end_only() {
        let s = DifferentialSettings::default();
        let p = plan(DifferentialKind::Line, &s, &Transformers::default(), 50.0);
        assert_eq!(p.shots.len(), 2);
        // 0.2 p.u. di 300 A con TA 300/5, al 110 %
        assert!((p.shots[1].outputs.currents[0].magnitude - 0.2 * 1.1 * 5.0).abs() < 1e-9);
    }

    #[test]
    fn generator_sides_are_in_opposition() {
        let s = DifferentialSettings::default();
        let p = plan(DifferentialKind::Generator, &s, &Transformers::default(), 50.0);
        let o = &p.shots[2].outputs;
        assert!((o.currents[3].angle_deg.abs() - 180.0).abs() < 1e-9);
    }
}
