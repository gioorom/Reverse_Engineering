//! Caratteristiche di intervento a tempo definito e a tempo inverso
//! (IEC 60255-151 e IEEE C37.112).

use serde::{Deserialize, Serialize};

use crate::shot::{Expected, Tolerances};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum InverseCurve {
    IecNormalInverse,
    IecVeryInverse,
    IecExtremelyInverse,
    IecLongTimeInverse,
    IeeeModeratelyInverse,
    IeeeVeryInverse,
    IeeeExtremelyInverse,
}

impl InverseCurve {
    pub const ALL: [InverseCurve; 7] = [
        InverseCurve::IecNormalInverse,
        InverseCurve::IecVeryInverse,
        InverseCurve::IecExtremelyInverse,
        InverseCurve::IecLongTimeInverse,
        InverseCurve::IeeeModeratelyInverse,
        InverseCurve::IeeeVeryInverse,
        InverseCurve::IeeeExtremelyInverse,
    ];

    pub fn label(self) -> &'static str {
        match self {
            InverseCurve::IecNormalInverse => "IEC normalmente inversa (NI)",
            InverseCurve::IecVeryInverse => "IEC molto inversa (VI)",
            InverseCurve::IecExtremelyInverse => "IEC estremamente inversa (EI)",
            InverseCurve::IecLongTimeInverse => "IEC inversa a tempo lungo (LTI)",
            InverseCurve::IeeeModeratelyInverse => "IEEE moderatamente inversa",
            InverseCurve::IeeeVeryInverse => "IEEE molto inversa",
            InverseCurve::IeeeExtremelyInverse => "IEEE estremamente inversa",
        }
    }

    /// Costanti (k, alfa, c) di t = moltiplicatore · (k / (M^alfa − 1) + c).
    fn constants(self) -> (f64, f64, f64) {
        match self {
            InverseCurve::IecNormalInverse => (0.14, 0.02, 0.0),
            InverseCurve::IecVeryInverse => (13.5, 1.0, 0.0),
            InverseCurve::IecExtremelyInverse => (80.0, 2.0, 0.0),
            InverseCurve::IecLongTimeInverse => (120.0, 1.0, 0.0),
            InverseCurve::IeeeModeratelyInverse => (0.0515, 0.02, 0.114),
            InverseCurve::IeeeVeryInverse => (19.61, 2.0, 0.491),
            InverseCurve::IeeeExtremelyInverse => (28.2, 2.0, 0.1217),
        }
    }

    /// Tempo di intervento con moltiplicatore 1 al multiplo `m` della soglia.
    fn time(self, m: f64) -> f64 {
        let (k, alpha, c) = self.constants();
        k / (m.powf(alpha) - 1.0) + c
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum TimeCharacteristic {
    DefiniteTime { delay_s: f64 },
    /// `multiplier` è il TMS delle curve IEC o il time dial delle curve IEEE.
    Inverse { curve: InverseCurve, multiplier: f64 },
}

impl TimeCharacteristic {
    /// Tempo di intervento nominale al multiplo `m` della soglia.
    pub fn operate_time(&self, m: f64) -> Option<f64> {
        if m <= 1.0 {
            return None;
        }
        Some(match *self {
            TimeCharacteristic::DefiniteTime { delay_s } => delay_s,
            TimeCharacteristic::Inverse { curve, multiplier } => multiplier * curve.time(m),
        })
    }

    /// Esito atteso al multiplo `m` della soglia. Per le curve inverse la
    /// finestra di tempo comprende l'effetto della tolleranza sulla corrente.
    /// `None` se `m` cade nella banda di tolleranza della soglia.
    pub fn expected(&self, m: f64, tol: &Tolerances) -> Option<Expected> {
        let q = tol.quantity();
        if m <= 1.0 - q {
            return Some(Expected::NoTrip);
        }
        if m < 1.0 + q {
            return None;
        }
        match *self {
            TimeCharacteristic::DefiniteTime { delay_s } => Some(tol.trip_at(delay_s)),
            TimeCharacteristic::Inverse { .. } => {
                let nominal_s = self.operate_time(m)?;
                let fastest = self.operate_time(m * (1.0 + q))?;
                // al limite inferiore della tolleranza la curva può non
                // intervenire: nessun limite superiore al tempo
                let slowest = self.operate_time(m * (1.0 - q));
                Some(Expected::Trip {
                    nominal_s,
                    min_s: (fastest - tol.time_margin(fastest)).max(0.0),
                    max_s: slowest.map_or(f64::INFINITY, |t| t + tol.time_margin(t)),
                })
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inverse(curve: InverseCurve, multiplier: f64) -> TimeCharacteristic {
        TimeCharacteristic::Inverse { curve, multiplier }
    }

    #[test]
    fn iec_curves_match_the_published_values() {
        // valori tabulati a 2 e 10 volte la soglia, TMS = 1
        let ni = inverse(InverseCurve::IecNormalInverse, 1.0);
        assert!((ni.operate_time(2.0).unwrap() - 10.029).abs() < 1e-3);
        assert!((ni.operate_time(10.0).unwrap() - 2.971).abs() < 1e-3);
        let vi = inverse(InverseCurve::IecVeryInverse, 1.0);
        assert!((vi.operate_time(2.0).unwrap() - 13.5).abs() < 1e-9);
        assert!((vi.operate_time(10.0).unwrap() - 1.5).abs() < 1e-9);
        let ei = inverse(InverseCurve::IecExtremelyInverse, 1.0);
        assert!((ei.operate_time(2.0).unwrap() - 26.667).abs() < 1e-3);
        let lti = inverse(InverseCurve::IecLongTimeInverse, 1.0);
        assert!((lti.operate_time(2.0).unwrap() - 120.0).abs() < 1e-9);
    }

    #[test]
    fn ieee_curves_match_the_standard_equation() {
        let vi = inverse(InverseCurve::IeeeVeryInverse, 1.0);
        assert!((vi.operate_time(2.0).unwrap() - (19.61 / 3.0 + 0.491)).abs() < 1e-9);
        let mi = inverse(InverseCurve::IeeeModeratelyInverse, 2.0);
        let expected = 2.0 * (0.0515 / (5f64.powf(0.02) - 1.0) + 0.114);
        assert!((mi.operate_time(5.0).unwrap() - expected).abs() < 1e-9);
    }

    #[test]
    fn multiplier_scales_the_time() {
        let a = inverse(InverseCurve::IecNormalInverse, 1.0).operate_time(3.0).unwrap();
        let b = inverse(InverseCurve::IecNormalInverse, 0.2).operate_time(3.0).unwrap();
        assert!((b - 0.2 * a).abs() < 1e-12);
    }

    #[test]
    fn inverse_window_includes_the_current_tolerance() {
        let tol = Tolerances::default();
        let c = inverse(InverseCurve::IecVeryInverse, 1.0);
        let Some(Expected::Trip { nominal_s, min_s, max_s }) = c.expected(2.0, &tol) else {
            panic!("atteso un intervento");
        };
        assert!((nominal_s - 13.5).abs() < 1e-9);
        // 13.5/(2.1-1) = 12.27 s meno il 5 %; 13.5/(1.9-1) = 15 s più il 5 %
        assert!((min_s - 12.2727 * 0.95).abs() < 1e-3);
        assert!((max_s - 15.0 * 1.05).abs() < 1e-9);
    }

    #[test]
    fn below_the_pickup_no_trip_is_expected() {
        let tol = Tolerances::default();
        let c = TimeCharacteristic::DefiniteTime { delay_s: 0.3 };
        assert_eq!(c.expected(0.9, &tol), Some(Expected::NoTrip));
        assert_eq!(c.expected(1.0, &tol), None);
        assert!(matches!(c.expected(1.1, &tol), Some(Expected::Trip { .. })));
        assert_eq!(c.operate_time(1.0), None);
    }
}
