"""Allinea in Revit i parametri IfcExportAs / IfcExportType alle classi IFC4 usate nell'export (esporta_ifc.CLASSI)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from rvt import Revit
from esporta_ifc import CLASSI

CODICE = r'''
try {
    var regole = new List<string[]>();
    foreach (var o in parameters[0].ToString().Split(new[] { ";;" }, System.StringSplitOptions.RemoveEmptyEntries)) regole.Add(o.Split('~'));
    int n = 0;
    foreach (var d in new FilteredElementCollector(document).OfClass(typeof(DirectShape)).Cast<DirectShape>().Where(x => x.ApplicationId == "CPF_Faggiano").ToList()) {
        var pa = d.LookupParameter("CPF_Apparecchio");
        string app = pa != null ? (pa.AsString() ?? "") : "";
        string[] r = null;
        foreach (var x in regole) if (System.Text.RegularExpressions.Regex.IsMatch(app, x[0])) { r = x; break; }
        if (r == null) continue;
        var p1 = d.LookupParameter("IfcExportAs"); if (p1 != null) p1.Set(r[1]);
        var p2 = d.LookupParameter("IfcExportType"); if (p2 != null) p2.Set(r[2] == "USERDEFINED" ? r[3] : r[2]);
        n++;
    }
    return "aggiornati " + n;
} catch (System.Exception ex) { return "ERR " + ex.ToString(); }
'''

r = Revit()
print(r.code(CODICE, [";;".join("~".join([rx, c, pt, ot or ""]) for rx, c, pt, ot in CLASSI)]))
r.close()
