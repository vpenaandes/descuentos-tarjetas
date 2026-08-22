"""Normaliza el JSON de promociones Santander (obtenido con
santander_fetch_browser.js) al esquema común y escribe JSON + Markdown.

Uso:
    python scripts/process_santander.py <raw.json> [--out output/AAAA-MM] [--categoria restaurantes]

<raw.json> puede ser:
  - el objeto {status, n, promos:[...]} que devuelve el snippet,
  - la lista `promos` directamente,
  - el archivo tool-results de Claude Code ([{type, text}] con el JSON adentro).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import (DIAS, dias_desde_texto, horario_desde_texto, lugares_desde_texto,  # noqa: E402
                    pct_desde_texto, tope_desde_texto)

TAG_TARJETA = {
    "wm-limited": "WorldMember Limited",
    "exclusivo-limited": "Exclusivo WorldMember Limited",
    "amex": "American Express Santander",
    "exclusivo-amex": "Exclusivo Amex",
    "amexforfoodies": "Amex for Foodies",
    "todas-las-tarjetas": "Todas las tarjetas Santander",
    "tarjetas-credito": "Tarjetas de Crédito",
    "tarjeta-credito": "Tarjetas de Crédito",
    "tarjetas-debito": "Tarjetas de Débito",
    "life-y-debito": "Life y Débito",
    "latam-pass": "LATAM Pass",
    "santander-teens": "Santander Teens",
    "jovenes": "Jóvenes",
    "senior-life": "Senior Life",
}
TAG_DIA = {"lunes": "Lunes", "martes": "Martes", "miercoles": "Miércoles", "jueves": "Jueves",
           "viernes": "Viernes", "sabado": "Sábado", "domingo": "Domingo",
           "miercoles-de-sabores": "Miércoles", "cuarenta-lunes": "Lunes", "cuarenta-martes": "Martes",
           "cuarenta-jueves": "Jueves"}


def load_raw(path):
    txt = open(path, encoding="utf-8").read()
    data = json.loads(txt)
    if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0] and "type" in data[0]:
        t = data[0]["text"]
        data = json.loads(t[t.find("{"): t.rfind("}") + 1])
    if isinstance(data, dict) and "promos" in data:
        return data["promos"]
    if isinstance(data, dict) and "promociones" in data:  # JSON crudo de la API
        return [flatten_api(p) for p in data["promociones"]]
    return data


def flatten_api(p):
    cf = {k: (v or {}).get("value") for k, v in (p.get("custom_fields") or {}).items()}
    desc = re.sub(r"<li>", "\n- ", p.get("description") or "")
    desc = re.sub(r"</p>|<br\s*/?>", "\n", desc)
    desc = re.sub(r"<[^>]+>", "", desc).replace("&nbsp;", " ").replace("&amp;", "&")
    return {"id": p["id"], "title": p["title"], "slug": p["slug"], "url": p["url"],
            "bajada": cf.get("Bajada externa"), "vigencia": cf.get("Vigencia"),
            "region_cf": cf.get("Región cobertura"), "comuna_cf": cf.get("Comuna cobertura"),
            "sitio": cf.get("Sitio web beneficio"), "tags": p.get("tags"), "description": desc.strip(),
            "start_date": p.get("start_date"), "end_date": p.get("end_date"), "discount": p.get("discount"),
            "location_street": p.get("location_street"), "lat": p.get("latitude"), "lng": p.get("longitude")}


def tarjetas_de(p):
    out = []
    for line in (p.get("description") or "").splitlines():
        if re.search(r"tarjeta", line, re.I) and re.search(r"exclusivo|pagando|v[áa]lido", line, re.I):
            out.append(line.strip(" -•"))
    tags = [TAG_TARJETA[t] for t in (p.get("tags") or []) if t in TAG_TARJETA]
    return out, tags


def modalidad_de(desc):
    d = (desc or "").lower()
    pres = bool(re.search(r"en local|presencial|en el local|en sal[óo]n|consumo en", d))
    onl = bool(re.search(r"online|en l[ií]nea|www\.|\.cl\b|delivery|app\b", d))
    if pres and onl:
        return "Presencial y online"
    if onl:
        return "Online / delivery"
    if pres:
        return "Presencial"
    return ""


def normalize(p):
    bajada = p.get("bajada") or ""
    desc = p.get("description") or ""
    # Días: el texto (bajada) es la fuente de verdad; los tags del CMS a veces quedan desactualizados
    # (p.ej. "todos los domingos" con tag `sabado`). Tags sólo si el texto no dice nada.
    dias = dias_desde_texto(bajada) or dias_desde_texto(desc)
    dias_tags = [TAG_DIA[t] for t in (p.get("tags") or []) if t in TAG_DIA]
    if not dias:
        dias = dias_tags
    dias = [d for d in DIAS if d in dias]
    dias_tags = [d for d in DIAS if d in dias_tags]
    tarj_txt, tarj_tags = tarjetas_de(p)
    region = "Región Metropolitana" if "metropolitana" in (p.get("tags") or []) else ("Regiones" if "regiones" in (p.get("tags") or []) else "")
    if p.get("region_cf"):
        region = p["region_cf"]
    lugares = lugares_desde_texto(desc)
    for extra in (p.get("location_street"), p.get("comuna_cf")):
        if extra and extra not in lugares:
            lugares.append(extra)
    pct = pct_desde_texto(bajada) or p.get("discount")
    return {
        "banco": "Santander",
        "comercio": (p.get("title") or "").strip(),
        "descuento": (re.search(r"\d{1,2}\s?%|2x1|\d+ ?mill?as?", bajada, re.I) or [bajada])[0] if bajada else "",
        "descuento_pct": pct,
        "bajada": bajada.strip(),
        "tope": tope_desde_texto(desc),
        "dias": dias,
        "dias_tags": dias_tags,
        "horario": horario_desde_texto(desc),
        "lugares": lugares,
        "tarjetas": tarj_txt or tarj_tags,
        "tarjetas_tags": tarj_tags,
        "modalidad": modalidad_de(desc),
        "region": region,
        "vigencia": (p.get("vigencia") or "").strip(),
        "condiciones": desc.strip(),
        "url": p.get("url"),
        "tags": p.get("tags"),
        "sitio_comercio": p.get("sitio"),
    }


def to_markdown(items, categoria, fecha):
    md = [f"# Santander — descuentos {categoria} ({fecha})", "",
          f"Fuente: https://banco.santander.cl/beneficios/descuentos-restaurantes (API promociones.json, tag cat-sabores) · {len(items)} beneficios · scrapeado {dt.date.today().isoformat()}",
          "", "## Resumen por día", ""]
    for d in DIAS:
        names = sorted({i["comercio"] for i in items if d in i["dias"]}, key=str.lower)
        md.append(f"- **{d}** ({len(names)}): " + ", ".join(names))
    sin_dia = sorted(i["comercio"] for i in items if not i["dias"])
    if sin_dia:
        md.append(f"- **Sin día detectado** ({len(sin_dia)}): " + ", ".join(sin_dia))
    md += ["", "## Detalle por comercio", ""]
    for i in sorted(items, key=lambda x: x["comercio"].lower()):
        md.append(f"### {i['comercio']}")
        md.append(f"- **Descuento:** {i['bajada']} · **Tope:** {i['tope'] or '—'}")
        md.append(f"- **Días:** {', '.join(i['dias']) or '—'}")
        md.append(f"- **Horario:** {i['horario'] or '—'}")
        md.append(f"- **Tarjetas:** {'; '.join(i['tarjetas']) or '—'}  (tags: {', '.join(i['tarjetas_tags']) or '—'})")
        md.append(f"- **Lugares:** {'; '.join(i['lugares']) or '—'}")
        md.append(f"- **Modalidad:** {i['modalidad'] or '—'} · **Región:** {i['region'] or '—'}")
        md.append(f"- **Vigencia:** {i['vigencia'] or '—'}")
        md.append("- **Condiciones (texto del banco):**")
        md.append("  ```")
        md.extend("  " + l for l in i["condiciones"].splitlines())
        md.append("  ```")
        md.append(f"- **URL:** {i['url']}")
        md.append("")
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    fecha = dt.date.today().strftime("%Y-%m")
    out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", fecha)
    os.makedirs(out, exist_ok=True)
    promos = load_raw(a.raw)
    items = [normalize(p) for p in promos]
    jpath = os.path.join(out, f"santander_{a.categoria}.json")
    mpath = os.path.join(out, f"santander_{a.categoria}.md")
    json.dump(items, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(mpath, "w", encoding="utf-8").write(to_markdown(items, a.categoria, fecha))
    print(f"OK {len(items)} items -> {jpath}\n          {mpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
