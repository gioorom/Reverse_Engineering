//! Progetto di prova: dati generali, trasformatori di misura e moduli.

use serde::{Deserialize, Serialize};

use crate::functions::{AnsiFunction, TestModule};
use crate::shot::{overall, ShotPlan, Verdict};
use crate::transformers::Transformers;

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TestInfo {
    pub relay_name: String,
    /// Montante provato.
    pub feeder: String,
    pub plant: String,
    pub location: String,
    pub engineer: String,
    pub date: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Project {
    pub info: TestInfo,
    pub frequency_hz: f64,
    pub transformers: Transformers,
    /// Un modulo per ogni funzione, anche se non presente nel relè.
    pub modules: Vec<TestModule>,
}

impl Default for Project {
    fn default() -> Self {
        let transformers = Transformers::default();
        let modules =
            AnsiFunction::ALL.iter().map(|&f| TestModule::new(f, &transformers)).collect();
        Project { info: TestInfo::default(), frequency_hz: 50.0, transformers, modules }
    }
}

impl Project {
    /// Rapporti validi per il modulo: i suoi, o quelli dei dati generali.
    pub fn transformers_for<'a>(&'a self, module: &'a TestModule) -> &'a Transformers {
        if module.use_project_transformers {
            &self.transformers
        } else {
            &module.transformers
        }
    }

    pub fn plan(&self, module: &TestModule) -> ShotPlan {
        module.plan(self.transformers_for(module), self.frequency_hz)
    }

    pub fn enabled_modules(&self) -> impl Iterator<Item = &TestModule> {
        self.modules.iter().filter(|m| m.enabled)
    }

    pub fn module_verdict(&self, module: &TestModule) -> Verdict {
        module.verdict(&self.plan(module))
    }

    /// Esito dell'intera prova sulle funzioni presenti nel relè.
    pub fn verdict(&self) -> Verdict {
        overall(self.enabled_modules().map(|m| self.module_verdict(m)))
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string_pretty(self).expect("il progetto è sempre serializzabile")
    }

    pub fn from_json(text: &str) -> Result<Project, serde_json::Error> {
        serde_json::from_str(text)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shot::Measured;
    use crate::transformers::Ratio;

    #[test]
    fn new_project_has_one_module_per_function_and_none_enabled() {
        let p = Project::default();
        assert_eq!(p.modules.len(), 14);
        assert_eq!(p.enabled_modules().count(), 0);
        assert_eq!(p.verdict(), Verdict::NotTested);
    }

    #[test]
    fn module_can_override_the_project_ratios() {
        let mut p = Project::default();
        let module = &mut p.modules[0];
        module.transformers.ct = Ratio::new(600.0, 5.0);
        let shared = p.plan(&p.modules[0]).shots[0].outputs.currents[0].magnitude;
        p.modules[0].use_project_transformers = false;
        let own = p.plan(&p.modules[0]).shots[0].outputs.currents[0].magnitude;
        assert!((shared - 2.0 * own).abs() < 1e-9);
    }

    #[test]
    fn project_survives_a_round_trip_through_json() {
        let mut p = Project::default();
        p.info.relay_name = "REF615 \"arrivo\"".to_string();
        p.modules[1].enabled = true;
        p.modules[1].results = vec![None, Some(Measured::Trip { time_s: 1.72 }), Some(Measured::NoTrip)];
        let restored = Project::from_json(&p.to_json()).unwrap();
        assert_eq!(restored, p);
    }

    #[test]
    fn project_verdict_counts_only_enabled_modules() {
        let mut p = Project::default();
        p.modules[0].enabled = true;
        p.modules[0].results = vec![
            Some(Measured::NoTrip),
            Some(Measured::Trip { time_s: 0.05 }),
            Some(Measured::Trip { time_s: 0.05 }),
        ];
        assert_eq!(p.verdict(), Verdict::Passed);
        p.modules[1].enabled = true;
        assert_eq!(p.verdict(), Verdict::NotTested);
    }
}
