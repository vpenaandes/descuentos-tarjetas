"""Scraper de descuentos BCI (tarjetas de crédito Bci).

Uso:
    python scripts/scrape_bci.py [--mes AAAA-MM] [--categoria restaurantes] [--channel chrome] [--headed]

Cómo funciona:
  La landing https://www.bci.cl/beneficios/beneficios-bci/restaurantes es React (nada en el HTML).
  Los datos vienen de https://api.bciplus.cl/bff-loyalty-beneficios/v1/offers?itemsPorPagina=100&pagina=N
  que responde 401 fuera del navegador -> se abre la landing con Playwright y se interceptan las
  respuestas de esa API (3 páginas, ~288 ofertas; ~76 con tag "Restaurantes").

Campos que trae la API y no hay que adivinar:
  beneficio.discount.porcentajeDescuento · scheduling.dayRecurrence (["VIERNES"]) ·
  tags con día, comuna, región, modalidad y categoría · fechaInicio/fechaTermino · legal.
El tope viene sólo en el texto ("con tope de $100.000") -> common.tope_desde_texto.

Salida: output/<mes>/bci_<categoria>.json + .md (esquema común de common.py)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DIAS, dias_desde_texto, horario_desde_texto, lugares_desde_texto,  # noqa: E402
                    pct_desde_texto, tope_desde_texto)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = "https://www.bci.cl/beneficios/beneficios-bci/{cat}"
API_RE = re.compile(r"bff-loyalty-beneficios/v1/offers")
DETALLE = "https://www.bci.cl/beneficios/beneficios-bci/detalle/{slug}"

DIA_TAG = {"LUNES": "Lunes", "MARTES": "Martes", "MIERCOLES": "Miércoles", "MIÉRCOLES": "Miércoles",
           "JUEVES": "Jueves", "VIERNES": "Viernes", "SABADO": "Sábado", "SÁBADO": "Sábado",
           "DOMINGO": "Domingo"}
# tags que NO son comuna (para separar comuna de región/categoría/modalidad)
NO_COMUNA = {"Restaurantes", "Descuentos", "Presencial", "Online", "Delivery", "Gastronomía",
             "Cuotas", "Viajes", "Entretenimiento", "Salud", "Belleza", "Educación", "Retail",
             "Tecnología", "Supermercados", "Bencina", "Hoteles", "Todos"}


def fetch_offers(cat, channel, headed, wait=15):
    from playwright.sync_api import sync_playwright
    payloads = []
    with sync_playwright() as p:
        kw = {"headless": not headed}
        if channel:
            kw["channel"] = channel
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(locale="es-CL", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
        page = ctx.new_page()

        def on_response(resp):
            if not API_RE.search(resp.url) or resp.status >= 400:
                return
            try:
                payloads.append(resp.json())
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)
        page.goto(LANDING.format(cat=cat), wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_load_state("networkidle", timeout=wait * 1000)
        except Exception:  # noqa: BLE001
            pass
        for _ in range(8):                      # scroll: dispara las páginas 2 y 3
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(700)
        page.wait_for_timeout(2000)
        browser.close()
    ofertas, vistos = [], set()
    for pl in payloads:
        for o in pl.get("ofertas") or []:
            if o.get("id") not in vistos:
                vistos.add(o.get("id"))
                ofertas.append(o)
    return ofertas


def tags_de(o):
    return [t.get("nombre", "").strip() for t in (o.get("tags") or []) if t.get("nombre")]


_PROMO_RE = re.compile(
    r"^\s*(hasta\s+)?\d{1,3}\s?%|descuento|dcto|tope|exclusivo|v[áa]lido|pagando|"
    r"acumula|cuotas|canje|puntos|reserva|c[óo]digo|cup[óo]n|paga\b|compra\b|"
    r"todos los|lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo|"
    # texto legal que BCI repite en casi todas las ofertas
    r"se excluyen|corporate|prepago|no acumulable|sujeto a|t[ée]rminos|condiciones|"
    r"stock|promoci[óo]n v[áa]lida|beneficio v[áa]lido|vigencia|aplica|consulta", re.I)


def tipo_de(desc, titulo, nombre):
    """Tipo/descripción del local. En BCI la descripción parte con la mecánica de la
    promo ('40% de descuento con tope de $40.000...'), así que se busca la primera
    línea que describa el local; si no hay, se usa el título promocional cuando no
    es sólo un día ('Viernes - Maitencillo')."""
    for linea in (desc or "").split("\n"):
        l = linea.strip(" .¡!")
        if len(l) < 12 or _PROMO_RE.search(l):
            continue
        if l.lower() == (nombre or "").lower():
            continue
        return l[:120]
    t = (titulo or "").strip()
    if t and not _PROMO_RE.search(t) and t.lower() != (nombre or "").lower():
        return t[:120]
    return ""


def normalize(o):
    tags = tags_de(o)
    desc = re.sub(r"\r\n?", "\n", o.get("descripcion") or "").strip()
    legal = re.sub(r"\r\n?", "\n", o.get("legal") or "").strip()
    sched = o.get("scheduling") or {}
    dias = [DIA_TAG[d.upper()] for d in (sched.get("dayRecurrence") or []) if d.upper() in DIA_TAG]
    dias += [t for t in tags if t in DIAS and t not in dias]
    if not dias:
        dias = dias_desde_texto(o.get("titulo", "") + " " + desc)
    dias = [d for d in DIAS if d in dias]

    pct = ((o.get("beneficio") or {}).get("discount") or {}).get("porcentajeDescuento") \
        or ((o.get("deal") or {}).get("discount") or {}).get("percentage") \
        or pct_desde_texto(desc)
    region = next((t for t in tags if t.startswith("R. ")), "")
    comunas = [t for t in tags if t not in NO_COMUNA and t not in DIAS and not t.startswith("R. ")]
    modalidad = ", ".join(t for t in tags if t in ("Presencial", "Online", "Delivery"))

    # OJO: `titulo` es texto promocional ("Viernes - Maitencillo"); el nombre real
    # del local está en comercio.nombre.
    titulo = re.sub(r"\s+", " ", o.get("titulo") or "").strip()
    nombre = re.sub(r"\s+", " ", ((o.get("comercio") or {}).get("nombre") or "")).strip() or titulo
    lugares = lugares_desde_texto(desc) or []
    # geocodificable: "<local>, <comuna>" (BCI no publica dirección, sólo comuna en tags)
    for c in comunas:
        cand = f"{nombre}, {c}"
        if not any(c.lower() in l.lower() for l in lugares):
            lugares.append(cand)
    if not lugares and region:
        lugares.append(f"{nombre}, {region.replace('R. ', '')}")
    return {
        "banco": "BCI",
        "comercio": nombre,
        "titulo_promo": titulo,
        "tipo": tipo_de(desc, titulo, nombre),
        "bajada": f"{pct}% dcto" + (f" · {sched.get('recurrenceLabel')}" if sched.get("recurrenceLabel") else ""),
        "descuento": f"{pct}%" if pct else "",
        "descuento_pct": pct,
        "tope": tope_desde_texto(desc) or tope_desde_texto(legal),
        "dias": dias,
        "horario": horario_desde_texto(desc) or horario_desde_texto(titulo),
        "detalle_promo": titulo,
        "lugares": lugares,
        "tarjetas": [s for s in [re.sub(r"\s+", " ", o.get("subtitulo") or "").strip()] if s],
        "tarjetas_tags": [],
        "modalidad": modalidad,
        "region": region.replace("R. ", "Región ") if region else "",
        "vigencia": f"{(o.get('fechaInicio') or '')[:10]} → {(o.get('fechaTermino') or '')[:10]}",
        "condiciones": (desc + ("\n\nLegal: " + legal if legal else "")).strip(),
        # "Verificar" debe abrir la página del banco, no el Instagram del local:
        # o.link a veces trae la web/IG del comercio -> va aparte como sitio_comercio.
        "url": DETALLE.format(slug=o.get("slug", "")),
        "sitio_comercio": (o.get("link") or "").strip(),
        "tags": tags,
    }


def to_markdown(items, categoria, mes):
    md = [f"# BCI — descuentos {categoria} ({mes})", "",
          f"Fuente: https://www.bci.cl/beneficios/beneficios-bci/{categoria} (API bciplus offers) · "
          f"{len(items)} beneficios · scrapeado {dt.date.today().isoformat()}", "", "## Resumen por día", ""]
    for d in DIAS:
        names = sorted({i["comercio"] for i in items if d in i["dias"]}, key=str.lower)
        md.append(f"- **{d}** ({len(names)}): " + ", ".join(names))
    md += ["", "## Detalle", ""]
    for i in sorted(items, key=lambda x: x["comercio"].lower()):
        md.append(f"### {i['comercio']}")
        if i["tipo"]:
            md.append(f"- *{i['tipo']}*")
        md.append(f"- **Descuento:** {i['bajada']} · **Tope:** {i['tope'] or '—'}")
        md.append(f"- **Días:** {', '.join(i['dias']) or '—'} · **Horario:** {i['horario'] or '—'}")
        md.append(f"- **Lugares:** {'; '.join(i['lugares']) or '—'} · **Región:** {i['region'] or '—'}")
        md.append(f"- **Tarjetas:** {'; '.join(i['tarjetas']) or '—'}")
        md.append(f"- **Vigencia:** {i['vigencia']}")
        md.append("- **Condiciones:**")
        md.append("  ```")
        md.extend("  " + l for l in i["condiciones"].splitlines() if l.strip())
        md.append("  ```")
        md.append(f"- **URL:** {i['url']}")
        md.append("")
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--tag", default="Restaurantes", help="tag de la API para filtrar la categoría")
    ap.add_argument("--channel", default="chrome")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    ofertas = fetch_offers(a.categoria, a.channel, a.headed)
    if not ofertas:
        sys.exit("No se capturaron ofertas (¿cambió la API o la landing?)")
    print(f"[bci] {len(ofertas)} ofertas totales", file=sys.stderr)
    sel = [o for o in ofertas if a.tag in tags_de(o)]
    items = [normalize(o) for o in sel]
    outdir = os.path.join(ROOT, "output", a.mes)
    os.makedirs(outdir, exist_ok=True)
    json.dump(ofertas, open(os.path.join(outdir, "bci_raw_offers.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    jp = os.path.join(outdir, f"bci_{a.categoria}.json")
    json.dump(items, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(outdir, f"bci_{a.categoria}.md"), "w", encoding="utf-8").write(to_markdown(items, a.categoria, a.mes))
    print(f"OK {len(items)} con tag {a.tag} -> {jp}", file=sys.stderr)


if __name__ == "__main__":
    main()
