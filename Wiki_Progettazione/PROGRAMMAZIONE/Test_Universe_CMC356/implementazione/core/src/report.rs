//! Report di prova in HTML, pronto per la stampa o il salvataggio in PDF.

use crate::project::Project;
use crate::shot::{assess, overall, Expected, Measured, Verdict};
use crate::transformers::{CtDirection, Transformers};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReportForm {
    /// Tarature, grandezze iniettate e risultati.
    Long,
    /// Solo dati della prova e risultati.
    Short,
}

pub fn verdict_label(verdict: Verdict) -> &'static str {
    match verdict {
        Verdict::NotTested => "Non eseguita",
        Verdict::Passed => "Superata",
        Verdict::Failed => "Non superata",
    }
}

pub fn expected_label(expected: &Expected) -> String {
    match *expected {
        Expected::NoTrip => "Nessun intervento".to_string(),
        Expected::Trip { nominal_s, min_s, max_s } if max_s.is_finite() => {
            format!("{nominal_s:.3} s ({min_s:.3} – {max_s:.3} s)")
        }
        Expected::Trip { nominal_s, min_s, .. } => {
            format!("{nominal_s:.3} s (oltre {min_s:.3} s)")
        }
    }
}

pub fn measured_label(measured: Option<&Measured>) -> String {
    match measured {
        None => "—".to_string(),
        Some(Measured::NoTrip) => "Nessun intervento".to_string(),
        Some(Measured::Trip { time_s }) => format!("{time_s:.3} s"),
    }
}

/// Scarto del tempo misurato dal nominale, se entrambi sono interventi.
pub fn deviation_label(expected: &Expected, measured: Option<&Measured>) -> String {
    match (expected, measured) {
        (Expected::Trip { nominal_s, .. }, Some(Measured::Trip { time_s })) => {
            let delta_ms = (time_s - nominal_s) * 1000.0;
            if *nominal_s > 0.0 {
                format!("{delta_ms:+.0} ms ({:+.1} %)", delta_ms / nominal_s / 10.0)
            } else {
                format!("{delta_ms:+.0} ms")
            }
        }
        _ => "—".to_string(),
    }
}

pub fn transformer_rows(tr: &Transformers) -> Vec<(String, String)> {
    let direction = match tr.ct_direction {
        CtDirection::TowardLine => "verso la linea",
        CtDirection::TowardBusbar => "verso le sbarre",
    };
    let mut rows = vec![
        ("TA".to_string(), format!("{} / {} A, {direction}", tr.ct.primary, tr.ct.secondary)),
        ("TV".to_string(), format!("{} / {} V", tr.vt.primary, tr.vt.secondary)),
        (
            "TV omopolare (3V0)".to_string(),
            format!("{} / {} V", tr.residual_vt.primary, tr.residual_vt.secondary),
        ),
    ];
    if tr.has_residual_ct {
        rows.insert(
            1,
            ("TO".to_string(), format!("{} / {} A", tr.residual_ct.primary, tr.residual_ct.secondary)),
        );
    }
    rows
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn verdict_cell(verdict: Verdict) -> String {
    let class = match verdict {
        Verdict::NotTested => "pending",
        Verdict::Passed => "passed",
        Verdict::Failed => "failed",
    };
    format!("<td class=\"{class}\">{}</td>", verdict_label(verdict))
}

fn key_value_table(rows: &[(String, String)]) -> String {
    let mut html = String::from("<table class=\"kv\">");
    for (key, value) in rows {
        html.push_str(&format!("<tr><th>{}</th><td>{}</td></tr>", escape(key), escape(value)));
    }
    html.push_str("</table>");
    html
}

const STYLE: &str = "\
body{font-family:Segoe UI,Arial,sans-serif;font-size:10.5pt;color:#1b1b1b;max-width:190mm;margin:12mm auto;padding:0 6mm}\
h1{font-size:18pt;margin:0 0 2mm}h2{font-size:13pt;margin:8mm 0 2mm;border-bottom:1px solid #888;padding-bottom:1mm}\
h3{font-size:10.5pt;margin:4mm 0 1mm}table{border-collapse:collapse;width:100%;margin:1mm 0 3mm}\
th,td{border:1px solid #bbb;padding:1mm 2mm;text-align:left;vertical-align:top}\
table.kv th{width:32%;background:#f2f2f2;font-weight:600}thead th{background:#e8e8e8}\
td.passed{color:#0a6b2d;font-weight:600}td.failed{color:#b00020;font-weight:600}td.pending{color:#666}\
p.verdict{font-size:12pt;font-weight:600}pre{margin:0;font-family:inherit;white-space:pre-wrap}\
.small{color:#555;font-size:9pt}section{break-inside:avoid-page}";

pub fn html_report(project: &Project, form: ReportForm) -> String {
    let info = &project.info;
    let mut html = String::new();
    html.push_str("<!DOCTYPE html><html lang=\"it\"><head><meta charset=\"utf-8\">");
    html.push_str(&format!(
        "<title>Rapporto di prova – {}</title><style>{STYLE}</style></head><body>",
        escape(&info.relay_name)
    ));
    html.push_str("<h1>Rapporto di prova del relè di protezione</h1>");

    html.push_str("<h2>Dati della prova</h2>");
    html.push_str(&key_value_table(&[
        ("Relè".to_string(), info.relay_name.clone()),
        ("Montante".to_string(), info.feeder.clone()),
        ("Impianto".to_string(), info.plant.clone()),
        ("Località".to_string(), info.location.clone()),
        ("Commissioning Engineer".to_string(), info.engineer.clone()),
        ("Data".to_string(), info.date.clone()),
        ("Frequenza nominale".to_string(), format!("{} Hz", project.frequency_hz)),
    ]));
    html.push_str("<h3>Trasformatori di misura</h3>");
    html.push_str(&key_value_table(&transformer_rows(&project.transformers)));

    html.push_str("<h2>Riepilogo</h2><table><thead><tr><th>ANSI</th><th>Funzione</th>");
    html.push_str("<th>Prove</th><th>Esito</th></tr></thead><tbody>");
    let mut all = Vec::new();
    for module in project.enabled_modules() {
        let plan = project.plan(module);
        let verdict = module.verdict(&plan);
        all.push(verdict);
        html.push_str(&format!(
            "<tr><td>{}</td><td>{}</td><td>{}</td>{}</tr>",
            module.function.code(),
            module.function.name(),
            plan.shots.len(),
            verdict_cell(verdict)
        ));
    }
    html.push_str("</tbody></table>");
    html.push_str(&format!(
        "<p class=\"verdict\">Esito della prova: {}</p>",
        verdict_label(overall(all))
    ));

    for module in project.enabled_modules() {
        let plan = project.plan(module);
        html.push_str(&format!(
            "<section><h2>ANSI {} – {}</h2>",
            module.function.code(),
            module.function.name()
        ));
        if form == ReportForm::Long {
            html.push_str("<h3>Tarature</h3>");
            html.push_str(&key_value_table(&module.summary()));
            if !module.use_project_transformers {
                html.push_str("<h3>Trasformatori di misura del modulo</h3>");
                html.push_str(&key_value_table(&transformer_rows(&module.transformers)));
            }
        }
        html.push_str("<h3>Risultati</h3><table><thead><tr><th>N.</th><th>Prova</th>");
        if form == ReportForm::Long {
            html.push_str("<th>Grandezze iniettate</th>");
        }
        html.push_str("<th>Atteso</th><th>Misurato</th><th>Scarto</th><th>Esito</th></tr></thead><tbody>");
        for (index, shot) in plan.shots.iter().enumerate() {
            let measured = module.result(index);
            html.push_str(&format!("<tr><td>{}</td><td>{}</td>", index + 1, escape(&shot.description)));
            if form == ReportForm::Long {
                html.push_str(&format!("<td><pre>{}</pre></td>", escape(&shot.outputs.describe())));
            }
            html.push_str(&format!(
                "<td>{}</td><td>{}</td><td>{}</td>{}</tr>",
                expected_label(&shot.expected),
                measured_label(measured),
                deviation_label(&shot.expected, measured),
                verdict_cell(assess(&shot.expected, measured))
            ));
        }
        html.push_str("</tbody></table>");
        html.push_str(&format!(
            "<p class=\"verdict\">Esito del modulo: {}</p>",
            verdict_label(module.verdict(&plan))
        ));
        if !module.notes.trim().is_empty() {
            html.push_str(&format!("<h3>Note</h3><p><pre>{}</pre></p>", escape(&module.notes)));
        }
        html.push_str("</section>");
    }

    html.push_str(&format!(
        "<p class=\"small\">Generato con ProvaRelè {}.</p></body></html>",
        env!("CARGO_PKG_VERSION")
    ));
    html
}

#[cfg(test)]
mod tests {
    use super::*;

    fn project() -> Project {
        let mut p = Project::default();
        p.info.relay_name = "7SJ82 <arrivo>".to_string();
        p.info.engineer = "M. Rossi".to_string();
        p.modules[0].enabled = true;
        p.modules[0].results = vec![
            Some(Measured::NoTrip),
            Some(Measured::Trip { time_s: 0.061 }),
            Some(Measured::Trip { time_s: 0.5 }),
        ];
        p
    }

    #[test]
    fn report_shows_the_test_data_and_only_the_enabled_functions() {
        let html = html_report(&project(), ReportForm::Long);
        assert!(html.contains("M. Rossi"));
        assert!(html.contains("ANSI 50 – Massima corrente istantanea"));
        assert!(!html.contains("ANSI 51 –"));
        assert!(html.contains("300 / 5 A, verso la linea"));
    }

    #[test]
    fn text_from_the_user_is_escaped() {
        let html = html_report(&project(), ReportForm::Short);
        assert!(html.contains("7SJ82 &lt;arrivo&gt;"));
        assert!(!html.contains("<arrivo>"));
    }

    #[test]
    fn short_form_leaves_out_settings_and_injected_quantities() {
        let p = project();
        let long = html_report(&p, ReportForm::Long);
        let short = html_report(&p, ReportForm::Short);
        assert!(long.contains("Tarature") && long.contains("Grandezze iniettate"));
        assert!(!short.contains("Tarature") && !short.contains("Grandezze iniettate"));
        assert!(short.contains("Risultati"));
    }

    #[test]
    fn failed_shot_fails_the_whole_test() {
        let html = html_report(&project(), ReportForm::Short);
        assert!(html.contains("Esito della prova: Non superata"));
        assert!(html.contains("+11 ms (+22.0 %)"));
    }

    #[test]
    fn labels_cover_every_outcome() {
        let trip = Expected::Trip { nominal_s: 0.5, min_s: 0.46, max_s: 0.54 };
        assert_eq!(expected_label(&trip), "0.500 s (0.460 – 0.540 s)");
        let open = Expected::Trip { nominal_s: 9.0, min_s: 7.0, max_s: f64::INFINITY };
        assert_eq!(expected_label(&open), "9.000 s (oltre 7.000 s)");
        assert_eq!(measured_label(None), "—");
        assert_eq!(deviation_label(&Expected::NoTrip, Some(&Measured::NoTrip)), "—");
    }
}
