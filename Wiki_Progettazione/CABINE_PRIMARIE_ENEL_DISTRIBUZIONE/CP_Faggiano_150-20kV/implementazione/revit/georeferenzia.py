"""CP Faggiano - georeferenziazione PROVVISORIA del modello Revit e dell'IFC.

!!! VALORI PROVVISORI DA VERIFICARE con la planimetria P-001 o il rilievo !!!
L'origine del modello (asse 7, quota +-0.00 = piano piazzale) e' messa al centro di Faggiano (TA),
non sulla CP reale; l'asse X del sito (lungo lo stallo, verso il TR) e' preso verso Est (rotazione 0).
Quando hai i dati veri cambia solo i parametri qui sotto e rilancia.

Revit : posizione di progetto (coordinate condivise) e luogo (lat/long)
IFC   : IfcProjectedCRS + IfcMapConversion (IFC4) e RefLatitude/RefLongitude/RefElevation di IfcSite
Uso: python georeferenzia.py <ifc_in> <ifczip_out>
"""
import sys, os, math, zipfile
sys.stdout.reconfigure(encoding="utf-8")
import ifcopenshell, ifcopenshell.api
from rvt import Revit

# ---- parametri di georeferenziazione (PROVVISORI) ----
EPSG = "EPSG:6708"                 # RDN2008 / UTM zona 33N (ETRF2000), quote Genova 1942
EST_m, NORD_m = 702180.00, 4476770.00   # coordinate dell'origine del modello (asse 7, +-0.00)
QUOTA_m = 56.00                    # quota s.l.m. del piano piazzale (+-0.00)
ROTAZIONE_deg = 0.0                # angolo dell'asse X del sito rispetto all'Est, antiorario
LAT, LON = 40.417, 17.383          # WGS84 dell'origine (coerente con EST/NORD)
LUOGO = "Faggiano (TA) - CP 150/20 kV - POSIZIONE PROVVISORIA da verificare"

REVIT = r'''
double ft = 1.0 / 0.3048;
var p = parameters[0].ToString().Split('|');
var inv = System.Globalization.CultureInfo.InvariantCulture;
double est = double.Parse(p[0], inv), nord = double.Parse(p[1], inv), quota = double.Parse(p[2], inv), rot = double.Parse(p[3], inv);
double lat = double.Parse(p[4], inv), lon = double.Parse(p[5], inv);
var site = document.SiteLocation;
site.Latitude = lat * System.Math.PI / 180.0;
site.Longitude = lon * System.Math.PI / 180.0;
try { site.PlaceName = p[6]; } catch { }
var loc = document.ActiveProjectLocation;
// rotazione del Nord di progetto rispetto al Nord reale: l'asse X del sito ruotato di 'rot' rispetto all'Est
loc.SetProjectPosition(XYZ.Zero, new ProjectPosition(est * ft, nord * ft, quota * ft, rot * System.Math.PI / 180.0));
var pp = loc.GetProjectPosition(XYZ.Zero);
return "posizione: E " + (pp.EastWest / ft).ToString("0.00", inv) + " N " + (pp.NorthSouth / ft).ToString("0.00", inv)
     + " quota " + (pp.Elevation / ft).ToString("0.00", inv) + " rotazione " + (pp.Angle * 180 / System.Math.PI).ToString("0.000", inv)
     + " | lat " + (site.Latitude * 180 / System.Math.PI).ToString("0.00000", inv) + " lon " + (site.Longitude * 180 / System.Math.PI).ToString("0.00000", inv);
'''

def dms(x):
    s = 1 if x >= 0 else -1; x = abs(x)
    d = int(x); m = int((x - d) * 60); sec = (x - d - m / 60) * 3600
    return [s * d, s * m, s * int(sec), s * int(round((sec - int(sec)) * 1e6))]

def georef_ifc(src, dst_zip):
    m = ifcopenshell.open(src)
    ctx = [c for c in m.by_type("IfcGeometricRepresentationContext") if not c.is_a("IfcGeometricRepresentationSubContext")]
    for c in ctx:                          # elimina eventuali georeferenziazioni precedenti
        for op in list(getattr(c, "HasCoordinateOperation", []) or []):
            if op.TargetCRS: m.remove(op.TargetCRS)
            m.remove(op)
    crs = m.create_entity("IfcProjectedCRS", Name=EPSG, Description="RDN2008 / UTM zone 33N - POSIZIONE PROVVISORIA",
                          GeodeticDatum="RDN2008", VerticalDatum="Genova 1942", MapProjection="UTM", MapZone="33N",
                          MapUnit=m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE"))
    a = math.radians(ROTAZIONE_deg)
    for c in ctx:
        m.create_entity("IfcMapConversion", SourceCRS=c, TargetCRS=crs, Eastings=EST_m, Northings=NORD_m,
                        OrthogonalHeight=QUOTA_m, XAxisAbscissa=math.cos(a), XAxisOrdinate=math.sin(a), Scale=0.001)
        # Nord reale espresso nel sistema del modello (con rotazione 0 coincide con +Y)
        c.TrueNorth = m.create_entity("IfcDirection", DirectionRatios=(-math.sin(a), math.cos(a)))
    for s in m.by_type("IfcSite"):
        s.RefLatitude, s.RefLongitude, s.RefElevation = dms(LAT), dms(LON), QUOTA_m
        s.LandTitleNumber = None
        s.Description = LUOGO
    out_ifc = os.path.join(os.path.dirname(src), os.path.basename(dst_zip).replace(".ifczip", ".ifc"))
    m.write(out_ifc)
    with zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(out_ifc, os.path.basename(out_ifc))
    # verifica
    v = ifcopenshell.open(out_ifc)
    mc = v.by_type("IfcMapConversion")[0]
    print("IFC:", mc.TargetCRS.Name, "E", mc.Eastings, "N", mc.Northings, "H", mc.OrthogonalHeight, "scala", mc.Scale,
          "| IfcSite lat", v.by_type("IfcSite")[0].RefLatitude, "lon", v.by_type("IfcSite")[0].RefLongitude)
    print("scritto", dst_zip, os.path.getsize(dst_zip), "byte")

if __name__ == "__main__":
    r = Revit()
    arg = "|".join(map(str, [EST_m, NORD_m, QUOTA_m, ROTAZIONE_deg, LAT, LON, LUOGO]))
    print("Revit:", r.code(REVIT, [arg]).split('"result": ')[1].split("\n")[0])
    r.close()
    if len(sys.argv) > 2:
        georef_ifc(sys.argv[1], sys.argv[2])
