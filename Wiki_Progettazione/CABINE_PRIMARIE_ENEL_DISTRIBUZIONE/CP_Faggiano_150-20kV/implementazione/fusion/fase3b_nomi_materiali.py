# -*- coding: utf-8 -*-
# Fase 3b - propaga il nome ai corpi multipli di una stessa feature e riassegna i materiali
import adsk.core, adsk.fusion, traceback
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

def run(context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        k = 0
        for c in des.allComponents:
            for coll in (c.features.extrudeFeatures, c.features.revolveFeatures):
                for f in coll:
                    if f.bodies.count > 1:
                        base = f.bodies.item(0).name
                        for i in range(1, f.bodies.count):
                            b = f.bodies.item(i)
                            if b.name.startswith('Corpo') or b.name.startswith('Body'):
                                b.name = '%s_%d' % (base, i); k += 1
        done, miss = apply_materials(app, des)
        app.activeDocument.save('Nomi corpi e materiali completati')
        print('rinominati', k, 'materiali', done, 'mancanti', miss)
    except:
        print('ERRORE:\n' + traceback.format_exc())
