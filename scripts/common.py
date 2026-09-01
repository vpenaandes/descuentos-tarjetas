"""Normalización común: días, horarios, topes, lugares.

Esquema normalizado (lo consumen build_report.py y cualquier banco nuevo):
{
  "banco": "Banco Falabella" | "Santander" | ...,
  "comercio": str,
  "descuento": str,          # "40%", "2x1", ...
  "descuento_pct": int|None,
  "tope": str,               # "Sin tope", "$40.000", "" si no se sabe
  "dias": [..],              # nombres en español con mayúscula
  "horario": str,            # texto libre si se detecta ("hasta las 17:00")
  "lugares": [..],           # locales / direcciones / malls específicos
  "tarjetas": [..],          # tarjetas que aplican
  "modalidad": str,          # Presencial / Online / Presencial y online
  "region": str,
  "vigencia": str,
  "condiciones": str,        # texto crudo del banco (fuente de verdad)
  "url": str,
}
"""
import re

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_DIA_RE = {
    "Lunes": r"lunes",
    "Martes": r"martes",
    "Miércoles": r"mi[ée]rcoles",
    "Jueves": r"jueves",
    "Viernes": r"viernes",
    "Sábado": r"s[áa]bados?",
    "Domingo": r"domingos?",
}


def dias_desde_texto(txt):
    """Extrae días de frases como 'todos los miércoles', 'martes y jueves',
    'de lunes a jueves', 'fines de semana'."""
    t = (txt or "").lower()
    found = set()
    # rangos "lunes a jueves"
    for m in re.finditer(r"(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?)\s+a\s+(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?)", t):
        a = _canon(m.group(1)); b = _canon(m.group(2))
        ia, ib = DIAS.index(a), DIAS.index(b)
        if ia <= ib:
            found.update(DIAS[ia:ib + 1])
        else:
            found.update(DIAS[ia:] + DIAS[:ib + 1])
    for d, rx in _DIA_RE.items():
        if re.search(rx, t):
            found.add(d)
    if re.search(r"fin(es)? de semana", t):
        found.update(["Sábado", "Domingo"])
    # "todos los días" sólo si NO viene seguido de días concretos
    # ("todos los días viernes y sábados" = viernes y sábado, no la semana entera)
    if re.search(r"todos los d[ií]as(?!\s+(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo))|toda la semana", t):
        found.update(DIAS)
    return [d for d in DIAS if d in found]


def _canon(w):
    for d, rx in _DIA_RE.items():
        if re.fullmatch(rx, w):
            return d
    return w


def horario_desde_texto(txt):
    """Frases con horas: 'hasta las 17:00', 'de 12:00 a 16:00 hrs', 'almuerzo'."""
    out = []
    for line in (txt or "").splitlines():
        l = line.strip(" -•\t")
        # OJO: no usar \d{1,2}[.]\d{2} porque matchea "$30.000" (tope)
        if re.search(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s?(hrs|hs|horas)\b|hasta las \d|desde las \d|entre las \d|a partir de las \d|horario|hora de", l, re.I) \
                and not re.search(r"\$\s?\d", l):
            out.append(l)
    return " | ".join(dict.fromkeys(out))


def tope_desde_texto(txt):
    t = txt or ""
    if re.search(r"sin tope", t, re.I):
        return "Sin tope"
    m = re.search(r"(?:tope|m[áa]ximo|máx\.?)[^$\n]{0,60}\$\s?([\d.]+)", t, re.I)
    if m:
        return "$" + m.group(1).rstrip(".")
    m = re.search(r"\$\s?([\d.]+)[^\n]{0,40}(?:tope|m[áa]ximo)", t, re.I)
    if m:
        return "$" + m.group(1).rstrip(".")
    return ""


_BOILER = re.compile(
    r"exclusivo|no acumulable|descuento|dcto|tope|m[áa]ximo|propina|dígitos|digitos|"
    r"código|codigo|v[áa]lido (para|en) (consumo|local|compras|pedidos)|recuerda que|"
    r"se excluyen|sigue estos pasos|conoce el detalle|presenta tu|paga con|pagando|"
    r"\d{1,2}\s?%|\$\s?\d|reserva|stock|promoci[óo]n|beneficio|sujeto|cliente|"
    r"aplica|incluye|excluye|válido hasta|valido hasta|vigencia|cupón|cupon|app |"
    r"v[áa]lida|feriado|^no\s",
    re.I,
)
_LUGAR_HINT = re.compile(
    # "Calle 123, Comuna"  /  "Av. X 456, Comuna"
    r"\d{1,5}\s*,\s*[A-ZÁÉÍÓÚÑ]|"
    r"^(av\.?|avda\.?|avenida|calle|pasaje|camino|ruta|mall|local|sucursal|costanera|parque|"
    r"boulevard|patio|paseo|plaza|portal|strip|centro|casa|km\b|\d+\b)|"
    # sin \b final: palabras con tilde (Concepción) rompen el boundary
    r"\b(mall|plaza|local|sucursal|boulevard|patio|paseo|portal|strip center|"
    r"providencia|las condes|vitacura|ñuñoa|santiago|la reina|lo barnechea|huechuraba|"
    r"la florida|maipú|maipu|macul|san miguel|recoleta|concón|concon|viña|vina|valpara|"
    r"reñaca|renaca|concepci|temuco|valdivia|osorno|puerto|antofagasta|iquique|la serena|"
    r"rancagua|talca|chillán|chillan|curicó|curico|los ángeles|puerto varas|punta arenas|"
    r"colina|chicureo|buin|talagante|peñalol|quilicura|independencia|estación central|"
    r"barnechea|pirque|cajón|cajon|borderío|borderio|bellavista|lastarria|italia|"
    r"costanera center|parque arauco|alto las condes|apumanque|egaña|vespucio|"
    r"dominicos|los trapenses|la dehesa|oeste|norte|sur|tobalaba|el golf|isidora|"
  r"nueva costanera|manquehue|kennedy|apoquindo|vitacura|alonso de córdova|"
    r"maitencillo|algarrobo|zapallar|cachagua|pucón|pucon|villarrica|frutillar|castro)",
    re.I,
)


def lugares_desde_texto(txt):
    """Bullets / líneas que parecen un local o dirección concreta.

    Heurística: línea corta, con pista de lugar (nombre de mall, comuna,
    'Av.', número de calle) y que NO sea boilerplate de condiciones.
    """
    out = []
    in_block = False
    for raw in (txt or "").splitlines():
        l = raw.strip()
        if not l:
            continue
        low = l.lower()
        if re.search(r"v[áa]lido en (los )?locales?|locales?:|direcci[óo]n(es)?:|sucursales?:|solo en|sólo en|disponible en", low):
            in_block = True
            rest = l.split(":", 1)[1].strip() if ":" in l else ""
            if rest and len(rest) < 220 and not _BOILER.search(rest):
                out.append(rest.strip(" -•"))
            continue
        bullet = l.startswith(("-", "•", "*"))
        l2 = l.lstrip("-•* ").strip()
        # "Exclusivo Alto Las Condes" / "Exclusivo en Parque Arauco" -> lugar (no es condición de tarjeta)
        m_ex = re.match(r"(?:exclusivo|exclusiva|solo|sólo)\s+(?:en\s+)?(.+)$", l2, re.I)
        if m_ex and re.search(r"\b(mall|plaza|parque arauco|costanera|open kennedy|border[íi]o|isidora|alto las condes|portal|patio|paseo|boulevard|strip|local de|sucursal)\b", m_ex.group(1), re.I) \
                and not re.search(r"tarjeta|cmr|d[ée]bito|cr[ée]dito|presencial|online|app|delivery|web|categor[íi]a", m_ex.group(1), re.I):
            out.append(m_ex.group(1).strip())
            continue
        if not l2 or len(l2) > 140:
            in_block = False if not bullet else in_block
            continue
        if in_block and bullet and not _BOILER.search(l2):
            out.append(l2)
            continue
        if bullet and _LUGAR_HINT.search(l2) and not _BOILER.search(l2):
            out.append(l2)
            continue
        if not bullet:
            in_block = False
    # filtrar ruido: líneas que son sólo días ("Todos los martes") o condiciones
    _solo_dias = re.compile(
        r"(todos los |de |los )?(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?)"
        r"(\s*(a|y|,|al)\s*(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?))*\.?", re.I)
    clean = []
    for o in out:
        o = o.rstrip(".").strip()
        low = o.lower()
        if _solo_dias.fullmatch(o) or low.startswith(("válido", "valido", "exclusivo", "solo ", "sólo ")):
            continue
        clean.append(o)
    # dedupe manteniendo orden
    return list(dict.fromkeys(clean))


def pct_desde_texto(txt):
    m = re.search(r"(\d{1,2})\s?%", txt or "")
    return int(m.group(1)) if m else None


def slug_id(banco, url, comercio=""):
    """ID estable de un beneficio: banco + slug del URL del banco.

    NO usar el índice de la lista: cambia cuando el banco agrega/saca beneficios
    y desparejaría las capturas ya tomadas (pasó en sept-2026).
    """
    import re as _re
    import unicodedata as _ud

    def _n(s):
        s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
        return _re.sub(r"[^a-z0-9]+", "-", s).strip("-")

    slug = _n((url or "").rstrip("/").split("/")[-1]) or _n(comercio)
    return f"{_n(banco)[:4]}-{slug[:48]}"
