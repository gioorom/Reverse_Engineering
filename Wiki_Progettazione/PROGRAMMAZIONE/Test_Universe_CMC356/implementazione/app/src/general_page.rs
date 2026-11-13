//! Pagina dei dati della prova: relè, impianto, trasformatori, funzioni presenti.

use eframe::egui;
use prova_rele_core::project::Project;

use crate::widgets;

pub fn today() -> String {
    chrono::Local::now().format("%d/%m/%Y").to_string()
}

pub fn show(ui: &mut egui::Ui, project: &mut Project) {
    ui.heading("Dati della prova");
    ui.add_space(6.0);

    let info = &mut project.info;
    egui::Grid::new("info").num_columns(2).spacing([24.0, 8.0]).show(ui, |ui| {
        let field = |ui: &mut egui::Ui, label: &str, value: &mut String| {
            ui.label(label);
            ui.add(egui::TextEdit::singleline(value).desired_width(380.0));
            ui.end_row();
        };
        field(ui, "Relè", &mut info.relay_name);
        field(ui, "Montante", &mut info.feeder);
        field(ui, "Impianto", &mut info.plant);
        field(ui, "Località", &mut info.location);
        field(ui, "Commissioning Engineer", &mut info.engineer);

        ui.label("Data");
        ui.horizontal(|ui| {
            ui.add(egui::TextEdit::singleline(&mut info.date).desired_width(120.0));
            if ui.button("Oggi").clicked() {
                info.date = today();
            }
        });
        ui.end_row();
    });

    widgets::section(ui, "Trasformatori di misura");
    let before = (project.transformers.clone(), project.frequency_hz);
    widgets::transformers(ui, "general", &mut project.transformers);
    ui.add_space(8.0);
    ui.horizontal(|ui| {
        ui.label("Frequenza nominale");
        for f in [50.0, 60.0] {
            ui.radio_value(&mut project.frequency_hz, f, format!("{f} Hz"));
        }
    });
    ui.weak("Ogni modulo usa questi rapporti, se non ne imposta di propri.");
    if before.1 != project.frequency_hz || before.0 != project.transformers {
        // i punti di prova cambiano: i risultati già inseriti non valgono più
        let frequency_changed = before.1 != project.frequency_hz;
        for module in &mut project.modules {
            if frequency_changed || module.use_project_transformers {
                module.results.clear();
            }
        }
    }

    widgets::section(ui, "Funzioni presenti nel relè");
    ui.weak("Per ogni funzione spuntata compare un modulo di prova nell'elenco a sinistra.");
    ui.add_space(4.0);
    egui::Grid::new("functions").num_columns(2).spacing([48.0, 8.0]).show(ui, |ui| {
        for (index, module) in project.modules.iter_mut().enumerate() {
            let label = format!("{}  —  {}", module.function.code(), module.function.name());
            ui.checkbox(&mut module.enabled, label);
            if index % 2 == 1 {
                ui.end_row();
            }
        }
    });
}
