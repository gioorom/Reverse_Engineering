//! Pagina di un modulo di prova: rapporti, tarature, punti di prova e risultati.

use eframe::egui::{self, RichText};
use prova_rele_core::curves::{InverseCurve, TimeCharacteristic};
use prova_rele_core::functions::differential::{BiasFormula, DifferentialKind, DifferentialSettings};
use prova_rele_core::functions::directional::DirectionalSettings;
use prova_rele_core::functions::distance::{DistanceSettings, FaultLoop, Zone};
use prova_rele_core::functions::frequency::{FrequencySettings, FrequencyStage, FrequencyStageKind};
use prova_rele_core::functions::overcurrent::{FaultType, OvercurrentSettings};
use prova_rele_core::functions::voltage::{VoltageKind, VoltageMeasurement, VoltageSettings};
use prova_rele_core::functions::{AnsiFunction, ModuleSettings, TestModule};
use prova_rele_core::project::Project;
use prova_rele_core::report::{deviation_label, expected_label, transformer_rows};
use prova_rele_core::shot::{assess, Measured, ShotPlan};

use crate::widgets::{self, angle, basis_unit, number, positive};

const GRID_SPACING: [f32; 2] = [24.0, 8.0];

pub fn show(ui: &mut egui::Ui, project: &mut Project, index: usize, show_outputs: &mut bool) {
    let Project { transformers, modules, frequency_hz, .. } = project;
    let module = &mut modules[index];
    let function = module.function;

    ui.heading(format!("ANSI {}  —  {}", function.code(), function.name()));

    let before = (
        module.settings.clone(),
        module.transformers.clone(),
        module.use_project_transformers,
    );

    widgets::section(ui, "Trasformatori di misura");
    ui.checkbox(&mut module.use_project_transformers, "Usa i rapporti dei dati generali");
    ui.add_space(4.0);
    if module.use_project_transformers {
        let text: Vec<String> =
            transformer_rows(transformers).into_iter().map(|(k, v)| format!("{k} {v}")).collect();
        ui.weak(text.join("   ·   "));
    } else {
        widgets::transformers(ui, ("module", index), &mut module.transformers);
    }

    widgets::section(ui, "Tarature");
    settings(ui, module);

    if before != (module.settings.clone(), module.transformers.clone(), module.use_project_transformers) {
        // i punti di prova cambiano: i risultati già inseriti non valgono più
        module.results.clear();
    }

    let plan = {
        let tr = if module.use_project_transformers { &*transformers } else { &module.transformers };
        module.plan(tr, *frequency_hz)
    };
    module.results.resize(plan.shots.len(), None);

    widgets::section(ui, "Prove");
    for warning in &plan.warnings {
        ui.colored_label(widgets::WARNING, format!("Attenzione: {warning}"));
    }
    ui.horizontal(|ui| {
        ui.label("Esito del modulo:");
        ui.label(widgets::verdict_text(module.verdict(&plan)));
        ui.add_space(24.0);
        ui.checkbox(show_outputs, "Mostra le grandezze iniettate");
        ui.add_space(24.0);
        if ui.button("Azzera i risultati").clicked() {
            module.results.iter_mut().for_each(|r| *r = None);
        }
    });
    ui.add_space(6.0);
    shots_table(ui, module, &plan, *show_outputs);
    ui.weak("Modificando rapporti o tarature i risultati del modulo vengono azzerati.");

    widgets::section(ui, "Note");
    ui.add(egui::TextEdit::multiline(&mut module.notes).desired_rows(3).desired_width(600.0));
}

fn shots_table(ui: &mut egui::Ui, module: &mut TestModule, plan: &ShotPlan, show_outputs: bool) {
    let columns = if show_outputs { 7 } else { 6 };
    egui::Grid::new(("shots", module.function))
        .num_columns(columns)
        .striped(true)
        .spacing([16.0, 8.0])
        .show(ui, |ui| {
            let mut titles = vec!["N.", "Prova"];
            if show_outputs {
                titles.push("Grandezze iniettate");
            }
            titles.extend(["Atteso", "Misurato", "Scarto", "Esito"]);
            for title in titles {
                ui.label(RichText::new(title).strong());
            }
            ui.end_row();

            for (index, shot) in plan.shots.iter().enumerate() {
                ui.label(format!("{}", index + 1));
                ui.label(&shot.description).on_hover_text(shot.outputs.describe());
                if show_outputs {
                    ui.label(RichText::new(shot.outputs.describe()).small());
                }
                ui.label(expected_label(&shot.expected));
                measured(ui, (module.function, index), &mut module.results[index]);
                let result = module.results[index].as_ref();
                ui.label(deviation_label(&shot.expected, result));
                ui.label(widgets::verdict_text(assess(&shot.expected, result)));
                ui.end_row();
            }
        });
}

/// Esito misurato di una prova: da eseguire, intervento con il suo tempo,
/// nessun intervento.
fn measured(ui: &mut egui::Ui, id: impl std::hash::Hash, value: &mut Option<Measured>) {
    ui.horizontal(|ui| {
        let label = match value {
            None => "Da eseguire",
            Some(Measured::Trip { .. }) => "Intervento",
            Some(Measured::NoTrip) => "Nessun intervento",
        };
        egui::ComboBox::from_id_salt(id).selected_text(label).width(140.0).show_ui(ui, |ui| {
            if ui.selectable_label(value.is_none(), "Da eseguire").clicked() {
                *value = None;
            }
            let is_trip = matches!(value, Some(Measured::Trip { .. }));
            if ui.selectable_label(is_trip, "Intervento").clicked() && !is_trip {
                *value = Some(Measured::Trip { time_s: 0.0 });
            }
            if ui.selectable_label(*value == Some(Measured::NoTrip), "Nessun intervento").clicked() {
                *value = Some(Measured::NoTrip);
            }
        });
        if let Some(Measured::Trip { time_s }) = value {
            ui.add(
                egui::DragValue::new(time_s)
                    .speed(0.001)
                    .range(0.0..=100000.0)
                    .fixed_decimals(3)
                    .suffix(" s"),
            );
        }
    });
}

fn settings(ui: &mut egui::Ui, module: &mut TestModule) {
    let function = module.function;
    let voltage_kind = module.voltage_kind();
    let differential_kind = module.differential_kind();
    let id = ("settings", function);
    match &mut module.settings {
        ModuleSettings::Overcurrent(s) => overcurrent(ui, id, function, s),
        ModuleSettings::Directional(s) => directional(ui, id, s),
        ModuleSettings::Voltage(s) => voltage(ui, id, voltage_kind, s),
        ModuleSettings::Frequency(s) => frequency(ui, id, s),
        ModuleSettings::Distance(s) => distance(ui, id, s),
        ModuleSettings::Differential(s) => differential(ui, id, differential_kind, s),
    }
}

type Id = (&'static str, AnsiFunction);

fn grid<R>(ui: &mut egui::Ui, id: impl std::hash::Hash, add: impl FnOnce(&mut egui::Ui) -> R) -> R {
    egui::Grid::new(id).num_columns(2).spacing(GRID_SPACING).show(ui, add).inner
}

fn overcurrent(ui: &mut egui::Ui, id: Id, function: AnsiFunction, s: &mut OvercurrentSettings) {
    grid(ui, id, |ui| {
        ui.label("Tarature espresse in");
        widgets::basis(ui, (id, "basis"), &mut s.basis);
        ui.end_row();

        ui.label("Soglia");
        positive(ui, &mut s.pickup, 0.1, &basis_unit(s.basis, "A"));
        ui.end_row();

        if function == AnsiFunction::F50 {
            // funzione istantanea: solo l'eventuale ritardo
            if let TimeCharacteristic::DefiniteTime { delay_s } = &mut s.characteristic {
                ui.label("Tempo");
                number(ui, delay_s, 0.01, " s");
                ui.end_row();
            }
        } else {
            ui.label("Caratteristica");
            let label = match s.characteristic {
                TimeCharacteristic::DefiniteTime { .. } => "Tempo definito",
                TimeCharacteristic::Inverse { curve, .. } => curve.label(),
            };
            egui::ComboBox::from_id_salt((id, "curve")).selected_text(label).width(260.0).show_ui(ui, |ui| {
                let definite = matches!(s.characteristic, TimeCharacteristic::DefiniteTime { .. });
                if ui.selectable_label(definite, "Tempo definito").clicked() && !definite {
                    s.characteristic = TimeCharacteristic::DefiniteTime { delay_s: 0.5 };
                }
                for curve in InverseCurve::ALL {
                    let (selected, multiplier) = match s.characteristic {
                        TimeCharacteristic::Inverse { curve: c, multiplier } => (c == curve, multiplier),
                        TimeCharacteristic::DefiniteTime { .. } => (false, 0.1),
                    };
                    if ui.selectable_label(selected, curve.label()).clicked() {
                        s.characteristic = TimeCharacteristic::Inverse { curve, multiplier };
                    }
                }
            });
            ui.end_row();

            match &mut s.characteristic {
                TimeCharacteristic::DefiniteTime { delay_s } => {
                    ui.label("Tempo");
                    number(ui, delay_s, 0.01, " s");
                }
                TimeCharacteristic::Inverse { multiplier, .. } => {
                    ui.label("Moltiplicatore di tempo (TMS)");
                    positive(ui, multiplier, 0.01, "");
                }
            }
            ui.end_row();
        }

        if matches!(function, AnsiFunction::F50 | AnsiFunction::F51) {
            ui.label("Tipi di guasto");
            ui.horizontal(|ui| {
                for fault in FaultType::ALL {
                    let mut on = s.fault_types.contains(&fault);
                    if ui.checkbox(&mut on, fault.label()).changed() {
                        if on {
                            s.fault_types.push(fault);
                            s.fault_types.sort_by_key(|f| FaultType::ALL.iter().position(|x| x == f));
                        } else {
                            s.fault_types.retain(|f| *f != fault);
                        }
                    }
                }
            });
            ui.end_row();
        }

        ui.label("Multipli della soglia da provare");
        widgets::list(ui, &mut s.multiples, 0.05, " ×");
        ui.end_row();

        widgets::tolerance_rows(ui, &mut s.tolerances, Some("sulla corrente"));
    });
}

fn directional(ui: &mut egui::Ui, id: Id, s: &mut DirectionalSettings) {
    grid(ui, id, |ui| {
        ui.label("Tarature espresse in");
        widgets::basis(ui, (id, "basis"), &mut s.basis);
        ui.end_row();

        ui.label("Soglia di corrente");
        positive(ui, &mut s.pickup, 0.1, &basis_unit(s.basis, "A"));
        ui.end_row();

        ui.label("Tempo");
        number(ui, &mut s.delay_s, 0.01, " s");
        ui.end_row();

        ui.label("Settore di intervento");
        ui.horizontal(|ui| {
            ui.label("da");
            angle(ui, &mut s.sector_from_deg);
            ui.label("a");
            angle(ui, &mut s.sector_to_deg);
            ui.weak("ritardo della corrente sulla tensione di riferimento");
        });
        ui.end_row();

        ui.label("Margine dai limiti del settore");
        number(ui, &mut s.angle_margin_deg, 0.5, "°");
        ui.end_row();

        ui.label("Tensione di prova");
        positive(ui, &mut s.test_voltage, 0.5, " V secondari");
        ui.end_row();

        ui.label("Corrente nelle prove di angolo");
        positive(ui, &mut s.test_multiple, 0.05, " × soglia");
        ui.end_row();

        ui.label("Multipli della soglia da provare");
        widgets::list(ui, &mut s.pickup_multiples, 0.05, " ×");
        ui.end_row();

        widgets::tolerance_rows(ui, &mut s.tolerances, Some("sulla corrente"));
    });
}

fn voltage(ui: &mut egui::Ui, id: Id, kind: VoltageKind, s: &mut VoltageSettings) {
    grid(ui, id, |ui| {
        ui.label("Tarature espresse in");
        widgets::basis(ui, (id, "basis"), &mut s.basis);
        ui.end_row();

        ui.label(if kind == VoltageKind::ResidualOver { "Soglia (3V0)" } else { "Soglia" });
        positive(ui, &mut s.pickup, 1.0, &basis_unit(s.basis, "V"));
        ui.end_row();

        if kind != VoltageKind::ResidualOver {
            ui.label("Tensione misurata");
            ui.horizontal(|ui| {
                ui.radio_value(&mut s.measurement, VoltageMeasurement::PhaseToPhase, "concatenata");
                ui.radio_value(&mut s.measurement, VoltageMeasurement::PhaseToNeutral, "di fase");
            });
            ui.end_row();
        }

        ui.label("Tempo");
        number(ui, &mut s.delay_s, 0.01, " s");
        ui.end_row();

        ui.label("Multipli della soglia da provare");
        widgets::list(ui, &mut s.multiples, 0.05, " ×");
        ui.end_row();

        widgets::tolerance_rows(ui, &mut s.tolerances, Some("sulla tensione"));
    });
}

fn frequency(ui: &mut egui::Ui, id: Id, s: &mut FrequencySettings) {
    let mut remove = None;
    egui::Grid::new((id, "stages")).num_columns(4).spacing(GRID_SPACING).show(ui, |ui| {
        for title in ["Soglia", "Frequenza", "Tempo", ""] {
            ui.label(RichText::new(title).strong());
        }
        ui.end_row();
        for (index, stage) in s.stages.iter_mut().enumerate() {
            let label = |k: FrequencyStageKind| match k {
                FrequencyStageKind::Under => "Minima frequenza (f<)",
                FrequencyStageKind::Over => "Massima frequenza (f>)",
            };
            egui::ComboBox::from_id_salt((id, "stage", index))
                .selected_text(label(stage.kind))
                .width(190.0)
                .show_ui(ui, |ui| {
                    for k in [FrequencyStageKind::Under, FrequencyStageKind::Over] {
                        ui.selectable_value(&mut stage.kind, k, label(k));
                    }
                });
            ui.add(egui::DragValue::new(&mut stage.pickup_hz).speed(0.01).range(1.0..=100.0).max_decimals(3).suffix(" Hz"));
            number(ui, &mut stage.delay_s, 0.01, " s");
            if ui.small_button("Togli").clicked() {
                remove = Some(index);
            }
            ui.end_row();
        }
    });
    if let Some(index) = remove {
        s.stages.remove(index);
    }
    if ui.button("+ Aggiungi una soglia").clicked() {
        s.stages.push(FrequencyStage { kind: FrequencyStageKind::Under, pickup_hz: 49.0, delay_s: 1.0 });
    }
    ui.add_space(8.0);
    grid(ui, id, |ui| {
        ui.label("Scostamento di prova dalla soglia");
        positive(ui, &mut s.test_offset_hz, 0.01, " Hz");
        ui.end_row();
        widgets::tolerance_rows(ui, &mut s.tolerances, None);
    });
}

fn distance(ui: &mut egui::Ui, id: Id, s: &mut DistanceSettings) {
    grid(ui, id, |ui| {
        ui.label("Impedenze espresse in");
        widgets::basis(ui, (id, "basis"), &mut s.basis);
        ui.end_row();

        ui.label("Angolo di linea");
        angle(ui, &mut s.line_angle_deg);
        ui.end_row();
    });
    ui.add_space(8.0);

    let unit = basis_unit(s.basis, "ohm");
    let mut remove = None;
    egui::Grid::new((id, "zones")).num_columns(5).spacing(GRID_SPACING).show(ui, |ui| {
        for title in ["Zona", "Portata", "Tempo", "Direzione", ""] {
            ui.label(RichText::new(title).strong());
        }
        ui.end_row();
        for (index, zone) in s.zones.iter_mut().enumerate() {
            ui.add(egui::TextEdit::singleline(&mut zone.name).desired_width(60.0));
            positive(ui, &mut zone.reach_ohm, 0.05, &unit);
            number(ui, &mut zone.delay_s, 0.01, " s");
            ui.horizontal(|ui| {
                ui.radio_value(&mut zone.forward, true, "avanti");
                ui.radio_value(&mut zone.forward, false, "indietro");
            });
            if ui.small_button("Togli").clicked() {
                remove = Some(index);
            }
            ui.end_row();
        }
    });
    if let Some(index) = remove {
        s.zones.remove(index);
    }
    if ui.button("+ Aggiungi una zona").clicked() {
        let reach_ohm = s.zones.iter().map(|z| z.reach_ohm).fold(0.0, f64::max) * 1.5 + 1.0;
        s.zones.push(Zone { name: format!("Z{}", s.zones.len() + 1), reach_ohm, delay_s: 1.0, forward: true });
    }
    ui.add_space(8.0);

    grid(ui, (id, "more"), |ui| {
        ui.label("Compensazione di terra k0");
        ui.horizontal(|ui| {
            number(ui, &mut s.k0_magnitude, 0.01, "");
            ui.label("angolo");
            angle(ui, &mut s.k0_angle_deg);
        });
        ui.end_row();

        ui.label("Corrente di prova");
        positive(ui, &mut s.test_current_a, 0.1, " A secondari");
        ui.end_row();

        ui.label("Anelli di guasto");
        ui.horizontal(|ui| {
            for fault in FaultLoop::ALL {
                let mut on = s.loops.contains(&fault);
                if ui.checkbox(&mut on, fault.label()).changed() {
                    if on {
                        s.loops.push(fault);
                        s.loops.sort_by_key(|f| FaultLoop::ALL.iter().position(|x| x == f));
                    } else {
                        s.loops.retain(|f| *f != fault);
                    }
                }
            }
        });
        ui.end_row();

        ui.label("Margine sulla portata");
        positive(ui, &mut s.reach_margin_pct, 0.5, " %");
        ui.end_row();

        widgets::tolerance_rows(ui, &mut s.tolerances, Some("sull'impedenza"));
    });
    ui.weak("Ogni zona è provata lungo l'angolo di linea, dentro e fuori dalla portata.");
}

fn differential(ui: &mut egui::Ui, id: Id, kind: DifferentialKind, s: &mut DifferentialSettings) {
    grid(ui, id, |ui| {
        match kind {
            DifferentialKind::Transformer => {
                ui.label("Potenza nominale");
                positive(ui, &mut s.rated_power_mva, 0.1, " MVA");
                ui.end_row();

                ui.label("Tensioni dei due lati");
                ui.horizontal(|ui| {
                    positive(ui, &mut s.voltage1_kv, 0.1, " kV");
                    ui.label("/");
                    positive(ui, &mut s.voltage2_kv, 0.1, " kV");
                });
                ui.end_row();

                ui.label("Indice orario del gruppo");
                ui.add(egui::DragValue::new(&mut s.clock_number).range(0..=11));
                ui.end_row();
            }
            _ => {
                ui.label("Corrente di riferimento");
                positive(ui, &mut s.rated_current_a, 1.0, " A primari");
                ui.end_row();
            }
        }

        if kind != DifferentialKind::Line {
            ui.label("TA del lato 2");
            widgets::ratio(ui, &mut s.ct2, "A");
            ui.end_row();
        }

        ui.label("Soglia differenziale");
        positive(ui, &mut s.pickup_pu, 0.01, " p.u.");
        ui.end_row();

        if kind != DifferentialKind::Line {
            ui.label("Prima pendenza");
            ui.horizontal(|ui| {
                number(ui, &mut s.slope1_pct, 0.5, " %");
                ui.label("a partire da");
                number(ui, &mut s.knee1_pu, 0.05, " p.u.");
            });
            ui.end_row();

            ui.label("Seconda pendenza");
            ui.horizontal(|ui| {
                number(ui, &mut s.slope2_pct, 0.5, " %");
                ui.label("a partire da");
                number(ui, &mut s.knee2_pu, 0.05, " p.u.");
            });
            ui.end_row();

            ui.label("Corrente di stabilizzazione");
            egui::ComboBox::from_id_salt((id, "bias")).selected_text(s.bias_formula.label()).show_ui(ui, |ui| {
                for formula in BiasFormula::ALL {
                    ui.selectable_value(&mut s.bias_formula, formula, formula.label());
                }
            });
            ui.end_row();

            ui.label("Stabilizzazioni da provare");
            widgets::list(ui, &mut s.bias_points_pu, 0.1, " p.u.");
            ui.end_row();
        }

        ui.label("Tempo");
        number(ui, &mut s.delay_s, 0.01, " s");
        ui.end_row();

        ui.label("Margine di prova");
        positive(ui, &mut s.margin_pct, 0.5, " %");
        ui.end_row();

        widgets::tolerance_rows(ui, &mut s.tolerances, Some("sulla corrente"));
    });
    match kind {
        DifferentialKind::Line => ui.weak(
            "Prova da un solo estremo: verifica la soglia e il tempo. La caratteristica di \
             stabilizzazione richiede due cassette sincronizzate ai due estremi.",
        ),
        _ => ui.weak("Lato 1 sulle uscite I L1..L3 con il TA del modulo, lato 2 sulle uscite I 4..I 6."),
    };
}
