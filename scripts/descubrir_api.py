"""Reconocimiento: abre una landing de beneficios y registra las APIs JSON que consulta.

Uso:
    python scripts/descubrir_api.py <url> [--out carpeta] [--headed] [--channel chrome] [--wait 12]

Sirve para incorporar un banco nuevo: dice si los datos vienen en el HTML (SSR/RSC),
en un XHR JSON, o si hay que renderizar. Guarda cada respuesta JSON en <out>/ para inspección.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default=None)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--channel", default="chrome")
    ap.add_argument("--wait", type=float, default=12)
    ap.add_argument("--scroll", type=int, default=6, help="scrolls para disparar lazy-load")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    out = a.out or os.path.join(ROOT, "output", "_recon", slugify(a.url))
    os.makedirs(out, exist_ok=True)
    hits = []

    with sync_playwright() as p:
        kw = {"headless": not a.headed}
        if a.channel:
            kw["channel"] = a.channel
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(locale="es-CL", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
        page = ctx.new_page()

        def on_response(resp):
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                if "json" not in ct or resp.status >= 400:
                    return
                url = resp.url
                if re.search(r"analytics|telemetry|gtm|beacon|collect|akam|sentry|datadog|_bm/", url, re.I):
                    return
                body = resp.text()
                if len(body) < 400:
                    return
                data = json.loads(body)
                hits.append({"url": url, "bytes": len(body), "top": _shape(data)})
                fn = os.path.join(out, f"{len(hits):02d}-{slugify(url.split('?')[0].split('/')[-1] or 'root')}.json")
                open(fn, "w", encoding="utf-8").write(body)
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)
        page.goto(a.url, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_load_state("networkidle", timeout=int(a.wait * 1000))
        except Exception:  # noqa: BLE001
            pass
        for _ in range(a.scroll):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(700)
        page.wait_for_timeout(1500)
        html = page.content()
        text = page.inner_text("body")[:3000]
        browser.close()

    open(os.path.join(out, "_page.html"), "w", encoding="utf-8").write(html)
    resumen = {
        "url": a.url, "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "html_len": len(html),
        "pistas_html": {k: html.count(k) for k in ["__NEXT_DATA__", "__next_f", "apolloState", "window.__",
                                                    "application/ld+json", "dcto", "descuento", "tope"]},
        "json_endpoints": sorted(hits, key=lambda h: -h["bytes"]),
        "texto_visible": text[:800],
    }
    json.dump(resumen, open(os.path.join(out, "_resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"OK -> {out}", file=sys.stderr)
    print(f"HTML {len(html)} bytes · endpoints JSON: {len(hits)}", file=sys.stderr)
    for h in resumen["json_endpoints"][:12]:
        print(f"  {h['bytes']:>8}  {h['url'][:110]}  {h['top']}", file=sys.stderr)


def _shape(d, depth=0):
    if isinstance(d, dict):
        ks = list(d.keys())[:6]
        return "{" + ", ".join(ks) + ("…" if len(d) > 6 else "") + "}"
    if isinstance(d, list):
        return f"[{len(d)}] " + (_shape(d[0], depth + 1) if d and depth < 2 else "")
    return type(d).__name__


if __name__ == "__main__":
    main()
