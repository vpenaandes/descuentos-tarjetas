"""Prepara la carpeta `docs/` (GitHub Pages) con la app de cada mes.

Uso:
    python scripts/publish_site.py [--mes AAAA-MM] [--categoria restaurantes] [--no-screens] [--quality 60]

Hace:
  - docs/<mes>/index.html            <- copia de output/<mes>/descuentos_<cat>_<mes>.html
  - docs/<mes>/screens/<id>.jpg      <- capturas PNG comprimidas a JPEG (≈115 MB -> ≈12 MB)
  - docs/index.html                  <- redirige al mes más reciente + lista de meses
Después: git add docs && git commit && git push  (Pages sirve desde main:/docs)
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")


def compress_screens(src_dir, dst_dir, quality):
    try:
        from PIL import Image
    except ImportError:
        print("(sin Pillow: copio PNG tal cual)", file=sys.stderr)
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
        return "png"
    os.makedirs(dst_dir, exist_ok=True)
    n = 0
    for p in glob.glob(os.path.join(src_dir, "*.png")):
        out = os.path.join(dst_dir, os.path.splitext(os.path.basename(p))[0] + ".jpg")
        if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(p):
            continue
        im = Image.open(p).convert("RGB")
        w, h = im.size
        if w > 1100:                       # 1280 -> 1100 px de ancho basta para leer
            im = im.resize((1100, int(h * 1100 / w)))
        if im.size[1] > 6000:              # páginas kilométricas: cortar (lo importante está arriba)
            im = im.crop((0, 0, im.size[0], 6000))
        im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        n += 1
    print(f"  {n} capturas comprimidas -> {dst_dir}", file=sys.stderr)
    return "jpg"


def write_pwa(docs, ultimo_mes):
    """manifest + service worker + iconos: la web se instala como app en el celular."""
    manifest = {
        "name": "Descuentos restaurantes", "short_name": "Descuentos",
        "description": "Descuentos de restaurantes con tarjetas Falabella y Santander",
        "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#f6f7f9", "theme_color": "#2563eb", "lang": "es-CL",
        "icons": [{"src": "./icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                  {"src": "./icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
                  {"src": "./icon-180.png", "sizes": "180x180", "type": "image/png"}],
    }
    json.dump(manifest, open(os.path.join(docs, "manifest.webmanifest"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _icons(docs)
    # SW: cache-first para la app del mes vigente; red primero para lo demás.
    sw = f"""// generado por publish_site.py
const CACHE = "descuentos-{ultimo_mes}-v1";
const CORE = ["./", "./{ultimo_mes}/", "./manifest.webmanifest"];
self.addEventListener("install", e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE).catch(() => {{}})).then(() => self.skipWaiting()));
}});
self.addEventListener("activate", e => {{
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
}});
self.addEventListener("fetch", e => {{
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;   // tiles OSM: siempre red
  e.respondWith(
    fetch(e.request).then(r => {{
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {{}});
      return r;
    }}).catch(() => caches.match(e.request).then(r => r || caches.match("./{ultimo_mes}/")))
  );
}});
"""
    open(os.path.join(docs, "sw.js"), "w", encoding="utf-8").write(sw)


def _icons(docs):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    for size in (192, 512, 180):
        im = Image.new("RGB", (size, size), "#2563eb")
        d = ImageDraw.Draw(im)
        r = int(size * 0.30)
        d.ellipse([size * .18, size * .18, size * .18 + r, size * .18 + r], fill="#ffffff")          # plato
        d.rectangle([size * .60, size * .18, size * .64, size * .58], fill="#ffffff")                # cuchillo
        d.rectangle([size * .72, size * .18, size * .75, size * .58], fill="#ffffff")                # tenedor
        d.rectangle([size * .78, size * .18, size * .81, size * .58], fill="#ffffff")
        d.ellipse([size * .30, size * .60, size * .30 + size * .34, size * .60 + size * .30], fill="#ffffff")
        d.text((size * .40, size * .66), "%", fill="#2563eb")
        im.save(os.path.join(docs, f"icon-{size}.png"), "PNG", optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--no-screens", action="store_true")
    ap.add_argument("--quality", type=int, default=60)
    a = ap.parse_args()
    src_html = os.path.join(ROOT, "output", a.mes, f"descuentos_{a.categoria}_{a.mes}.html")
    if not os.path.exists(src_html):
        sys.exit(f"No existe {src_html} (corre build_app.py)")
    mdir = os.path.join(DOCS, a.mes)
    os.makedirs(mdir, exist_ok=True)
    html = open(src_html, encoding="utf-8").read()
    ext = "png"
    src_scr = os.path.join(ROOT, "output", a.mes, "screens")
    if not a.no_screens and os.path.isdir(src_scr):
        ext = compress_screens(src_scr, os.path.join(mdir, "screens"), a.quality)
        if ext == "jpg":
            # SÓLO las rutas de capturas; no tocar p.ej. la URL de tiles OSM ({z}/{x}/{y}.png)
            html = re.sub(r'(screens/[^"\']+)\.png(["\'])', r'\1.jpg\2', html)
    else:
        html = re.sub(r'"shot": ?"screens/[^"]+"', '"shot": null', html)
    open(os.path.join(mdir, "index.html"), "w", encoding="utf-8").write(html)
    # índice raíz
    meses = sorted([d for d in os.listdir(DOCS) if re.fullmatch(r"\d{4}-\d{2}", d)], reverse=True)
    links = "".join(f'<li><a href="{m}/">{m}</a></li>' for m in meses)
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Descuentos restaurantes</title>
<meta http-equiv="refresh" content="0; url={meses[0]}/"></head>
<body style="font:16px system-ui;padding:20px"><p>Redirigiendo a <a href="{meses[0]}/">{meses[0]}</a>…</p>
<p>Meses:</p><ul>{links}</ul></body></html>""")
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    write_pwa(DOCS, meses[0])
    print(f"OK docs/{a.mes}/index.html + docs/index.html (meses: {', '.join(meses)})", file=sys.stderr)


if __name__ == "__main__":
    main()
