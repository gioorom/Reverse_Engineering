//! Genera la prova di esempio `esempi/cabina_mt.json` e, con un secondo
//! argomento, il suo report.
//!
//! Uso: cargo run -p prova-rele-core --example esempio -- esempi/cabina_mt.json [report.html]

use prova_rele_core::functions::AnsiFunction;
use prova_rele_core::project::Project;
use prova_rele_core::report::{html_report, ReportForm};
use prova_rele_core::shot::{Expected, Measured};

/// Risultato che rispetta l'esito atteso, con un piccolo ritardo sul nominale.
fn passing(expected: &Expected) -> Measured {
    match *expected {
        Expected::NoTrip => Measured::NoTrip,
        Expected::Trip { nominal_s, .. } => {
            Measured::Trip { time_s: ((nominal_s * 1.02 + 0.008) * 1000.0).round() / 1000.0 }
        }
    }
}

fn example() -> Project {
    let mut project = Project::default();
    project.info.relay_name = "REF615".to_string();
    project.info.feeder = "Linea 1".to_string();
    project.info.plant = "Cabina di consegna MT (esempio)".to_string();
    project.info.location = "Milano".to_string();
    project.info.engineer = "Mario Rossi".to_string();
    project.info.date = "13/11/2026".to_string();
    project.transformers.has_residual_ct = true;

    use AnsiFunction::*;
    for function in [F50, F51, F51N, F67N, F27, F59, F81] {
        let index = project.modules.iter().position(|m| m.function == function).unwrap();
        project.modules[index].enabled = true;
        let plan = project.plan(&project.modules[index]);
        let module = &mut project.modules[index];
        module.results = plan.shots.iter().map(|shot| Some(passing(&shot.expected))).collect();
        match function {
            // un intervento troppo lento: la prova non è superata
            F51N => module.results[1] = Some(Measured::Trip { time_s: 0.412 }),
            // modulo lasciato a metà
            F81 => module.results[2..].iter_mut().for_each(|r| *r = None),
            _ => {}
        }
    }
    project
}

fn main() -> std::io::Result<()> {
    let mut args = std::env::args().skip(1);
    let project = example();
    match args.next() {
        Some(path) => std::fs::write(path, project.to_json() + "\n")?,
        None => println!("{}", project.to_json()),
    }
    if let Some(path) = args.next() {
        std::fs::write(path, html_report(&project, ReportForm::Long))?;
    }
    Ok(())
}
