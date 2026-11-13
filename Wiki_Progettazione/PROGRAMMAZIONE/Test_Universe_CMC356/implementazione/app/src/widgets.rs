//! Campi e piccoli componenti condivisi dalle pagine.

use eframe::egui::{self, Color32, RichText};
use prova_rele_core::shot::{Tolerances, Verdict};
use prova_rele_core::transformers::{Basis, CtDirection, Ratio, Transformers};

pub const PASSED: Color32 = Color32::from_rgb(10, 125, 55);
pub const FAILED: Color32 = Color32::from_rgb(185, 25, 35);
pub const PENDING: Color32 = Color32::from_rgb(120, 120, 120);
pub const WARNING: Color32 = Color32::from_rgb(160, 95, 0);

pub fn verdict_color(verdict: Verdict) -> Color32 {
    match verdict {
        Verdict::NotTested => PENDING,
        Verdict::Passed => PASSED,
        Verdict::Failed => FAILED,
    }
}

pub fn verdict_text(verdict: Verdict) -> RichText {
    let label = match verdict {
        Verdict::NotTested => "Da eseguire",
        Verdict::Passed => "Superata",
        Verdict::Failed => "Non superata",
    };
    RichText::new(label).color(verdict_color(verdict)).strong()
}

pub fn section(ui: &mut egui::Ui, title: &str) {
    ui.add_space(14.0);
    ui.label(RichText::new(title).size(17.0).strong());
    ui.separator();
    ui.add_space(2.0);
}

/// Numero non negativo.
pub fn number(ui: &mut egui::Ui, value: &mut f64, speed: f64, suffix: &str) -> egui::Response {
    ui.add(
        egui::DragValue::new(value)
            .speed(speed)
            .range(0.0..=1.0e9)
            .max_decimals(4)
            .suffix(suffix),
    )
}

/// Numero strettamente positivo (rapporti, soglie).
pub fn positive(ui: &mut egui::Ui, value: &mut f64, speed: f64, suffix: &str) -> egui::Response {
    ui.add(
        egui::DragValue::new(value)
            .speed(speed)
            .range(1.0e-4..=1.0e9)
            .max_decimals(4)
            .suffix(suffix),
    )
}

pub fn angle(ui: &mut egui::Ui, value: &mut f64) -> egui::Response {
    ui.add(egui::DragValue::new(value).speed(1.0).range(-360.0..=360.0).max_decimals(1).suffix("°"))
}

pub fn ratio(ui: &mut egui::Ui, ratio: &mut Ratio, unit: &str) {
    ui.horizontal(|ui| {
        positive(ui, &mut ratio.primary, 1.0, "");
        ui.label("/");
        positive(ui, &mut ratio.secondary, 0.1, "");
        ui.label(unit);
    });
}

pub fn basis(ui: &mut egui::Ui, id: impl std::hash::Hash, basis: &mut Basis) {
    let label = |b: Basis| match b {
        Basis::Primary => "valori primari",
        Basis::Secondary => "valori secondari",
    };
    egui::ComboBox::from_id_salt(id).selected_text(label(*basis)).show_ui(ui, |ui| {
        for b in [Basis::Primary, Basis::Secondary] {
            ui.selectable_value(basis, b, label(b));
        }
    });
}

pub fn basis_unit(basis: Basis, unit: &str) -> String {
    match basis {
        Basis::Primary => format!(" {unit} primari"),
        Basis::Secondary => format!(" {unit} secondari"),
    }
}

/// Rapporti di TA, TO e TV.
pub fn transformers(ui: &mut egui::Ui, id: impl std::hash::Hash + Copy, tr: &mut Transformers) {
    egui::Grid::new((id, "transformers")).num_columns(2).spacing([24.0, 8.0]).show(ui, |ui| {
        ui.label("TA");
        ratio(ui, &mut tr.ct, "A");
        ui.end_row();

        ui.label("Verso del TA");
        let label = |d: CtDirection| match d {
            CtDirection::TowardLine => "verso la linea",
            CtDirection::TowardBusbar => "verso le sbarre",
        };
        egui::ComboBox::from_id_salt((id, "direction"))
            .selected_text(label(tr.ct_direction))
            .show_ui(ui, |ui| {
                for d in [CtDirection::TowardLine, CtDirection::TowardBusbar] {
                    ui.selectable_value(&mut tr.ct_direction, d, label(d));
                }
            });
        ui.end_row();

        ui.label("TO (toroide omopolare)");
        ui.horizontal(|ui| {
            ui.checkbox(&mut tr.has_residual_ct, "presente");
            ui.add_enabled_ui(tr.has_residual_ct, |ui| ratio(ui, &mut tr.residual_ct, "A"));
        });
        ui.end_row();

        ui.label("TV");
        ratio(ui, &mut tr.vt, "V concatenati");
        ui.end_row();

        ui.label("TV omopolare (3V0)");
        ratio(ui, &mut tr.residual_vt, "V");
        ui.end_row();
    });
}

/// Righe di tolleranza dentro una griglia a due colonne. Senza `quantity`
/// si mostra solo la tolleranza sul tempo.
pub fn tolerance_rows(ui: &mut egui::Ui, tol: &mut Tolerances, quantity: Option<&str>) {
    if let Some(quantity) = quantity {
        ui.label(format!("Tolleranza sulla {quantity}"));
        number(ui, &mut tol.quantity_pct, 0.1, " %");
        ui.end_row();
    }
    ui.label("Tolleranza sul tempo");
    ui.horizontal(|ui| {
        number(ui, &mut tol.time_pct, 0.1, " %");
        ui.label("con un minimo di");
        let mut ms = tol.time_abs_s * 1000.0;
        if number(ui, &mut ms, 1.0, " ms").changed() {
            tol.time_abs_s = ms / 1000.0;
        }
    });
    ui.end_row();
}

/// Elenco modificabile di numeri (multipli della soglia, punti di prova).
pub fn list(ui: &mut egui::Ui, values: &mut Vec<f64>, speed: f64, suffix: &str) {
    ui.horizontal_wrapped(|ui| {
        let mut remove = None;
        for (index, value) in values.iter_mut().enumerate() {
            positive(ui, value, speed, suffix);
            if ui.small_button("x").on_hover_text("Togli").clicked() {
                remove = Some(index);
            }
            ui.add_space(6.0);
        }
        if let Some(index) = remove {
            values.remove(index);
        }
        if ui.button("+ Aggiungi").clicked() {
            values.push(values.last().map_or(1.1, |last| last + 0.5));
        }
    });
}
