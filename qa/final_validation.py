#!/usr/bin/env python3
"""Final validation battery: >1000 pre-registered structural checks against
the SHIPPED /api/convert (default POST, no fields). Kept in-repo because ad-
hoc copies under /tmp were repeatedly lost to sandbox wipes; run with:

  PYTHONPATH=qa:vendor:app/deps:. python3 qa/final_validation.py

Gates: every probe -> 200, XML well-formed, dims preserved, no NaN/Inf,
>=1 path; subset re-POST byte-determinism; both sealed uploads.
"""
import sys, io, json, time, hashlib, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'qa')); sys.path.insert(0, str(ROOT/'vendor')); sys.path.insert(0, str(ROOT/'app/deps'))
import urllib.request
import numpy as np
from PIL import Image, ImageDraw
import xml.etree.ElementTree as ET

BASE = 'http://127.0.0.1:8000'
CHECKS = []

def check(name, ok, detail=''):
    CHECKS.append((name, bool(ok), str(detail)))

def post(data, fname, timeout=90):
    boundary = '____fv' + hashlib.md5(fname.encode()).hexdigest()
    body = [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
            data, f'\r\n--{boundary}--\r\n'.encode()]
    req = urllib.request.Request(BASE + '/api/convert', data=b''.join(body),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode()), time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, {'detail': ''}, time.time() - t0

def gen_flat(seed):
    r = np.random.default_rng(seed)
    im = Image.new('RGBA', (256, 256), tuple(int(x) for x in r.integers(140, 255, 3)) + (255,))
    dr = ImageDraw.Draw(im)
    for _ in range(int(r.integers(2, 6))):
        c = tuple(int(x) for x in r.integers(0, 200, 3)) + (255,)
        x0, y0 = r.integers(0, 160, 2); x1, y1 = x0 + r.integers(30, 96), y0 + r.integers(30, 96)
        if r.random() < 0.5: dr.ellipse([x0, y0, x1, y1], fill=c)
        else: dr.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=c)
    return im

def gen_alpha(seed):
    im = gen_flat(seed)
    a = np.array(im).copy(); a[..., 3] = (a[..., 3].astype(np.float32) * 0.55).astype(np.uint8)
    im2 = Image.new('RGBA', im.size, (0, 0, 0, 0)); pa = Image.fromarray(a)
    im2.paste(pa, (0, 0), pa)
    return im2

def gen_gradient(seed):
    r = np.random.default_rng(seed); c0 = r.integers(0, 255, 3); c1 = r.integers(0, 255, 3)
    t = np.linspace(0, 1, 256)[None, :, None]
    img = np.repeat((c0[None, None, :] * (1 - t) + c1[None, None, :] * t), 256, axis=0).astype(np.uint8)
    return Image.fromarray(img, 'RGB').convert('RGBA')

def gen_strokes(seed):
    r = np.random.default_rng(seed)
    im = Image.new('RGBA', (256, 256), (255, 255, 255, 255)); dr = ImageDraw.Draw(im)
    for _ in range(int(r.integers(3, 8))):
        pts = [(int(x), int(y)) for x, y in r.integers(10, 246, (int(r.integers(2, 5)), 2))]
        dr.line(pts, fill=(20, 20, 40, 255), width=int(r.integers(1, 4)))
    return im

def gen_noise(seed):
    im = gen_flat(seed)
    a = np.asarray(im).astype(np.int16)
    n = np.random.default_rng(seed + 7).normal(0, 7, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a + n, 0, 255).astype(np.uint8), 'RGBA')

def gen_icons(seed):
    r = np.random.default_rng(seed)
    cols = [(230, 60, 90), (40, 150, 220), (250, 200, 60), (90, 200, 120), (150, 90, 220)]
    bg = cols[int(r.integers(0, 5))]
    im = Image.new('RGBA', (256, 256), bg + (255, )); dr = ImageDraw.Draw(im)
    fg = tuple(255 - c for c in bg) + (255,)
    if r.random() < 0.5:
        rs = int(r.integers(3, 8))
        dr.regular_polygon((128, 128, 60), n_sides=rs, rotation=90, fill=fg)
    else:
        dr.ellipse([68, 68, 188, 188], fill=fg); dr.ellipse([103, 103, 153, 153], fill=bg + (255,))
    return im

GENS = [('flat', gen_flat), ('alpha', gen_alpha), ('gradient', gen_gradient),
        ('strokes', gen_strokes), ('noise', gen_noise), ('icon', gen_icons)]

def pngb(im):
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()

def one(item):
    name, im = item
    st, d, t = post(pngb(im), f'{name}.png')
    out = {'name': name, 'status': st}
    if st == 200:
        out['svg'] = d.get('svg', ''); out['meta'] = d.get('meta', {})
        if name.endswith(('00', '01', '02', '03')):
            st2, d2, _ = post(pngb(im), f'{name}.png')
            if st2: out['det'] = (d2.get('svg') == out['svg'])
    return out

def main():
    probes = []
    for gi, (gname, g) in enumerate(GENS):
        for k in range(40):
            probes.append((f'{gname}-{k:02d}', g(1000 * (gi + 1) + k)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(one, probes))
    print(f'conversions done in {time.time()-t0:.1f}s', flush=True)
    for o in results:
        name = o['name']; ok = o['status'] == 200
        check(f'{name} status 200', ok)
        if not ok: continue
        svg = o['svg']; m = o['meta']
        try: ET.fromstring(svg); xml_ok = True
        except Exception: xml_ok = False
        check(f'{name} svg XML well-formed', xml_ok)
        check(f'{name} dims preserved', m.get('width') == 256 and m.get('height') == 256,
              f"{m.get('width')}x{m.get('height')}")
        check(f'{name} no NaN/Inf', not re.search(r'nan|inf', svg, re.I))
        check(f'{name} at least 1 vector element', m.get('paths', 0) >= 1 or '<rect' in svg, m.get('paths'))
        if 'det' in o: check(f'{name} determinism byte-identical', o['det'])
    for up in ['teal-orbit-logo.png', 'blue-bird-appicon.png']:
        data = open(ROOT/f'test-assets/images/user-provided/{up}', 'rb').read()
        st, d, t = post(data, up)
        check(f'upload {up} 200 + svg', st == 200 and d.get('svg'))
        check(f'upload {up} XML well-formed', st == 200 and bool(ET.fromstring(d['svg'])))
        check(f'upload {up} paths >= 10', st == 200 and d['meta'].get('paths', 0) >= 10, d.get('meta', {}).get('paths'))
        check(f'upload {up} paths < 300', st == 200 and d['meta'].get('paths', 999) < 300, d.get('meta', {}).get('paths'))
        check(f'upload {up} latency < 5s', t < 5, f'{t:.2f}s')
    n = len(CHECKS); p = sum(1 for _, ok, _ in CHECKS if ok)
    print(f'FINAL VALIDATION: {p}/{n} structural checks PASS')
    for c in [c for c in CHECKS if not c[1]][:15]: print(' FAIL', c[0], c[2][:60])
    json.dump({'total': n, 'passed': p, 'checks': [{'name': a, 'ok': b, 'detail': c} for a, b, c in CHECKS]},
              open(ROOT/'qa/results/final_validation.json', 'w'))
    return 0 if p == n else 1

if __name__ == '__main__':
    sys.exit(main())
