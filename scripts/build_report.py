"""Reporte combinado de todos los bancos para un mes.

Uso:
    python scripts/build_report.py [--mes AAAA-MM] [--categoria restaurantes]

Lee output/<mes>/<banco>_<categoria>.json (falabella_*, santander_*, ...) y
escribe:
    output/<mes>/descuentos_<categoria>_<mes>.md   (por día + por comercio)
    output/<mes>/descuentos_<categoria>_<mes>.csv  (plano, para Excel)

Para agregar un banco nuevo: producir un JSON con el esquema de common.py
(ver docstring) y este script lo toma solo.
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DIAS, horario_desde_texto, lugares_desde_texto  # noqa: E402


def tipo_corto(desc, maxlen=120):
    """Primera frase de la descripción del comercio ('Restaurante especializado en
    pizzas y pastas al estilo italiano. Destaca por…' -> primera oración)."""
    d = re.sub(r"\s+", " ", (desc or "")).strip()
    if not d:
        return ""
    m = re.match(r"(.{0,%d}?[.!?])(\s|$)" % maxlen, d)
    out = (m.group(1) if m else d[:maxlen]).strip(" .")
    return out


def norm_falabella(i):
    cond = i.get("condiciones") or ""
    lug = lugares_desde_texto(cond)
    desc_card = (i.get("descripcion_card") or "").strip()
    m = re.search(r"(?:presencial|exclusivo presencial)\s+(?:en|solo en)\s+(.+)", desc_card, re.I)
    if m and m.group(1).strip() not in lug:
        lug.insert(0, m.group(1).strip())
    hor = horario_desde_texto(cond) or horario_desde_texto(desc_card)
    tarj = i.get("tarjetas") or []
    # Falabella: 40% CMR / 30% Débito es el patrón típico -> capturar la frase
    m2 = re.search(r"(\d{1,2}% ?dcto[^\n]*d[ée]bito[^\n]*)", cond, re.I)
    desc = i.get("descuento") or ""
    if m2:
        desc = desc + " (" + m2.group(1).strip() + ")"
    return {
        "banco": "Banco Falabella",
        "comercio": i.get("comercio"),
        "tipo": tipo_corto(i.get("descripcion_comercio")),
        "descuento": desc,
        "descuento_pct": i.get("descuento_pct"),
        "tope": i.get("tope") or "",
        "dias": i.get("dias") or [],
        "horario": hor,
        "lugares": lug,
        "tarjetas": tarj,
        "modalidad": ", ".join(i.get("modalidad") or []) or desc_card,
        "region": ", ".join(i.get("region") or []),
        "vigencia": f"{i.get('vigencia_inicio','')} → {i.get('vigencia_fin','')}",
        "condiciones": cond,
        "url": i.get("url"),
    }


def norm_generic(i):
    # ya viene en esquema común (santander y futuros)
    return {
        "banco": i.get("banco"),
        "comercio": i.get("comercio"),
        "tipo": tipo_corto(i.get("tipo")),
        "descuento": i.get("bajada") or i.get("descuento") or "",
        "descuento_pct": i.get("descuento_pct"),
        "tope": i.get("tope") or "",
        "dias": i.get("dias") or [],
        "horario": i.get("horario") or "",
        "lugares": i.get("lugares") or [],
        "tarjetas": i.get("tarjetas") or [],
        "modalidad": i.get("modalidad") or "",
        "region": i.get("region") or "",
        "vigencia": i.get("vigencia") or "",
        "condiciones": i.get("condiciones") or "",
        "url": i.get("url"),
    }


def load_all(outdir, categoria):
    items = []
    for path in sorted(glob.glob(os.path.join(outdir, f"*_{categoria}.json"))):
        base = os.path.basename(path)
        if base.startswith("descuentos_"):
            continue
        data = json.load(open(path, encoding="utf-8"))
        if base.startswith("falabella_"):
            items += [norm_falabella(i) for i in data]
        else:
            items += [norm_generic(i) for i in data]
    return items


def short(s, n=90):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def cell(s):
    return (s or "").replace("|", "/").replace("\n", " ").strip() or "—"


def to_markdown(items, categoria, mes):
    md = [f"# Descuentos {categoria} — {mes}", "",
          f"Generado {dt.date.today().isoformat()} · {len(items)} beneficios · "
          + " · ".join(f"{b}: {sum(1 for i in items if i['banco']==b)}" for b in sorted({i['banco'] for i in items})),
          "", "Campos: lugar específico · horario · tope · días · tarjeta. "
          "Cuando un campo dice — es que el banco no lo publica; revisar `Condiciones` o la URL.", ""]
    md += ["## Por día", ""]
    for d in DIAS:
        rows = sorted([i for i in items if d in i["dias"]], key=lambda x: (x["banco"], x["comercio"].lower()))
        md.append(f"### {d} ({len(rows)})")
        md.append("")
        md.append("| Banco | Comercio | Tipo | Dcto | Tope | Horario | Lugar | Tarjetas |")
        md.append("|---|---|---|---|---|---|---|---|")
        for i in rows:
            md.append(f"| {i['banco']} | [{cell(i['comercio'])}]({i['url']}) | {cell(short(i.get('tipo'),50))} | {cell(short(i['descuento'],90))} | {cell(i['tope'])} | "
                      f"{cell(short(i['horario'],80))} | {cell(short('; '.join(i['lugares']),160))} | {cell(short('; '.join(i['tarjetas']),90))} |")
        md.append("")
    sin = [i for i in items if not i["dias"]]
    if sin:
        md.append(f"### Sin día identificado ({len(sin)})")
        md.append("")
        for i in sin:
            md.append(f"- {i['banco']} · [{i['comercio']}]({i['url']}) · {short(i['descuento'],60)}")
        md.append("")
    md += ["## Por comercio (detalle completo)", ""]
    for i in sorted(items, key=lambda x: (x["comercio"].lower(), x["banco"])):
        md.append(f"### {i['comercio']} — {i['banco']}")
        if i.get("tipo"):
            md.append(f"- *{i['tipo']}*")
        md.append(f"- **Descuento:** {i['descuento']} · **Tope:** {i['tope'] or '—'}")
        md.append(f"- **Días:** {', '.join(i['dias']) or '—'} · **Horario:** {i['horario'] or '—'}")
        md.append(f"- **Lugar(es):** {'; '.join(i['lugares']) or '— (ver condiciones)'}")
        md.append(f"- **Tarjetas:** {'; '.join(i['tarjetas']) or '—'}")
        md.append(f"- **Modalidad:** {i['modalidad'] or '—'} · **Región:** {i['region'] or '—'} · **Vigencia:** {i['vigencia'] or '—'}")
        if i["condiciones"]:
            md.append("- **Condiciones (texto del banco):**")
            md.append("  ```")
            md.extend("  " + l for l in i["condiciones"].splitlines() if l.strip())
            md.append("  ```")
        md.append(f"- **URL:** {i['url']}")
        md.append("")
    return "\n".join(md)


def to_csv(items, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["banco", "comercio", "tipo", "descuento", "descuento_pct", "tope", "dias", "horario", "lugares",
                    "tarjetas", "modalidad", "region", "vigencia", "url", "condiciones"])
        for i in items:
            w.writerow([i["banco"], i["comercio"], i.get("tipo", ""), i["descuento"], i["descuento_pct"], i["tope"], ", ".join(i["dias"]),
                        i["horario"], "; ".join(i["lugares"]), "; ".join(i["tarjetas"]), i["modalidad"], i["region"],
                        i["vigencia"], i["url"], i["condiciones"].replace("\n", " / ")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, "output", a.mes)
    items = load_all(outdir, a.categoria)
    if not items:
        sys.exit(f"No hay *_{a.categoria}.json en {outdir}")
    mpath = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.md")
    cpath = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.csv")
    jpath = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.json")
    open(mpath, "w", encoding="utf-8").write(to_markdown(items, a.categoria, a.mes))
    to_csv(items, cpath)
    json.dump(items, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"OK {len(items)} items\n  {mpath}\n  {cpath}\n  {jpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
