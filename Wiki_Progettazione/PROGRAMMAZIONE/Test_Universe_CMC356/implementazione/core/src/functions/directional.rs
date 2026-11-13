//! Massima corrente direzionale di fase (67) e di terra (67N).
//!
//! Il settore di intervento è espresso come ritardo della corrente rispetto
//! alla tensione di riferimento: la tensione di fase per la 67, la tensione
//! residua 3V0 per la 67N. Il segno della tensione residua cambia da un
//! costruttore all'altro: va verificato sul manuale del relè.

use serde::{Deserialize, Serialize};

use crate::functions::overcurrent::{basis_unit, tolerance_rows};
use crate::functions::voltage::displaced_phase_voltages;
use crate::phasor::{three_phase, Phasor};
use crate::shot::{Expected, Outputs, ShotPlan, Tolerances};
use crate::transformers::{Basis, Transformers};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DirectionalKind {
    Phase,
    Residual,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DirectionalSettings {
    pub basis: Basis,
    /// Soglia di corrente in ampere.
    pub pickup: f64,
    pub delay_s: f64,
    /// Settore di intervento, dal primo al secondo angolo a ritardo crescente.
    pub sector_from_deg: f64,
    pub sector_to_deg: f64,
    /// Distanza dai limiti del settore a cui provare.
    pub angle_margin_deg: f64,
    /// Multiplo della soglia usato nelle prove di angolo.
    pub test_multiple: f64,
    /// Multipli della soglia provati al centro del settore.
    pub pickup_multiples: Vec<f64>,
    /// Tensione di riferimento durante la prova, in volt secondari.
    pub test_voltage: f64,
    pub tolerances: Tolerances,
}

impl DirectionalSettings {
    pub fn new(pickup: f64, delay_s: f64, sector: (f64, f64), test_voltage: f64) -> Self {
        DirectionalSettings {
            basis: Basis::Primary,
            pickup,
            delay_s,
            sector_from_deg: sector.0,
            sector_to_deg: sector.1,
            angle_margin_deg: 5.0,
            test_multiple: 2.0,
            pickup_multiples: vec![0.9, 1.1],
            test_voltage,
            tolerances: Tolerances::default(),
        }
    }

    /// Ampiezza del settore in gradi (360 se i due angoli coincidono).
    pub fn sector_width(&self) -> f64 {
        let w = (self.sector_to_deg - self.sector_from_deg).rem_euclid(360.0);
        if w == 0.0 {
            360.0
        } else {
            w
        }
    }

    pub fn sector_center(&self) -> f64 {
        self.sector_from_deg + self.sector_width() / 2.0
    }
}

fn outputs(
    kind: DirectionalKind,
    s: &DirectionalSettings,
    tr: &Transformers,
    current: f64,
    lag_deg: f64,
    frequency_hz: f64,
) -> Outputs {
    let mut o = Outputs::new(frequency_hz);
    match kind {
        DirectionalKind::Phase => {
            o.set_phase_voltages(three_phase(s.test_voltage, 0.0));
            o.set_phase_currents(three_phase(current, -lag_deg));
        }
        DirectionalKind::Residual => {
            let on_phase_vts = s.test_voltage * tr.residual_vt.value() / tr.vt.value();
            o.set_phase_voltages(displaced_phase_voltages(tr.nominal_phase_voltage(), on_phase_vts));
            // la tensione residua è a 180°: la corrente la segue con il ritardo dato
            o.voltages[3] = Phasor::new(s.test_voltage, 180.0);
            let i = Phasor::new(current, 180.0 - lag_deg);
            if tr.has_residual_ct {
                o.currents[3] = i;
            } else {
                o.currents[0] = i;
            }
        }
    }
    o
}

pub fn plan(
    kind: DirectionalKind,
    s: &DirectionalSettings,
    tr: &Transformers,
    frequency_hz: f64,
) -> ShotPlan {
    let mut plan = ShotPlan::default();
    let pickup = match kind {
        DirectionalKind::Phase => tr.phase_current_secondary(s.pickup, s.basis),
        DirectionalKind::Residual => tr.residual_current_secondary(s.pickup, s.basis),
    };
    let center = s.sector_center();
    for &m in &s.pickup_multiples {
        let i = pickup * m;
        plan.push(
            format!("Soglia al centro del settore ({center:.0}°): {m:.2} × soglia = {i:.3} A"),
            outputs(kind, s, tr, i, center, frequency_hz),
            s.tolerances.threshold(m, true, s.delay_s),
        );
    }

    let width = s.sector_width();
    if width >= 360.0 {
        return plan;
    }
    let margin = s.angle_margin_deg;
    let i = pickup * s.test_multiple;
    let trip = s.tolerances.trip_at(s.delay_s);
    let angle_shot = |plan: &mut ShotPlan, lag: f64, what: &str, expected: Expected| {
        plan.push(
            format!("Angolo {lag:.0}°: {what}"),
            outputs(kind, s, tr, i, lag, frequency_hz),
            Some(expected),
        );
    };
    if margin > 0.0 && margin < width / 2.0 && margin < (360.0 - width) / 2.0 {
        angle_shot(&mut plan, s.sector_from_deg + margin, "dentro il settore, primo limite", trip);
        angle_shot(&mut plan, s.sector_from_deg - margin, "fuori dal settore, primo limite", Expected::NoTrip);
        angle_shot(&mut plan, s.sector_to_deg - margin, "dentro il settore, secondo limite", trip);
        angle_shot(&mut plan, s.sector_to_deg + margin, "fuori dal settore, secondo limite", Expected::NoTrip);
    } else {
        plan.warn("Margine angolare non compatibile con l'ampiezza del settore: limiti non provati");
    }
    angle_shot(&mut plan, center + 180.0, "direzione opposta", Expected::NoTrip);
    plan
}

pub fn summary(s: &DirectionalSettings) -> Vec<(String, String)> {
    let mut rows = vec![
        ("Soglia".to_string(), format!("{} {}", s.pickup, basis_unit(s.basis, "A"))),
        ("Tempo".to_string(), format!("{} s", s.delay_s)),
        (
            "Settore di intervento".to_string(),
            format!("da {}° a {}° (ritardo della corrente)", s.sector_from_deg, s.sector_to_deg),
        ),
        ("Tensione di prova".to_string(), format!("{} V secondari", s.test_voltage)),
        ("Corrente nelle prove di angolo".to_string(), format!("{} × soglia", s.test_multiple)),
    ];
    rows.extend(tolerance_rows(&s.tolerances, "corrente"));
    rows
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::phasor::normalize_angle;

    fn lag(o: &Outputs, v: usize, i: usize) -> f64 {
        normalize_angle(o.voltages[v].angle_deg - o.currents[i].angle_deg)
    }

    #[test]
    fn sector_geometry() {
        let s = DirectionalSettings::new(2.0, 0.4, (60.0, 250.0), 20.0);
        assert_eq!(s.sector_width(), 190.0);
        assert_eq!(s.sector_center(), 155.0);
        let wrapped = DirectionalSettings::new(2.0, 0.4, (300.0, 60.0), 20.0);
        assert_eq!(wrapped.sector_width(), 120.0);
    }

    #[test]
    fn phase_current_lags_its_voltage_by_the_test_angle() {
        let s = DirectionalSettings::new(250.0, 0.3, (-25.0, 145.0), 30.0);
        let p = plan(DirectionalKind::Phase, &s, &Transformers::default(), 50.0);
        // prove di soglia al centro (60°), poi 4 limiti e la direzione opposta
        assert_eq!(p.shots.len(), 7);
        for phase in 0..3 {
            assert!((lag(&p.shots[0].outputs, phase, phase) - 60.0).abs() < 1e-9);
        }
        assert!((lag(&p.shots[2].outputs, 0, 0) + 20.0).abs() < 1e-9);
        assert!(matches!(p.shots[2].expected, Expected::Trip { .. }));
        assert!((lag(&p.shots[3].outputs, 0, 0) + 30.0).abs() < 1e-9);
        assert_eq!(p.shots[3].expected, Expected::NoTrip);
        assert!((lag(&p.shots[6].outputs, 0, 0) + 120.0).abs() < 1e-9);
        assert_eq!(p.shots[6].expected, Expected::NoTrip);
    }

    #[test]
    fn residual_current_lags_the_residual_voltage() {
        let s = DirectionalSettings::new(2.0, 0.4, (60.0, 250.0), 20.0);
        let p = plan(DirectionalKind::Residual, &s, &Transformers::default(), 50.0);
        let o = &p.shots[0].outputs;
        assert!((lag(o, 3, 0) - 155.0).abs() < 1e-9);
        let sum = o.voltages[0].plus(o.voltages[1]).plus(o.voltages[2]);
        assert!((sum.magnitude - 20.0).abs() < 1e-9);
    }

    #[test]
    fn margin_wider_than_the_sector_is_reported() {
        let mut s = DirectionalSettings::new(2.0, 0.4, (0.0, 8.0), 20.0);
        s.angle_margin_deg = 5.0;
        let p = plan(DirectionalKind::Residual, &s, &Transformers::default(), 50.0);
        assert_eq!(p.warnings.len(), 1);
        assert_eq!(p.shots.len(), 3);
    }
}
