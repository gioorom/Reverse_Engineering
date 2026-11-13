//! Minima tensione (27), massima tensione (59), massima tensione omopolare (59N).

use serde::{Deserialize, Serialize};

use crate::functions::overcurrent::{basis_unit, tolerance_rows};
use crate::phasor::{three_phase, Phasor};
use crate::shot::{Outputs, ShotPlan, Tolerances};
use crate::transformers::{Basis, Transformers};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VoltageKind {
    Under,
    Over,
    ResidualOver,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum VoltageMeasurement {
    PhaseToPhase,
    PhaseToNeutral,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VoltageSettings {
    pub basis: Basis,
    /// Soglia in volt. Per la 59N è la tensione residua 3V0.
    pub pickup: f64,
    /// Tensione a cui si riferisce la soglia (27 e 59).
    pub measurement: VoltageMeasurement,
    pub delay_s: f64,
    pub multiples: Vec<f64>,
    pub tolerances: Tolerances,
}

impl VoltageSettings {
    pub fn new(pickup: f64, delay_s: f64, multiples: &[f64]) -> Self {
        VoltageSettings {
            basis: Basis::Primary,
            pickup,
            measurement: VoltageMeasurement::PhaseToPhase,
            delay_s,
            multiples: multiples.to_vec(),
            tolerances: Tolerances::default(),
        }
    }
}

/// Tensioni di fase con il centro stella spostato: la somma delle tre vale
/// la tensione residua `residual` (3V0), in opposizione a L1 come in un
/// guasto a terra sulla fase L1.
pub(crate) fn displaced_phase_voltages(nominal: f64, residual: f64) -> [Phasor; 3] {
    let shift = Phasor::new(residual / 3.0, 180.0);
    three_phase(nominal, 0.0).map(|v| v.plus(shift))
}

pub fn plan(kind: VoltageKind, s: &VoltageSettings, tr: &Transformers, frequency_hz: f64) -> ShotPlan {
    let mut plan = ShotPlan::default();
    for &m in &s.multiples {
        let mut outputs = Outputs::new(frequency_hz);
        let description = match kind {
            VoltageKind::ResidualOver => {
                // tensione all'ingresso omopolare del relè e la stessa
                // tensione residua riportata al secondario dei TV di fase
                let at_relay = tr.residual_voltage_secondary(s.pickup, s.basis) * m;
                let on_phase_vts = at_relay * tr.residual_vt.value() / tr.vt.value();
                outputs.set_phase_voltages(displaced_phase_voltages(
                    tr.nominal_phase_voltage(),
                    on_phase_vts,
                ));
                outputs.voltages[3] = Phasor::new(at_relay, 180.0);
                format!("{m:.2} × soglia: 3V0 = {at_relay:.2} V")
            }
            _ => {
                let v = tr.voltage_secondary(s.pickup, s.basis) * m;
                let (phase, label) = match s.measurement {
                    VoltageMeasurement::PhaseToPhase => (v / 3f64.sqrt(), "concatenata"),
                    VoltageMeasurement::PhaseToNeutral => (v, "di fase"),
                };
                outputs.set_phase_voltages(three_phase(phase, 0.0));
                format!("{m:.2} × soglia: tensione {label} = {v:.2} V")
            }
        };
        let over = kind != VoltageKind::Under;
        plan.push(description, outputs, s.tolerances.threshold(m, over, s.delay_s));
    }
    plan
}

pub fn summary(kind: VoltageKind, s: &VoltageSettings) -> Vec<(String, String)> {
    let mut rows = vec![("Soglia".to_string(), format!("{} {}", s.pickup, basis_unit(s.basis, "V")))];
    if kind != VoltageKind::ResidualOver {
        let m = match s.measurement {
            VoltageMeasurement::PhaseToPhase => "concatenata",
            VoltageMeasurement::PhaseToNeutral => "di fase",
        };
        rows.push(("Tensione misurata".to_string(), m.to_string()));
    }
    rows.push(("Tempo".to_string(), format!("{} s", s.delay_s)));
    rows.extend(tolerance_rows(&s.tolerances, "tensione"));
    rows
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shot::Expected;

    #[test]
    fn undervoltage_trips_below_the_pickup() {
        let s = VoltageSettings::new(16000.0, 0.5, &[1.1, 0.9]);
        let p = plan(VoltageKind::Under, &s, &Transformers::default(), 50.0);
        assert_eq!(p.shots[0].expected, Expected::NoTrip);
        assert!(matches!(p.shots[1].expected, Expected::Trip { .. }));
        // 16 kV · 0.9 con TV 20000/100 = 72 V concatenati = 41.57 V di fase
        assert!((p.shots[1].outputs.voltages[0].magnitude - 72.0 / 3f64.sqrt()).abs() < 1e-9);
    }

    #[test]
    fn overvoltage_trips_above_the_pickup() {
        let s = VoltageSettings::new(24000.0, 1.0, &[0.9, 1.1]);
        let p = plan(VoltageKind::Over, &s, &Transformers::default(), 50.0);
        assert_eq!(p.shots[0].expected, Expected::NoTrip);
        assert!(matches!(p.shots[1].expected, Expected::Trip { .. }));
    }

    #[test]
    fn residual_voltage_is_the_sum_of_the_phase_voltages() {
        let mut s = VoltageSettings::new(10.0, 1.0, &[1.2]);
        s.basis = Basis::Secondary;
        let p = plan(VoltageKind::ResidualOver, &s, &Transformers::default(), 50.0);
        let v = p.shots[0].outputs.voltages;
        let sum = v[0].plus(v[1]).plus(v[2]);
        assert!((sum.magnitude - 12.0).abs() < 1e-9);
        assert!((sum.angle_deg.abs() - 180.0).abs() < 1e-6);
        assert!((v[3].magnitude - 12.0).abs() < 1e-9);
    }
}
