//! Trasformatori di misura: rapporti di TA, TO e TV e conversione delle
//! tarature dai valori primari ai valori secondari visti dal relè.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Ratio {
    pub primary: f64,
    pub secondary: f64,
}

impl Ratio {
    pub fn new(primary: f64, secondary: f64) -> Self {
        Ratio { primary, secondary }
    }

    /// Primario diviso secondario.
    pub fn value(self) -> f64 {
        self.primary / self.secondary
    }
}

/// Verso del TA: dove guarda il lato P1 (o il centro stella dei secondari).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CtDirection {
    TowardLine,
    TowardBusbar,
}

/// Come sono espresse le tarature inserite.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Basis {
    Primary,
    Secondary,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Transformers {
    /// TA di fase (A / A).
    pub ct: Ratio,
    pub ct_direction: CtDirection,
    /// TO, toroide omopolare (A / A), usato solo se `has_residual_ct`.
    pub has_residual_ct: bool,
    pub residual_ct: Ratio,
    /// TV di fase (V concatenati / V concatenati).
    pub vt: Ratio,
    /// TV omopolare: tensione residua 3V0 primaria / tensione all'ingresso
    /// del relè.
    pub residual_vt: Ratio,
}

impl Default for Transformers {
    fn default() -> Self {
        Transformers {
            ct: Ratio::new(300.0, 5.0),
            ct_direction: CtDirection::TowardLine,
            has_residual_ct: false,
            residual_ct: Ratio::new(100.0, 1.0),
            vt: Ratio::new(20000.0, 100.0),
            residual_vt: Ratio::new(20000.0, 100.0),
        }
    }
}

impl Transformers {
    pub fn phase_current_secondary(&self, value: f64, basis: Basis) -> f64 {
        match basis {
            Basis::Primary => value / self.ct.value(),
            Basis::Secondary => value,
        }
    }

    /// La corrente residua passa dal TO se c'è, altrimenti dai TA di fase.
    pub fn residual_current_secondary(&self, value: f64, basis: Basis) -> f64 {
        match basis {
            Basis::Primary if self.has_residual_ct => value / self.residual_ct.value(),
            Basis::Primary => value / self.ct.value(),
            Basis::Secondary => value,
        }
    }

    pub fn voltage_secondary(&self, value: f64, basis: Basis) -> f64 {
        match basis {
            Basis::Primary => value / self.vt.value(),
            Basis::Secondary => value,
        }
    }

    pub fn residual_voltage_secondary(&self, value: f64, basis: Basis) -> f64 {
        match basis {
            Basis::Primary => value / self.residual_vt.value(),
            Basis::Secondary => value,
        }
    }

    /// Un'impedenza primaria vista dal relè vale Z · (rapporto TA / rapporto TV).
    pub fn impedance_secondary(&self, value: f64, basis: Basis) -> f64 {
        match basis {
            Basis::Primary => value * self.ct.value() / self.vt.value(),
            Basis::Secondary => value,
        }
    }

    /// Tensione nominale di fase al secondario dei TV.
    pub fn nominal_phase_voltage(&self) -> f64 {
        self.vt.secondary / 3f64.sqrt()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn primary_settings_are_scaled_by_the_ratio() {
        let t = Transformers::default();
        assert!((t.phase_current_secondary(600.0, Basis::Primary) - 10.0).abs() < 1e-9);
        assert!((t.voltage_secondary(20000.0, Basis::Primary) - 100.0).abs() < 1e-9);
        assert_eq!(t.phase_current_secondary(2.5, Basis::Secondary), 2.5);
    }

    #[test]
    fn residual_current_uses_the_core_balance_ct_when_present() {
        let mut t = Transformers::default();
        assert!((t.residual_current_secondary(3.0, Basis::Primary) - 0.05).abs() < 1e-9);
        t.has_residual_ct = true;
        assert!((t.residual_current_secondary(3.0, Basis::Primary) - 0.03).abs() < 1e-9);
    }

    #[test]
    fn primary_impedance_is_seen_through_both_ratios() {
        let t = Transformers::default();
        // 10 ohm primari · (60 / 200) = 3 ohm secondari
        assert!((t.impedance_secondary(10.0, Basis::Primary) - 3.0).abs() < 1e-9);
    }
}
