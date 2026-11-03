"""CP Faggiano - esporta da Revit (via MCP) la sezione AT in IFC4 e imposta le classi IFC.

1) Revit esporta l'IFC4 della vista "CPF - Sezione AT 3D" (i DirectShape escono come IfcBuildingElementProxy)
2) dal modello Revit si legge, per ogni elemento (Tag IFC = Id Revit), apparecchio, stallo e descrizione
3) con IfcOpenShell ogni proxy diventa la classe IFC4 corretta con il suo PredefinedType, nome leggibile
   e Pset "CPF_CP_Faggiano" (Stallo, Apparecchio, Occorrenza, Descrizione, Categoria Revit)
Uso: python esporta_ifc.py <cartella_uscita> [nome_file.ifc]
"""
import sys, os, re, json, collections
sys.stdout.reconfigure(encoding="utf-8")
import ifcopenshell, ifcopenshell.api, ifcopenshell.util.element as ue
from rvt import Revit

# apparecchio -> (classe IFC4, PredefinedType, ObjectType se USERDEFINED)
CLASSI = [
    (r"^TR_MATELEC",      "IfcTransformer",               "VOLTAGE",            None),
    (r"^INT_GL313",       "IfcProtectiveDevice",          "CIRCUITBREAKER",     None),
    (r"^SEZ_S3CT_TERRA",  "IfcSwitchingDevice",           "USERDEFINED",        "DISCONNECTOR_WITH_EARTHING_SWITCH"),
    (r"^SEZ_S3C",         "IfcSwitchingDevice",           "USERDEFINED",        "DISCONNECTOR"),
    (r"^TA_DY34",         "IfcTransformer",               "CURRENT",            None),
    (r"^TV_DY46",         "IfcTransformer",               "VOLTAGE",            None),
    (r"^SCAR_",           "IfcProtectiveDevice",          "VARISTOR",           None),
    (r"^ARM_",            "IfcElectricDistributionBoard", "SWITCHBOARD",        None),
    (r"^ISO_",            "IfcDiscreteAccessory",         "USERDEFINED",        "INSULATOR"),
    (r"^MORS_",           "IfcCableFitting",              "CONNECTOR",          None),
    (r"^TERM_CAVO",       "IfcCableFitting",              "CONNECTOR",          None),
    (r"^(SBARRA_|SBARRE_|COLL_MT)", "IfcCableSegment",    "BUSBARSEGMENT",      None),
    (r"^(COND_|CAVI_MT)", "IfcCableSegment",              "CONDUCTORSEGMENT",   None),
    (r"^SOST_",           "IfcMember",                    "POST",               None),
    (r"^MURO_",           "IfcWall",                      "SOLIDWALL",          None),
    (r"^FONDAZIONE_MURO", "IfcFooting",                   "STRIP_FOOTING",      None),
    (r"^FOND",            "IfcFooting",                   "PAD_FOOTING",        None),
]

LEGGI = r'''
var ds = new FilteredElementCollector(document).OfClass(typeof(DirectShape)).Cast<DirectShape>().Where(d => d.ApplicationId == "CPF_Faggiano");
var sb = new System.Text.StringBuilder();
foreach (var d in ds) {
    System.Func<string, string> g = n => { var p = d.LookupParameter(n); return p != null ? (p.AsString() ?? "") : ""; };
    sb.Append(d.Id.Value).Append('|').Append(d.ApplicationDataId).Append('|').Append(d.Name).Append('|').Append(g("CPF_Stallo"))
      .Append('|').Append(g("CPF_Apparecchio")).Append('|').Append(g("CPF_Descrizione")).Append('|').Append(d.Category.Name).Append('\n');
}
return sb.ToString();
'''

ESPORTA = r'''
string cartella = parameters[0].ToString(), nome = parameters[1].ToString();
var v3 = new FilteredElementCollector(document).OfClass(typeof(View3D)).Cast<View3D>()
    .FirstOrDefault(v => v.Name == "CPF - Sezione AT 3D" && !v.IsTemplate);
var opt = new IFCExportOptions();
opt.FileVersion = IFCVersion.IFC4;
opt.ExportBaseQuantities = true;
opt.WallAndColumnSplitting = false;
opt.SpaceBoundaryLevel = 0;
if (v3 != null) opt.FilterViewId = v3.Id;
opt.AddOption("ExportInternalRevitPropertySets", "true");
opt.AddOption("ExportIFCCommonPropertySets", "true");
bool ok = document.Export(cartella, nome, opt);
var f = System.IO.Path.Combine(cartella, nome);
return (ok ? "OK " : "FALLITO ") + (System.IO.File.Exists(f) ? new System.IO.FileInfo(f).Length : 0) + " byte";
'''

def classe(app):
    for rx, cls, pt, ot in CLASSI:
        if re.search(rx, app):
            return cls, pt, ot
    return "IfcBuildingElementProxy", "USERDEFINED", app

if __name__ == "__main__":
    out = sys.argv[1]
    nome = sys.argv[2] if len(sys.argv) > 2 else "CP_Faggiano_Sezione_AT.ifc"
    grezzo = "_revit_" + nome
    r = Revit()
    print("export Revit:", r.code(ESPORTA, [out, grezzo]).split('"result": ')[1].split("\n")[0])
    txt = r.code(LEGGI)
    r.close()
    righe = json.loads(json.loads(txt.split("Result: ", 1)[1])["result"]).strip().split("\n")
    info = {}
    for l in righe:
        idx, key, nm, st, app, des, cat = l.split("|")
        info[idx] = dict(key=key, nome=nm, stallo=st, app=app, des=des, cat=cat)
    print("elementi letti da Revit:", len(info))

    m = ifcopenshell.open(os.path.join(out, grezzo))
    conta = collections.Counter(); senza = []
    for el in list(m.by_type("IfcBuildingElementProxy")) + list(m.by_type("IfcSlab")) + list(m.by_type("IfcWall")):
        d = info.get(str(el.Tag))
        if not d:
            senza.append(el.Tag); continue
        cls, pt, ot = classe(d["app"])
        if el.is_a() != cls:
            el = ifcopenshell.api.run("root.reassign_class", m, product=el, ifc_class=cls, predefined_type=pt)
        else:
            try:
                el.PredefinedType = pt
            except Exception:
                pass
        occ = d["key"].split("/")[-1].lstrip("@")
        el.Name = f"{d['app']} - {d['stallo']}"
        el.Description = d["des"]
        el.ObjectType = ot if ot else el.ObjectType
        el.Tag = d["key"]
        ps = ifcopenshell.api.run("pset.add_pset", m, product=el, name="CPF_CP_Faggiano")
        ifcopenshell.api.run("pset.edit_pset", m, pset=ps, properties={
            "Stallo": d["stallo"], "Apparecchio": d["app"], "Occorrenza": occ, "Descrizione": d["des"],
            "CategoriaRevit": d["cat"], "Impianto": "CP Faggiano 150/20 kV - Enel Distribuzione"})
        conta[(cls, pt if pt != "USERDEFINED" else f"USERDEFINED/{ot}")] += 1
    for p in m.by_type("IfcProject"):
        p.Name = "CP Faggiano 150/20 kV"; p.Description = "Sezione AT - 2 stalli linea, 2 stalli trafo"
    m.write(os.path.join(out, nome))
    os.remove(os.path.join(out, grezzo))
    print("senza corrispondenza Revit:", senza)
    for (c, t), n in sorted(conta.items()):
        print(f"  {c:30s} {t:45s} {n}")
    print("totale", sum(conta.values()), "->", os.path.join(out, nome), os.path.getsize(os.path.join(out, nome)), "byte")
