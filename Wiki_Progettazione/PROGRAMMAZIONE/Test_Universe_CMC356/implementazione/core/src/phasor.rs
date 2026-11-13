//! Fasori: ampiezza efficace e angolo in gradi.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct Phasor {
    pub magnitude: f64,
    pub angle_deg: f64,
}

impl Phasor {
    pub const ZERO: Phasor = Phasor { magnitude: 0.0, angle_deg: 0.0 };

    /// Un'ampiezza negativa diventa positiva con l'angolo ruotato di 180°.
    pub fn new(magnitude: f64, angle_deg: f64) -> Self {
        let (magnitude, angle_deg) = if magnitude < 0.0 {
            (-magnitude, angle_deg + 180.0)
        } else {
            (magnitude, angle_deg)
        };
        Phasor { magnitude, angle_deg: normalize_angle(angle_deg) }
    }

    pub fn from_rect(re: f64, im: f64) -> Self {
        let magnitude = re.hypot(im);
        if magnitude < 1e-12 {
            return Phasor::ZERO;
        }
        Phasor::new(magnitude, im.atan2(re).to_degrees())
    }

    pub fn re(self) -> f64 {
        self.magnitude * self.angle_deg.to_radians().cos()
    }

    pub fn im(self) -> f64 {
        self.magnitude * self.angle_deg.to_radians().sin()
    }

    pub fn plus(self, other: Phasor) -> Phasor {
        Phasor::from_rect(self.re() + other.re(), self.im() + other.im())
    }

    pub fn rotated(self, deg: f64) -> Phasor {
        Phasor::new(self.magnitude, self.angle_deg + deg)
    }

    pub fn is_zero(self) -> bool {
        self.magnitude < 1e-9
    }
}

/// Riporta l'angolo nell'intervallo (-180°, 180°].
pub fn normalize_angle(angle_deg: f64) -> f64 {
    let mut a = angle_deg % 360.0;
    if a > 180.0 {
        a -= 360.0;
    } else if a <= -180.0 {
        a += 360.0;
    }
    a
}

/// Terna simmetrica diretta: L1, L2 in ritardo di 120°, L3 in anticipo di 120°.
pub fn three_phase(magnitude: f64, angle_l1_deg: f64) -> [Phasor; 3] {
    [
        Phasor::new(magnitude, angle_l1_deg),
        Phasor::new(magnitude, angle_l1_deg - 120.0),
        Phasor::new(magnitude, angle_l1_deg + 120.0),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn negative_magnitude_flips_the_angle() {
        let p = Phasor::new(-2.0, 30.0);
        assert_eq!(p.magnitude, 2.0);
        assert!((p.angle_deg + 150.0).abs() < 1e-9);
    }

    #[test]
    fn symmetrical_set_sums_to_zero() {
        let [a, b, c] = three_phase(57.7, 12.0);
        assert!(a.plus(b).plus(c).magnitude < 1e-9);
    }

    #[test]
    fn angle_is_normalised() {
        assert_eq!(normalize_angle(270.0), -90.0);
        assert_eq!(normalize_angle(-180.0), 180.0);
    }
}
