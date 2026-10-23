# -*- coding: utf-8 -*-
# Fase 4 - CP Faggiano: armadi di comando unici (interruttore: 1 armadio sul polo centrale, D1301-AB-IT par. 6.7;
# sezionatori: 1 comando tripolare CMM + albero verticale e tiranti interpolari, D1060-AC-IT figg. 11/14).
import adsk.core, adsk.fusion, traceback, math

ARM = {   # mm: larghezza (fronte), profondita', altezza
  "INT": {"W": 700, "D": 450, "H": 850, "z0": 800, "back": 310},          # DC: H e D misurati in scala su P-006, W stimata
  "CMM": {"W": 545, "D": 463, "H": 598, "z0": 900, "back": 600, "kg": 70},  # D1060 fig.11 (disegno ruotato di 90 gradi)
  "DBST": {"W": 656, "D": 463, "H": 698, "z0": 900, "back": 600, "kg": 80}, # D1060 fig.14
  "x_albero": 114,                      # albero d'uscita a 114 mm dal retro (vista dall'alto)
  "d_albero": 50, "d_tirante": 48,
}
X = {"QS_3": -14200, "QF_5": -8200, "QSB_6": -4200, "QSB_6p": 4200, "QF_5p": 8200}
YP = [-2200, 0, 2200]
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



def bar_between(c, p1, p2, w, h, name):
    """Piatto/asta a sezione rettangolare w x h tra due punti (diagonali)."""
    L = math.sqrt(sum((p2[i] - p1[i]) ** 2 for i in range(3)))
    f = boxes(c, [(0, -w / 2, L, w / 2)], -h / 2, h / 2, name)
    ux = adsk.core.Vector3D.create(*(p2[i] - p1[i] for i in range(3))); ux.normalize()
    ref = adsk.core.Vector3D.create(0, 0, 1) if abs(ux.z) < 0.9 else adsk.core.Vector3D.create(1, 0, 0)
    uy = ref.crossProduct(ux); uy.normalize(); uz = ux.crossProduct(uy)
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(P3(*p1), ux, uy, uz)
    mv = adsk.core.ObjectCollection.create(); mv.add(f.bodies.item(0))
    mi = c.features.moveFeatures.createInput2(mv); mi.defineAsFreeMove(m); c.features.moveFeatures.add(mi)


def clear_component(c):
    """Elimina tutte le feature e gli schizzi del componente (mantiene componente, occorrenze e attributi)."""
    feats = []
    for coll in (c.features.extrudeFeatures, c.features.revolveFeatures, c.features.moveFeatures, c.features.baseFeatures):
        for f in coll:
            feats.append(f)
    feats.sort(key=lambda f: f.timelineObject.index, reverse=True)
    for f in feats:
        f.deleteMe()
    for sk in [s for s in c.sketches][::-1]:
        sk.deleteMe()


def material_rules(cname, bname):
    n = bname.lower(); cn = cname
    if cn.startswith('SOST_'):
        return ('Acciaio, Galvanizzato', None)
    if cn.startswith('FOND_'):
        return (None, 'Calcestruzzo')
    if cn.startswith('SBARRA'):
        return ('Alluminio 6061', 'Alluminio - Satinato')
    if cn.startswith('COND_'):
        return ('Alluminio', 'Alluminio - Satinato')
    if cn.startswith('COLL_MT') or cn.startswith('SBARRE_MT'):
        return ('Rame', 'Rame - Lucidato')
    if cn.startswith('CAVI_MT'):
        return ('Gomma, nero', None)
    if cn.startswith('MORS_'):
        return ('Alluminio A356 T6', None)
    if cn.startswith('ARM_'):
        if 'oblo' in n:
            return ('Vetro', None)
        if 'piastra_cavi' in n or 'targa' in n:
            return ('Alluminio', None)
        if 'pressacavo' in n:
            return ('Ottone', None)
        if 'staffa' in n or 'morsa' in n or 'golfar' in n:
            return ('Acciaio, Galvanizzato', None)
        return ('Acciaio inox AISI 304', None)
    if cn.startswith('RINVIO_'):
        return ('Acciaio, Galvanizzato', None)
    if cn.startswith('TUBI_CAVI'):
        return ('Gomma, nero', None)
    if cn == 'ISO_DJ1003':
        return ('Gomma, Silicone', 'Plastica - Opaco (grigio)')
    if cn.startswith('ISO_MT'):
        return ('Porcellana', None)
    if cn.startswith('TERM_'):
        return ('Rame', 'Rame - Lucidato') if 'capocorda' in n else ('Gomma, Silicone', 'Plastica - Opaco (grigio)')
    if cn.startswith('SCAR_'):
        if 'silicone' in n:
            return ('Gomma, Silicone', 'Plastica - Opaco (grigio)')
        return ('Alluminio A356 T6', None)
    if cn.startswith('INT_'):
        if 'isolatore' in n or 'camera' in n:
            return ('Porcellana', None)
        return ('Alluminio A356 T6', None)
    if cn.startswith('SEZ_'):
        if 'colonna' in n:
            return ('Porcellana', None)
        if 'telaio' in n or 'cerniera' in n:
            return ('Acciaio, Galvanizzato', None)
        if 'contatti' in n:
            return ('Rame', 'Rame - Lucidato')
        return ('Alluminio 6061', None)
    if cn.startswith('TA_') or cn.startswith('TV_'):
        if 'isolatore' in n:
            return ('Porcellana', None)
        if 'cassa' in n:
            return ('Acciaio, Galvanizzato', None)
        if 'codolo' in n or 'attacchi' in n:
            return ('Alluminio', None)
        return ('Alluminio A356 T6', None)
    if cn.startswith('TR_'):
        if 'composito' in n:
            return ('Gomma, Silicone', 'Plastica - Opaco (grigio)')
        if 'porcellana' in n:
            return ('Porcellana', None)
        if 'codolo' in n or 'bandiera' in n:
            return ('Rame', 'Rame - Lucidato')
        if 'flangia_passante' in n or 'corpo_montaggio' in n or 'testa_passante' in n or 'cappello' in n or 'presa' in n:
            return ('Alluminio A356 T6', None)
        if 'comando' in n or 'cassetta' in n:
            return ('Acciaio inox AISI 304', None)
        return ('Acciaio, finitura verniciata, grigio scuro', None)
    return (None, None)


def apply_materials(app, des):
    libs = {l.name: l for l in app.materialLibraries}
    mlib = libs['Libreria dei materiali di Fusion']; alib = libs['Libreria aspetti di Fusion']
    mats = {m.name: m for m in mlib.materials}
    apps = {a.name: a for a in alib.appearances}
    cache_a = {}
    done, miss = 0, set()
    for c in des.allComponents:
        for b in c.bRepBodies:
            mn, an = material_rules(c.name, b.name)
            if mn and mn in mats:
                b.material = mats[mn]; done += 1
            elif mn:
                miss.add(mn)
            if an:
                if an not in cache_a:
                    ex = des.appearances.itemByName(an)
                    cache_a[an] = ex if ex else des.appearances.addByCopy(apps[an], an)
                b.appearance = cache_a[an]
    return done, miss
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






def f_armadio(q, albero):
    def build(c):
        W, D, H = q['W'], q['D'], q['H']
        boxes(c, [(0, -W / 2, D, W / 2)], 0, H, 'cassa_inox_IP54')
        boxes(c, [(-5, -W / 2 - 25, D + 35, W / 2 + 25)], H, H + 12, 'tetto')
        boxes(c, [(D, -W / 2 + 12, D + 10, W / 2 - 12)], 15, H - 15, 'porta_frontale')
        boxes(c, [(D + 10, -80, D + 14, 80)], 0.62 * H, 0.62 * H + 120, 'oblo_ispezione')
        hz = 0.42 * H
        boxes(c, [(D + 10, W / 2 - 75, D + 40, W / 2 - 55)], hz, hz + 20, 'maniglia_supporti')
        boxes(c, [(D + 10, W / 2 - 75, D + 40, W / 2 - 55)], hz + 130, hz + 150, 'maniglia_supporti')
        cyl(c, D + 40, W / 2 - 65, 22, hz, hz + 150, name='maniglia_lucchettabile')
        for zc in (0.15 * H, 0.5 * H, 0.85 * H):
            cyl(c, D + 9, -W / 2 + 10, 18, zc - 30, zc + 30, name='cerniera')
        boxes(c, [(40, -W / 2 + 40, D - 40, W / 2 - 40)], -8, 0, 'piastra_cavi_Al')
        for yy in (-W / 4, 0, W / 4):
            cyl(c, D / 2, yy, 40, -45, -8, name='pressacavo')
        for yy in (-W / 2 + 70, W / 2 - 70):
            cyl(c, D / 2, yy, 30, H + 12, H + 47, name='golfare')
        boxes(c, [(D + 10, -W / 2 + 40, D + 12, -W / 2 + 160)], 0.85 * H, 0.85 * H + 50, 'targa_aperto_chiuso')
        boxes(c, [(D / 2 - 60, -W / 2 - 6, D / 2 + 60, -W / 2)], 0.2 * H, 0.2 * H + 80, 'aeratore')
        for zz in (0.25 * H, 0.75 * H):
            boxes(c, [(-60, -W / 2 - 80, 0, W / 2 + 80)], zz, zz + 50, 'staffa_fissaggio')
        if albero:
            xa = ARM['x_albero']
            boxes(c, [(xa - 35, -40, xa + 35, 40)], H + 12, H + 72, 'morsa_albero')
            boxes(c, [(D / 2 - 30, W / 2, D / 2 + 30, W / 2 + 40)], 0.45 * H, 0.45 * H + 60, 'sede_manovella_emergenza')
    return build


def f_rinvio(back, z_cab_top, ztop, xl, ylink=0, terra=False):
    """Rinvio sezionatore (armadio sul lato -X): albero verticale, tirante al rinvio, tirante interpolare, leve ai 3 poli."""
    def build(c):
        xs = -(back + ARM['x_albero'])
        cyl(c, xs, 0, ARM['d_albero'], z_cab_top, ztop + 30, name='albero_trasmissione_verticale')
        boxes(c, [(xs - 50, -50, xs + 50, 50)], ztop - 30, ztop + 30, 'leva_albero')
        if abs(xs - xl) > 1:
            bar_between(c, (xs, 0, ztop), (xl, ylink, ztop), 40, 40, 'tirante_rinvio')
        cyl_h(c, 'y', xl, ztop, ARM['d_tirante'], YP[0] + ylink - 60, YP[-1] + ylink + 60, 'tirante_interpolare')
        for yp in YP:
            if terra:
                boxes(c, [(xl - 30, yp + ylink - 30, xl + 30, yp + ylink + 30)], ztop, 3000, 'leva_polo_terra')
            else:
                boxes(c, [(min(xl, 0), yp - 30, max(xl, 0), yp + 30)], ztop - 20, ztop + 20, 'leva_polo')
    return build

def run(context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        root = des.rootComponent
        by = {c.name: c for c in des.allComponents}
        libc = by['00_LIBRERIA_ORGANI']
        SL, ST, SB = by['STALLO_LINEA'], by['STALLO_TRAFO'], by['SISTEMA_SBARRE']
        # 1) via gli armadi per polo (FK3) e i vecchi CMM posizionati
        # cancellazione SOLO di occorrenze native nei rispettivi sottoassiemi (mai proxy annidati)
        for P in (SL, ST, SB):
            for o in [o for o in P.occurrences if o.component.name in ('ARM_MANOVRA_FK3-1', 'ARM_CMM')]:
                o.deleteMe()
        for o in [o for o in libc.occurrences if o.component.name == 'ARM_MANOVRA_FK3-1']:
            o.deleteMe()
        def newlib(name, fn, ifc, descr, fonte):
            c = libc.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
            c.name = name; fn(c); c.description = descr
            c.attributes.add('BIM', 'IfcClass', ifc); c.attributes.add('BIM', 'Fonte', fonte)
            return c
        cmm = by['ARM_CMM']; clear_component(cmm); f_armadio(ARM['CMM'], True)(cmm)
        cmm.description = 'Armadio di manovra tripolare e interfacciamento SC serie CMM (GE) - 598x545x463, 70 kg, inox IP54'
        AINT = newlib('ARM_COMANDO_INT_GL313', f_armadio(ARM['INT'], False), 'IfcElectricDistributionBoard', 'Armadio di comando interruttore GL313 (unico, sul polo centrale)', 'D1301-AB-IT par.6.7 / P-006')
        ADB = newlib('ARM_CMM_DBST', f_armadio(ARM['DBST'], True), 'IfcElectricDistributionBoard', 'Armadio di manovra CMM con DBST per sezionatore di terra - 698x656x463, 80 kg', 'D1060-AC-IT fig.14')
        q = ARM['CMM']; qd = ARM['DBST']
        R_SEZ = newlib('RINVIO_SEZ_S3C', f_rinvio(q['back'], q['z0'] + q['H'] + 72, 2850, -200), 'IfcMechanicalFastener', 'Albero verticale e tiranti interpolari sezionatore S3C', 'D1060-AC-IT / D1210-AA-IT')
        R_TER = newlib('RINVIO_TERRA_S3CT', f_rinvio(qd['back'], qd['z0'] + qd['H'] + 72, 2950, -1250, 210, True), 'IfcMechanicalFastener', 'Albero e tiranti lame di terra S3CT', 'D1060-AC-IT')
        R_LON = newlib('RINVIO_SEZ_LONG', f_rinvio(850, q['z0'] + q['H'] + 72, 5400, -200), 'IfcMechanicalFastener', 'Albero e tiranti sezionatore longitudinale 6\'\'', 'D1060-AC-IT')
        libocc = [o for o in root.occurrences if o.component == libc][0]
        libocc.isLightBulbOn = False

        def place(P, comp, x, y, z, rot=0.0, tag=None):
            m = adsk.core.Matrix3D.create()
            if rot:
                m.setToRotation(math.radians(rot), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
            m.translation = adsk.core.Vector3D.create(x * 0.1, y * 0.1, z * 0.1)
            o = P.occurrences.addExistingComponent(comp, m)
            if tag:
                o.attributes.add('BIM', 'Tag', tag)
            return o
        # 3) interruttori: un armadio di comando sul polo centrale + cavidotti verso i poli laterali
        qi = ARM['INT']
        TC = {SL: [], ST: []}
        for P, xq, s, tag in ((SL, X['QF_5'], 1, 'QF5-ARM'), (ST, X['QF_5p'], -1, 'QF5p-ARM')):
            place(P, AINT, xq + s * qi['back'], 0, qi['z0'], 0 if s > 0 else 180, tag)
            xc = xq + s * (qi['back'] + qi['D'] / 2)
            for sy in (-1, 1):
                TC[P].append([(xc, sy * (qi['W'] / 2), qi['z0'] + 150), (xc, sy * (qi['W'] / 2 + 150), qi['z0'] + 150), (xc, sy * 2200, qi['z0'] + 150), (xq + s * 260, sy * 2200, qi['z0'] + 150)])
        # 4) sezionatori: un comando tripolare per apparecchio (+ comando lame di terra su QS3)
        place(SL, cmm, X['QSB_6'] - q['back'], 0, q['z0'], 180, 'QSB6-CMM')
        place(SL, R_SEZ, X['QSB_6'], 0, 0)
        place(SL, cmm, X['QS_3'] + q['back'], 0, q['z0'], 0, 'QS3-CMM')
        place(SL, R_SEZ, X['QS_3'], 0, 0, 180)
        place(SL, ADB, X['QS_3'] - qd['back'], 0, qd['z0'], 180, 'QS3-CMM-DBST')
        place(SL, R_TER, X['QS_3'], 0, 0)
        place(ST, cmm, X['QSB_6p'] + q['back'], 0, q['z0'], 0, 'QSB6p-CMM')
        place(ST, R_SEZ, X['QSB_6p'], 0, 0, 180)
        # sezionatore longitudinale di sbarra 6'' (poli lungo X a Y=6200, armadio verso -Y)
        place(SB, cmm, 0, 6200 - 850, q['z0'], -90, 'QSL6pp-CMM')
        place(SB, R_LON, 0, 6200, 0, 90)
        for P, nm in ((SL, 'TUBI_CAVI_INT_QF5'), (ST, 'TUBI_CAVI_INT_QF5p')):
            cc = P.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
            cc.name = nm
            conductor(cc, TC[P], 63, 'tubo_corrugato_cavi_interconnessione')
        done, miss = apply_materials(app, des)
        for c in des.allComponents:
            for sk in c.sketches:
                sk.isLightBulbOn = False
        names = {c.name for c in des.allComponents}
        if not {'STALLO_LINEA', 'STALLO_TRAFO', 'SISTEMA_SBARRE'} <= names:
            print('ERRORE: assieme incompleto, NON salvo'); return
        app.activeDocument.save('Armadi di comando unici per interruttori e sezionatori, rinvii meccanici')
        print('OK materiali', done, 'mancanti', miss)
    except:
        print('ERRORE:\n' + traceback.format_exc())
