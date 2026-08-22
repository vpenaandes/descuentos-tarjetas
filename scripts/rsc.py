"""Utilidades para extraer el payload RSC (React Server Components) embebido
en páginas Next.js renderizadas en servidor (self.__next_f.push([1,"..."])).

Banco Falabella usa Next.js App Router; los datos de beneficios vienen en
este payload, no en llamadas XHR, así que basta con un GET del HTML.
"""
import json
import re

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
_LINE_RE = re.compile(r'^([0-9a-f]+):(.*)$')


def rsc_payload(html: str) -> str:
    """Concatena todos los chunks de texto del payload RSC."""
    out = []
    for m in _PUSH_RE.finditer(html):
        try:
            out.append(json.loads(m.group(1)))  # literal JS string ~ JSON string
        except json.JSONDecodeError:
            pass
    return "".join(out)


def rsc_lines(payload: str) -> dict:
    """Separa el payload en líneas `id:contenido`."""
    d = {}
    for line in payload.split("\n"):
        m = _LINE_RE.match(line)
        if m:
            d[m.group(1)] = m.group(2)
    return d


def find_json_lines(lines: dict, needle: str):
    """Devuelve (id, objeto) de las líneas cuyo contenido contiene `needle`
    y parsea como JSON."""
    for k, v in lines.items():
        if needle in v:
            try:
                yield k, json.loads(v)
            except json.JSONDecodeError:
                continue


def walk(obj, path=()):
    """Recorre recursivamente y emite (path, valor) para hojas y dicts."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (i,))
    else:
        yield path, obj
