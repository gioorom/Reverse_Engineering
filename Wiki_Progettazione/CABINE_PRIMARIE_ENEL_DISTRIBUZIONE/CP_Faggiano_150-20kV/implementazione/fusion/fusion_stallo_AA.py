# -*- coding: utf-8 -*-
"""
CP 150/20 kV Faggiano - Sezione AT, profilo elettromeccanico A-A
Libreria componenti (un componente per organo) + assieme stallo linea / sbarre / stallo trafo.
LOD 200-300. Unita': mm. Assi impianto: X lungo lo stallo (linea -> trafo), Y lungo le sbarre, Z verticale.
Origine: asse 7 (sostegno sbarre) a quota piazzale +0.00 (28 m s.l.m.), Y=0 sulla fase centrale dello stallo.
Fonti: vedi PARAM['_fonti'] e la scheda stallo. Valori marcati DC = da confermare.
"""
import adsk.core, adsk.fusion, traceback, math, json

# =====================================================================
# PARAMETRI (unica fonte dati; replicata in stallo_AA_parametri.json)
# =====================================================================
PARAM = {
  "layout": {   # P-006 profilo A-A, catena quote orizzontali [mm] rispetto asse 7
    "X": {"TV_2": -16700, "QS_3": -14200, "TA_4": -10700, "QF_5": -8200, "QSB_6": -4200,
          "SB_7": 0, "QSB_6p": 4200, "QF_5p": 8200, "TA_4p": 10700, "SC_8": 13700,
          "IS_7p": 19200, "TR_9": 23700},
    "Y_fasi": [-2200, 0, 2200],            # interfase 2.20 m (P-006 B-B, C-041 interasse 2200)
    "Y_portale_sbarre": -4200,             # P-006 B-B: 7 -> 6' = 4.20 m
    "Z_fondazione": 200,                   # +0.20 piano posa sostegni
    "Z_sbarre": 7200, "Z_derivazione": 4700, "Z_plinto_TR": 650,
    "Y_sbarre": [-4500, 5200],             # estensione modellata del tratto di sbarra (DC: planimetria P-001)
  },
  "DJ1003": {"H": 1500, "d_big": 235, "d_small": 200, "n_big": 16, "n_small": 15, "d_trunk": 130,
             "flange_bot": [235, 15], "fit_bot": [180, 160], "fit_top": [160, 110]},
  "LS6096_1": {"H": 4850, "tubo": [219.1, 5.9], "piastra_base": [550, 15], "trave": [4700, 250, 100], "passo_iso": 2200},
  "LS6096_2": {"H": 5350, "tubo": [219.1, 5.9], "piastra_base": [550, 15], "trave": [4700, 250, 100], "passo_iso": 2200},
  "DY43_SC": {"H": 4940, "tubo": [168.3, 6.3], "piastra_base": [550, 15], "piastra_testa": [300, 15]},
  "DY43_TA": {"H": 3150, "tubo": [168.3, 6.3], "piastra_base": [550, 15], "piastra_testa": [400, 20]},   # DC
  "DY43_TV": {"H": 2050, "tubo": [168.3, 6.3], "piastra_base": [550, 15], "piastra_testa": [400, 20]},   # DC
  "SBKC138": {"H": 1337, "Hges": 1513, "h_base": 83, "d_base": 260, "d_big": 205, "d_small": 153, "d_trunk": 95,
              "n_big": 14, "n_small": 13, "stud": [40, 93]},
  "GL313_polo": {"h_inf": 1400, "h_mid": 100, "h_cam": 1600, "h_top": 100, "d_mid": 420, "d_top": 380,
                 "iso_inf": [200, 360, 310, 13, 12], "camera": [260, 400, 350, 15, 14]},          # DC (scala 1:50)
  "GL313_sost": {"H": 2850, "lato": 500, "ang": 80, "piastra": [600, 20]},                           # DC
  "FK3_armadio": {"L": 450, "P": 350, "H": 850, "z0": 600, "dx": 410},                              # DC
  "S3C": {"interasse_col": 1120, "telaio": [2500, 300, 150], "col_H": 1450, "col": [150, 230, 190, 15, 14],
          "lama": [2300, 80, 50], "z_lama": 1660},                                                  # DC (scala 1:50)
  "S3C_sost": {"H": 2800, "tubo_c": [273, 8], "tubo_l": [114.3, 5], "dx_l": 500, "trave": [1300, 250, 100]},  # DC
  "CMM": {"L": 400, "P": 300, "H": 600, "z0": 700, "dx": -500},                                     # DC
  "TA_DY34": {"base": [500, 200], "iso": [1600, 220, 400, 340, 20, 19], "testa": [560, 400], "cupola": [320, 100],
              "z_P": 1950, "pad": [100, 100, 20]},                                                  # DC
  "TV_DY46": {"base": [520, 700], "iso": [1750, 180, 330, 280, 18, 17], "cap": [260, 80], "stud": [40, 50]},  # DC
  "LM1034_1": {"base": [160, 15], "stelo": 70, "h_asse": 150, "d_tubo": 40, "barile": [90, 200]},
  "LM1041": {"base": [160, 15], "stelo": 90, "h_asse": 150, "d_tubo": 100, "barile": [150, 250]},   # DC (tabella non fornita)
  "LM1085": {"codolo": [60, 110], "h_asse": 150, "d_tubo": 40, "barile": [80, 160]},
  "SBARRA": {"D": 100, "s": 5},                                                                     # Al 100/90 LC1050/60
  "COND": {"D": 40},                                                                                # LM1050/11 DC
  "TR_TBEA": {"Ltot": 6960, "Wtot": 3600, "skid": 250, "vasca": [6200, 1900, 2650], "Y_1V_da_estremo": 2969,
              "AT_dx": -625, "AT_passo": 1650, "AT_Ztop": 4088, "MT_Ztop": 3213, "MT_passo": 253,
              "conserv": [1050, 3500, 1315, 3560], "rad": [850, 40, 2000, 8, 600]},
  "FOND_TR": {"X": 6400, "Y": 8000},                                                                # DC
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

# =====================================================================
# FAMIGLIE (una funzione = un componente)
# =====================================================================

def f_DJ1003(c):
    q = PARAM['DJ1003']
    revolve(c, insulator_rz(0, q['H'], q['d_trunk'], q['d_big'], q['d_small'], q['n_big'], q['n_small'],
                            q['flange_bot'], q['fit_bot'], q['fit_top']), 'isolatore')


def f_portale(q):
    def build(c):
        H, (D, t) = q['H'], q['tubo']
        B, tb = q['piastra_base']
        L, W, Ht = q['trave']
        boxes(c, [(-B / 2, -B / 2, B / 2, B / 2)], 0, tb, 'piastra_base')
        cyl(c, 0, 0, D, tb, H - Ht, D - 2 * t, 'colonna')
        boxes(c, [(-L / 2, -W / 2, L / 2, W / 2)], H - Ht, H, 'trave_2UPN100')
        r = 60
        boxes(c, [(-D / 2 - 135, -5, -D / 2, 5), (D / 2, -5, D / 2 + 135, 5), (-5, -D / 2 - 135, 5, -D / 2), (-5, D / 2, 5, D / 2 + 135)], tb, tb + 200, 'nervature')
    return build


def f_sost_tubo(q):
    def build(c):
        H, (D, t) = q['H'], q['tubo']
        B, tb = q['piastra_base']
        T, tt = q['piastra_testa']
        boxes(c, [(-B / 2, -B / 2, B / 2, B / 2)], 0, tb, 'piastra_base')
        cyl(c, 0, 0, D, tb, H - tt, D - 2 * t, 'tubo')
        boxes(c, [(-T / 2, -T / 2, T / 2, T / 2)], H - tt, H, 'piastra_testa')
        boxes(c, [(-D / 2 - 120, -5, -D / 2, 5), (D / 2, -5, D / 2 + 120, 5), (-5, -D / 2 - 120, 5, -D / 2), (-5, D / 2, 5, D / 2 + 120)], tb, tb + 150, 'nervature')
    return build


def f_SBKC(c):
    q = PARAM['SBKC138']
    revolve(c, [(0, 0), (q['d_base'] / 2, 0), (q['d_base'] / 2, 50), (110, 50), (110, q['h_base']), (0, q['h_base'])], 'base_isolante')
    hb = q['h_base']
    revolve(c, insulator_rz(hb, q['H'], q['d_trunk'], q['d_big'], q['d_small'], q['n_big'], q['n_small'],
                            (150, 15), (150, 60), (150, 50)), 'involucro_silicone')
    sd, sh = q['stud']
    cyl(c, 0, 0, sd, hb + q['H'], hb + q['H'] + sh, name='codolo_AT')


def f_morsetto(q, axis='x'):
    def build(c):
        if 'base' in q:
            cyl(c, 0, 0, q['base'][0], 0, q['base'][1], name='flangia')
            cyl(c, 0, 0, q['stelo'], q['base'][1], q['h_asse'], name='stelo')
        else:
            cyl(c, 0, 0, q['codolo'][0], 0, q['h_asse'], name='codolo')
        d, L = q['barile']
        cyl_h(c, axis, 0, q['h_asse'], d, -L / 2, L / 2, 'barile')
    return build


def f_GL313_polo(c):
    q = PARAM['GL313_polo']
    z1 = q['h_inf']; z2 = z1 + q['h_mid']; z3 = z2 + q['h_cam']; z4 = z3 + q['h_top']
    a = q['iso_inf']; b = q['camera']
    revolve(c, insulator_rz(0, z1, a[0], a[1], a[2], a[3], a[4], (360, 25), (260, 120), (300, 60)), 'isolatore_supporto')
    cyl(c, 0, 0, q['d_mid'], z1, z2, name='carter_intermedio')
    revolve(c, insulator_rz(z2, q['h_cam'], b[0], b[1], b[2], b[3], b[4], (q['d_mid'], 20), (320, 100), (320, 80)), 'camera_interruzione')
    cyl(c, 0, 0, q['d_top'], z3, z4, name='testa')
    zm = (z1 + z2) / 2.0
    boxes(c, [(-q['d_mid'] / 2 - 120, -50, -q['d_mid'] / 2, 50)], zm - 10, zm + 10, 'attacco_inferiore')
    boxes(c, [(q['d_top'] / 2, -50, q['d_top'] / 2 + 120, 50)], z4 - 30, z4 - 10, 'attacco_superiore')


def f_GL313_sost(c):
    q = PARAM['GL313_sost']
    H, l, a = q['H'], q['lato'], q['ang']
    B, t = q['piastra']
    boxes(c, [(-B / 2, -B / 2, B / 2, B / 2)], 0, t, 'piastra_base')
    h = l / 2
    boxes(c, [(-h, -h, -h + a, -h + a), (h - a, -h, h, -h + a), (-h, h - a, -h + a, h), (h - a, h - a, h, h)], t, H - t, 'montanti')
    boxes(c, [(-B / 2, -B / 2, B / 2, B / 2)], H - t, H, 'piastra_testa')
    for zz in (900, 1700, 2400):
        boxes(c, [(-h + a, -h, h - a, -h + 10), (-h + a, h - 10, h - a, h), (-h, -h + a, -h + 10, h - a), (h - 10, -h + a, h, h - a)], zz, zz + 60, 'traversi')


def f_box_cab(q):
    def build(c):
        boxes(c, [(-q['L'] / 2, -q['P'] / 2, q['L'] / 2, q['P'] / 2)], 0, q['H'], 'armadio')
    return build


def f_S3C(terra):
    def build(c):
        q = PARAM['S3C']
        L, W, Hf = q['telaio']
        a = q['interasse_col']
        boxes(c, [(-L / 2, -W / 2, L / 2, W / 2)], 0, Hf, 'telaio_base')
        col = q['col']
        for x in (-a, 0, a):
            rz = insulator_rz(Hf, q['col_H'], col[0], col[1], col[2], col[3], col[4], (220, 20), (180, 80), (180, 60))
            f = revolve(c, rz, 'colonna')
            if x != 0:
                _move(c, f.bodies.item(0), x, 0)
        zt = Hf + q['col_H']
        cyl(c, 0, 0, 200, zt, q['z_lama'], name='testa_rotante')
        bl, bw, bh = q['lama']
        boxes(c, [(-bl / 2, -bw / 2, bl / 2, bw / 2)], q['z_lama'], q['z_lama'] + bh, 'lama')
        boxes(c, [(-a - 125, -75, -a + 125, 75), (a - 125, -75, a + 125, 75)], zt, zt + 120, 'contatti_fissi')
        boxes(c, [(-a - 145 - 120, -50, -a - 145, 50), (a + 145, -50, a + 145 + 120, 50)], zt + 40, zt + 60, 'attacchi_AT')
        if terra:
            cyl_h(c, 'x', W / 2 + 60, Hf + 70, 50, -L / 2 - 50, L / 2 - 400, 'lama_terra')
            boxes(c, [(-L / 2 - 100, W / 2, -L / 2 + 100, W / 2 + 120)], 0, Hf + 120, 'cerniera_terra')
    return build


def f_S3C_sost(c):
    q = PARAM['S3C_sost']
    H = q['H']
    L, W, Ht = q['trave']
    for x, (D, t) in ((0, q['tubo_c']), (-q['dx_l'], q['tubo_l']), (q['dx_l'], q['tubo_l'])):
        boxes(c, [(x - 225, -225, x + 225, 225)], 0, 15, 'piastra_base')
        cyl(c, x, 0, D, 15, H - Ht, D - 2 * t, 'montante')
    boxes(c, [(-L / 2, -W / 2, L / 2, W / 2)], H - Ht, H, 'trave_testa')


def f_TA(c):
    q = PARAM['TA_DY34']
    bd, bh = q['base']
    boxes(c, [(-bd / 2, -bd / 2, bd / 2, bd / 2)], 0, bh, 'cassa_base')
    boxes(c, [(-150, bd / 2, 150, bd / 2 + 200)], 20, 270, 'cassetta_secondari')
    i = q['iso']
    revolve(c, insulator_rz(bh, i[0], i[1], i[2], i[3], i[4], i[5], (300, 20), (260, 100), (300, 60)), 'isolatore')
    z = bh + i[0]
    td, th = q['testa']
    cyl(c, 0, 0, td, z, z + th, name='testa')
    cd, ch = q['cupola']
    cyl(c, 0, 0, cd, z + th, z + th + ch, name='cupola')
    pw, ph, pt = q['pad']
    zp = q['z_P']
    boxes(c, [(-td / 2 - 100, -pw / 2, -td / 2, pw / 2), (td / 2, -pw / 2, td / 2 + 100, pw / 2)], zp - pt / 2, zp + pt / 2, 'attacchi_P1_P2')


def f_TV(c):
    q = PARAM['TV_DY46']
    bd, bh = q['base']
    boxes(c, [(-bd / 2, -bd / 2, bd / 2, bd / 2)], 0, bh, 'cassa_base')
    boxes(c, [(-150, bd / 2, 150, bd / 2 + 180)], 150, 450, 'cassetta_secondari')
    i = q['iso']
    revolve(c, insulator_rz(bh, i[0], i[1], i[2], i[3], i[4], i[5], (300, 20), (240, 120), (240, 60)), 'isolatore')
    z = bh + i[0]
    cyl(c, 0, 0, q['cap'][0], z, z + q['cap'][1], name='cappello')
    cyl(c, 0, 0, q['stud'][0], z + q['cap'][1], z + q['cap'][1] + q['stud'][1], name='codolo_AT')


def f_sbarra(L):
    def build(c):
        q = PARAM['SBARRA']
        sk = c.sketches.add(c.xZConstructionPlane)
        cc = sk.modelToSketchSpace(P3(0, 0, 0))
        sk.sketchCurves.sketchCircles.addByCenterRadius(cc, q['D'] / 2 * MM)
        sk.sketchCurves.sketchCircles.addByCenterRadius(cc, (q['D'] / 2 - q['s']) * MM)
        f = _extrude(c, c.xZConstructionPlane, _all_profiles(sk, True), 0, L, 'y')
        f.bodies.item(0).name = 'tubo_Al_100_90'
    return build


def f_TR(c):
    """Trasformatore 25 MVA 150/20.8 kV TBEA SZ-25000/150 (LOD 200). Origine: proiezione a terra del passante 1V."""
    q = PARAM['TR_TBEA']
    y0 = -q['Y_1V_da_estremo']               # estremo lato 1U
    VL, VW, VH = q['vasca']
    sk_h = q['skid']
    boxes(c, [(-VW / 2 - 100, y0 + 300, VW / 2 + 100, y0 + 300 + 200), (-VW / 2 - 100, y0 + VL - 500, VW / 2 + 100, y0 + VL - 300)], 0, sk_h, 'carrello')
    boxes(c, [(-VW / 2, y0, VW / 2, y0 + VL)], sk_h, sk_h + VH, 'cassa')
    boxes(c, [(-VW / 2 - 40, y0 - 40, VW / 2 + 40, y0 + VL + 40)], sk_h + VH, sk_h + VH + 40, 'coperchio')
    boxes(c, [(-450, y0 + VL, 450, y0 + q['Ltot'])], 600, 2200, 'armadio_OLTC')
    fx, fy, fz, nf, pf = q['rad']
    rects = []
    for side in (-1, 1):
        for k in range(nf):
            yy = y0 + 900 + k * pf
            x0 = side * VW / 2
            x1 = side * (VW / 2 + fx)
            rects.append((min(x0, x1), yy, max(x0, x1), yy + fy))
    boxes(c, rects, 700, 700 + fz, 'radiatori')
    zc = sk_h + VH + 40
    for k in (-1, 0, 1):
        y = k * q['AT_passo']
        cyl(c, q['AT_dx'], y, 420, zc, zc + 250, name='torretta_AT')
        rz = insulator_rz(zc + 250, q['AT_Ztop'] - zc - 250 - 40, 160, 330, 280, 9, 8, (300, 20), (240, 120), (200, 80))
        f = revolve(c, rz, 'passante_AT')
        _move(c, f.bodies.item(0), q['AT_dx'], y)
        cyl(c, q['AT_dx'], y, 40, q['AT_Ztop'] - 40, q['AT_Ztop'], name='codolo_AT')
    for k in range(4):
        x = 250 + (k - 1.5) * q['MT_passo']
        cyl(c, x, y0 + 600, 180, zc, q['MT_Ztop'], name='passante_MT')
    d, L, dx, zcen = q['conserv']
    cyl_h(c, 'y', dx, zcen, d, y0 + 800, y0 + 800 + L, 'conservatore')
    boxes(c, [(dx - 60, y0 + 1200, dx + 60, y0 + 1320), (dx - 60, y0 + 800 + L - 520, dx + 60, y0 + 800 + L - 400)], zc, zcen, 'supporti_conservatore')


def f_fond_TR(c):
    q = PARAM['FOND_TR']
    boxes(c, [(-q['X'] / 2, -q['Y'] / 2, q['X'] / 2, q['Y'] / 2)], 0, PARAM['layout']['Z_plinto_TR'], 'plinto')

# =====================================================================
# ASSIEME
# =====================================================================
LIB = {}


def lib(libcomp, key, builder, ifc, descr, fonte):
    if key in LIB:
        return LIB[key]
    occ = libcomp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    c = occ.component
    c.name = key
    builder(c)
    c.description = descr
    a = c.attributes
    a.add('BIM', 'IfcClass', ifc)
    a.add('BIM', 'Fonte', fonte)
    LIB[key] = c
    return c


def place(parent, comp, x, y, z, rot_deg=0.0, tag=None):
    m = adsk.core.Matrix3D.create()
    if rot_deg:
        m.setToRotation(math.radians(rot_deg), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
    m.translation = adsk.core.Vector3D.create(x * MM, y * MM, z * MM)
    occ = parent.occurrences.addExistingComponent(comp, m)
    if tag:
        occ.attributes.add('BIM', 'Tag', tag)
    return occ


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


def build_all(design):
    root = design.rootComponent
    LY = PARAM['layout']
    X = LY['X']; YF = LY['Y_fasi']; ZF = LY['Z_fondazione']
    FASI = ['L1', 'L2', 'L3']

    libocc = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    libc = libocc.component; libc.name = '00_LIBRERIA_ORGANI'

    m = adsk.core.Matrix3D.create()
    m.setToRotation(-math.pi / 2, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
    site = root.occurrences.addNewComponent(m).component
    site.name = 'CP_FAGGIANO_AT_ProfiloA-A'

    def sub(name):
        s = site.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        s.name = name
        return s
    SL, SB, ST = sub('STALLO_LINEA'), sub('SISTEMA_SBARRE'), sub('STALLO_TRAFO')

    # --- definizioni (libreria) ---
    D = {}
    D['ISO'] = lib(libc, 'ISO_DJ1003', f_DJ1003, 'IfcDiscreteAccessory', 'Isolatore portante 150 kV tab. ENEL DJ1003 (Bonomi ISI-BUL-A16+15-GG)', 'Bonomi S050645')
    D['P1'] = lib(libc, 'SOST_LS6096-1_H4850', f_portale(PARAM['LS6096_1']), 'IfcMember', 'Sostegno terna isolatori portanti H4850', 'C-041 / LS6016-1')
    D['P2'] = lib(libc, 'SOST_LS6096-2_H5350', f_portale(PARAM['LS6096_2']), 'IfcMember', 'Sostegno terna isolatori portanti sbarre H5350', 'C-041 / LS6016-1')
    D['SCs'] = lib(libc, 'SOST_DY43_SC_H4940', f_sost_tubo(PARAM['DY43_SC']), 'IfcMember', 'Sostegno scaricatore Tridelta 221281', 'C-036')
    D['TAs'] = lib(libc, 'SOST_DY43_TA', f_sost_tubo(PARAM['DY43_TA']), 'IfcMember', 'Sostegno TA (DC)', 'P-006 scala')
    D['TVs'] = lib(libc, 'SOST_DY43_TV', f_sost_tubo(PARAM['DY43_TV']), 'IfcMember', 'Sostegno TV (DC)', 'P-006 scala')
    D['SC'] = lib(libc, 'SCAR_SBKC138-SMII', f_SBKC, 'IfcProtectiveDevice', 'Scaricatore Tridelta SBKC 138/SM-II CQX 4500', 'E-007 / disegno 2313.6-0138')
    D['LM1034'] = lib(libc, 'MORS_LM1034-1', f_morsetto(PARAM['LM1034_1'], 'x'), 'IfcDiscreteAccessory', 'Morsetto portante tubo Al d40', 'ENEL LM1034')
    D['LM1041'] = lib(libc, 'MORS_LM1041', f_morsetto(PARAM['LM1041'], 'y'), 'IfcDiscreteAccessory', 'Morsetto portante sbarra d100 (DC)', 'P-006')
    D['LM1085'] = lib(libc, 'MORS_LM1085', f_morsetto(PARAM['LM1085'], 'x'), 'IfcDiscreteAccessory', 'Morsetto a T tubo d40 - codolo', 'ENEL LM1085')
    D['QF'] = lib(libc, 'INT_GL313_POLO', f_GL313_polo, 'IfcSwitchingDevice', 'Polo interruttore GE GL313 170 kV 2000 A 40 kA SF6', 'E-002 / D1301-AB-IT / P-006 scala')
    D['QFs'] = lib(libc, 'SOST_INT_GL313', f_GL313_sost, 'IfcMember', 'Struttura di supporto polo GL313 (DC)', 'P-006 scala')
    D['FK3'] = lib(libc, 'ARM_MANOVRA_FK3-1', f_box_cab(PARAM['FK3_armadio']), 'IfcElectricDistributionBoard', 'Armadio di manovra a molla FK3-1', 'D1301-AB-IT')
    D['QS'] = lib(libc, 'SEZ_S3CT_TERRA', f_S3C(True), 'IfcSwitchingDevice', 'Sezionatore GE S3CT doppia interruzione laterale + lame di terra 170 kV 1250 A', 'M-009 / D1210-AA-IT')
    D['QSB'] = lib(libc, 'SEZ_S3C', f_S3C(False), 'IfcSwitchingDevice', 'Sezionatore GE S3C doppia interruzione laterale 170 kV 1250 A', 'D1210-AA-IT')
    D['QSs'] = lib(libc, 'SOST_SEZ_S3C', f_S3C_sost, 'IfcMember', 'Sostegno sezionatore (DC)', 'P-006 scala')
    D['CMM'] = lib(libc, 'ARM_CMM', f_box_cab(PARAM['CMM']), 'IfcElectricDistributionBoard', 'Comando a motore CMM', 'D1060-AC-IT')
    D['TA'] = lib(libc, 'TA_DY34', f_TA, 'IfcTransformer', 'TA 170 kV tipo DY34 (DC)', 'P-006 scala')
    D['TV'] = lib(libc, 'TV_DY46-2', f_TV, 'IfcTransformer', 'TV 170 kV tipo DY46/2 (DC)', 'P-006 scala / M-019')
    yb0, yb1 = LY['Y_sbarre']
    D['SBARRA'] = lib(libc, 'SBARRA_AL100-90', f_sbarra(yb1 - yb0), 'IfcCableCarrierSegment', 'Sbarra tubo Al 100/90 LC1050/60', 'P-006')
    D['TR'] = lib(libc, 'TR_TBEA_25MVA', f_TR, 'IfcTransformer', 'Trasformatore TBEA SZ-25000/150 25 MVA 150/20.8 kV ONAN', 'TBEA 1TBC.710.H10299.1')
    D['FTR'] = lib(libc, 'FOND_TR', f_fond_TR, 'IfcFooting', 'Plinto trasformatore (DC)', 'P-006')
    libocc.isLightBulbOn = False

    # --- STALLO LINEA (lato X negativo) e STALLO TRAFO (lato X positivo) ---
    H_DY43 = {k: PARAM[k]['H'] for k in ('DY43_SC', 'DY43_TA', 'DY43_TV')}
    zQF = ZF + PARAM['GL313_sost']['H']
    zQS = ZF + PARAM['S3C_sost']['H']
    for i, y in enumerate(YF):
        f = FASI[i]
        # linea
        place(SL, D['TVs'], X['TV_2'], y, ZF); place(SL, D['TV'], X['TV_2'], y, ZF + H_DY43['DY43_TV'], tag='TV2-' + f)
        place(SL, D['QSs'], X['QS_3'], y, ZF); place(SL, D['QS'], X['QS_3'], y, zQS, tag='QS3-' + f)
        place(SL, D['TAs'], X['TA_4'], y, ZF); place(SL, D['TA'], X['TA_4'], y, ZF + H_DY43['DY43_TA'], tag='TA4-' + f)
        place(SL, D['QFs'], X['QF_5'], y, ZF); place(SL, D['QF'], X['QF_5'], y, zQF, tag='QF5-' + f)
        place(SL, D['FK3'], X['QF_5'] + PARAM['FK3_armadio']['dx'], y, ZF + PARAM['FK3_armadio']['z0'])
        place(SL, D['QSs'], X['QSB_6'], y, ZF); place(SL, D['QSB'], X['QSB_6'], y, zQS, tag='QSB6-' + f)
        # trafo (apparecchi ruotati di 180 deg: attacco superiore verso le sbarre)
        place(ST, D['QSs'], X['QSB_6p'], y, ZF); place(ST, D['QSB'], X['QSB_6p'], y, zQS, 180, tag='QSB6p-' + f)
        place(ST, D['QFs'], X['QF_5p'], y, ZF); place(ST, D['QF'], X['QF_5p'], y, zQF, 180, tag='QF5p-' + f)
        place(ST, D['FK3'], X['QF_5p'] - PARAM['FK3_armadio']['dx'], y, ZF + PARAM['FK3_armadio']['z0'])
        place(ST, D['TAs'], X['TA_4p'], y, ZF); place(ST, D['TA'], X['TA_4p'], y, ZF + H_DY43['DY43_TA'], tag='TA4p-' + f)
        place(ST, D['SCs'], X['SC_8'], y, ZF)
        zsc = ZF + H_DY43['DY43_SC']
        place(ST, D['SC'], X['SC_8'], y, zsc, tag='FV8-' + f)
        place(ST, D['LM1085'], X['SC_8'], y, zsc + PARAM['SBKC138']['Hges'] - 110)
    # comandi a motore sezionatori (uno per tripolare, sulla fase centrale)
    cm = PARAM['CMM']
    place(SL, D['CMM'], X['QS_3'] + cm['dx'], 0, ZF + cm['z0'])
    place(SL, D['CMM'], X['QS_3'] - cm['dx'], 0, ZF + cm['z0'])      # comando lame di terra
    place(SL, D['CMM'], X['QSB_6'] + cm['dx'], 0, ZF + cm['z0'])
    place(ST, D['CMM'], X['QSB_6p'] - cm['dx'], 0, ZF + cm['z0'])

    # isolatori portanti 7' (trave lungo Y) e trafo
    zP1 = ZF + PARAM['LS6096_1']['H']
    place(ST, D['P1'], X['IS_7p'], 0, ZF, 90)
    for i, y in enumerate(YF):
        place(ST, D['ISO'], X['IS_7p'], y, zP1, tag='IS7p-' + FASI[i])
        place(ST, D['LM1034'], X['IS_7p'], y, zP1 + PARAM['DJ1003']['H'])
    zTR = LY['Z_plinto_TR']
    place(ST, D['FTR'], X['TR_9'], 0, 0)
    place(ST, D['TR'], X['TR_9'] - PARAM['TR_TBEA']['AT_dx'], 0, zTR, tag='TR9')

    # --- SISTEMA SBARRE ---
    zP2 = ZF + PARAM['LS6096_2']['H']
    yP = LY['Y_portale_sbarre']
    place(SB, D['P2'], 0, yP, ZF)
    XB = [-2200, 0, 2200]
    for i, xb in enumerate(XB):
        place(SB, D['ISO'], xb, yP, zP2, tag='IS7-' + FASI[i])
        place(SB, D['LM1041'], xb, yP, zP2 + PARAM['DJ1003']['H'])
        place(SB, D['SBARRA'], xb, yb0, LY['Z_sbarre'], tag='SB-' + FASI[i])

    # --- CONDUTTORI ---
    dC = PARAM['COND']['D']
    zD = LY['Z_derivazione']
    q = PARAM['S3C']; xs = q['interasse_col'] + 145 + 60
    zQSa = zQS + q['col_H'] + q['telaio'][2] + 50
    zTV = ZF + H_DY43['DY43_TV'] + PARAM['TV_DY46']['base'][1] + PARAM['TV_DY46']['iso'][0] + 80
    zTA = ZF + H_DY43['DY43_TA'] + PARAM['TA_DY34']['z_P']
    pq = PARAM['GL313_polo']
    zQFi = zQF + pq['h_inf'] + pq['h_mid'] / 2
    zQFs = zQF + pq['h_inf'] + pq['h_mid'] + pq['h_cam'] + pq['h_top'] - 20
    dQFi = pq['d_mid'] / 2 + 60; dQFs = pq['d_top'] / 2 + 60
    dTA = PARAM['TA_DY34']['testa'][0] / 2 + 50
    zSC = zsc + PARAM['SBKC138']['Hges'] - 110 + PARAM['LM1085']['h_asse']
    z7p = zP1 + PARAM['DJ1003']['H'] + PARAM['LM1034_1']['h_asse']
    tq = PARAM['TR_TBEA']
    CL, CB, CT = [], [], []
    for i, y in enumerate(YF):
        # linea
        CL.append([(X['TV_2'], y, zTV), (X['TV_2'], y, zQSa), (X['QS_3'] - xs, y, zQSa)])
        CL.append([(X['QS_3'] + xs, y, zQSa), (X['QS_3'] + xs + 500, y, zQSa), (X['TA_4'] - dTA - 500, y, zTA), (X['TA_4'] - dTA, y, zTA)])
        CL.append([(X['TA_4'] + dTA, y, zTA), (X['TA_4'] + dTA + 400, y, zTA), (X['QF_5'] - dQFi - 500, y, zQFi), (X['QF_5'] - dQFi, y, zQFi)])
        CL.append([(X['QF_5'] + dQFs, y, zQFs), (X['QF_5'] + dQFs + 400, y, zQFs), (X['QSB_6'] - xs - 500, y, zQSa), (X['QSB_6'] - xs, y, zQSa)])
        # derivazione sbarre (6 <-> 6') e calata dalla sbarra di fase
        CB.append([(X['QSB_6'] + xs, y, zQSa), (X['QSB_6p'] - xs, y, zQSa)])
        CB.append([(XB[i], y, zQSa), (XB[i], y, LY['Z_sbarre'] - 50)])
        # trafo
        CT.append([(X['QSB_6p'] + xs, y, zQSa), (X['QSB_6p'] + xs + 500, y, zQSa), (X['QF_5p'] - dQFs - 400, y, zQFs), (X['QF_5p'] - dQFs, y, zQFs)])
        CT.append([(X['QF_5p'] + dQFi, y, zQFi), (X['QF_5p'] + dQFi + 500, y, zQFi), (X['TA_4p'] - dTA - 400, y, zTA), (X['TA_4p'] - dTA, y, zTA)])
        CT.append([(X['TA_4p'] + dTA, y, zTA), (X['TA_4p'] + dTA + 400, y, zTA), (X['SC_8'] - 600, y, zSC), (X['SC_8'], y, zSC)])
        CT.append([(X['SC_8'], y, zSC), (X['IS_7p'], y, z7p)])
        yt = (i - 1) * tq['AT_passo']
        CT.append([(X['IS_7p'], y, z7p), (X['IS_7p'] + 1500, y, z7p), (X['TR_9'], yt, tq['AT_Ztop'] + zTR + 300), (X['TR_9'], yt, tq['AT_Ztop'] + zTR)])
    for comp_, pls, nm in ((SL, CL, 'COND_LINEA'), (SB, CB, 'COND_DERIV_SBARRE'), (ST, CT, 'COND_TRAFO')):
        cc = comp_.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        cc.name = nm
        conductor(cc, pls, dC, 'conduttore_LM1050-11')
    return root


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        build_all(design)
        app.activeViewport.fit()
        # salvataggio nel progetto "Progetti AI"
        try:
            for pr in app.data.dataProjects:
                if pr.name == 'Progetti AI':
                    doc.saveAs('CP_Faggiano_Sezione_AT_A-A', pr.rootFolder, 'Stallo AT linea+sbarre+trafo LOD200-300', '')
                    break
        except:
            print('salvataggio non riuscito: ' + traceback.format_exc())
        print('OK: ' + ', '.join(sorted(LIB.keys())))
    except:
        print('ERRORE:\n' + traceback.format_exc())
