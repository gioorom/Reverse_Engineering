"""Verifica in Revit: conteggio elementi CPF per categoria/stallo, vista 3D dedicata e immagine PNG."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
from rvt import Revit

CODICE = r'''
var ds = new FilteredElementCollector(document).OfClass(typeof(DirectShape)).Cast<DirectShape>()
    .Where(d => d.ApplicationId == "CPF_Faggiano").ToList();
var perCat = ds.GroupBy(d => d.Category.Name).Select(g => g.Key + ": " + g.Count());
var perSt = ds.GroupBy(d => { var p = d.LookupParameter("CPF_Stallo"); return p != null ? p.AsString() : "?"; }).Select(g => g.Key + ": " + g.Count());
BoundingBoxXYZ bb = null;
foreach (var d in ds) { var b = d.get_BoundingBox(null); if (b == null) continue;
    if (bb == null) { bb = new BoundingBoxXYZ { Min = b.Min, Max = b.Max }; }
    else { bb.Min = new XYZ(System.Math.Min(bb.Min.X, b.Min.X), System.Math.Min(bb.Min.Y, b.Min.Y), System.Math.Min(bb.Min.Z, b.Min.Z));
           bb.Max = new XYZ(System.Math.Max(bb.Max.X, b.Max.X), System.Math.Max(bb.Max.Y, b.Max.Y), System.Math.Max(bb.Max.Z, b.Max.Z)); } }
// vista 3D dedicata
var nome = "CPF - Sezione AT 3D";
var v3 = new FilteredElementCollector(document).OfClass(typeof(View3D)).Cast<View3D>().FirstOrDefault(v => v.Name == nome && !v.IsTemplate);
if (v3 == null) {
    var vft = new FilteredElementCollector(document).OfClass(typeof(ViewFamilyType)).Cast<ViewFamilyType>().First(t => t.ViewFamily == ViewFamily.ThreeDimensional);
    v3 = View3D.CreateIsometric(document, vft.Id); v3.Name = nome;
}
v3.DetailLevel = ViewDetailLevel.Fine;
v3.DisplayStyle = DisplayStyle.ShadingWithEdges;
string png = System.IO.Path.Combine(parameters[0].ToString(), "revit_sezione_AT");
var opt = new ImageExportOptions { ZoomType = ZoomFitType.FitToPage, PixelSize = 1800, FilePath = png,
    FitDirection = FitDirectionType.Horizontal, HLRandWFViewsFileType = ImageFileType.PNG, ShadowViewsFileType = ImageFileType.PNG,
    ImageResolution = ImageResolution.DPI_150, ExportRange = ExportRange.SetOfViews };
opt.SetViewsAndSheets(new List<ElementId> { v3.Id });
string exp;
try { document.ExportImage(opt); exp = "immagine esportata"; } catch (System.Exception ex) { exp = "export immagine non riuscito: " + ex.Message; }
double f = 304.8;
return "DirectShape CPF: " + ds.Count + " | " + string.Join(", ", perCat) + " | stalli: " + string.Join(", ", perSt)
    + " | ingombro mm: X " + (bb.Min.X * f).ToString("0") + ".." + (bb.Max.X * f).ToString("0") + " Y " + (bb.Min.Y * f).ToString("0") + ".." + (bb.Max.Y * f).ToString("0")
    + " Z " + (bb.Min.Z * f).ToString("0") + ".." + (bb.Max.Z * f).ToString("0") + " | vista: " + nome + " (id " + v3.Id + ") | " + exp;
'''

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\pietr\Desktop\sc_mcp\revit"
    r = Revit()
    print(r.code(CODICE, [out]))
    r.close()
