//! ProvaRelè: prove sui relè di protezione, un modulo per funzione ANSI.

// niente finestra di console su Windows nelle build di rilascio
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod general_page;
mod module_page;
mod report_page;
mod widgets;

use eframe::egui;

fn main() -> eframe::Result {
    // un file di progetto passato come argomento viene aperto all'avvio
    let file = std::env::args_os().nth(1).map(std::path::PathBuf::from);
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("ProvaRelè")
            .with_inner_size([1280.0, 820.0])
            .with_min_inner_size([980.0, 620.0]),
        ..Default::default()
    };
    eframe::run_native(
        "ProvaRelè",
        options,
        Box::new(move |cc| Ok(Box::new(app::App::new(cc, file)))),
    )
}
