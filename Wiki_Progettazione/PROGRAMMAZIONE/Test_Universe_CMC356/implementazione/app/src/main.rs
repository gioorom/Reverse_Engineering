//! ProvaRelè: prove sui relè di protezione, un modulo per funzione ANSI.

// niente finestra di console su Windows nelle build di rilascio
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod general_page;
mod module_page;
mod report_page;
mod widgets;

use eframe::egui;

fn options(renderer: eframe::Renderer) -> eframe::NativeOptions {
    eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("ProvaRelè")
            .with_inner_size([1360.0, 840.0])
            .with_min_inner_size([980.0, 620.0]),
        renderer,
        ..Default::default()
    }
}

fn run(renderer: eframe::Renderer) -> eframe::Result {
    // un file di progetto passato come argomento viene aperto all'avvio
    let file = std::env::args_os().nth(1).map(std::path::PathBuf::from);
    eframe::run_native(
        "ProvaRelè",
        options(renderer),
        Box::new(move |cc| Ok(Box::new(app::App::new(cc, file)))),
    )
}

fn main() -> eframe::Result {
    // Su Windows si disegna con DirectX, che funziona anche senza scheda
    // grafica dedicata e in desktop remoto, dove OpenGL spesso manca; se non
    // parte si prova con OpenGL. Altrove si usa OpenGL.
    if cfg!(windows) {
        run(eframe::Renderer::Wgpu).or_else(|_| run(eframe::Renderer::Glow))
    } else {
        run(eframe::Renderer::Glow)
    }
}
