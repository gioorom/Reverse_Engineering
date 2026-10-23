# -*- coding: utf-8 -*-
# Fase 5 - CP Faggiano: sezionatore di linea S3CT con sezionatore di terra serie STA di dettaglio
# (D1210-AA-IT figg. 1.2, 3.3, 6.1, 6.6) e rinvio lame di terra coassiale alle cerniere.
import adsk.core, adsk.fusion, traceback, math

S3C = {"interasse_col": 1120, "telaio": [2500, 300, 150], "col_H": 1450, "col": [150, 230, 190, 15, 14],
       "lama": [2300, 80, 50], "z_lama": 1660}
STA = {   # sezionatore di terra (lato linea = -X), quote locali del sezionatore (z=0 base telaio)
  "x_cern": -1300, "y_braccio": 215, "z_cern": 120,     # cerniera: estremo telaio lato linea, braccio a 215 dall'asse (fig. 3.3)
  "L_braccio": 1565, "sez_braccio": [80, 60],            # DC: lunghezza ~0.7 A (fig. 3.3), tubo Al rettangolare
  "testa": [140, 90, 70],                                # aste di contatto + guida (fig. 6.1)
  "cont_fisso": [215, 145],                              # sbalzo dal contatto principale, altezza (fig. 6.6)
  "d_albero": 60,
}
YP = [-2200, 0, 2200]
ARM_DBST = {"back": 600, "H": 698, "z0": 900, "x_albero": 114}
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
        if 'contatti' in n or 'treccia' in n or 'contatto' in n:
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

def f_S3CT(c):
    q = S3C
    L, W, Hf = q['telaio']
    a = q['interasse_col']
    boxes(c, [(-L / 2, -W / 2, L / 2, W / 2)], 0, Hf, 'telaio_base')
    col = q['col']
    for x in (-a, 0, a):
        f = revolve(c, insulator_rz(Hf, q['col_H'], col[0], col[1], col[2], col[3], col[4], (220, 20), (180, 80), (180, 60)), 'colonna')
        if x != 0:
            _move(c, f.bodies.item(0), x, 0)
    zt = Hf + q['col_H']
    cyl(c, 0, 0, 200, zt, q['z_lama'], name='testa_rotante')
    bl, bw, bh = q['lama']
    boxes(c, [(-bl / 2, -bw / 2, bl / 2, bw / 2)], q['z_lama'], q['z_lama'] + bh, 'lama_principale')
    boxes(c, [(-a - 125, -75, -a + 125, 75)], zt, zt + 120, 'contatti_fissi')
    boxes(c, [(a - 125, -75, a + 125, 75)], zt, zt + 120, 'contatti_fissi')
    boxes(c, [(-a - 145 - 120, -50, -a - 145, 50)], zt + 40, zt + 60, 'attacchi_AT')
    boxes(c, [(a + 145, -50, a + 145 + 120, 50)], zt + 40, zt + 60, 'attacchi_AT')
    # ---------------- sezionatore di terra STA ----------------
    s = STA
    xc, yb, zc = s['x_cern'], s['y_braccio'], s['z_cern']
    bw2, bh2 = s['sez_braccio']
    # supporto cerniera (6.4) sull'estremo del telaio + albero di cerniera lungo Y
    boxes(c, [(-L / 2 - 90, W / 2, -L / 2 + 40, yb + 90)], 0, Hf, 'supporto_cerniera_terra')
    cyl_h(c, 'y', xc, zc, s['d_albero'], -W / 2 - 40, yb + bw2 / 2 + 40, 'albero_cerniera_terra')
    # braccio mobile (6.1) in posizione APERTO: orizzontale lungo +X
    boxes(c, [(xc, yb - bw2 / 2, xc + s['L_braccio'], yb + bw2 / 2)], zc - bh2 / 2, zc + bh2 / 2, 'braccio_terra_Al')
    # bulloni a U del braccio (6.6)
    for dx in (120, 260):
        boxes(c, [(xc + dx, yb - bw2 / 2 - 8, xc + dx + 25, yb + bw2 / 2 + 8)], zc - bh2 / 2 - 8, zc + bh2 / 2 + 8, 'cerniera_bulloni_U')
    # testa: aste di contatto (6.2) + guida di contatto (6.10)
    tl, tw, th = s['testa']
    xe = xc + s['L_braccio']
    boxes(c, [(xe, yb - tw / 2, xe + tl, yb + tw / 2)], zc - th / 2, zc + th / 2, 'contatto_mobile_terra')
    boxes(c, [(xe + 30, yb - 20, xe + tl - 20, yb + 20)], zc + th / 2, zc + th / 2 + 40, 'guida_contatto_terra')
    # conduttore flessibile (6.9) dal braccio al telaio
    boxes(c, [(xc + 40, yb - 15, xc + 100, yb + 15)], 0, zc - bh2 / 2, 'treccia_flessibile_terra')
    # contatto fisso di terra (6.20) sul contatto principale lato linea: sbalzo 215, altezza 145
    sb, hc = s['cont_fisso']
    xf = -a - sb
    boxes(c, [(xf - 20, 60, -a - 125, yb - 30)], zt + 60, zt + 80, 'supporto_contatto_terra')
    boxes(c, [(xf - 40, yb - 50, xf + 40, yb + 50)], zt + 80 - hc, zt + 80, 'contatto_fisso_terra')
    boxes(c, [(xf - 12, yb - 35, xf + 12, yb + 35)], zt + 80 - hc - 60, zt + 80 - hc, 'contatto_lama_terra')


def f_rinvio_terra(c):
    """Comando lame di terra: armadio DBST a -X, albero verticale, leva, tirante alla leva 4.7 sull'asta 4.2 coassiale alle cerniere."""
    s = STA; q = ARM_DBST
    xs = -(q['back'] + q['x_albero'])
    z_cab = q['z0'] + q['H'] + 72
    z_t = 3000 + s['z_cern']
    cyl(c, xs, 0, 50, z_cab, 2950, name='albero_trasmissione_verticale')
    boxes(c, [(xs - 50, -50, xs + 50, 50)], 2920, 2980, 'leva_albero')
    # asta orizzontale di trasmissione (4.2) coassiale agli alberi di cerniera dei 3 poli
    cyl_h(c, 'y', s['x_cern'], z_t, 48, YP[0] - 150, YP[-1] + s['y_braccio'] + 120, 'asta_orizzontale_terra_4.2')
    # leva 4.7 sull'asta e tirante di comando
    yl = -500
    boxes(c, [(s['x_cern'] - 25, yl - 25, s['x_cern'] + 25, yl + 25)], z_t - 160, z_t, 'leva_4.7')
    bar_between(c, (xs, 0, 2950), (s['x_cern'], yl, z_t - 140), 35, 35, 'tirante_comando_terra')

def run(context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        by = {c.name: c for c in des.allComponents}
        for nm in ('STALLO_LINEA', 'STALLO_TRAFO', 'SISTEMA_SBARRE', 'SEZ_S3CT_TERRA', 'RINVIO_TERRA_S3CT'):
            if nm not in by:
                print('ERRORE: manca', nm); return
        sz = by['SEZ_S3CT_TERRA']; clear_component(sz); f_S3CT(sz)
        sz.description = 'Sezionatore GE S3CT doppia interruzione laterale 170 kV 1250 A con sezionatore di terra serie STA (lato linea)'
        rt = by['RINVIO_TERRA_S3CT']; clear_component(rt); f_rinvio_terra(rt)
        rt.description = 'Comando lame di terra: albero verticale, tirante, leva 4.7, asta orizzontale 4.2 coassiale alle cerniere'
        done, miss = apply_materials(app, des)
        for c in (sz, rt):
            for sk in c.sketches:
                sk.isLightBulbOn = False
        names = {c.name for c in des.allComponents}
        if not {'STALLO_LINEA', 'STALLO_TRAFO', 'SISTEMA_SBARRE'} <= names:
            print('ERRORE: assieme incompleto, NON salvo'); return
        app.activeDocument.save('Sezionatore di linea S3CT con sezionatore di terra STA di dettaglio')
        print('OK materiali', done, 'mancanti', miss)
    except:
        print('ERRORE:\n' + traceback.format_exc())
