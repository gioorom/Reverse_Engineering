//! Pagina del report: riepilogo degli esiti ed esportazione.

use eframe::egui::{self, RichText};
use prova_rele_core::project::Project;
use prova_rele_core::report::{html_report, ReportForm};
use prova_rele_core::shot::Verdict;

use crate::widgets;

pub fn show(ui: &mut egui::Ui, project: &Project, form: &mut ReportForm, message: &mut String) {
    ui.heading("Report");
    ui.add_space(6.0);

    if project.enabled_modules().next().is_none() {
        ui.label("Nessuna funzione da provare: scegli le funzioni presenti nel relè nei dati della prova.");
        return;
    }

    ui.horizontal(|ui| {
        ui.label(RichText::new("Esito della prova:").size(16.0));
        ui.label(widgets::verdict_text(project.verdict()).size(16.0));
    });
    ui.add_space(8.0);

    egui::Grid::new("summary").num_columns(4).striped(true).spacing([28.0, 8.0]).show(ui, |ui| {
        for title in ["ANSI", "Funzione", "Prove eseguite", "Esito"] {
            ui.label(RichText::new(title).strong());
        }
        ui.end_row();
        for module in project.enabled_modules() {
            let plan = project.plan(module);
            let verdicts = module.verdicts(&plan);
            let done = verdicts.iter().filter(|v| **v != Verdict::NotTested).count();
            ui.label(module.function.code());
            ui.label(module.function.name());
            ui.label(format!("{done} di {}", verdicts.len()));
            ui.label(widgets::verdict_text(module.verdict(&plan)));
            ui.end_row();
        }
    });

    widgets::section(ui, "Contenuto");
    ui.radio_value(form, ReportForm::Long, "Forma estesa: tarature, grandezze iniettate e risultati");
    ui.radio_value(form, ReportForm::Short, "Forma sintetica: solo dati della prova e risultati");
    ui.add_space(12.0);

    if ui.button(RichText::new("Esporta il report…").size(15.0)).clicked() {
        export(project, *form, message);
    }
    ui.weak("Il report è una pagina HTML: si apre nel browser, da cui si stampa o si salva in PDF.");
}

fn export(project: &Project, form: ReportForm, message: &mut String) {
    let relay: String = project
        .info
        .relay_name
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' { c } else { '_' })
        .collect();
    let name = if relay.is_empty() { "Rapporto_di_prova.html".to_string() } else { format!("Rapporto_{relay}.html") };
    let Some(path) = rfd::FileDialog::new()
        .set_title("Esporta il report")
        .set_file_name(name)
        .add_filter("Pagina HTML", &["html"])
        .save_file()
    else {
        return;
    };
    *message = match std::fs::write(&path, html_report(project, form)) {
        Err(error) => format!("Report non salvato: {error}"),
        Ok(()) => match open::that(&path) {
            Ok(()) => format!("Report salvato in {}", path.display()),
            Err(_) => format!("Report salvato in {} (non sono riuscito ad aprirlo nel browser)", path.display()),
        },
    };
}
