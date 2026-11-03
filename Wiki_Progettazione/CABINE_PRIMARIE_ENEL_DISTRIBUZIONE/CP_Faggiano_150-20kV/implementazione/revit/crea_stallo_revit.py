"""CP Faggiano 150/20 kV - crea in Revit (via MCP, send_code_to_revit) la sezione AT come DirectShape BIM.

Passi:
  0) pulizia degli elementi gia' importati (ApplicationId = CPF_Faggiano), parametri condivisi
     (IfcExportAs, IfcExportType, CPF_Stallo, CPF_Apparecchio, CPF_Descrizione) legati alle categorie
  1) un lotto alla volta (file di testo da prepara_mesh.py): materiali, un DirectShape per apparecchio
     con categoria Revit, nome, parametri BIM e materiale per faccia
Unita': i lotti sono in mm (frame sito), Revit lavora in piedi -> /304.8.
Uso: python crea_stallo_revit.py <cartella lotti> [primo_lotto] [ultimo_lotto]
"""
import sys, os, glob, json, time
sys.stdout.reconfigure(encoding="utf-8")
from rvt import Revit

SETUP = r'''
var app = document.Application;
var tx = document.IsModifiable ? null : new Transaction(document, "CPF - preparazione");
if (tx != null) tx.Start();
// 1) pulizia
var old = new FilteredElementCollector(document).OfClass(typeof(DirectShape)).Cast<DirectShape>()
    .Where(d => d.ApplicationId == "CPF_Faggiano").Select(d => d.Id).ToList();
if (old.Count > 0) document.Delete(old);
// 2) parametri condivisi
string[] nomi = { "IfcExportAs", "IfcExportType", "CPF_Stallo", "CPF_Apparecchio", "CPF_Descrizione" };
string spf = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "CPF_SharedParameters.txt");
if (!System.IO.File.Exists(spf)) System.IO.File.WriteAllText(spf, "");
string prev = app.SharedParametersFilename;
app.SharedParametersFilename = spf;
var def = app.OpenSharedParameterFile();
var grp = def.Groups.get_Item("CP_Faggiano") ?? def.Groups.Create("CP_Faggiano");
var cats = new CategorySet();
foreach (var bic in new[] { BuiltInCategory.OST_ElectricalEquipment, BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_GenericModel, BuiltInCategory.OST_StructuralFraming, BuiltInCategory.OST_StructuralFoundation,
    BuiltInCategory.OST_Walls })
    cats.Insert(Category.GetCategory(document, bic));
int legati = 0;
foreach (var n in nomi) {
    var d = grp.Definitions.get_Item(n) ?? grp.Definitions.Create(new ExternalDefinitionCreationOptions(n, SpecTypeId.String.Text));
    var b = app.Create.NewInstanceBinding(cats);
    if (document.ParameterBindings.Contains(d)) { document.ParameterBindings.ReInsert(d, b, GroupTypeId.IdentityData); }
    else if (document.ParameterBindings.Insert(d, b, GroupTypeId.IdentityData)) legati++;
}
if (!string.IsNullOrEmpty(prev)) app.SharedParametersFilename = prev;
if (tx != null) tx.Commit();
return "rimossi " + old.Count + " DirectShape precedenti, parametri nuovi legati: " + legati;
'''

LOTTO = r'''
string path = parameters[0].ToString();
double k = 1.0 / 304.8;
double tol = document.Application.ShortCurveTolerance;   // ~0.8 mm: lati piu' corti non sono accettati da Revit
var lines = System.IO.File.ReadAllLines(path);
var tx = document.IsModifiable ? null : new Transaction(document, "CPF - lotto " + System.IO.Path.GetFileName(path));
if (tx != null) tx.Start();
var mats = new Dictionary<int, ElementId>();
var allMats = new FilteredElementCollector(document).OfClass(typeof(Material)).Cast<Material>().ToList();
int creati = 0, facceScartate = 0; var errori = new List<string>();
string[] cur = null; var geo = new List<GeometryObject>(); int corpiScartati = 0; ElementId curMat = ElementId.InvalidElementId;
List<XYZ> pts = null; int nTri = 0;
System.Action chiudi = () => {
    if (cur == null) return;
    try {
        if (geo.Count == 0) throw new System.Exception("nessuna geometria valida");
        var bic = (BuiltInCategory)System.Enum.Parse(typeof(BuiltInCategory), cur[3]);
        var catId = new ElementId(bic);
        if (!DirectShape.IsValidCategoryId(catId, document)) catId = new ElementId(BuiltInCategory.OST_GenericModel);
        var ds = DirectShape.CreateElement(document, catId);
        ds.ApplicationId = "CPF_Faggiano"; ds.ApplicationDataId = cur[1];
        ds.SetShape(geo);
        ds.SetName(cur[2]);
        System.Action<string, string> setp = (n, v) => { var p = ds.LookupParameter(n); if (p != null && !p.IsReadOnly) p.Set(v); };
        setp("IfcExportAs", cur[4]); setp("IfcExportType", cur[5]); setp("CPF_Stallo", cur[6]);
        setp("CPF_Apparecchio", cur[7]); setp("CPF_Descrizione", cur[8]);
        var pc = ds.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS); if (pc != null) pc.Set(cur[8]);
        var pm = ds.get_Parameter(BuiltInParameter.ALL_MODEL_MARK); if (pm != null) pm.Set(cur[1]);
        creati++;
    } catch (System.Exception ex) { errori.Add(cur[1] + ": " + ex.Message); }
    cur = null;
};
foreach (var l in lines) {
    if (l.StartsWith("MAT|")) {
        var a = l.Split('|');
        var m = allMats.FirstOrDefault(x => x.Name == a[2]);
        if (m == null) {
            var id = Material.Create(document, a[2]); m = document.GetElement(id) as Material; allMats.Add(m);
            m.Color = new Color(byte.Parse(a[3]), byte.Parse(a[4]), byte.Parse(a[5]));
            m.MaterialClass = "CP Faggiano";
        }
        mats[int.Parse(a[1])] = m.Id;
    } else if (l.StartsWith("E|")) {
        chiudi();
        cur = l.Split('|'); geo = new List<GeometryObject>(); nTri = 0;
    } else if (l.StartsWith("M|")) {
        var a = l.Split('|'); curMat = mats[int.Parse(a[1])];
    } else if (l.StartsWith("V|")) {
        var s = l.Substring(2).Split(' ');
        pts = new List<XYZ>(s.Length / 3);
        for (int i = 0; i + 2 < s.Length; i += 3)
            pts.Add(new XYZ(double.Parse(s[i], System.Globalization.CultureInfo.InvariantCulture) * k,
                            double.Parse(s[i + 1], System.Globalization.CultureInfo.InvariantCulture) * k,
                            double.Parse(s[i + 2], System.Globalization.CultureInfo.InvariantCulture) * k));
    } else if (l.StartsWith("T|")) {
        var s = l.Substring(2).Split(' ');
        var tsb = new TessellatedShapeBuilder();       // un costruttore per corpo: un errore scarta solo quel corpo
        tsb.OpenConnectedFaceSet(false);
        int n = 0;
        for (int i = 0; i + 2 < s.Length; i += 3) {
            var p0 = pts[int.Parse(s[i])]; var p1 = pts[int.Parse(s[i + 1])]; var p2 = pts[int.Parse(s[i + 2])];
            if (p0.DistanceTo(p1) < tol || p1.DistanceTo(p2) < tol || p2.DistanceTo(p0) < tol ||
                (p1 - p0).CrossProduct(p2 - p0).GetLength() < tol * tol) { facceScartate++; continue; }
            tsb.AddFace(new TessellatedFace(new List<XYZ> { p0, p1, p2 }, curMat)); n++;
        }
        tsb.CloseConnectedFaceSet();
        if (n == 0) continue;
        bool ok = false;
        for (int tent = 0; tent < 2; tent++) {
            try {
                tsb.Target = tent == 0 && n <= 4000 ? TessellatedShapeBuilderTarget.AnyGeometry : TessellatedShapeBuilderTarget.Mesh;
                tsb.Fallback = tent == 0 ? TessellatedShapeBuilderFallback.Mesh : TessellatedShapeBuilderFallback.Salvage;
                tsb.Build();
                geo.AddRange(tsb.GetBuildResult().GetGeometricalObjects()); nTri += n; ok = true;
                break;
            } catch { }
        }
        if (!ok) corpiScartati++;
    }
}
chiudi();
if (tx != null) tx.Commit();
return System.IO.Path.GetFileName(path) + ": creati " + creati + ", facce degeneri scartate " + facceScartate + ", corpi scartati " + corpiScartati + (errori.Count > 0 ? ", ERRORI: " + string.Join(" ; ", errori.Take(10)) : "");
'''

if __name__ == "__main__":
    D = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\pietr\Desktop\sc_mcp\revit\lotti"
    files = sorted(glob.glob(os.path.join(D, "lotto_*.txt")))
    a = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    b = int(sys.argv[3]) if len(sys.argv) > 3 else len(files) - 1
    r = Revit()
    if a == 0:
        print(r.code(SETUP), flush=True)
    for f in files[a:b + 1]:
        t0 = time.time()
        try:
            print(r.code(LOTTO, [f]).replace("Code execution successful!\nResult: ", ""), f"({time.time() - t0:.0f} s)", flush=True)
        except Exception as e:
            print("ERRORE", os.path.basename(f), str(e)[:1500], flush=True)
            break
    r.close()
