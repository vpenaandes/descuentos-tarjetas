"""Scraper de descuentos Banco Falabella (CMR / Débito).

Uso:
    python scripts/scrape_falabella.py [--categoria restaurantes] [--out output/AAAA-MM]

Cómo funciona:
  1. GET https://www.bancofalabella.cl/descuentos/<categoria>  (Next.js SSR)
     -> el payload RSC trae `benefitCardsData` con todas las tarjetas.
  2. Por cada tarjeta GET /descuentos/detalle/<slug>
     -> el payload RSC trae `benefitData` con: condiciones (rich text),
        legalText, locations, creditCards, discountDays, tope, vigencia.
  3. Escribe JSON crudo + Markdown resumido.

No requiere navegador ni login. Sólo `urllib` de la stdlib.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import rsc  # noqa: E402

BASE = "https://www.bancofalabella.cl"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def rich_to_text(node, depth=0):
    """Convierte rich text de Contentful a texto plano con viñetas."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    t = node.get("nodeType", "")
    kids = node.get("content", []) or []
    if t == "text":
        return node.get("value", "")
    if t in ("unordered-list", "ordered-list"):
        return "\n".join(rich_to_text(k, depth + 1) for k in kids)
    if t == "list-item":
        inner = " ".join(rich_to_text(k, depth).strip() for k in kids).strip()
        return ("  " * (depth - 1)) + "- " + inner
    if t.startswith("heading"):
        return "\n" + "".join(rich_to_text(k, depth) for k in kids).strip() + "\n"
    if t == "paragraph":
        return "".join(rich_to_text(k, depth) for k in kids)
    if t == "hyperlink":
        return "".join(rich_to_text(k, depth) for k in kids)
    # document u otros contenedores
    parts = [rich_to_text(k, depth) for k in kids]
    return "\n".join(p for p in parts if p is not None)


def clean(s):
    s = re.sub(r"[ \t]+", " ", s or "")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def parse_list(html):
    lines = rsc.rsc_lines(rsc.rsc_payload(html))
    for _k, obj in rsc.find_json_lines(lines, "benefitCardsData"):
        props = obj[3] if isinstance(obj, list) else obj
        return props["benefitCardsData"]
    raise RuntimeError("No se encontró benefitCardsData en la página de lista")


def parse_detail(html):
    """Busca el objeto {"benefitData": {...}} en cualquier parte del payload.

    No se puede confiar en el split por líneas: el stream RSC a veces pega
    chunks `T` (texto crudo) sin salto de línea antes del id siguiente, o
    repite la misma línea bajo dos ids. raw_decode desde la posición del
    patrón es robusto a ambos casos.
    """
    payload = rsc.rsc_payload(html)
    dec = json.JSONDecoder()
    best = None
    for m in re.finditer(r'\{"benefitData":', payload):
        try:
            obj, _end = dec.raw_decode(payload, m.start())
        except json.JSONDecodeError:
            continue
        bd = obj.get("benefitData")
        if isinstance(bd, dict) and bd.get("benefitTitle"):
            # preferir el que tenga más campos (por si hay copia parcial)
            if best is None or len(bd) > len(best):
                best = bd
    return best


def order_days(days):
    return [d for d in DIAS if d in (days or [])]


def scrape(categoria, workers=6, limit=None):
    list_html = get(f"{BASE}/descuentos/{categoria}")
    cards = parse_list(list_html)
    if limit:
        cards = cards[:limit]
    print(f"[falabella/{categoria}] {len(cards)} tarjetas en lista", file=sys.stderr)

    def one(c):
        bc = c["benefitCard"]
        url = BASE + bc["linkUrl"]
        item = {
            "banco": "Banco Falabella",
            "categoria": categoria,
            "comercio": c.get("benefitTitle") or bc.get("title"),
            "titulo_card": bc.get("title"),
            "descripcion_card": (bc.get("description") or "").strip(),
            "url": url,
            "descuento": bc.get("centerDiscountText"),
            "descuento_pct": c.get("discount"),
            "tope": bc.get("bottomDiscountText"),
            "dias": order_days(bc.get("discountDays")),
            "vigencia_inicio": (bc.get("initDate") or "")[:10],
            "vigencia_fin": (bc.get("endDate") or "")[:10],
            "region": c.get("region"),
            "tarjetas": c.get("creditCards"),
            "elite": bc.get("eliteTag"),
            "destacado": c.get("highlighted"),
        }
        try:
            d = parse_detail(get(url))
        except Exception as e:  # noqa: BLE001
            item["error_detalle"] = str(e)
            d = None
        if d:
            item.update({
                "comercio": d.get("commerceName") or item["comercio"],
                "descripcion_comercio": clean(d.get("commerceInfoDescription")),
                "modalidad": d.get("benefitsMode"),
                "condiciones": clean(rich_to_text(d.get("detailBanner1"))),
                "condiciones2": clean(rich_to_text(d.get("detailBanner2"))) if d.get("detailBanner2") else "",
                "legal": clean(d.get("legalText")),
                "locations": d.get("locations"),
                "tarjetas": d.get("creditCards") or item["tarjetas"],
                "dias": order_days(d.get("discountDays")) or item["dias"],
                "tope": d.get("bottomDiscountText") or item["tope"],
                "sitio_comercio": d.get("urlCta"),
                "es_cupon": d.get("isCoupon"),
                "categorias": d.get("relatedCategory"),
            })
        return item

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        items = list(ex.map(one, cards))
    return items


def fmt_locs(locs):
    if not locs:
        return ""
    out = []
    for l in locs:
        if isinstance(l, dict):
            parts = [str(l.get(k)) for k in ("name", "title", "address", "direccion", "comuna", "region", "schedule", "horario") if l.get(k)]
            out.append(" · ".join(parts) if parts else json.dumps(l, ensure_ascii=False))
        else:
            out.append(str(l))
    return "\n".join(f"  - {x}" for x in out)


def to_markdown(items, categoria, fecha):
    md = [f"# Banco Falabella — descuentos {categoria} ({fecha})", "",
          f"Fuente: {BASE}/descuentos/{categoria}  ·  {len(items)} beneficios  ·  scrapeado {dt.date.today().isoformat()}",
          "",
          "## Resumen por día", ""]
    for d in DIAS:
        names = sorted({i["comercio"] for i in items if d in i["dias"]}, key=str.lower)
        md.append(f"- **{d}** ({len(names)}): " + ", ".join(names))
    md += ["", "## Detalle por comercio", ""]
    for i in sorted(items, key=lambda x: (x["comercio"] or "").lower()):
        md.append(f"### {i['comercio']}")
        md.append(f"- **Descuento:** {i['descuento']} · **Tope:** {i['tope']}")
        md.append(f"- **Días:** {', '.join(i['dias']) or '—'}")
        md.append(f"- **Tarjetas:** {', '.join(i['tarjetas'] or [])}")
        md.append(f"- **Modalidad:** {', '.join(i.get('modalidad') or [])} — {i['descripcion_card']}")
        md.append(f"- **Región:** {', '.join(i['region'] or [])}")
        md.append(f"- **Vigencia:** {i['vigencia_inicio']} → {i['vigencia_fin']}")
        if i.get("locations"):
            md.append("- **Locales:**")
            md.append(fmt_locs(i["locations"]))
        if i.get("condiciones"):
            md.append("- **Condiciones / horario (texto del banco):**")
            md.append("  ```")
            md.extend("  " + l for l in i["condiciones"].splitlines())
            md.append("  ```")
        if i.get("condiciones2"):
            md.append("- **Condiciones (2):**")
            md.append("  ```")
            md.extend("  " + l for l in i["condiciones2"].splitlines())
            md.append("  ```")
        if i.get("legal"):
            md.append(f"- **Legal:** {i['legal']}")
        md.append(f"- **URL:** {i['url']}")
        md.append("")
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--out", default=None, help="carpeta de salida (default output/AAAA-MM)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    fecha = dt.date.today().strftime("%Y-%m")
    out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", fecha)
    os.makedirs(out, exist_ok=True)
    items = scrape(a.categoria, a.workers, a.limit)
    jpath = os.path.join(out, f"falabella_{a.categoria}.json")
    mpath = os.path.join(out, f"falabella_{a.categoria}.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(to_markdown(items, a.categoria, fecha))
    errs = [i for i in items if i.get("error_detalle")]
    print(f"OK {len(items)} items -> {jpath}\n          {mpath}\nerrores detalle: {len(errs)}", file=sys.stderr)


if __name__ == "__main__":
    main()
