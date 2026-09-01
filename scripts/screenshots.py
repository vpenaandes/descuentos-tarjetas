"""Captura screenshot de la página del banco de cada descuento (evidencia para verificar).

Uso:
    python scripts/screenshots.py [--mes AAAA-MM] [--categoria restaurantes] [--only falabella|santander]
                                  [--headed] [--limit N] [--force]

Requiere (una sola vez):
    python -m pip install playwright
    python -m playwright install chromium

Lee  output/<mes>/descuentos_<cat>_<mes>.geo.json (o .json si no hay geo)
Deja output/<mes>/screens/<id>.png  (id = campo "id" que asigna geocode.py; si no existe se deriva)
La app HTML (build_app.py) muestra el screenshot al hacer clic en "Ver captura".

Notas:
- Falabella: Next.js, hidrata rápido; se espera `networkidle` + 1.5 s.
- Santander: Akamai Bot Manager. Headless a veces devuelve la página "Internet Connection Error";
  si pasa, correr con --headed (abre ventana visible) o reintentar más tarde. El script detecta
  esa página y la marca como error para reintentar.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import slug_id  # noqa: E402


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--only", default=None)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="recapturar aunque exista")
    ap.add_argument("--channel", default=None, help="chrome | msedge (usa el navegador instalado; menos detectable que Chromium)")
    ap.add_argument("--idle-timeout", type=int, default=20000,
                    help="ms a esperar networkidle (Santander nunca queda idle por analytics: usar ~4000)")
    a = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Falta playwright: python -m pip install playwright && python -m playwright install chromium")

    outdir = os.path.join(ROOT, "output", a.mes)
    src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.geo.json")
    if not os.path.exists(src):
        src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.json")
    items = json.load(open(src, encoding="utf-8"))
    for idx, it in enumerate(items):
        it["id"] = slug_id(it["banco"], it.get("url"), it["comercio"])  # recalcular: los .geo.json viejos traen ids por índice
    if a.only:
        items = [i for i in items if a.only.lower() in i["banco"].lower()]
    if a.limit:
        items = items[: a.limit]
    sdir = os.path.join(outdir, "screens")
    os.makedirs(sdir, exist_ok=True)
    log_path = os.path.join(sdir, "_log.json")
    log = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else {}

    ok = err = skip = 0
    with sync_playwright() as p:
        launch_kw = {"headless": not a.headed}
        if a.channel:
            launch_kw["channel"] = a.channel
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 1600},
            locale="es-CL",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        for it in items:
            dst = os.path.join(sdir, it["id"] + ".png")
            if os.path.exists(dst) and not a.force and log.get(it["id"], {}).get("ok"):
                skip += 1
                continue
            url = it["url"]
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=a.idle_timeout)
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1.5)
                # Falabella: cerrar posibles modales/cookies
                for sel in ["button:has-text('Aceptar')", "button:has-text('Entendido')", "[aria-label='Cerrar']"]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=500):
                            el.click(timeout=1000)
                    except Exception:  # noqa: BLE001
                        pass
                title = page.title()
                body = page.inner_text("body")[:4000]
                blocked = ("Internet Connection Error" in title) or ("Access Denied" in title) or len(body.strip()) < 200
                page.screenshot(path=dst, full_page=True)
                log[it["id"]] = {"ok": not blocked, "url": url, "title": title, "ts": dt.datetime.now().isoformat(timespec="seconds"),
                                 "nota": "bloqueado/vacío" if blocked else ""}
                if blocked:
                    err += 1
                    print(f"  ? {it['banco']} {it['comercio']} -> página bloqueada/vacía ({title})", file=sys.stderr)
                else:
                    ok += 1
            except Exception as e:  # noqa: BLE001
                err += 1
                log[it["id"]] = {"ok": False, "url": url, "error": str(e)[:200], "ts": dt.datetime.now().isoformat(timespec="seconds")}
                print(f"  ! {it['banco']} {it['comercio']} -> {e}", file=sys.stderr)
            # merge con lo que haya en disco (permite correr falabella y santander en paralelo)
            try:
                disk = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else {}
            except Exception:  # noqa: BLE001
                disk = {}
            disk[it["id"]] = log[it["id"]]
            log = disk
            json.dump(log, open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        browser.close()
    print(f"OK capturas={ok} errores={err} omitidas={skip} -> {sdir}", file=sys.stderr)


if __name__ == "__main__":
    main()
