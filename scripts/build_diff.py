"""Diff entre dos meses: altas, bajas y cambios de condiciones.

Uso:
    python scripts/build_diff.py --mes AAAA-MM [--prev AAAA-MM] [--categoria restaurantes]

Sin --prev usa el mes anterior con datos en output/.
Escribe output/<mes>/cambios_<cat>_<mes>.json  (lo consume build_app.py: badges NUEVO / cambió)
y   output/<mes>/cambios_<cat>_<mes>.md        (para leer)

Compara por clave estable slug_id(banco,url). Campos vigilados: descuento, tope, días,
horario, lugares, tarjetas.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import slug_id  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMPOS = [("descuento", "Descuento"), ("tope", "Tope"), ("dias", "Días"),
          ("horario", "Horario"), ("lugares", "Lugares"), ("tarjetas", "Tarjetas")]


def load(mes, cat):
    for name in (f"descuentos_{cat}_{mes}.geo.json", f"descuentos_{cat}_{mes}.json"):
        p = os.path.join(ROOT, "output", mes, name)
        if os.path.exists(p):
            items = json.load(open(p, encoding="utf-8"))
            return {slug_id(i["banco"], i.get("url"), i["comercio"]): i for i in items}
    return None


def mes_anterior_con_datos(mes, cat):
    meses = sorted(d for d in os.listdir(os.path.join(ROOT, "output"))
                   if re.fullmatch(r"\d{4}-\d{2}", d) and d < mes
                   and glob.glob(os.path.join(ROOT, "output", d, f"descuentos_{cat}_{d}*.json")))
    return meses[-1] if meses else None


def val(i, k):
    v = i.get(k)
    return "; ".join(v) if isinstance(v, list) else (v or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--prev", default=None)
    ap.add_argument("--categoria", default="restaurantes")
    a = ap.parse_args()
    cur = load(a.mes, a.categoria)
    if cur is None:
        sys.exit(f"No hay datos de {a.mes}")
    prev_mes = a.prev or mes_anterior_con_datos(a.mes, a.categoria)
    if not prev_mes:
        print("(no hay mes previo: todo se marca como base, sin diff)", file=sys.stderr)
        prev, prev_mes = {}, None
    else:
        prev = load(prev_mes, a.categoria) or {}

    # Un banco recién incorporado no son "altas del mes": todos sus beneficios serían nuevos
    # y ahogarían el diff real (pasó al sumar BCI en sept-2026).
    bancos_prev = {i["banco"] for i in prev.values()}
    bancos_nuevos = {i["banco"] for i in cur.values()} - bancos_prev
    altas = [k for k in cur if k not in prev and cur[k]["banco"] not in bancos_nuevos]
    bajas = [k for k in prev if k not in cur]
    cambios = {}
    for k in cur:
        if k not in prev:
            continue
        difs = {}
        for campo, _label in CAMPOS:
            antes, ahora = val(prev[k], campo), val(cur[k], campo)
            if antes != ahora:
                difs[campo] = {"antes": antes, "ahora": ahora}
        if difs:
            cambios[k] = difs

    out = {"mes": a.mes, "prev": prev_mes, "generado": dt.date.today().isoformat(),
           "altas": altas, "bajas": [{"id": k, "comercio": prev[k]["comercio"], "banco": prev[k]["banco"],
                                      "url": prev[k].get("url")} for k in bajas],
           "cambios": cambios}
    outdir = os.path.join(ROOT, "output", a.mes)
    jp = os.path.join(outdir, f"cambios_{a.categoria}_{a.mes}.json")
    json.dump(out, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    md = [f"# Cambios {a.categoria} — {a.mes} vs {prev_mes or '(sin mes previo)'}", "",
          f"Altas: {len(altas)} · Bajas: {len(bajas)} · Con cambios: {len(cambios)}", "",
          "## Altas (no estaban el mes pasado)", ""]
    for k in sorted(altas, key=lambda k: cur[k]["comercio"].lower()):
        i = cur[k]
        md.append(f"- **{i['comercio']}** ({i['banco']}) — {i.get('tipo') or 's/ descripción'} · "
                  f"{i['descuento']} · tope {i['tope'] or '—'} · {', '.join(i['dias']) or '—'} · [ver]({i['url']})")
    md += ["", "## Bajas (ya no aparecen)", ""]
    for b in sorted(out["bajas"], key=lambda x: x["comercio"].lower()):
        md.append(f"- {b['comercio']} ({b['banco']})")
    md += ["", "## Cambios en condiciones", ""]
    for k, difs in sorted(cambios.items(), key=lambda kv: cur[kv[0]]["comercio"].lower()):
        i = cur[k]
        md.append(f"### {i['comercio']} — {i['banco']}")
        for campo, label in CAMPOS:
            if campo in difs:
                md.append(f"- **{label}:** `{difs[campo]['antes'] or '—'}` → `{difs[campo]['ahora'] or '—'}`")
        md.append(f"- [ver]({i['url']})")
        md.append("")
    mp = os.path.join(outdir, f"cambios_{a.categoria}_{a.mes}.md")
    open(mp, "w", encoding="utf-8").write("\n".join(md))
    print(f"OK vs {prev_mes}: altas={len(altas)} bajas={len(bajas)} cambios={len(cambios)}\n  {jp}\n  {mp}", file=sys.stderr)


if __name__ == "__main__":
    main()
