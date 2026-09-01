"""Baja el JSON de promociones Santander usando Playwright (pasa Akamai).

Alternativa automatizada a santander_fetch_browser.js (que requiere el navegador
integrado de Claude Code). Requiere Chrome instalado:
    python -m pip install playwright && python -m playwright install chromium

Uso:
    python scripts/santander_fetch_playwright.py [--mes AAAA-MM] [--tag cat-sabores]
                                                 [--channel chrome] [--headed]

Salida: output/<mes>/santander_raw_<tag>.json  (formato {status,n,promos:[...]})
        -> pasar a process_santander.py
"""
import argparse
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = "https://banco.santander.cl/beneficios/descuentos-restaurantes"

JS = r"""
async (tag) => {
  const r = await fetch(`/beneficios/promociones.json?per_page=9999&tags=${tag}&custom_fields=true&order_by=updated_at&desc=true`, {credentials:'include'});
  const j = await r.json();
  const promos = j.promociones || [];
  const strip = h => (h||'').replace(/<li>/g,'\n- ').replace(/<\/p>|<br\s*\/?>/g,'\n')
    .replace(/<[^>]+>/g,'').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/\n{2,}/g,'\n').trim();
  const out = promos.map(p => {
    const cf = {};
    for (const [k,v] of Object.entries(p.custom_fields||{})) cf[k] = v && v.value;
    return {id:p.id, title:p.title, slug:p.slug, url:p.url, bajada:cf['Bajada externa'],
      vigencia:cf['Vigencia'], region_cf:cf['Región cobertura'], comuna_cf:cf['Comuna cobertura'],
      sitio:cf['Sitio web beneficio'], tags:p.tags, description:strip(p.description),
      start_date:p.start_date, end_date:p.end_date, discount:p.discount,
      location_street:p.location_street, lat:p.latitude, lng:p.longitude,
      published_at:p.published_at, updated_at:p.updated_at};
  });
  return {status:r.status, n:promos.length, promos:out};
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--tag", default="cat-sabores")
    ap.add_argument("--channel", default="chrome")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta playwright: python -m pip install playwright && python -m playwright install chromium")
    outdir = os.path.join(ROOT, "output", a.mes)
    os.makedirs(outdir, exist_ok=True)
    with sync_playwright() as p:
        kw = {"headless": not a.headed}
        if a.channel:
            kw["channel"] = a.channel
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(locale="es-CL", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
        page = ctx.new_page()
        page.goto(LANDING, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:  # noqa: BLE001
            pass
        res = page.evaluate(JS, a.tag)
        browser.close()
    if res.get("status") != 200 or not res.get("n"):
        sys.exit(f"Respuesta inesperada: status={res.get('status')} n={res.get('n')} (Akamai? reintentar con --headed)")
    dst = os.path.join(outdir, f"santander_raw_{a.tag}.json")
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"OK {res['n']} promociones -> {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
