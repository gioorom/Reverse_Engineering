//! Massima corrente: di fase (50, 51), omopolare (51N), di sequenza inversa (46).

use serde::{Deserialize, Serialize};

use crate::curves::TimeCharacteristic;
use crate::phasor::{three_phase, Phasor};
use crate::shot::{Outputs, ShotPlan, Tolerances};
use crate::transformers::{Basis, Transformers};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OvercurrentKind {
    Phase,
    Residual,
    NegativeSequence,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FaultType {
    L1,
    L2,
    L3,
    L1L2,
    L2L3,
    L3L1,
    L1L2L3,
}

impl FaultType {
    pub const ALL: [FaultType; 7] = [
        FaultType::L1,
        FaultType::L2,
        FaultType::L3,
        FaultType::L1L2,
        FaultType::L2L3,
        FaultType::L3L1,
        FaultType::L1L2L3,
    ];

    pub fn label(self) -> &'static str {
        match self {
            FaultType::L1 => "L1",
            FaultType::L2 => "L2",
            FaultType::L3 => "L3",
            FaultType::L1L2 => "L1-L2",
            FaultType::L2L3 => "L2-L3",
            FaultType::L3L1 => "L3-L1",
            FaultType::L1L2L3 => "L1-L2-L3",
        }
    }

    /// Correnti di fase per un guasto di ampiezza `i`.
    pub fn currents(self, i: f64) -> [Phasor; 3] {
        let z = Phasor::ZERO;
        let a = Phasor::new(i, 0.0);
        let b = Phasor::new(i, 180.0);
        match self {
            FaultType::L1 => [a, z, z],
            FaultType::L2 => [z, a, z],
            FaultType::L3 => [z, z, a],
            FaultType::L1L2 => [a, b, z],
            FaultType::L2L3 => [z, a, b],
            FaultType::L3L1 => [b, z, a],
            FaultType::L1L2L3 => three_phase(i, 0.0),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OvercurrentSettings {
    pub basis: Basis,
    /// Soglia in ampere.
    pub pickup: f64,
    pub characteristic: TimeCharacteristic,
    /// Multipli della soglia a cui provare.
    pub multiples: Vec<f64>,
    /// Tipi di guasto (solo per le funzioni di fase).
    pub fault_types: Vec<FaultType>,
    pub tolerances: Tolerances,
}

impl OvercurrentSettings {
    pub fn new(pickup: f64, characteristic: TimeCharacteristic, multiples: &[f64]) -> Self {
        OvercurrentSettings {
            basis: Basis::Primary,
            pickup,
            characteristic,
            multiples: multiples.to_vec(),
            fault_types: vec![FaultType::L1L2L3],
            tolerances: Tolerances::default(),
        }
    }
}

pub fn plan(
    kind: OvercurrentKind,
    s: &OvercurrentSettings,
    tr: &Transformers,
    frequency_hz: f64,
) -> ShotPlan {
    let mut plan = ShotPlan::default();
    let pickup = match kind {
        OvercurrentKind::Residual => tr.residual_current_secondary(s.pickup, s.basis),
        _ => tr.phase_current_secondary(s.pickup, s.basis),
    };
    let variants: Vec<Option<FaultType>> = match kind {
        OvercurrentKind::Phase => s.fault_types.iter().copied().map(Some).collect(),
        _ => vec![None],
    };
    for variant in variants {
        for &m in &s.multiples {
            let i = pickup * m;
            let mut outputs = Outputs::new(frequency_hz);
            let what = match (kind, variant) {
                (OvercurrentKind::Phase, Some(fault)) => {
                    outputs.set_phase_currents(fault.currents(i));
                    fault.label().to_string()
                }
                (OvercurrentKind::Residual, _) if tr.has_residual_ct => {
                    outputs.currents[3] = Phasor::new(i, 0.0);
                    "Corrente residua sul TO (I 4)".to_string()
                }
                (OvercurrentKind::Residual, _) => {
                    outputs.currents[0] = Phasor::new(i, 0.0);
                    "Corrente residua su L1".to_string()
                }
                _ => {
                    // terna di sequenza inversa: L2 in anticipo, L3 in ritardo
                    outputs.set_phase_currents([
                        Phasor::new(i, 0.0),
                        Phasor::new(i, 120.0),
                        Phasor::new(i, -120.0),
                    ]);
                    "Terna di sequenza inversa".to_string()
                }
            };
            plan.push(
                format!("{what}: {m:.2} × soglia = {i:.3} A"),
                outputs,
                s.characteristic.expected(m, &s.tolerances),
            );
        }
    }
    plan
}

pub fn summary(s: &OvercurrentSettings) -> Vec<(String, String)> {
    let unit = basis_unit(s.basis, "A");
    let mut rows = vec![("Soglia".to_string(), format!("{} {unit}", s.pickup))];
    match s.characteristic {
        TimeCharacteristic::DefiniteTime { delay_s } => {
            rows.push(("Tempo".to_string(), format!("{delay_s} s")));
        }
        TimeCharacteristic::Inverse { curve, multiplier } => {
            rows.push(("Curva".to_string(), curve.label().to_string()));
            rows.push(("Moltiplicatore di tempo".to_string(), format!("{multiplier}")));
        }
    }
    rows.extend(tolerance_rows(&s.tolerances, "corrente"));
    rows
}

pub(crate) fn basis_unit(basis: Basis, unit: &str) -> String {
    match basis {
        Basis::Primary => format!("{unit} primari"),
        Basis::Secondary => format!("{unit} secondari"),
    }
}

pub(crate) fn tolerance_rows(t: &Tolerances, quantity: &str) -> Vec<(String, String)> {
    vec![
        (format!("Tolleranza sulla {quantity}"), format!("{} %", t.quantity_pct)),
        (
            "Tolleranza sul tempo".to_string(),
            format!("{} % (minimo {} ms)", t.time_pct, t.time_abs_s * 1000.0),
        ),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curves::InverseCurve;
    use crate::shot::Expected;

    fn settings() -> OvercurrentSettings {
        OvercurrentSettings::new(
            600.0,
            TimeCharacteristic::DefiniteTime { delay_s: 0.1 },
            &[0.9, 1.1],
        )
    }

    #[test]
    fn phase_shots_use_secondary_amperes() {
        let plan = plan(OvercurrentKind::Phase, &settings(), &Transformers::default(), 50.0);
        assert_eq!(plan.shots.len(), 2);
        // 600 A primari con TA 300/5 = 10 A secondari
        assert!((plan.shots[0].outputs.currents[0].magnitude - 9.0).abs() < 1e-9);
        assert_eq!(plan.shots[0].expected, Expected::NoTrip);
        assert!((plan.shots[1].outputs.currents[2].magnitude - 11.0).abs() < 1e-9);
        assert!(matches!(plan.shots[1].expected, Expected::Trip { .. }));
    }

    #[test]
    fn two_phase_fault_has_opposite_currents() {
        let i = FaultType::L2L3.currents(4.0);
        assert!(i[0].is_zero());
        assert!(i[1].plus(i[2]).magnitude < 1e-9);
    }

    #[test]
    fn residual_shot_goes_to_the_core_balance_ct_when_present() {
        let mut tr = Transformers::default();
        let mut s = settings();
        s.pickup = 2.0;
        let without = plan(OvercurrentKind::Residual, &s, &tr, 50.0);
        assert!(without.shots[0].outputs.currents[0].magnitude > 0.0);
        tr.has_residual_ct = true;
        let with = plan(OvercurrentKind::Residual, &s, &tr, 50.0);
        assert!(with.shots[0].outputs.currents[0].is_zero());
        // 2 A primari · 0.9 con TO 100/1
        assert!((with.shots[0].outputs.currents[3].magnitude - 0.018).abs() < 1e-9);
    }

    #[test]
    fn negative_sequence_set_has_no_positive_sequence() {
        let p = plan(OvercurrentKind::NegativeSequence, &settings(), &Transformers::default(), 50.0);
        let i = p.shots[0].outputs.currents;
        // componente diretta: I1 + a·I2 + a²·I3
        let positive = i[0].plus(i[1].rotated(120.0)).plus(i[2].rotated(-120.0));
        assert!(positive.magnitude < 1e-9);
        let negative = i[0].plus(i[1].rotated(-120.0)).plus(i[2].rotated(120.0));
        assert!((negative.magnitude / 3.0 - 9.0).abs() < 1e-9);
    }

    #[test]
    fn multiple_inside_the_tolerance_band_is_excluded() {
        let mut s = settings();
        s.multiples = vec![1.0, 2.0];
        s.characteristic =
            TimeCharacteristic::Inverse { curve: InverseCurve::IecNormalInverse, multiplier: 0.1 };
        let p = plan(OvercurrentKind::Phase, &s, &Transformers::default(), 50.0);
        assert_eq!(p.shots.len(), 1);
        assert_eq!(p.warnings.len(), 1);
    }
}
