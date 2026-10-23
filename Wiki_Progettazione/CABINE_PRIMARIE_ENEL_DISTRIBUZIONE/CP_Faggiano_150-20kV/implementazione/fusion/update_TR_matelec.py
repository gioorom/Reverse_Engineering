# -*- coding: utf-8 -*-
# Aggiornamento modello CP Faggiano A-A: trasformatore TBEA -> MATELEC TP18781E01N (25 MVA 150/20.8 kV ONAN)
import adsk.core, adsk.fusion, traceback, math

TR_MAT = {   # mm - Matelec TP18781E01N rev.5 04/12/25 (fogli 2-4)
  "base": [2400, 5205, 300],      # piastra/carrello: larghezza, lunghezza, altezza (DC altezza)
  "vasca": [1934, 5000],          # larghezza (1934 quotata), lunghezza (DC)
  "z_coperchio": 2450,            # quota coperchio
  "AT_passo": 1650, "AT_Ztop": 4090, "AT_Xtop": 1709, "AT_incl": 30, "AT_L": 1650,   # passanti AT inclinati 30 deg verso il lato linea
  "AT_flangia": [335, 290],       # flangia passante, PCD 12 fori d16
  "MT_passo": 370, "MT_Ztop": 2850, "MT_Y": -2200,
  "rad": [700, 480, 9, 575, 600, 2820],   # profondita' (Wtot 3600), larghezza banco, n per lato, passo, z0, z1 (DC)
  "conserv": [1000, 4380, 1410, 3440],    # diametro, lunghezza, offset X, quota asse (DC)
}
PH = {"Y_fasi": [-2200, 0, 2200]}
MM = 0.1   # Fusion lavora in cm


def P3(x, y, z=0.0):
    return adsk.core.Point3D.create(x * MM, y * MM, z * MM)


VI = adsk.core.ValueInput
NEWB = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation

# =====================================================================
# PRIMITIVE (schizzo -> estrusione / rivoluzione)
# =====================================================================

def _extrude(comp, plane, profs, a0, a1, axis, op=NEWB):
    """Estrude profili da coordinata a0 ad a1 lungo l'asse 'x','y','z' del componente."""
    n = plane.geometry.normal
    s = {'x': n.x, 'y': n.y, 'z': n.z}[axis]
    s = 1 if s > 0 else -1
    inp = comp.features.extrudeFeatures.createInput(profs, op)
    inp.startExtent = adsk.fusion.OffsetStartDefinition.create(VI.createByReal(s * a0 * MM))
    d = adsk.fusion.ExtentDirections.PositiveExtentDirection if s > 0 else adsk.fusion.ExtentDirections.NegativeExtentDirection
    inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(VI.createByReal((a1 - a0) * MM)), d)
    return comp.features.extrudeFeatures.add(inp)


def _all_profiles(sk, only_rings=False):
    oc = adsk.core.ObjectCollection.create()
    for p in sk.profiles:
        if only_rings and p.profileLoops.count < 2:
            continue
        oc.add(p)
    return oc


def boxes(comp, rects, z0, z1, name=None):
    """rects: lista (x0, y0, x1, y1) in mm; estrusi tutti tra z0 e z1."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.isComputeDeferred = True
    for (x0, y0, x1, y1) in rects:
        sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P3(x0, y0)), sk.modelToSketchSpace(P3(x1, y1)))
    sk.isComputeDeferred = False
    f = _extrude(comp, comp.xYConstructionPlane, _all_profiles(sk), z0, z1, 'z')
    if name and f.bodies.count:
        f.bodies.item(0).name = name
    return f


def cyl(comp, x, y, d, z0, z1, d_in=0, name=None):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    c = sk.modelToSketchSpace(P3(x, y))
    sk.sketchCurves.sketchCircles.addByCenterRadius(c, d / 2 * MM)
    if d_in > 0:
        sk.sketchCurves.sketchCircles.addByCenterRadius(c, d_in / 2 * MM)
    f = _extrude(comp, comp.xYConstructionPlane, _all_profiles(sk, only_rings=d_in > 0), z0, z1, 'z')
    if name and f.bodies.count:
        f.bodies.item(0).name = name
    return f


def cyl_h(comp, axis, c1, c2, d, a0, a1, name=None):
    """Cilindro orizzontale lungo 'x' (c1=y, c2=z) o 'y' (c1=x, c2=z), da a0 ad a1."""
    plane = comp.yZConstructionPlane if axis == 'x' else comp.xZConstructionPlane
    sk = comp.sketches.add(plane)
    pt = P3(0, c1, c2) if axis == 'x' else P3(c1, 0, c2)
    sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(pt), d / 2 * MM)
    f = _extrude(comp, plane, _all_profiles(sk), a0, a1, axis)
    if name and f.bodies.count:
        f.bodies.item(0).name = name
    return f


def revolve(comp, rz, name=None):
    """Rivoluzione attorno all'asse Z del componente di un profilo chiuso (r, z) in mm."""
    sk = comp.sketches.add(comp.xZConstructionPlane)
    sk.isComputeDeferred = True
    L = sk.sketchCurves.sketchLines
    clean = []
    for p in rz:
        if not clean or abs(p[0] - clean[-1][0]) > 1e-3 or abs(p[1] - clean[-1][1]) > 1e-3:
            clean.append(p)
    pts = [sk.modelToSketchSpace(P3(r, 0, z)) for (r, z) in clean]
    first = L.addByTwoPoints(pts[0], pts[1])
    prev = first.endSketchPoint
    for i in range(2, len(pts)):
        prev = L.addByTwoPoints(prev, pts[i]).endSketchPoint
    L.addByTwoPoints(prev, first.startSketchPoint)
    sk.isComputeDeferred = False
    prof = sk.profiles.item(0)
    ri = comp.features.revolveFeatures.createInput(prof, comp.zConstructionAxis, NEWB)
    ri.setAngleExtent(False, VI.createByString('360 deg'))
    f = comp.features.revolveFeatures.add(ri)
    if name and f.bodies.count:
        f.bodies.item(0).name = name
    return f


def insulator_rz(z0, H, d_trunk, d_big, d_small, n_big, n_small, fb, fit_b, fit_t):
    """Profilo (r,z) di un isolatore a colonna con alette alternate grande/piccola.
    fb=(d,t) flangia base; fit_b=(d,h) raccordo inferiore; fit_t=(d,h) raccordo superiore."""
    rt = d_trunk / 2.0
    pts = [(0, z0), (fb[0] / 2.0, z0), (fb[0] / 2.0, z0 + fb[1]), (fit_b[0] / 2.0, z0 + fb[1]), (fit_b[0] / 2.0, z0 + fit_b[1]), (rt, z0 + fit_b[1])]
    zs0, zs1 = z0 + fit_b[1], z0 + H - fit_t[1]
    n = n_big + n_small
    p = (zs1 - zs0) / float(n)
    seq, b, s = [], n_big, n_small
    while b or s:
        if b: seq.append(d_big); b -= 1
        if s: seq.append(d_small); s -= 1
    for i, dd in enumerate(seq):
        z = zs0 + i * p + 0.15 * p
        th = min(12.0, 0.25 * p)
        pts += [(rt, z), (dd / 2.0, z + 0.3 * th), (dd / 2.0, z + th), (rt, z + 0.6 * p)]
    pts += [(rt, zs1), (fit_t[0] / 2.0, zs1), (fit_t[0] / 2.0, z0 + H), (0, z0 + H)]
    return pts

def _move(c, body, x, y):
    mv = adsk.core.ObjectCollection.create(); mv.add(body)
    tr = adsk.core.Matrix3D.create(); tr.translation = adsk.core.Vector3D.create(x * MM, y * MM, 0)
    mi = c.features.moveFeatures.createInput2(mv); mi.defineAsFreeMove(tr); c.features.moveFeatures.add(mi)


def f_TR_MATELEC(c):
    q = TR_MAT
    bw, bl, bh = q['base']
    boxes(c, [(-bw / 2, -bl / 2, bw / 2, bl / 2)], 0, bh, 'base_carrello')
    vw, vl = q['vasca']; zc = q['z_coperchio']
    boxes(c, [(-vw / 2, -vl / 2, vw / 2, vl / 2)], bh, zc, 'cassa')
    boxes(c, [(-vw / 2 - 40, -vl / 2 - 40, vw / 2 + 40, vl / 2 + 40)], zc, zc + 40, 'coperchio')
    rd, rw, rn, rp, rz0, rz1 = q['rad']
    rects = []
    for side in (-1, 1):
        for k in range(rn):
            yc = (k - (rn - 1) / 2.0) * rp
            x0, x1 = side * (vw / 2 + 100), side * (vw / 2 + 100 + rd)
            rects.append((min(x0, x1), yc - rw / 2, max(x0, x1), yc + rw / 2))
    boxes(c, rects, rz0, rz1, 'radiatori')
    # passanti AT (lato linea = -X), 1U a -Y
    L = q['AT_L']; a = math.radians(q['AT_incl'])
    zb = q['AT_Ztop'] - L * math.cos(a)
    xb = -(q['AT_Xtop'] - L * math.sin(a))
    for k in (-1, 0, 1):
        y = k * q['AT_passo']
        cyl(c, xb, y, 420, zc + 40, zb, name='torretta_AT')
        f1 = revolve(c, insulator_rz(0, L - 80, 170, 300, 250, 22, 21, (q['AT_flangia'][0], 25), (230, 300), (200, 80)), 'passante_AT')
        f2 = cyl(c, 0, 0, 40, L - 80, L, name='codolo_AT_d40')
        mv = adsk.core.ObjectCollection.create(); mv.add(f1.bodies.item(0)); mv.add(f2.bodies.item(0))
        m = adsk.core.Matrix3D.create()
        m.setToRotation(-a, adsk.core.Vector3D.create(0, 1, 0), adsk.core.Point3D.create(0, 0, 0))
        t = adsk.core.Matrix3D.create(); t.translation = adsk.core.Vector3D.create(xb * MM, y * MM, zb * MM)
        m.transformBy(t)
        mi = c.features.moveFeatures.createInput2(mv); mi.defineAsFreeMove(m); c.features.moveFeatures.add(mi)
    for k in range(4):
        cyl(c, (k - 1.5) * q['MT_passo'], q['MT_Y'], 200, zc + 40, q['MT_Ztop'], name='passante_MT')
    d, Lc, dx, zcen = q['conserv']
    cyl_h(c, 'y', dx, zcen, d, -Lc / 2, Lc / 2, 'conservatore')
    boxes(c, [(dx - 60, -Lc / 2 + 400, dx + 60, -Lc / 2 + 520), (dx - 60, Lc / 2 - 520, dx + 60, Lc / 2 - 400)], zc + 40, zcen, 'supporti_conservatore')
    boxes(c, [(-1090, bl / 2 + 50, -390, bl / 2 + 460)], 900, 1700, 'comando_motore_CSC')
    boxes(c, [(-350, bl / 2 + 50, 350, bl / 2 + 500)], 600, 1500, 'cassetta_ausiliari')

def conductor(comp, polylines, d, name):
    """Conduttori di collegamento come geometria 'muta' (base feature): cilindri + sfere ai nodi."""
    tbm = adsk.fusion.TemporaryBRepManager.get()
    r = d / 2.0 * MM
    bf = comp.features.baseFeatures.add()
    bf.startEdit()
    for pl in polylines:
        UN = adsk.fusion.BooleanTypes.UnionBooleanType
        body = None
        for i in range(len(pl) - 1):
            seg = tbm.createCylinderOrCone(P3(*pl[i]), r, P3(*pl[i + 1]), r)
            if body is None:
                body = seg
            else:
                tbm.booleanOperation(body, seg, UN)
            if i + 1 < len(pl) - 1:
                tbm.booleanOperation(body, tbm.createSphere(P3(*pl[i + 1]), r), UN)
        b = comp.bRepBodies.add(body, bf)
        b.name = name
    bf.finishEdit()



def run(context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        root = des.rootComponent
        byname = {c.name: c for c in des.allComponents}
        libc = byname['00_LIBRERIA_ORGANI']; ST = byname['STALLO_TRAFO']
        for P in (ST, libc):   # solo occorrenze native (mai proxy annidati)
            for o in [o for o in P.occurrences if o.component.name in ('TR_TBEA_25MVA', 'COND_TRAFO')]:
                o.deleteMe()
        occ = libc.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        c = occ.component; c.name = 'TR_MATELEC_25MVA'
        f_TR_MATELEC(c)
        c.description = 'Trasformatore Matelec 25 MVA ONAN 150/20.8 kV CSC (TP18781E01N)'
        c.attributes.add('BIM', 'IfcClass', 'IfcTransformer')
        c.attributes.add('BIM', 'Fonte', 'Matelec TP18781E01N rev.5')
        XTR, ZTR = 23700, 650
        m = adsk.core.Matrix3D.create(); m.translation = adsk.core.Vector3D.create(XTR * MM, 0, ZTR * MM)
        o = ST.occurrences.addExistingComponent(c, m); o.attributes.add('BIM', 'Tag', 'TR9')
        # conduttori stallo trafo (ricostruiti)
        CT = []
        for i, y in enumerate(PH['Y_fasi']):
            CT.append([(5525, y, 4650), (6025, y, 4650), (7550, y, 6230), (7950, y, 6230)])
            CT.append([(8470, y, 4500), (8970, y, 4500), (9970, y, 5300), (10370, y, 5300)])
            CT.append([(11030, y, 5300), (11430, y, 5300), (13100, y, 6693), (13700, y, 6693)])
            CT.append([(13700, y, 6693), (19200, y, 6700)])
            yt = (i - 1) * TR_MAT['AT_passo']
            CT.append([(19200, y, 6700), (20600, y, 6700), (XTR - TR_MAT['AT_Xtop'], yt, ZTR + TR_MAT['AT_Ztop'])])
        cc = ST.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        cc.name = 'COND_TRAFO'
        conductor(cc, CT, 40, 'conduttore_LM1050-11')
        app.activeDocument.save('Trasformatore Matelec al posto di TBEA')
        print('OK')
    except:
        print('ERRORE:\n' + traceback.format_exc())
