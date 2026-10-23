# -*- coding: utf-8 -*-
# Fase 2 - CP Faggiano: secondo stallo (linea+trafo), sezionatore longitudinale di sbarra 6'',
# completamento sistema sbarre (2 semisbarre, 2 portali) e castelletto portaterminali MT (C-045 / E-020).
import adsk.core, adsk.fusion, traceback, math

P2 = {
  "dY_stallo2": 12400,          # P-006 B-B: 4.20 + 6.20 + 6.20 + 4.20 (6' - 6'' - 6')
  "Y_portale2": 16600, "Y_sez_long": 6200,
  "sbarra1": [-4500, 4850], "sbarra2": [7550, 16900],     # semisbarre (DC: estremi)
  "Z_sbarre": 7200, "ZF": 200, "H_portale_sb": 5350,
  # S3C riprodotto come nella libreria (sez. longitudinale = S3C su sostegno alto)
  "S3C": {"interasse_col": 1120, "telaio": [2500, 300, 150], "col_H": 1450, "col": [150, 230, 190, 15, 14], "lama": [2300, 80, 50], "z_lama": 1660},
  # castelletto MT (C-045): montanti 2xUPN180 H4450, interasse 2600, testa P19 a +4.580
  "CMT": {"interasse": 2600, "H": 4450, "z0": 30, "cap": [940, 100], "z_mensola_term": 4218,
          "P11": [3680, 3800], "P9": [2928, 3008], "telaio": [1420, 748], "z_telaio": 4180,
          "reggicavo_z": [724, 1724, 2724], "X": 23700, "Y": -5200},
  "C8_125": {"H": 255, "trunk": 90, "big": 160, "small": 135, "nb": 3, "ns": 2},       # DC
  "TERM": {"z0": 4218, "z1": 4835, "d": 90, "shed": 150},                               # DC
  "TR_MT": {"x": [-185, 185, 555], "y": -2200, "z": 650 + 2850, "XTR": 23700},
}
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


def f_sost_alto(c):
    """Sostegno sezionatore longitudinale di sbarra: 2 colonne d219.1 + trave, H 5350 (DC, da P-006 B-B)."""
    H = P2['H_portale_sb']
    for x in (-700, 700):
        boxes(c, [(x - 275, -275, x + 275, 275)], 0, 15, 'piastra_base')
        cyl(c, x, 0, 219.1, 15, H - 100, 219.1 - 11.8, 'colonna')
    boxes(c, [(-1300, -125, 1300, 125)], H - 100, H, 'trave')


def f_C8125(c):
    q = P2['C8_125']
    revolve(c, insulator_rz(0, q['H'], q['trunk'], q['big'], q['small'], q['nb'], q['ns'], (120, 12), (100, 45), (100, 40)), 'isolatore_C8-125')


def f_terminale(c):
    q = P2['TERM']; h = q['z1'] - q['z0']
    revolve(c, insulator_rz(0, h - 60, q['d'], q['shed'], q['shed'] - 20, 3, 2, (110, 30), (110, 120), (70, 60)), 'terminale_unipolare')
    boxes(c, [(-50, -6, 50, 6)], h - 60, h, 'capocorda')


def f_castelletto(c):
    q = P2['CMT']; a = q['interasse'] / 2.0; z0 = q['z0']; zt = z0 + q['H']
    for s in (-1, 1):
        x = s * a
        boxes(c, [(x - 225, -225, x + 225, 225)], 0, z0, 'piastra_base')
        boxes(c, [(x - 90, -125, x - 25, 125), (x + 25, -125, x + 90, 125)], z0, zt, 'montante_2UPN180')
        boxes(c, [(x - 90, -q['cap'][0] / 2, x + 90, q['cap'][0] / 2)], zt, zt + q['cap'][1], 'testa_P19_UPN100')
        zm = q['z_mensola_term']
        boxes(c, [(x - 270, -470, x - 190, 470), (x + 190, -470, x + 270, 470)], zm - 80, zm, 'mensola_porta_terminali')
        boxes(c, [(x - 190, -40, x - 90, 40), (x + 90, -40, x + 190, 40)], zm - 80, zm, 'staffe_mensola')
        for k, zz in enumerate(q['reggicavo_z']):
            boxes(c, [(x - 360, -50, x - 90, 50), (x + 90, -50, x + 360, 50)], zz, zz + 50, 'mensola_reggicavo')
    boxes(c, [(-a + 90, 125, a - 90, 185)], q['P11'][0], q['P11'][1], 'P11_UPN120')
    boxes(c, [(-a + 90, 125, a - 90, 165)], q['P9'][0], q['P9'][1], 'P9_L80x5')
    w, d = q['telaio']; zt2 = q['z_telaio']
    yf = 125 + d
    boxes(c, [(-w / 2, 185, -w / 2 + 80, yf), (w / 2 - 80, 185, w / 2, yf)], q['P11'][0], q['P11'][1] - 60, 'telaio_longheroni')
    boxes(c, [(-w / 2, yf - 80, -w / 2 + 80, yf), (w / 2 - 80, yf - 80, w / 2, yf)], q['P11'][1] - 60, zt2 - 60, 'telaio_montanti_P15')
    boxes(c, [(-w / 2, yf - 80, w / 2, yf)], zt2 - 60, zt2, 'telaio_trave_P16')
    boxes(c, [(-w / 2, 125, -w / 2 + 60, 185), (w / 2 - 60, 125, w / 2, 185)], q['P9'][1], q['P11'][0], 'P10_montanti')


def f_sbarre_MT(c):
    """Sbarre Cu 100x10 di testa (una per fase) lungo X, in costa."""
    q = P2['CMT']; a = q['interasse'] / 2.0
    zb = q['z0'] + q['H'] + q['cap'][1] + P2['C8_125']['H']
    boxes(c, [(-a - 400, y - 5, a + 400, y + 5) for y in (-370, 0, 370)], zb, zb + 100, 'barra_Cu_100x10')
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
        libc = byname['00_LIBRERIA_ORGANI']
        site = byname['CP_FAGGIANO_AT_ProfiloA-A']
        SL, SB, ST = byname['STALLO_LINEA'], byname['SISTEMA_SBARRE'], byname['STALLO_TRAFO']
        site.name = 'CP_FAGGIANO_150-20kV'

        def newlib(name, fn, ifc, descr, fonte):
            c = libc.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
            c.name = name; fn(c); c.description = descr
            c.attributes.add('BIM', 'IfcClass', ifc); c.attributes.add('BIM', 'Fonte', fonte)
            return c

        def place(parent, comp, x, y, z, rot=0.0, tag=None):
            m = adsk.core.Matrix3D.create()
            if rot:
                m.setToRotation(math.radians(rot), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
            m.translation = adsk.core.Vector3D.create(x * MM, y * MM, z * MM)
            o = parent.occurrences.addExistingComponent(comp, m)
            if tag:
                o.attributes.add('BIM', 'Tag', tag)
            return o

        # ---------- castelletto MT nello stallo trafo ----------
        CST = newlib('SOST_PORTATERMINALI_MT', f_castelletto, 'IfcMember', 'Sostegno portaterminali MT trasformatore (castelletto) 2xUPN180 H4450', 'C-045 / E-020')
        ISO_MT = newlib('ISO_MT_C8-125', f_C8125, 'IfcDiscreteAccessory', 'Isolatore portante MT C8-125 (DC)', 'E-020')
        TERM = newlib('TERM_CAVO_MT_unipolare', f_terminale, 'IfcCableFitting', 'Terminale cavo MT unipolare per esterno (DC)', 'E-020')
        BMT = newlib('SBARRE_MT_CU100x10', f_sbarre_MT, 'IfcCableCarrierSegment', 'Sbarre Cu 100x10 castelletto MT', 'E-020')
        q = P2['CMT']; X0, Y0 = q['X'], q['Y']; a = q['interasse'] / 2.0
        zcap = q['z0'] + q['H'] + q['cap'][1]
        place(ST, CST, X0, Y0, 0, tag='CMT')
        place(ST, BMT, X0, Y0, 0)
        yf = 125 + q['telaio'][1] - 40
        for i, y in enumerate((-370, 0, 370)):
            for s in (-1, 1):
                place(ST, ISO_MT, X0 + s * a, Y0 + y, zcap)
                for dx in (-230, 230):
                    place(ST, TERM, X0 + s * a + dx, Y0 + y, q['z_mensola_term'])
            place(ST, ISO_MT, X0 + (i - 1) * 370, Y0 + yf, q['z_telaio'])
        # collegamenti MT: passanti TR -> isolatori telaio -> sbarre di testa; cavi lungo i montanti
        zb = zcap + P2['C8_125']['H']
        zi = q['z_telaio'] + P2['C8_125']['H']
        tm = P2['TR_MT']
        CM, CV = [], []
        for i, xb in enumerate(tm['x']):
            xi = X0 + (i - 1) * 370
            yi = Y0 + (i - 1) * 370
            CM.append([(tm['XTR'] + xb, tm['y'], tm['z']), (tm['XTR'] + xb, tm['y'], zi + 150), (xi, Y0 + yf, zi + 150), (xi, Y0 + yf, zi)])
            CM.append([(xi, Y0 + yf, zi), (xi, Y0 + yf, zb + 350), (xi, yi, zb + 350), (xi, yi, zb + 100)])
            for s in (-1, 1):
                for dx in (-230, 230):
                    xx = X0 + s * a + dx
                    CV.append([(xx, Y0 + (i - 1) * 370, q['z_mensola_term']), (xx + (60 if dx > 0 else -60), Y0 + (i - 1) * 370, q['z_mensola_term'] - 300), (xx + (60 if dx > 0 else -60), Y0 + (i - 1) * 370, 0)])
        cc = ST.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        cc.name = 'COLL_MT_TR-CASTELLETTO'
        conductor(cc, CM, 40, 'collegamento_MT')
        cv = ST.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        cv.name = 'CAVI_MT_USCITA'
        conductor(cv, CV, 50, 'cavo_MT')

        # ---------- secondo stallo: nuove occorrenze dei sottoassiemi ----------
        for oc in site.occurrences:
            if oc.component.name in ('STALLO_LINEA', 'STALLO_TRAFO'):
                oc.attributes.add('BIM', 'Stallo', '1')
        dY = P2['dY_stallo2']
        for comp_ in (SL, ST):
            m = adsk.core.Matrix3D.create(); m.translation = adsk.core.Vector3D.create(0, dY * MM, 0)
            o = site.occurrences.addExistingComponent(comp_, m)
            o.attributes.add('BIM', 'Stallo', '2')

        # ---------- sistema sbarre: 2 semisbarre, 2 portali, sezionatore longitudinale ----------
        if 'SBARRA_AL100-90' in byname:
            for P in (SB, libc):   # solo occorrenze native (mai proxy annidati)
                for o in [o for o in P.occurrences if o.component.name == 'SBARRA_AL100-90']:
                    o.deleteMe()
        L1 = P2['sbarra1'][1] - P2['sbarra1'][0]
        def f_sb(L):
            def b(c):
                sk = c.sketches.add(c.xZConstructionPlane)
                cc0 = sk.modelToSketchSpace(P3(0, 0, 0))
                sk.sketchCurves.sketchCircles.addByCenterRadius(cc0, 5.0)
                sk.sketchCurves.sketchCircles.addByCenterRadius(cc0, 4.5)
                f = _extrude(c, c.xZConstructionPlane, _all_profiles(sk, True), 0, L, 'y')
                f.bodies.item(0).name = 'tubo_Al_100_90'
            return b
        SBR = newlib('SBARRA_AL100-90_L%d' % L1, f_sb(L1), 'IfcCableCarrierSegment', 'Semisbarra tubo Al 100/90 LC1050/60', 'P-006')
        XB = [-2200, 0, 2200]; F = ['L1', 'L2', 'L3']
        for i, xb in enumerate(XB):
            place(SB, SBR, xb, P2['sbarra1'][0], P2['Z_sbarre'], tag='SB1-' + F[i])
            place(SB, SBR, xb, P2['sbarra2'][0], P2['Z_sbarre'], tag='SB2-' + F[i])
        zP2 = P2['ZF'] + P2['H_portale_sb']
        place(SB, byname['SOST_LS6096-2_H5350'], 0, P2['Y_portale2'], P2['ZF'])
        for i, xb in enumerate(XB):
            place(SB, byname['ISO_DJ1003'], xb, P2['Y_portale2'], zP2, tag='IS7b-' + F[i])
            place(SB, byname['MORS_LM1041'], xb, P2['Y_portale2'], zP2 + 1500)
        # sezionatore longitudinale 6'' (S3C, lama lungo Y) su sostegno alto
        SA = newlib('SOST_SEZ_LONG_H5350', f_sost_alto, 'IfcMember', 'Sostegno sezionatore longitudinale di sbarra (DC)', 'P-006 B-B')
        yS = P2['Y_sez_long']
        for i, xb in enumerate(XB):
            place(SB, SA, xb, yS, P2['ZF'], 90)
            place(SB, byname['SEZ_S3C'], xb, yS, P2['Z_sbarre'] - 1650, 90, tag='QSL6pp-' + F[i])
        place(SB, byname['ARM_CMM'], 600, yS, P2['ZF'] + 700)
        # derivazioni dalla sbarra per lo stallo 2
        q3 = P2['S3C']; xs = q3['interasse_col'] + 145 + 60
        CB = []
        for i, y in enumerate((-2200, 0, 2200)):
            yy = y + dY
            CB.append([(-4200 + xs, yy, 4650), (4200 - xs, yy, 4650)])
            CB.append([(XB[i], yy, 4650), (XB[i], yy, P2['Z_sbarre'] - 50)])
        cb = SB.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        cb.name = 'COND_DERIV_SBARRE_STALLO2'
        conductor(cb, CB, 40, 'conduttore_LM1050-11')
        app.activeViewport.fit()
        app.activeDocument.save('Stallo 2, sezionatore longitudinale, castelletti MT')
        print('OK')
    except:
        print('ERRORE:\n' + traceback.format_exc())
