//! Distanza di linea (21L): verifica della portata e del tempo di ogni zona
//! lungo l'angolo di linea, a corrente di prova costante.

use serde::{Deserialize, Serialize};

use crate::functions::overcurrent::{basis_unit, tolerance_rows};
use crate::phasor::{three_phase, Phasor};
use crate::shot::{Expected, Outputs, ShotPlan, Tolerances};
use crate::transformers::{Basis, Transformers};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FaultLoop {
    L1E,
    L1L2,
    L1L2L3,
}

impl FaultLoop {
    pub const ALL: [FaultLoop; 3] = [FaultLoop::L1E, FaultLoop::L1L2, FaultLoop::L1L2L3];

    pub fn label(self) -> &'static str {
        match self {
            FaultLoop::L1E => "L1-E",
            FaultLoop::L1L2 => "L1-L2",
            FaultLoop::L1L2L3 => "L1-L2-L3",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Zone {
    pub name: String,
    /// Portata lungo l'angolo di linea, in ohm.
    pub reach_ohm: f64,
    pub delay_s: f64,
    /// Zona in avanti (verso la linea) o all'indietro.
    pub forward: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DistanceSettings {
    pub basis: Basis,
    pub line_angle_deg: f64,
    pub zones: Vec<Zone>,
    /// Fattore di compensazione di terra k0 = (Z0 − Z1) / (3 · Z1).
    pub k0_magnitude: f64,
    pub k0_angle_deg: f64,
    /// Corrente di prova in ampere secondari.
    pub test_current_a: f64,
    pub loops: Vec<FaultLoop>,
    /// Ogni portata è provata a (1 − margine) e (1 + margine).
    pub reach_margin_pct: f64,
    pub tolerances: Tolerances,
}

impl Default for DistanceSettings {
    fn default() -> Self {
        let zone = |name: &str, reach_ohm, delay_s| Zone {
            name: name.to_string(),
            reach_ohm,
            delay_s,
            forward: true,
        };
        DistanceSettings {
            basis: Basis::Primary,
            line_angle_deg: 75.0,
            zones: vec![zone("Z1", 8.0, 0.0), zone("Z2", 12.0, 0.4), zone("Z3", 20.0, 0.8)],
            k0_magnitude: 0.6,
            k0_angle_deg: 0.0,
            test_current_a: 2.0,
            loops: vec![FaultLoop::L1E, FaultLoop::L1L2, FaultLoop::L1L2L3],
            reach_margin_pct: 10.0,
            tolerances: Tolerances::default(),
        }
    }
}

/// Tensioni e correnti di un guasto con impedenza di sequenza diretta
/// `z_ohm` (secondari) all'angolo `angle_deg`. Restituisce anche la tensione
/// dell'anello di guasto, da confrontare con la nominale.
fn fault_outputs(
    s: &DistanceSettings,
    fault: FaultLoop,
    z_ohm: f64,
    angle_deg: f64,
    nominal: f64,
    frequency_hz: f64,
) -> (Outputs, f64) {
    let i = s.test_current_a;
    let mut o = Outputs::new(frequency_hz);
    let healthy = three_phase(nominal, 0.0);
    let loop_voltage = match fault {
        FaultLoop::L1L2L3 => {
            let v = i * z_ohm;
            o.set_phase_voltages(three_phase(v, 0.0));
            o.set_phase_currents(three_phase(i, -angle_deg));
            v
        }
        FaultLoop::L1L2 => {
            // V12 = 2 · Z · I, diretta come nella rete sana (30°); L1 e L2
            // si avvicinano al punto medio, L3 resta sana
            let v12 = 2.0 * i * z_ohm;
            let middle = Phasor::new(nominal / 2.0, -60.0);
            let half = Phasor::new(v12 / 2.0, 30.0);
            o.set_phase_voltages([middle.plus(half), middle.plus(half.rotated(180.0)), healthy[2]]);
            let i1 = Phasor::new(i, 30.0 - angle_deg);
            o.set_phase_currents([i1, i1.rotated(180.0), Phasor::ZERO]);
            v12 / 3f64.sqrt()
        }
        FaultLoop::L1E => {
            // V1 = Z · (1 + k0) · I
            let k = Phasor::new(1.0, 0.0).plus(Phasor::new(s.k0_magnitude, s.k0_angle_deg));
            let v = i * z_ohm * k.magnitude;
            o.set_phase_voltages([Phasor::new(v, 0.0), healthy[1], healthy[2]]);
            o.currents[0] = Phasor::new(i, -(angle_deg + k.angle_deg));
            v
        }
    };
    (o, loop_voltage)
}

/// Esito atteso a `z` ohm tra le zone ordinate per portata crescente:
/// interviene la prima zona che contiene il punto.
fn expected_at(z: f64, zones: &[(f64, f64)], tol: &Tolerances) -> Option<Expected> {
    let q = tol.quantity();
    for &(reach, delay_s) in zones {
        if z <= reach * (1.0 - q) {
            return Some(tol.trip_at(delay_s));
        }
        if z < reach * (1.0 + q) {
            return None;
        }
    }
    Some(Expected::NoTrip)
}

pub fn plan(s: &DistanceSettings, tr: &Transformers, frequency_hz: f64) -> ShotPlan {
    let mut plan = ShotPlan::default();
    let nominal = tr.nominal_phase_voltage();
    let margin = s.reach_margin_pct / 100.0;
    for &fault in &s.loops {
        for forward in [true, false] {
            let mut zones: Vec<(&Zone, f64)> = s
                .zones
                .iter()
                .filter(|z| z.forward == forward)
                .map(|z| (z, tr.impedance_secondary(z.reach_ohm, s.basis)))
                .collect();
            zones.sort_by(|a, b| a.1.total_cmp(&b.1));
            let reaches: Vec<(f64, f64)> = zones.iter().map(|(z, r)| (*r, z.delay_s)).collect();
            let angle = if forward { s.line_angle_deg } else { s.line_angle_deg + 180.0 };
            for (zone, reach) in &zones {
                for (factor, side) in [(1.0 - margin, "dentro"), (1.0 + margin, "fuori")] {
                    let z = reach * factor;
                    let (outputs, loop_voltage) =
                        fault_outputs(s, fault, z, angle, nominal, frequency_hz);
                    let description = format!(
                        "{} {}: {side}, {:.0} % della portata = {z:.3} ohm secondari",
                        fault.label(),
                        zone.name,
                        factor * 100.0
                    );
                    if loop_voltage > nominal {
                        plan.warn(format!(
                            "{description}: tensione di guasto oltre la nominale, ridurre la corrente di prova"
                        ));
                    }
                    plan.push(description, outputs, expected_at(z, &reaches, &s.tolerances));
                }
            }
        }
    }
    plan
}

pub fn summary(s: &DistanceSettings) -> Vec<(String, String)> {
    let unit = basis_unit(s.basis, "ohm");
    let mut rows = vec![("Angolo di linea".to_string(), format!("{}°", s.line_angle_deg))];
    for z in &s.zones {
        let direction = if z.forward { "avanti" } else { "indietro" };
        rows.push((
            format!("Zona {}", z.name),
            format!("{} {unit}, {} s, {direction}", z.reach_ohm, z.delay_s),
        ));
    }
    rows.push(("Compensazione di terra k0".to_string(), format!("{} / {}°", s.k0_magnitude, s.k0_angle_deg)));
    rows.push(("Corrente di prova".to_string(), format!("{} A secondari", s.test_current_a)));
    rows.push(("Margine sulla portata".to_string(), format!("{} %", s.reach_margin_pct)));
    rows.extend(tolerance_rows(&s.tolerances, "impedenza"));
    rows
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Rapporto tra due fasori: (modulo, angolo).
    fn ratio(v: Phasor, i: Phasor) -> (f64, f64) {
        (v.magnitude / i.magnitude, crate::phasor::normalize_angle(v.angle_deg - i.angle_deg))
    }

    fn settings() -> DistanceSettings {
        DistanceSettings { basis: Basis::Secondary, ..DistanceSettings::default() }
    }

    #[test]
    fn three_phase_fault_shows_the_set_impedance() {
        let s = settings();
        let (o, _) = fault_outputs(&s, FaultLoop::L1L2L3, 3.0, 75.0, 57.7, 50.0);
        for phase in 0..3 {
            let (z, angle) = ratio(o.voltages[phase], o.currents[phase]);
            assert!((z - 3.0).abs() < 1e-9);
            assert!((angle - 75.0).abs() < 1e-9);
        }
    }

    #[test]
    fn two_phase_fault_shows_the_set_impedance_in_the_loop() {
        let s = settings();
        let (o, _) = fault_outputs(&s, FaultLoop::L1L2, 3.0, 75.0, 57.7, 50.0);
        let v12 = o.voltages[0].plus(o.voltages[1].rotated(180.0));
        let i12 = o.currents[0].plus(o.currents[1].rotated(180.0));
        let (z, angle) = ratio(v12, i12);
        assert!((z - 3.0).abs() < 1e-9);
        assert!((angle - 75.0).abs() < 1e-6);
        // la terna resta senza componente omopolare
        let sum = o.voltages[0].plus(o.voltages[1]).plus(o.voltages[2]);
        assert!(sum.magnitude < 1e-9);
    }

    #[test]
    fn earth_fault_includes_the_earth_compensation() {
        let mut s = settings();
        s.k0_magnitude = 0.8;
        s.k0_angle_deg = -10.0;
        let (o, _) = fault_outputs(&s, FaultLoop::L1E, 3.0, 75.0, 57.7, 50.0);
        // il relè calcola Z = V1 / (I1 · (1 + k0))
        let k = Phasor::new(1.0, 0.0).plus(Phasor::new(0.8, -10.0));
        let (z, angle) = ratio(o.voltages[0], o.currents[0]);
        assert!((z / k.magnitude - 3.0).abs() < 1e-9);
        assert!((angle - k.angle_deg - 75.0).abs() < 1e-9);
    }

    #[test]
    fn outside_a_zone_the_next_zone_trips() {
        let mut s = settings();
        s.loops = vec![FaultLoop::L1L2L3];
        let p = plan(&s, &Transformers::default(), 50.0);
        assert_eq!(p.shots.len(), 6);
        let nominal = |e: &Expected| match *e {
            Expected::Trip { nominal_s, .. } => Some(nominal_s),
            Expected::NoTrip => None,
        };
        let times: Vec<Option<f64>> = p.shots.iter().map(|s| nominal(&s.expected)).collect();
        // Z1 dentro e fuori, Z2 dentro e fuori, Z3 dentro e fuori
        assert_eq!(times, vec![Some(0.0), Some(0.4), Some(0.4), Some(0.8), Some(0.8), None]);
    }

    #[test]
    fn primary_reach_is_converted_to_secondary_ohms() {
        let mut s = DistanceSettings::default();
        s.loops = vec![FaultLoop::L1L2L3];
        let p = plan(&s, &Transformers::default(), 50.0);
        // Z1 = 8 ohm primari · 0.3 = 2.4 ohm secondari; al 90 % con 2 A: 4.32 V
        assert!((p.shots[0].outputs.voltages[0].magnitude - 4.32).abs() < 1e-9);
    }

    #[test]
    fn reverse_zone_is_tested_behind_the_relay() {
        let mut s = settings();
        s.loops = vec![FaultLoop::L1L2L3];
        s.zones = vec![Zone { name: "Z4".into(), reach_ohm: 2.0, delay_s: 1.0, forward: false }];
        let p = plan(&s, &Transformers::default(), 50.0);
        let o = &p.shots[0].outputs;
        let (_, angle) = ratio(o.voltages[0], o.currents[0]);
        assert!((angle + 105.0).abs() < 1e-9);
    }

    #[test]
    fn fault_voltage_above_nominal_is_reported() {
        let mut s = settings();
        s.loops = vec![FaultLoop::L1L2L3];
        s.test_current_a = 20.0;
        let p = plan(&s, &Transformers::default(), 50.0);
        assert!(!p.warnings.is_empty());
    }
}
