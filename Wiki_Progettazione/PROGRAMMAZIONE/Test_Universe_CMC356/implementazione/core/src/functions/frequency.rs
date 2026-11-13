//! Frequenza (81): soglie di minima e di massima frequenza.

use serde::{Deserialize, Serialize};

use crate::phasor::three_phase;
use crate::shot::{Expected, Outputs, ShotPlan, Tolerances};
use crate::transformers::Transformers;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FrequencyStageKind {
    Under,
    Over,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FrequencyStage {
    pub kind: FrequencyStageKind,
    pub pickup_hz: f64,
    pub delay_s: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FrequencySettings {
    pub stages: Vec<FrequencyStage>,
    /// Scostamento dalla soglia a cui provare, da una parte e dall'altra.
    pub test_offset_hz: f64,
    /// Si usa solo la tolleranza sul tempo.
    pub tolerances: Tolerances,
}

impl Default for FrequencySettings {
    fn default() -> Self {
        FrequencySettings {
            stages: vec![
                FrequencyStage { kind: FrequencyStageKind::Under, pickup_hz: 47.5, delay_s: 4.0 },
                FrequencyStage { kind: FrequencyStageKind::Over, pickup_hz: 51.5, delay_s: 1.0 },
            ],
            test_offset_hz: 0.05,
            tolerances: Tolerances::default(),
        }
    }
}

pub fn plan(s: &FrequencySettings, tr: &Transformers) -> ShotPlan {
    let mut plan = ShotPlan::default();
    let voltages = three_phase(tr.nominal_phase_voltage(), 0.0);
    for stage in &s.stages {
        let (name, toward_trip) = match stage.kind {
            FrequencyStageKind::Under => ("f<", -1.0),
            FrequencyStageKind::Over => ("f>", 1.0),
        };
        for (sign, trips) in [(-toward_trip, false), (toward_trip, true)] {
            let f = stage.pickup_hz + sign * s.test_offset_hz;
            let mut outputs = Outputs::new(f);
            outputs.set_phase_voltages(voltages);
            let expected =
                if trips { s.tolerances.trip_at(stage.delay_s) } else { Expected::NoTrip };
            plan.push(
                format!("{name} {:.2} Hz: prova a {f:.3} Hz", stage.pickup_hz),
                outputs,
                Some(expected),
            );
        }
    }
    plan
}

pub fn summary(s: &FrequencySettings) -> Vec<(String, String)> {
    let mut rows: Vec<(String, String)> = s
        .stages
        .iter()
        .map(|stage| {
            let name = match stage.kind {
                FrequencyStageKind::Under => "Soglia f<",
                FrequencyStageKind::Over => "Soglia f>",
            };
            (name.to_string(), format!("{} Hz, {} s", stage.pickup_hz, stage.delay_s))
        })
        .collect();
    rows.push(("Scostamento di prova".to_string(), format!("{} Hz", s.test_offset_hz)));
    rows.push((
        "Tolleranza sul tempo".to_string(),
        format!("{} % (minimo {} ms)", s.tolerances.time_pct, s.tolerances.time_abs_s * 1000.0),
    ));
    rows
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_stage_is_tested_on_both_sides_of_the_pickup() {
        let p = plan(&FrequencySettings::default(), &Transformers::default());
        assert_eq!(p.shots.len(), 4);
        // f< 47.5 Hz: sopra non interviene, sotto interviene
        assert!((p.shots[0].outputs.frequency_hz - 47.55).abs() < 1e-9);
        assert_eq!(p.shots[0].expected, Expected::NoTrip);
        assert!((p.shots[1].outputs.frequency_hz - 47.45).abs() < 1e-9);
        assert!(matches!(p.shots[1].expected, Expected::Trip { .. }));
        // f> 51.5 Hz: sotto non interviene, sopra interviene
        assert!((p.shots[2].outputs.frequency_hz - 51.45).abs() < 1e-9);
        assert_eq!(p.shots[2].expected, Expected::NoTrip);
        assert!((p.shots[3].outputs.frequency_hz - 51.55).abs() < 1e-9);
    }

    #[test]
    fn nominal_voltage_is_applied() {
        let p = plan(&FrequencySettings::default(), &Transformers::default());
        assert!((p.shots[0].outputs.voltages[1].magnitude - 100.0 / 3f64.sqrt()).abs() < 1e-9);
    }
}
