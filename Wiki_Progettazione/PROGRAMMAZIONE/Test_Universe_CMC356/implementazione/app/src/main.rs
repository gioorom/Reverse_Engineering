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

fn main() {
    // Su Windows si disegna con DirectX, che funziona anche senza scheda
    // grafica dedicata e in desktop remoto, dove OpenGL spesso manca; se non
    // parte si prova con OpenGL. Altrove si usa OpenGL.
    let result = if cfg!(windows) {
        run(eframe::Renderer::Wgpu).or_else(|directx| {
            run(eframe::Renderer::Glow)
                .map_err(|opengl| format!("DirectX: {directx}\nOpenGL: {opengl}"))
        })
    } else {
        run(eframe::Renderer::Glow).map_err(|error| error.to_string())
    };
    if let Err(details) = result {
        // senza finestra l'errore non si vedrebbe: lo si mostra in un avviso
        let message = format!("ProvaRelè non riesce ad aprire la finestra.\n\n{details}");
        eprintln!("{message}");
        rfd::MessageDialog::new()
            .set_level(rfd::MessageLevel::Error)
            .set_title("ProvaRelè")
            .set_description(message)
            .show();
        std::process::exit(1);
    }
}
