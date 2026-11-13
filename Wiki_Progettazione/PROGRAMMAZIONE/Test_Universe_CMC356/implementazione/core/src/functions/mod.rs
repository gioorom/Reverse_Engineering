//! Funzioni protettive e moduli di prova.

pub mod differential;
pub mod directional;
pub mod distance;
pub mod frequency;
pub mod overcurrent;
pub mod voltage;

use serde::{Deserialize, Serialize};

use crate::curves::{InverseCurve, TimeCharacteristic};
use crate::shot::{assess, overall, Measured, ShotPlan, Verdict};
use crate::transformers::{CtDirection, Transformers};

use differential::{DifferentialKind, DifferentialSettings};
use directional::{DirectionalKind, DirectionalSettings};
use distance::DistanceSettings;
use frequency::FrequencySettings;
use overcurrent::{OvercurrentKind, OvercurrentSettings};
use voltage::{VoltageKind, VoltageSettings};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AnsiFunction {
    F50,
    F51,
    F51N,
    F67,
    F67N,
    F46,
    F27,
    F59,
    F59N,
    F81,
    F21L,
    F87L,
    F87T,
    F87G,
}

impl AnsiFunction {
    pub const ALL: [AnsiFunction; 14] = [
        AnsiFunction::F50,
        AnsiFunction::F51,
        AnsiFunction::F51N,
        AnsiFunction::F67,
        AnsiFunction::F67N,
        AnsiFunction::F46,
        AnsiFunction::F27,
        AnsiFunction::F59,
        AnsiFunction::F59N,
        AnsiFunction::F81,
        AnsiFunction::F21L,
        AnsiFunction::F87L,
        AnsiFunction::F87T,
        AnsiFunction::F87G,
    ];

    pub fn code(self) -> &'static str {
        match self {
            AnsiFunction::F50 => "50",
            AnsiFunction::F51 => "51",
            AnsiFunction::F51N => "51N",
            AnsiFunction::F67 => "67",
            AnsiFunction::F67N => "67N",
            AnsiFunction::F46 => "46",
            AnsiFunction::F27 => "27",
            AnsiFunction::F59 => "59",
            AnsiFunction::F59N => "59N",
            AnsiFunction::F81 => "81",
            AnsiFunction::F21L => "21L",
            AnsiFunction::F87L => "87L",
            AnsiFunction::F87T => "87T",
            AnsiFunction::F87G => "87G",
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            AnsiFunction::F50 => "Massima corrente istantanea",
            AnsiFunction::F51 => "Massima corrente a tempo",
            AnsiFunction::F51N => "Massima corrente omopolare",
            AnsiFunction::F67 => "Massima corrente direzionale",
            AnsiFunction::F67N => "Direzionale di terra",
            AnsiFunction::F46 => "Sequenza inversa",
            AnsiFunction::F27 => "Minima tensione",
            AnsiFunction::F59 => "Massima tensione",
            AnsiFunction::F59N => "Massima tensione omopolare",
            AnsiFunction::F81 => "Frequenza",
            AnsiFunction::F21L => "Distanza di linea",
            AnsiFunction::F87L => "Differenziale di linea",
            AnsiFunction::F87T => "Differenziale di trasformatore",
            AnsiFunction::F87G => "Differenziale di generatore",
        }
    }

    fn default_settings(self) -> ModuleSettings {
        let definite = |delay_s| TimeCharacteristic::DefiniteTime { delay_s };
        match self {
            AnsiFunction::F50 => ModuleSettings::Overcurrent(OvercurrentSettings::new(
                600.0,
                definite(0.05),
                &[0.9, 1.1, 2.0],
            )),
            AnsiFunction::F51 => ModuleSettings::Overcurrent(OvercurrentSettings::new(
                250.0,
                TimeCharacteristic::Inverse {
                    curve: InverseCurve::IecNormalInverse,
                    multiplier: 0.1,
                },
                &[0.9, 1.5, 2.0, 5.0],
            )),
            AnsiFunction::F51N => ModuleSettings::Overcurrent(OvercurrentSettings::new(
                2.0,
                definite(0.3),
                &[0.9, 1.1, 2.0],
            )),
            AnsiFunction::F46 => ModuleSettings::Overcurrent(OvercurrentSettings::new(
                60.0,
                definite(1.0),
                &[0.9, 1.1, 2.0],
            )),
            AnsiFunction::F67 => ModuleSettings::Directional(DirectionalSettings::new(
                250.0,
                0.3,
                (-25.0, 145.0),
                30.0,
            )),
            AnsiFunction::F67N => ModuleSettings::Directional(DirectionalSettings::new(
                2.0,
                0.4,
                (60.0, 250.0),
                20.0,
            )),
            AnsiFunction::F27 => {
                ModuleSettings::Voltage(VoltageSettings::new(16000.0, 0.5, &[1.1, 0.9, 0.5]))
            }
            AnsiFunction::F59 => {
                ModuleSettings::Voltage(VoltageSettings::new(24000.0, 0.5, &[0.9, 1.1]))
            }
            AnsiFunction::F59N => {
                ModuleSettings::Voltage(VoltageSettings::new(1000.0, 1.0, &[0.9, 1.1, 2.0]))
            }
            AnsiFunction::F81 => ModuleSettings::Frequency(FrequencySettings::default()),
            AnsiFunction::F21L => ModuleSettings::Distance(DistanceSettings::default()),
            AnsiFunction::F87L | AnsiFunction::F87T | AnsiFunction::F87G => {
                ModuleSettings::Differential(DifferentialSettings::default())
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ModuleSettings {
    Overcurrent(OvercurrentSettings),
    Directional(DirectionalSettings),
    Voltage(VoltageSettings),
    Frequency(FrequencySettings),
    Distance(DistanceSettings),
    Differential(DifferentialSettings),
}

/// Modulo di prova di una funzione protettiva.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TestModule {
    pub function: AnsiFunction,
    /// La funzione è presente nel relè e va provata.
    pub enabled: bool,
    /// Usa i rapporti dei dati generali invece di quelli del modulo.
    pub use_project_transformers: bool,
    pub transformers: Transformers,
    pub settings: ModuleSettings,
    /// Esiti misurati, nell'ordine dei punti di prova.
    pub results: Vec<Option<Measured>>,
    pub notes: String,
}

impl TestModule {
    pub fn new(function: AnsiFunction, transformers: &Transformers) -> Self {
        TestModule {
            function,
            enabled: false,
            use_project_transformers: true,
            transformers: transformers.clone(),
            settings: function.default_settings(),
            results: Vec::new(),
            notes: String::new(),
        }
    }

    /// Punti di prova con i rapporti dati.
    pub fn plan(&self, tr: &Transformers, frequency_hz: f64) -> ShotPlan {
        use AnsiFunction::*;
        let mut plan = match (&self.settings, self.function) {
            (ModuleSettings::Overcurrent(s), F51N) => {
                overcurrent::plan(OvercurrentKind::Residual, s, tr, frequency_hz)
            }
            (ModuleSettings::Overcurrent(s), F46) => {
                overcurrent::plan(OvercurrentKind::NegativeSequence, s, tr, frequency_hz)
            }
            (ModuleSettings::Overcurrent(s), _) => {
                overcurrent::plan(OvercurrentKind::Phase, s, tr, frequency_hz)
            }
            (ModuleSettings::Directional(s), F67N) => {
                directional::plan(DirectionalKind::Residual, s, tr, frequency_hz)
            }
            (ModuleSettings::Directional(s), _) => {
                directional::plan(DirectionalKind::Phase, s, tr, frequency_hz)
            }
            (ModuleSettings::Voltage(s), _) => {
                voltage::plan(self.voltage_kind(), s, tr, frequency_hz)
            }
            (ModuleSettings::Frequency(s), _) => frequency::plan(s, tr),
            (ModuleSettings::Distance(s), _) => distance::plan(s, tr, frequency_hz),
            (ModuleSettings::Differential(s), _) => {
                differential::plan(self.differential_kind(), s, tr, frequency_hz)
            }
        };
        if tr.ct_direction == CtDirection::TowardBusbar {
            // TA rivolti verso le sbarre: le correnti della terna di fase si invertono
            for shot in &mut plan.shots {
                for i in &mut shot.outputs.currents[..3] {
                    *i = i.rotated(180.0);
                }
            }
        }
        plan.check_limits();
        plan
    }

    pub fn voltage_kind(&self) -> VoltageKind {
        match self.function {
            AnsiFunction::F27 => VoltageKind::Under,
            AnsiFunction::F59N => VoltageKind::ResidualOver,
            _ => VoltageKind::Over,
        }
    }

    pub fn differential_kind(&self) -> DifferentialKind {
        match self.function {
            AnsiFunction::F87T => DifferentialKind::Transformer,
            AnsiFunction::F87G => DifferentialKind::Generator,
            _ => DifferentialKind::Line,
        }
    }

    /// Tarature in forma di righe (voce, valore) per il report.
    pub fn summary(&self) -> Vec<(String, String)> {
        match &self.settings {
            ModuleSettings::Overcurrent(s) => overcurrent::summary(s),
            ModuleSettings::Directional(s) => directional::summary(s),
            ModuleSettings::Voltage(s) => voltage::summary(self.voltage_kind(), s),
            ModuleSettings::Frequency(s) => frequency::summary(s),
            ModuleSettings::Distance(s) => distance::summary(s),
            ModuleSettings::Differential(s) => differential::summary(self.differential_kind(), s),
        }
    }

    pub fn result(&self, index: usize) -> Option<&Measured> {
        self.results.get(index).and_then(Option::as_ref)
    }

    pub fn verdicts(&self, plan: &ShotPlan) -> Vec<Verdict> {
        plan.shots
            .iter()
            .enumerate()
            .map(|(i, shot)| assess(&shot.expected, self.result(i)))
            .collect()
    }

    pub fn verdict(&self, plan: &ShotPlan) -> Verdict {
        overall(self.verdicts(plan))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shot::Measured;

    #[test]
    fn every_function_has_a_plan_with_default_settings() {
        let tr = Transformers::default();
        for function in AnsiFunction::ALL {
            let module = TestModule::new(function, &tr);
            let plan = module.plan(&tr, 50.0);
            assert!(!plan.shots.is_empty(), "{} senza punti di prova", function.code());
            assert!(plan.warnings.is_empty(), "{}: {:?}", function.code(), plan.warnings);
            assert!(!module.summary().is_empty());
        }
    }

    #[test]
    fn ct_toward_busbar_reverses_the_phase_currents() {
        let mut tr = Transformers::default();
        let module = TestModule::new(AnsiFunction::F67, &tr);
        let line = module.plan(&tr, 50.0);
        tr.ct_direction = CtDirection::TowardBusbar;
        let busbar = module.plan(&tr, 50.0);
        let a = line.shots[0].outputs.currents[0];
        let b = busbar.shots[0].outputs.currents[0];
        assert!(a.plus(b).magnitude < 1e-9);
        assert_eq!(line.shots[0].outputs.voltages, busbar.shots[0].outputs.voltages);
    }

    #[test]
    fn module_verdict_follows_the_results() {
        let tr = Transformers::default();
        let mut module = TestModule::new(AnsiFunction::F50, &tr);
        let plan = module.plan(&tr, 50.0);
        assert_eq!(module.verdict(&plan), Verdict::NotTested);
        module.results = vec![
            Some(Measured::NoTrip),
            Some(Measured::Trip { time_s: 0.06 }),
            Some(Measured::Trip { time_s: 0.05 }),
        ];
        assert_eq!(module.verdict(&plan), Verdict::Passed);
        module.results[1] = Some(Measured::Trip { time_s: 0.5 });
        assert_eq!(module.verdict(&plan), Verdict::Failed);
    }
}
