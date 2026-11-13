//! Finestra principale: barra dei comandi, elenco dei moduli, pagina corrente.

use std::path::{Path, PathBuf};

use eframe::egui::{self, RichText};
use prova_rele_core::project::Project;
use prova_rele_core::report::ReportForm;
use prova_rele_core::shot::Verdict;

use crate::{general_page, module_page, report_page, widgets};

#[derive(Clone, Copy, PartialEq)]
enum Page {
    General,
    Module(usize),
    Report,
}

/// Azione che farebbe perdere le modifiche non salvate.
#[derive(Clone, Copy, PartialEq)]
enum Pending {
    New,
    Open,
    Close,
}

pub struct App {
    project: Project,
    /// Stato all'ultimo salvataggio, per sapere se ci sono modifiche.
    saved: Project,
    path: Option<PathBuf>,
    page: Page,
    report_form: ReportForm,
    show_outputs: bool,
    message: String,
    pending: Option<Pending>,
    close_confirmed: bool,
    title: String,
}

fn new_project() -> Project {
    let mut project = Project::default();
    project.info.date = general_page::today();
    project
}

impl App {
    pub fn new(cc: &eframe::CreationContext<'_>, file: Option<PathBuf>) -> Self {
        let mut visuals = egui::Visuals::light();
        // bordo visibile su caselle, campi e pulsanti
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0_f32, egui::Color32::from_gray(165));
        cc.egui_ctx.set_visuals(visuals);
        cc.egui_ctx.style_mut(|style| {
            for font in style.text_styles.values_mut() {
                font.size *= 1.12;
            }
            style.spacing.item_spacing = egui::vec2(8.0, 6.0);
            style.spacing.button_padding = egui::vec2(8.0, 4.0);
        });
        let project = new_project();
        let mut app = App {
            saved: project.clone(),
            project,
            path: None,
            page: Page::General,
            report_form: ReportForm::Long,
            show_outputs: false,
            message: String::new(),
            pending: None,
            close_confirmed: false,
            title: String::new(),
        };
        if let Some(file) = file {
            app.load(&file);
        }
        app
    }

    fn dirty(&self) -> bool {
        self.project != self.saved
    }

    fn load(&mut self, path: &Path) {
        let loaded = std::fs::read_to_string(path)
            .map_err(|e| e.to_string())
            .and_then(|text| Project::from_json(&text).map_err(|e| e.to_string()));
        match loaded {
            Ok(project) => {
                self.saved = project.clone();
                self.project = project;
                self.path = Some(path.to_path_buf());
                self.page = Page::General;
                self.message = format!("Aperto {}", path.display());
            }
            Err(error) => self.message = format!("Non riesco ad aprire {}: {error}", path.display()),
        }
    }

    fn write(&mut self, path: &Path) -> bool {
        match std::fs::write(path, self.project.to_json()) {
            Ok(()) => {
                self.saved = self.project.clone();
                self.path = Some(path.to_path_buf());
                self.message = format!("Salvato in {}", path.display());
                true
            }
            Err(error) => {
                self.message = format!("Non salvato: {error}");
                false
            }
        }
    }

    fn save(&mut self) -> bool {
        match self.path.clone() {
            Some(path) => self.write(&path),
            None => self.save_as(),
        }
    }

    fn save_as(&mut self) -> bool {
        let relay = self.project.info.relay_name.trim();
        let name = if relay.is_empty() { "Prova.json".to_string() } else { format!("{relay}.json") };
        match rfd::FileDialog::new()
            .set_title("Salva la prova")
            .set_file_name(name)
            .add_filter("Prova ProvaRelè", &["json"])
            .save_file()
        {
            Some(path) => self.write(&path),
            None => false,
        }
    }

    /// Esegue l'azione, chiedendo prima conferma se ci sono modifiche non salvate.
    fn request(&mut self, action: Pending, ctx: &egui::Context) {
        if self.dirty() {
            self.pending = Some(action);
        } else {
            self.run(action, ctx);
        }
    }

    fn run(&mut self, action: Pending, ctx: &egui::Context) {
        match action {
            Pending::New => {
                self.project = new_project();
                self.saved = self.project.clone();
                self.path = None;
                self.page = Page::General;
                self.message.clear();
            }
            Pending::Open => {
                if let Some(path) = rfd::FileDialog::new()
                    .set_title("Apri una prova")
                    .add_filter("Prova ProvaRelè", &["json"])
                    .pick_file()
                {
                    self.load(&path);
                }
            }
            Pending::Close => {
                self.close_confirmed = true;
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
    }

    fn update_title(&mut self, ctx: &egui::Context) {
        let file = self
            .path
            .as_ref()
            .and_then(|p| p.file_name())
            .map_or("Nuova prova".to_string(), |n| n.to_string_lossy().into_owned());
        let title = format!("{file}{} — ProvaRelè", if self.dirty() { " *" } else { "" });
        if title != self.title {
            ctx.send_viewport_cmd(egui::ViewportCommand::Title(title.clone()));
            self.title = title;
        }
    }

    fn toolbar(&mut self, ctx: &egui::Context) {
        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                if ui.button("Nuova").clicked() {
                    self.request(Pending::New, ctx);
                }
                if ui.button("Apri…").clicked() {
                    self.request(Pending::Open, ctx);
                }
                if ui.button("Salva").clicked() {
                    self.save();
                }
                if ui.button("Salva con nome…").clicked() {
                    self.save_as();
                }
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.weak("Strumento: non collegato (i risultati si inseriscono a mano)");
                });
            });
            ui.add_space(4.0);
        });
    }

    fn navigation(&mut self, ctx: &egui::Context) {
        egui::SidePanel::left("navigation").resizable(false).exact_width(260.0).show(ctx, |ui| {
            ui.add_space(8.0);
            // voci a tutta larghezza, allineate a sinistra
            let layout = egui::Layout::top_down_justified(egui::Align::LEFT);
            let mut entry = |ui: &mut egui::Ui, page: Page, text: RichText| {
                ui.with_layout(layout, |ui| {
                    if ui.selectable_label(self.page == page, text).clicked() {
                        self.page = page;
                    }
                });
            };
            entry(ui, Page::General, RichText::new("Dati della prova").size(15.0));
            ui.add_space(10.0);
            ui.label(RichText::new("FUNZIONI DA PROVARE").small().weak());
            ui.separator();

            let project = &self.project;
            let modules: Vec<(usize, RichText)> = project
                .modules
                .iter()
                .enumerate()
                .filter(|(_, m)| m.enabled)
                .map(|(index, m)| {
                    let text = format!("{}   {}", m.function.code(), m.function.name());
                    let text = match project.module_verdict(m) {
                        Verdict::NotTested => RichText::new(text),
                        verdict => RichText::new(text).color(widgets::verdict_color(verdict)).strong(),
                    };
                    (index, text)
                })
                .collect();
            if modules.is_empty() {
                ui.weak("Nessuna: spunta le funzioni presenti nel relè nei dati della prova.");
            }
            egui::ScrollArea::vertical().show(ui, |ui| {
                for (index, text) in modules {
                    entry(ui, Page::Module(index), text);
                }
                ui.add_space(10.0);
                ui.separator();
                entry(ui, Page::Report, RichText::new("Report").size(15.0));
                ui.add_space(8.0);
                ui.horizontal_wrapped(|ui| {
                    ui.spacing_mut().item_spacing.x = 10.0;
                    ui.label(RichText::new("superata").small().color(widgets::PASSED));
                    ui.label(RichText::new("non superata").small().color(widgets::FAILED));
                });
            });
        });
    }

    fn unsaved_dialog(&mut self, ctx: &egui::Context) {
        let Some(action) = self.pending else { return };
        egui::Window::new("Modifiche non salvate")
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.label("La prova ha modifiche non salvate. Vuoi salvarle?");
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui.button("Salva").clicked() && self.save() {
                        self.pending = None;
                        self.run(action, ctx);
                    }
                    if ui.button("Non salvare").clicked() {
                        self.pending = None;
                        self.run(action, ctx);
                    }
                    if ui.button("Annulla").clicked() {
                        self.pending = None;
                    }
                });
            });
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.update_title(ctx);

        // chiusura della finestra con modifiche non salvate: prima si chiede
        if ctx.input(|i| i.viewport().close_requested()) && self.dirty() && !self.close_confirmed {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            self.pending = Some(Pending::Close);
        }

        // un modulo tolto dalle funzioni presenti non resta aperto
        if let Page::Module(index) = self.page {
            if !self.project.modules[index].enabled {
                self.page = Page::General;
            }
        }

        self.toolbar(ctx);
        if !self.message.is_empty() {
            egui::TopBottomPanel::bottom("message").show(ctx, |ui| {
                ui.add_space(2.0);
                ui.label(&self.message);
                ui.add_space(2.0);
            });
        }
        self.navigation(ctx);
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.add_enabled_ui(self.pending.is_none(), |ui| {
                egui::ScrollArea::both().auto_shrink([false, false]).show(ui, |ui| {
                    ui.add_space(6.0);
                    match self.page {
                        Page::General => general_page::show(ui, &mut self.project),
                        Page::Module(index) => {
                            module_page::show(ui, &mut self.project, index, &mut self.show_outputs)
                        }
                        Page::Report => report_page::show(
                            ui,
                            &self.project,
                            &mut self.report_form,
                            &mut self.message,
                        ),
                    }
                    ui.add_space(20.0);
                });
            });
        });
        self.unsaved_dialog(ctx);
    }
}
