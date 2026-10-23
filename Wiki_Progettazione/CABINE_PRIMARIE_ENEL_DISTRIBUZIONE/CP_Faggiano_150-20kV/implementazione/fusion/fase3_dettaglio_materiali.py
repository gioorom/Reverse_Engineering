# -*- coding: utf-8 -*-
# Fase 3 - CP Faggiano: dettaglio passanti AT trasformatore (Hitachi Energy GSA 170-OA 1600/0, CLC/TS 50458),
# dettaglio castelletto portaterminali MT (C-045, profili reali UPN/L, piastre di base, calastrelli),
# assegnazione materiali a tutto il modello.
import adsk.core, adsk.fusion, traceback, math

# ---------------- PASSANTE AT (mm, asse passante: z=0 piano inferiore flangia) ----------------
BAT = {
  "L_aria": 1700,                 # flangia -> sommita' codolo (lato aria), coerente con vista Matelec (tip a +4090, 1709 dall'asse)
  "incl": 30, "Ztop": 4090, "Xtop": 1709, "passo": 1650,
  "flangia": [335, 25, 290, 12, 16],   # D, spessore, PCD, n fori, d foro  (Matelec foglio 4)
  "corpo": [260, 230, 115],       # cono di montaggio: D base, D sommita', quota sommita'
  "manicotto": [200, 50],         # manicotti lisci inferiore/superiore: D, altezza
  "alette": [180, 325, 285, 24, 23],   # tronco, aletta grande, piccola, n grandi, n piccole (DC: conteggio da disegno)
  "testa": [230, 30, 160, 50],    # cappello D/h, testa terminale D/h
  "codolo": [40, 80],             # codolo AT d40 x 80 (Matelec foglio 4)
  "torretta": [450, 520, 300],    # torretta TA: D, D flangia, lunghezza lungo l'asse (DC)
}
BMT_ = {"flangia": [230, 20], "alette": [110, 180, 150, 3, 2], "h": 360, "codolo": [30, 60], "bandiera": [60, 12, 100]}  # Cedaspe SBC 24-1250 (DC)
TR_MAT = {"base": [2400, 5205, 300], "vasca": [1934, 5000], "z_coperchio": 2450, "MT_passo": 370, "MT_Y": -2200,
          "rad": [700, 480, 9, 575, 600, 2820], "conserv": [1000, 4380, 1410, 3440]}

# ---------------- CASTELLETTO MT (C-045) ----------------
UPN = {180: [180, 70, 8, 11], 120: [120, 55, 7, 9], 100: [100, 50, 6, 8.5], 80: [80, 45, 6, 8]}   # h, b, tw, tf (EN 10279)
CM = {"a": 1300, "H": 4450, "z_base": 10, "piastra": [500, 10, 205, 22], "gap_ali": 250,
      "P5_z": [920, 1620, 2320, 3020, 3720], "P5_h": 80,
      "P19": [940, 100], "P18": [940, 330, 4218], "P11": [2780, 3740], "P9": [2780, 3008],
      "telaio": [1420, 873, 4180], "reggicavo_z": [724, 1724, 2724],
      "X": 23700, "Y": -5200, "y_fasi": [-370, 0, 370], "C8_H": 255}
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



def poly_extrude(c, plane, pts2, a0, a1, axis, name=None, holes=None):
    """Poligono chiuso (coordinate nel sistema del componente) su un piano principale, estruso da a0 ad a1 lungo axis."""
    sk = c.sketches.add(plane); sk.isComputeDeferred = True
    L = sk.sketchCurves.sketchLines
    P = [sk.modelToSketchSpace(P3(*p)) for p in pts2]
    first = L.addByTwoPoints(P[0], P[1]); prev = first.endSketchPoint
    for i in range(2, len(P)):
        prev = L.addByTwoPoints(prev, P[i]).endSketchPoint
    L.addByTwoPoints(prev, first.startSketchPoint)
    for (hx, hy, hz, hd) in (holes or []):
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P3(hx, hy, hz)), hd / 2 * MM)
    sk.isComputeDeferred = False
    best = max(sk.profiles, key=lambda p: p.areaProperties().area)
    f = _extrude(c, plane, best, a0, a1, axis)
    if name and f.bodies.count:
        f.bodies.item(0).name = name
    return f


def upn_xy(cx, cy, s, rot):
    """Sezione UPN nel piano XY. rot: 'ali+x' anima a sinistra, ali verso +x; 'ali-x' speculare."""
    h, b, tw, tf = UPN[s]
    pts = [(0, -h / 2), (b, -h / 2), (b, -h / 2 + tf), (tw, -h / 2 + tf), (tw, h / 2 - tf), (b, h / 2 - tf), (b, h / 2), (0, h / 2)]
    sg = 1 if rot == 'ali+x' else -1
    return [(cx + sg * px, cy + py, 0) for (px, py) in pts]


def upn_yz(cy, cz, s, ali):
    """Sezione UPN nel piano YZ (anima verticale), ali verso +y o -y."""
    h, b, tw, tf = UPN[s]
    pts = [(0, -h / 2), (b, -h / 2), (b, -h / 2 + tf), (tw, -h / 2 + tf), (tw, h / 2 - tf), (b, h / 2 - tf), (b, h / 2), (0, h / 2)]
    sg = 1 if ali == '+y' else -1
    return [(0, cy + sg * py_, cz + pz) for (py_, pz) in pts]


def upn_xz(cx, cz, s, ali):
    h, b, tw, tf = UPN[s]
    pts = [(0, -h / 2), (b, -h / 2), (b, -h / 2 + tf), (tw, -h / 2 + tf), (tw, h / 2 - tf), (b, h / 2 - tf), (b, h / 2), (0, h / 2)]
    sg = 1 if ali == '+x' else -1
    return [(cx + sg * px, 0, cz + pz) for (px, pz) in pts]


def angolare_yz(cy, cz, l, t, oy, oz):
    """Angolare L l x t nel piano YZ, spigolo in (cy,cz), ali verso oy (+1/-1) e oz (+1/-1)."""
    return [(0, cy, cz), (0, cy + oy * l, cz), (0, cy + oy * l, cz + oz * t), (0, cy + oy * t, cz + oz * t), (0, cy + oy * t, cz + oz * l), (0, cy, cz + oz * l)]


def angolare_xz(cx, cz, l, t, ox, oz):
    return [(cx, 0, cz), (cx + ox * l, 0, cz), (cx + ox * l, 0, cz + oz * t), (cx + ox * t, 0, cz + oz * t), (cx + ox * t, 0, cz + oz * l), (cx, 0, cz + oz * l)]


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


def _xform_bodies(c, bodies, m):
    mv = adsk.core.ObjectCollection.create()
    for b in bodies:
        mv.add(b)
    mi = c.features.moveFeatures.createInput2(mv); mi.defineAsFreeMove(m); c.features.moveFeatures.add(mi)


# ===================== TRASFORMATORE (cassa invariata, passanti AT/MT di dettaglio) =====================
def f_TR_MATELEC(c):
    q = TR_MAT
    bw, bl, bh = q['base']
    boxes(c, [(-bw / 2, -bl / 2, bw / 2, bl / 2)], 0, bh, 'carrello')
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
    d, Lc, dx, zcen = q['conserv']
    cyl_h(c, 'y', dx, zcen, d, -Lc / 2, Lc / 2, 'conservatore')
    boxes(c, [(dx - 60, -Lc / 2 + 400, dx + 60, -Lc / 2 + 520), (dx - 60, Lc / 2 - 520, dx + 60, Lc / 2 - 400)], zc + 40, zcen, 'supporti_conservatore')
    boxes(c, [(-1090, bl / 2 + 50, -390, bl / 2 + 460)], 900, 1700, 'comando_motore_CSC')
    boxes(c, [(-350, bl / 2 + 50, 350, bl / 2 + 500)], 600, 1500, 'cassetta_ausiliari')
    # ---- passanti AT ----
    b = BAT; a = math.radians(b['incl']); La = b['L_aria']
    zb = b['Ztop'] - La * math.cos(a)
    xb = -(b['Xtop'] - La * math.sin(a))
    fD, ft, pcd, nh, dh = b['flangia']
    cb0, cb1, zcorpo = b['corpo']
    dm, hm = b['manicotto']
    tr_, gD, pD, ng, npic = b['alette']
    hD, hh, tD, th = b['testa']
    sd, sh = b['codolo']
    tD_, tfD, tL = b['torretta']
    z_al0 = zcorpo + hm; z_al1 = La - sh - th - hh - hm
    for k in (-1, 0, 1):
        y = k * b['passo']
        bodies = []
        f = cyl(c, 0, 0, tD_, -tL, -20, name='torretta_TA_AT'); bodies.append(f.bodies.item(0))
        f = cyl(c, 0, 0, tfD, -20, 0, name='flangia_torretta'); bodies.append(f.bodies.item(0))
        sk = c.sketches.add(c.xYConstructionPlane)
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P3(0, 0)), fD / 2 * MM)
        for i in range(nh):
            t = 2 * math.pi * (i + 0.5) / nh
            sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P3(pcd / 2 * math.cos(t), pcd / 2 * math.sin(t))), dh / 2 * MM)
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P3(0, 0)), 40 * MM)
        prof = max(sk.profiles, key=lambda p: p.areaProperties().area)
        f = _extrude(c, c.xYConstructionPlane, prof, 0, ft, 'z'); f.bodies.item(0).name = 'flangia_passante_AT'; bodies.append(f.bodies.item(0))
        f = revolve(c, [(0, ft), (cb0 / 2, ft), (cb1 / 2, zcorpo), (0, zcorpo)], 'corpo_montaggio_AT'); bodies.append(f.bodies.item(0))
        f = boxes(c, [(fD / 2 - 40, -35, fD / 2 + 25, 35)], ft, ft + 60, 'presa_capacitiva'); bodies.append(f.bodies.item(0))
        rz = [(0, zcorpo), (dm / 2, zcorpo), (dm / 2, z_al0)]
        rt = tr_ / 2.0
        n = ng + npic; p = (z_al1 - z_al0) / float(n)
        seq, bb, ss = [], ng, npic
        while bb or ss:
            if bb: seq.append(gD); bb -= 1
            if ss: seq.append(pD); ss -= 1
        rz.append((rt, z_al0))
        for i, dd in enumerate(seq):
            z = z_al0 + i * p + 0.1 * p
            rz += [(rt, z), (dd / 2.0, z + 0.18 * p), (dd / 2.0, z + 0.30 * p), (rt, z + 0.55 * p)]
        rz += [(rt, z_al1), (dm / 2, z_al1), (dm / 2, z_al1 + hm), (0, z_al1 + hm)]
        f = revolve(c, rz, 'isolatore_composito_AT'); bodies.append(f.bodies.item(0))
        z5 = z_al1 + hm
        f = revolve(c, [(0, z5), (hD / 2, z5), (hD / 2, z5 + hh), (tD / 2, z5 + hh), (tD / 2, z5 + hh + th), (0, z5 + hh + th)], 'testa_passante_AT'); bodies.append(f.bodies.item(0))
        f = cyl(c, 0, 0, sd, z5 + hh + th, La, name='codolo_AT_d40'); bodies.append(f.bodies.item(0))
        m = adsk.core.Matrix3D.create()
        m.setToRotation(-a, adsk.core.Vector3D.create(0, 1, 0), adsk.core.Point3D.create(0, 0, 0))
        t2 = adsk.core.Matrix3D.create(); t2.translation = adsk.core.Vector3D.create(xb * MM, y * MM, zb * MM)
        m.transformBy(t2)
        _xform_bodies(c, bodies, m)
    # ---- passanti MT (2n, 2u, 2v, 2w) ----
    q2 = BMT_; z0 = zc + 40
    for k in range(4):
        x = (k - 1.5) * q['MT_passo']; y = q['MT_Y']
        bodies = []
        f = cyl(c, 0, 0, q2['flangia'][0], z0, z0 + q2['flangia'][1], name='flangia_passante_MT'); bodies.append(f.bodies.item(0))
        al = q2['alette']
        f = revolve(c, insulator_rz(z0 + q2['flangia'][1], q2['h'] - q2['flangia'][1] - 40, al[0], al[1], al[2], al[3], al[4], (140, 10), (140, 40), (100, 40)), 'isolatore_porcellana_MT'); bodies.append(f.bodies.item(0))
        zt = z0 + q2['h'] - 40
        f = cyl(c, 0, 0, 90, zt, zt + 40, name='cappello_MT'); bodies.append(f.bodies.item(0))
        f = cyl(c, 0, 0, q2['codolo'][0], zt + 40, zt + 40 + q2['codolo'][1], name='codolo_MT_M30'); bodies.append(f.bodies.item(0))
        bw_, bt_, bh_ = q2['bandiera']
        f = boxes(c, [(-bt_ / 2, -bw_ / 2, bt_ / 2, bw_ / 2)], zt + 40 + q2['codolo'][1], zt + 40 + q2['codolo'][1] + bh_, 'bandiera_MT'); bodies.append(f.bodies.item(0))
        m = adsk.core.Matrix3D.create(); m.translation = adsk.core.Vector3D.create(x * MM, y * MM, 0)
        _xform_bodies(c, bodies, m)


# ===================== CASTELLETTO MT (C-045) =====================
def f_castelletto(c):
    q = CM; a = q['a']
    B, tB, eh, dH = q['piastra']
    z0 = q['z_base']; zt = z0 + q['H'] + 20
    g = q['gap_ali'] / 2.0
    for s in (-1, 1):
        cx = s * a
        # piastra di base P1 500x500x10 con 4 fori d22 (interasse 410)
        poly_extrude(c, c.xYConstructionPlane, [(cx - B / 2, -B / 2, 0), (cx + B / 2, -B / 2, 0), (cx + B / 2, B / 2, 0), (cx - B / 2, B / 2, 0)], 0, tB, 'z', 'P1_piastra_base',
                     holes=[(cx + i * eh, j * eh, 0, dH) for i in (-1, 1) for j in (-1, 1)])
        # montante: 2 x UPN180 ad ali contrapposte (ingombro 250 x 180)
        poly_extrude(c, c.xYConstructionPlane, upn_xy(cx - g, 0, 180, 'ali+x'), tB, zt, 'z', 'P4_UPN180')
        poly_extrude(c, c.xYConstructionPlane, upn_xy(cx + g, 0, 180, 'ali-x'), tB, zt, 'z', 'P4_UPN180')
        # fazzoletti P2 (trapezi 500/250 x 150, sp.10) e nervature P3
        for yy in (95, -95):
            poly_extrude(c, c.xZConstructionPlane, [(cx - B / 2, 0, tB), (cx + B / 2, 0, tB), (cx + g, 0, tB + 150), (cx - g, 0, tB + 150)], yy - 5, yy + 5, 'y', 'P2_fazzoletto')
        for sy in (1, -1):
            y0, y1 = sy * 100, sy * B / 2
            poly_extrude(c, c.yZConstructionPlane, [(0, y0, tB), (0, y1, tB), (0, y0, tB + 150)], cx - 5, cx + 5, 'x', 'P3_nervatura')
        # calastrelli P5 sulle due facce
        for zz in q['P5_z']:
            boxes(c, [(cx - g, 90, cx + g, 100), (cx - g, -100, cx + g, -90)], zz, zz + q['P5_h'], 'P5_calastrello')
        # testa P19 UPN100 lungo Y (anima verticale)
        poly_extrude(c, c.xZConstructionPlane, upn_xz(cx - 25, zt + 50, 100, '+x'), -q['P19'][0] / 2, q['P19'][0] / 2, 'y', 'P19_UPN100')
        # mensole porta terminali: P18 L80x5 lungo Y a +-330, bracci P17 L50x5
        dx18, z18 = q['P18'][1], q['P18'][2]
        for sx in (-1, 1):
            xc = cx + sx * dx18
            poly_extrude(c, c.xZConstructionPlane, angolare_xz(xc - sx * 40, z18, 80, 5, sx, -1), -q['P18'][0] / 2, q['P18'][0] / 2, 'y', 'P18_L80x5')
            for yy in (-300, 300):
                x0, x1 = sorted((cx + sx * g, xc - sx * 40))
                boxes(c, [(x0, yy - 25, x1, yy + 25)], z18 - 50, z18, 'P17_L50x5')
            # mensole reggicavo (3 livelli)
            for zz in q['reggicavo_z']:
                x0, x1 = sorted((cx + sx * g, xc + sx * 40))
                boxes(c, [(x0, -40, x1, 40)], zz, zz + 50, 'mensola_reggicavo_braccio')
                boxes(c, [(xc - 40 + sx * 40, -400, xc + 40 + sx * 40, 400)], zz, zz + 50, 'mensola_reggicavo_traverso')
    # traverse P11 (UPN120 a +3.740) e P9 (UPN80 a +3.008), sulla faccia anteriore (+y)
    L11 = q['P11'][0] / 2.0
    poly_extrude(c, c.yZConstructionPlane, upn_yz(100, q['P11'][1] - 60, 120, '+y'), -L11, L11, 'x', 'P11_UPN120')
    poly_extrude(c, c.yZConstructionPlane, upn_yz(100, q['P9'][1] - 40, 80, '+y'), -L11, L11, 'x', 'P9_UPN80')
    # carpenteria sostegno sbarre (interamente saldata)
    w, yf, zf = q['telaio']
    for sx in (-1, 1):
        x = sx * (w / 2 - 40)
        poly_extrude(c, c.yZConstructionPlane, [(0, 155, q['P11'][1]), (0, yf, q['P11'][1]), (0, yf, q['P11'][1] + 80), (0, 155, q['P11'][1] + 80)], x - 22, x + 22, 'x', 'P14_UPN80_braccio')
        boxes(c, [(x - 30, yf - 60, x + 30, yf)], q['P11'][1] + 80, zf - 80, 'P15_montante')
        bar_between(c, (x, 160, q['P9'][1] - 40), (x, yf - 30, q['P11'][1]), 50, 6, 'P12_diagonale_L50x5')
        boxes(c, [(x - 25, 107, x + 25, 155)], q['P9'][1], q['P11'][1] - 120, 'P10_montante')
    poly_extrude(c, c.yZConstructionPlane, upn_yz(yf - 40, zf - 40, 80, '-y'), -w / 2, w / 2, 'x', 'P16_UPN80_trave_isolatori')


def f_sbarre_MT(c):
    q = CM; a = q['a']
    zb = q['z_base'] + q['H'] + 20 + 100 + q['C8_H']
    boxes(c, [(-a - 400, y - 5, a + 400, y + 5) for y in q['y_fasi']], zb, zb + 100, 'barra_Cu_100x10')


# ===================== MATERIALI =====================
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
        return ('Acciaio inox AISI 304', None)
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





def run(context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        root = des.rootComponent
        byname = {c.name: c for c in des.allComponents}
        ST = byname['STALLO_TRAFO']
        # 1) trasformatore: ricostruzione con passanti di dettaglio
        tr = byname['TR_MATELEC_25MVA']; clear_component(tr); f_TR_MATELEC(tr)
        tr.description = 'Trasformatore Matelec TP18781E01N 25 MVA ONAN 150/20.8 kV - passanti AT Hitachi Energy GSA 170-OA 1600/0, MT Cedaspe SBC 24-1250'
        # 2) castelletto e sbarre MT
        cs = byname['SOST_PORTATERMINALI_MT']; clear_component(cs); f_castelletto(cs)
        bm = byname['SBARRE_MT_CU100x10']; clear_component(bm); f_sbarre_MT(bm)
        # 3) terminali: riposizionati sulle mensole P18 (+-330 dall'asse montante)
        term = byname['TERM_CAVO_MT_unipolare']
        for o in [o for o in ST.occurrences if o.component == term]:
            o.deleteMe()
        q = CM; X0, Y0, a = q['X'], q['Y'], q['a']
        def put(comp, x, y, z):
            m = adsk.core.Matrix3D.create(); m.translation = adsk.core.Vector3D.create(x * MM, y * MM, z * MM)
            return ST.occurrences.addExistingComponent(comp, m)
        for y in q['y_fasi']:
            for s in (-1, 1):
                for sx in (-1, 1):
                    put(term, X0 + s * a + sx * q['P18'][1], Y0 + y, q['P18'][2])
        # 4) cavi MT ricostruiti lungo le mensole reggicavo
        if 'CAVI_MT_USCITA' in byname:
            for o in [o for o in ST.occurrences if o.component.name == 'CAVI_MT_USCITA']:   # solo occorrenze native
                o.deleteMe()
        CV = []
        for y in q['y_fasi']:
            for s in (-1, 1):
                for sx in (-1, 1):
                    xt = X0 + s * a + sx * q['P18'][1]
                    xc = xt + sx * 110
                    CV.append([(xt, Y0 + y, q['P18'][2] + 60), (xt, Y0 + y, q['P18'][2] - 250), (xc, Y0 + y, q['P18'][2] - 450), (xc, Y0 + y, 0)])
        cv = ST.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        cv.name = 'CAVI_MT_USCITA'
        conductor(cv, CV, 50, 'cavo_MT_ARE4H5E')
        # 5) materiali
        done, miss = apply_materials(app, des)
        for c in des.allComponents:
            for sk in c.sketches:
                sk.isLightBulbOn = False
        app.activeDocument.save('Passanti AT/MT di dettaglio, castelletto C-045 a profili reali, materiali')
        print('OK corpi con materiale:', done, 'mancanti:', miss)
    except:
        print('ERRORE:\n' + traceback.format_exc())
