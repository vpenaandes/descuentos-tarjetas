"""Geocodifica los `lugares` del reporte combinado y deduce comunas.

Uso:
    python scripts/geocode.py [--mes AAAA-MM] [--categoria restaurantes] [--no-net]

Entrada : output/<mes>/descuentos_<cat>_<mes>.json   (de build_report.py)
Salida  : output/<mes>/descuentos_<cat>_<mes>.geo.json
          data/geocache.json  (caché persistente Nominatim, se reutiliza cada mes)

Estrategia por cada texto de lugar:
  1. Limpieza: quitar sufijo ": días", prefijo "Nombre: dirección", dividir multi-direcciones.
  2. Si es lista de comunas ("Vitacura, Las Condes") -> sólo comunas, sin punto.
  3. Si coincide con un mall conocido (MALLS) -> coordenadas/comuna del diccionario (precisión "mall").
  4. Si parece dirección (número + comuna/ciudad) -> Nominatim (OSM). precisión "exacta" si OSM
     devolvió house_number, si no "calle".
  5. Si es sólo ciudad/comuna -> centroide, precisión "ciudad" (aprox, se dibuja distinto).
  6. Si es sólo nombre de comercio -> Nominatim por nombre; se acepta sólo si el resultado contiene
     el nombre (precisión "nombre"), para no confundir con otro local.

Nominatim: máx 1 req/s, User-Agent obligatorio. ~200 consultas la primera vez; después casi todo
sale del caché.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import slug_id  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(ROOT, "data", "geocache.json")
UA = "DescuentosTarjetas/1.0 (uso personal; contacto: software@andeselectronics.cl)"

# ---------------------------------------------------------------- malls / lugares fijos
# clave normalizada (sin tildes, minúsculas, sin espacios) -> (nombre canónico, dirección para OSM, comuna, lat, lng)
# lat/lng: aproximación conocida; si Nominatim encuentra la dirección se prefiere OSM.
MALLS = {
    "costaneracenter": ("Costanera Center", "Avenida Andrés Bello 2425, Providencia", "Providencia", -33.4176, -70.6066),
    "parquearauco": ("Parque Arauco", "Avenida Presidente Kennedy 5413, Las Condes", "Las Condes", -33.4022, -70.5781),
    "boulevardparquearauco": ("Parque Arauco", "Avenida Presidente Kennedy 5413, Las Condes", "Las Condes", -33.4022, -70.5781),
    "altolascondes": ("Alto Las Condes", "Avenida Presidente Kennedy 9001, Las Condes", "Las Condes", -33.3905, -70.5476),
    "mallaltolascondes": ("Alto Las Condes", "Avenida Presidente Kennedy 9001, Las Condes", "Las Condes", -33.3905, -70.5476),
    "mallplazaegana": ("Mallplaza Egaña", "Avenida Larraín 5862, La Reina", "La Reina", -33.4534, -70.5703),
    "mallplazavespucio": ("Mallplaza Vespucio", "Avenida Vicuña Mackenna 7110, La Florida", "La Florida", -33.5187, -70.5984),
    "mallplazanorte": ("Mallplaza Norte", "Avenida Américo Vespucio 1737, Huechuraba", "Huechuraba", -33.3685, -70.6786),
    "mallplazatobalaba": ("Mallplaza Tobalaba", "Avenida Camilo Henríquez 3296, Puente Alto", "Puente Alto", -33.5788, -70.5530),
    "mallplazaoeste": ("Mallplaza Oeste", "Avenida Américo Vespucio 1501, Cerrillos", "Cerrillos", -33.5164, -70.7150),
    "mallplazalosdominicos": ("Mallplaza Los Dominicos", "Avenida Padre Hurtado Sur 875, Las Condes", "Las Condes", -33.4055, -70.5250),
    "mallplazasur": ("Mallplaza Sur", "Avenida Jorge Alessandri 20040, San Bernardo", "San Bernardo", -33.6240, -70.7100),
    "mallplazaalameda": ("Mallplaza Alameda", "Avenida Libertador Bernardo O'Higgins 3470, Estación Central", "Estación Central", -33.4530, -70.6790),
    "mallplazaantofagasta": ("Mallplaza Antofagasta", "Avenida Balmaceda 2355, Antofagasta", "Antofagasta", -23.6470, -70.4015),
    "mallfloridacenter": ("Mall Florida Center", "Avenida Vicuña Mackenna 6100, La Florida", "La Florida", -33.5227, -70.6081),
    "floridacenter": ("Mall Florida Center", "Avenida Vicuña Mackenna 6100, La Florida", "La Florida", -33.5227, -70.6081),
    "openkennedy": ("Open Kennedy", "Avenida Presidente Kennedy 5600, Vitacura", "Vitacura", -33.3990, -70.5780),
    "vivopanoramico": ("Mall Vivo Panorámico", "Avenida Nueva Providencia 2155, Providencia", "Providencia", -33.4233, -70.6096),
    "mallvivopanoramico": ("Mall Vivo Panorámico", "Avenida Nueva Providencia 2155, Providencia", "Providencia", -33.4233, -70.6096),
    "vivopanomarico": ("Mall Vivo Panorámico", "Avenida Nueva Providencia 2155, Providencia", "Providencia", -33.4233, -70.6096),
    "vivoimperio": ("Mall Vivo Imperio", "Agustinas 1025, Santiago", "Santiago", -33.4410, -70.6530),
    "mallvivoimperio": ("Mall Vivo Imperio", "Agustinas 1025, Santiago", "Santiago", -33.4410, -70.6530),
    "mercadobulnes": ("Mercado Bulnes", "Presidente Bulnes 80, Santiago", "Santiago", -33.4477, -70.6575),
    "patiobellavista": ("Patio Bellavista", "Constitución 30, Providencia", "Providencia", -33.4333, -70.6340),
    "borderio": ("BordeRío", "Monseñor Escrivá de Balaguer 6400, Vitacura", "Vitacura", -33.3888, -70.5530),
    "balaguer6400": ("BordeRío", "Monseñor Escrivá de Balaguer 6400, Vitacura", "Vitacura", -33.3888, -70.5530),
    "isidora3000": ("Isidora 3000", "Isidora Goyenechea 3000, Las Condes", "Las Condes", -33.4145, -70.5975),
    "mallaraucomaipu": ("Mall Arauco Maipú", "Avenida Américo Vespucio 399, Maipú", "Maipú", -33.4849, -70.7523),
    "mallmarinavina": ("Mall Marina", "Avenida Libertad 1348, Viña del Mar", "Viña del Mar", -33.0230, -71.5510),
    "mallmarina": ("Mall Marina", "Avenida Libertad 1348, Viña del Mar", "Viña del Mar", -33.0230, -71.5510),
    "portalladehesa": ("Portal La Dehesa", "Avenida La Dehesa 1445, Lo Barnechea", "Lo Barnechea", -33.3600, -70.5170),
    "casacostanera": ("Casa Costanera", "Avenida Nueva Costanera 3900, Vitacura", "Vitacura", -33.3990, -70.6000),
    "apumanque": ("Apumanque", "Avenida Manquehue Sur 31, Las Condes", "Las Condes", -33.4120, -70.5650),
    "mallsport": ("Mall Sport", "Avenida Las Condes 13451, Las Condes", "Las Condes", -33.3850, -70.5060),
    "mallplazalosangeles": ("Mallplaza Los Ángeles", "Avenida Alemania 670, Los Ángeles", "Los Ángeles", -37.4700, -72.3500),
    "mallplazatrebol": ("Mallplaza Trébol", "Autopista Concepción-Talcahuano 8671, Talcahuano", "Talcahuano", -36.7930, -73.0680),
}

# ---------------------------------------------------------------- comunas conocidas
COMUNAS = [
    # RM
    "Santiago", "Providencia", "Las Condes", "Vitacura", "Lo Barnechea", "La Reina", "Ñuñoa", "Macul",
    "Peñalolén", "La Florida", "Puente Alto", "San Miguel", "San Joaquín", "La Cisterna", "El Bosque",
    "La Granja", "La Pintana", "San Ramón", "Lo Espejo", "Pedro Aguirre Cerda", "Cerrillos", "Maipú",
    "Estación Central", "Quinta Normal", "Lo Prado", "Cerro Navia", "Pudahuel", "Renca", "Quilicura",
    "Huechuraba", "Conchalí", "Independencia", "Recoleta", "Colina", "Lampa", "Buin", "San Bernardo",
    "Talagante", "Pirque", "Padre Hurtado", "Peñaflor", "Melipilla", "Curacaví", "Calera de Tango", "Paine",
    # regiones
    "Viña del Mar", "Valparaíso", "Concón", "Quilpué", "Villa Alemana", "Zapallar", "Puchuncaví", "Algarrobo",
    "El Quisco", "Cartagena", "Quintero", "Limache", "Olmué", "Llay Llay", "Hijuelas", "Quillota", "La Calera",
    "Concepción", "Talcahuano", "Hualpén", "San Pedro de la Paz", "Chiguayante", "Los Ángeles", "Chillán",
    "Temuco", "Villarrica", "Pucón", "Valdivia", "Osorno", "Puerto Varas", "Puerto Montt", "Frutillar",
    "Castro", "Punta Arenas", "Talca", "Curicó", "Rancagua", "San Fernando", "Mostazal", "Antofagasta",
    "Iquique", "La Serena", "Coquimbo", "Copiapó", "Calama", "Arica", "Coyhaique",
]
ALIAS_COMUNA = {
    "santiago centro": "Santiago", "stgo": "Santiago", "reñaca": "Viña del Mar", "renaca": "Viña del Mar",
    "chicureo": "Colina", "cachagua": "Zapallar", "maitencillo": "Puchuncaví", "la dehesa": "Lo Barnechea",
    "los trapenses": "Lo Barnechea", "el golf": "Las Condes", "san francisco de mostazal": "Mostazal",
    "lomas de san andrés": "Concepción", "lomas de san andres": "Concepción", "chillan": "Chillán",
    "vina del mar": "Viña del Mar", "vina": "Viña del Mar", "nunoa": "Ñuñoa", "maipu": "Maipú",
    "penalolen": "Peñalolén", "concon": "Concón", "curico": "Curicó", "valparaiso": "Valparaíso",
    "estacion central": "Estación Central", "penaflor": "Peñaflor", "bio bío": "Concepción",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_words(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


_COMUNA_NORM = {norm_words(c): c for c in COMUNAS}
_COMUNA_NORM.update({norm_words(k): v for k, v in ALIAS_COMUNA.items()})


def comunas_en(texto):
    """Comunas mencionadas en un texto (orden de aparición, sin repetir)."""
    t = " " + norm_words(texto) + " "
    found = []
    for k, v in sorted(_COMUNA_NORM.items(), key=lambda kv: -len(kv[0])):
        if f" {k} " in t and v not in found:
            found.append(v)
            t = t.replace(f" {k} ", "  ")
    return found


def es_lista_comunas(texto):
    """'Vitacura, Las Condes, Ñuñoa' -> True (todos los tokens son comunas)."""
    toks = [x.strip() for x in re.split(r",| y ", texto) if x.strip()]
    if not toks:
        return False
    return all(norm_words(t.rstrip(".")) in _COMUNA_NORM for t in toks)


# ---------------------------------------------------------------- limpieza de texto de lugar
DIAS_RX = r"(todos los d[ií]as|todos los dias|lunes|martes|mi[ée]rcoles|miercoles|jueves|viernes|s[áa]bados?|domingos?|fin(es)? de semana)"


def limpiar(lugar):
    """Devuelve lista de strings 'consultables' a partir de un texto de lugar."""
    s = lugar.strip()
    # "Open Kennedy desde las 19:00hrs: miércoles a domingo" -> "Open Kennedy"  (antes de quitar paréntesis)
    s = re.sub(r"\s+desde( las)?\s+\d{1,2}(:\d{2})?\s*(hrs|hs)?\.?", "", s, flags=re.I)
    s = re.sub(r"\s*\([^)]*\)", "", s)                                   # "(solo delivery)", "(2do piso...)"
    s = re.sub(r"^(todos los )?" + DIAS_RX + r"\s+en\s+", "", s, flags=re.I)  # "Todos los Miércoles en X"
    s = re.sub(r"([A-Za-zÁÉÍÓÚÑáéíóúñ.]),\s*(\d{1,6})\b", r"\1 \2", s)     # "Av. Santa María, 5870" -> "... 5870"
    s = re.sub(r",?\s*\b(local(es)?|piso|oficina|of\.|torre|galer[íi]a|esquina|esq\.)\b[^,:]*", "", s, flags=re.I)
    s = re.sub(r"\s*,\s*,", ",", s).strip(" ,")
    if ":" in s:
        left, right = [x.strip() for x in s.split(":", 1)]
        if re.search(r"\d", right) and not re.fullmatch(r"[^\d]*" + DIAS_RX + r".*", right, re.I):
            s = right                       # "Kechua BordeRío: Costanera Sur ... 6400, Vitacura"
            lc = comunas_en(left)           # "Estación Central: Libertador B. O'Higgins 3750" -> conservar comuna
            if lc and not comunas_en(right):
                s = right + ", " + lc[0]
        elif re.search(DIAS_RX, right, re.I) or not right:
            s = left                        # "Mallplaza Egaña: lunes a jueves"
        else:
            s = right or left
    # multi-direcciones
    parts = [s]
    if " / " in s:
        parts = [p.strip() for p in s.split(" / ")]
    elif re.search(r"\d.*\s+y\s+.*\d", s):
        parts = [p.strip() for p in re.split(r"\s+y\s+(?=[A-ZÁÉÍÓÚ0-9])", s) if p.strip()]
    elif len(re.findall(r"\b(Av\.?|Avenida|Calle|Camino)\s", s)) > 1:
        parts = [p.strip() for p in re.split(r",\s*(?=(?:Av\.?|Avenida|Calle|Camino)\s)", s) if p.strip()]
    out = []
    for p in parts:
        p = p.strip(" .,-–")
        if p:
            out.append(p)
    return out


def match_mall(texto):
    n = norm(texto)
    # quitar prefijos tipo "La Patrona Mall Plaza Vespucio" -> buscar claves contenidas
    for k, v in sorted(MALLS.items(), key=lambda kv: -len(kv[0])):
        if k in n:
            return v
    return None


def es_direccion(texto):
    if es_lista_comunas(texto):
        return False
    return bool(re.search(r"\d", texto)) or bool(re.match(r"(av\.?|avda\.?|avenida|calle|camino|pasaje|ruta)\s", texto, re.I))


# ---------------------------------------------------------------- Nominatim
class Geocoder:
    def __init__(self, net=True):
        self.net = net
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        self.cache = json.load(open(CACHE_PATH, encoding="utf-8")) if os.path.exists(CACHE_PATH) else {}
        self.last = 0.0
        self.calls = 0

    def save(self):
        json.dump(self.cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def query(self, q):
        return self._get(q.strip().lower(), {"q": q})

    def query_comuna(self, comuna, region=""):
        """Centroide de una comuna. Se consulta con la región cuando se conoce:
        'Las Condes, Chile' a veces vuelve vacío, 'Las Condes, Región Metropolitana, Chile' no."""
        q = f"{comuna}, {region}, Chile" if region else f"{comuna}, Región Metropolitana, Chile"
        res = self.query(q)
        return res or self.query(f"{comuna}, Chile")

    def query_structured(self, street, city):
        """Consulta estructurada (street=, city=); a veces Nominatim interpola el número."""
        return self._get(f"S|{street.strip().lower()}|{city.strip().lower()}", {"street": street, "city": city, "country": "Chile"})

    def _get(self, key, params):
        if key in self.cache and self.cache[key]:
            return self.cache[key]
        if not self.net:
            return self.cache.get(key)
        params = dict(params, format="jsonv2", addressdetails=1, limit=3, countrycodes="cl")
        params["accept-language"] = "es"
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
        q = params.get("q") or f"{params.get('street')}, {params.get('city')}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        res = []
        # Nominatim: 1 req/s. Si se excede devuelve 429; hay que esperar y reintentar,
        # y NUNCA cachear la respuesta vacía (si no, el mes siguiente queda sin puntos).
        for intento in range(4):
            wait = 1.1 - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    res = json.loads(r.read().decode("utf-8"))
                self.last = time.time()
                break
            except urllib.error.HTTPError as e:
                self.last = time.time()
                if e.code == 429:
                    espera = 5 * (intento + 1)
                    print(f"  · 429 de Nominatim, esperando {espera}s", file=sys.stderr)
                    time.sleep(espera)
                    continue
                print(f"  ! nominatim {e} :: {q}", file=sys.stderr)
                break
            except Exception as e:  # noqa: BLE001
                self.last = time.time()
                print(f"  ! nominatim error {e} :: {q}", file=sys.stderr)
                time.sleep(2)
        self.calls += 1
        if res:                      # sólo se cachean respuestas útiles
            self.cache[key] = res
            if self.calls % 20 == 0:
                self.save()
        return res



def comuna_de_osm(addr):
    for k in ("city_district", "suburb", "municipality", "town", "city", "village", "county"):
        v = addr.get(k)
        if v:
            c = _COMUNA_NORM.get(norm_words(v))
            if c:
                return c
    return None


def geocodificar_lugar(geo, lugar, region_hint, comercio):
    """Devuelve lista de ubicaciones {lugar, consulta, lat, lng, comuna, precision, osm}"""
    out = []
    for q in limpiar(lugar):
        base = {"lugar": lugar, "consulta": q}
        comunas = comunas_en(q)
        # 1) lista de comunas -> sin punto
        if es_lista_comunas(q):
            for c in comunas:
                out.append({**base, "comuna": c, "precision": "comuna", "lat": None, "lng": None})
            continue
        # 2) mall conocido (en el texto consultable, o en el prefijo "Nombre Mall: dirección")
        m = match_mall(q) or (match_mall(lugar.split(":", 1)[0]) if ":" in lugar else None)
        if m:
            nombre, direccion, comuna, lat, lng = m
            res = geo.query(direccion + ", Chile")
            if res and res[0].get("address", {}).get("house_number"):
                lat, lng = float(res[0]["lat"]), float(res[0]["lon"])
            out.append({**base, "nombre": nombre, "comuna": comuna, "precision": "mall", "lat": lat, "lng": lng})
            continue
        # 3) dirección
        if es_direccion(q):
            ciudad = comunas[0] if comunas else (region_hint or "")
            tries = []
            base_q = q if comunas else (f"{q}, {region_hint}" if region_hint else q)
            tries.append(base_q + ", Chile")
            alt = re.sub(r"\b0+(\d)", r"\1", q)                                  # "Av. Imperial 0561" -> "561"
            if alt != q:
                tries.append((alt if comunas else f"{alt}, {region_hint}") + ", Chile")
            alt2 = re.sub(r"^(av\.?|avda\.?|avenida)\s+", "", alt, flags=re.I)    # sin prefijo Av.
            if alt2 != alt:
                tries.append(alt2 + ", Chile")
            m2 = re.search(r"([A-Za-zÁÉÍÓÚÑáéíóúñ'.\s]+?\s\d{1,6})\b", alt)        # sólo "calle número, comuna"
            if m2 and ciudad:
                tries.append(f"{m2.group(1).strip()}, {ciudad}, Chile")
            best = None
            for t in dict.fromkeys(tries):
                res = geo.query(t)
                if res and res[0].get("address", {}).get("house_number"):
                    best = res[0]
                    break
                if res and best is None and res[0].get("address", {}).get("road"):
                    best = res[0]
            # último intento: consulta estructurada (a veces interpola el número)
            if (best is None or not best.get("address", {}).get("house_number")) and m2 and ciudad:
                res = geo.query_structured(m2.group(1).strip(), ciudad)
                if res and res[0].get("address", {}).get("house_number"):
                    best = res[0]
            if best:
                addr = best.get("address", {})
                prec = "exacta" if addr.get("house_number") else ("calle" if addr.get("road") else "zona")
                out.append({**base, "comuna": comuna_de_osm(addr) or (comunas[0] if comunas else None),
                            "precision": prec, "lat": float(best["lat"]), "lng": float(best["lon"]),
                            "osm": best.get("display_name")})
            else:
                out.append({**base, "comuna": comunas[0] if comunas else None, "precision": "sin_geo", "lat": None, "lng": None})
            continue
        # 4) sólo ciudad/comuna
        if comunas and norm_words(q) in _COMUNA_NORM:
            c = comunas[0]
            res = geo.query_comuna(c, region_hint)
            if res:
                out.append({**base, "comuna": c, "precision": "ciudad", "lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])})
            else:
                out.append({**base, "comuna": c, "precision": "comuna", "lat": None, "lng": None})
            continue
        # 5) nombre de comercio / lugar genérico -> buscar por nombre. Se acepta SÓLO si el resultado
        #    es un local gastronómico/comercio en OSM y su nombre contiene la frase completa buscada
        #    (evita "Social" -> Ministerio de Desarrollo Social, "De Barrio" -> Centro de Conciliación).
        AMENITY_OK = {"restaurant", "cafe", "bar", "fast_food", "pub", "ice_cream", "food_court", "biergarten",
                      "nightclub", "bbq", "marketplace"}
        hint = region_hint or "Chile"
        nq = norm_words(q)
        q_sin = q
        for c in comunas:                       # "Taurus Steak Bar Chillan" -> "Taurus Steak Bar"
            for alias in [c] + [k for k, v in ALIAS_COMUNA.items() if v == c]:
                q_sin = re.sub(r"\b" + re.escape(alias) + r"\b", "", q_sin, flags=re.I)
        q_sin = re.sub(r"\s{2,}", " ", q_sin).strip(" ,-")
        q_sin = re.sub(r"\b(5ta|quinta)\s+regi[óo]n\b", "", q_sin, flags=re.I).strip(" ,-")
        tries = [f"{q}, {hint}", f"{q}, Chile"]
        if comunas and q_sin and norm_words(q_sin) != nq:
            tries.insert(0, f"{q_sin}, {comunas[0]}, Chile")
        cands = []
        for qq in dict.fromkeys(tries):
            cands += geo.query(qq) or []
        ok = None
        frase = norm_words(q_sin) if q_sin else nq
        for r in cands:
            dn = norm_words(r.get("display_name", ""))
            nname = norm_words(r.get("name", ""))
            cls, typ = (r.get("category") or r.get("class")), r.get("type")   # jsonv2 usa "category"
            es_local = (cls == "amenity" and typ in AMENITY_OK) or cls == "shop" or \
                       (cls == "tourism" and typ in ("hotel", "attraction")) or (cls == "craft")
            if es_local and frase and len(frase) >= 4 and (frase in nname or frase in dn):
                ok = r
                break
        if ok:
            addr = ok.get("address", {})
            out.append({**base, "comuna": comuna_de_osm(addr) or (comunas[0] if comunas else None),
                        "precision": "nombre", "lat": float(ok["lat"]), "lng": float(ok["lon"]), "osm": ok.get("display_name")})
        elif comunas:
            # No se pudo ubicar el local (p.ej. BCI publica sólo la comuna): centro de la comuna,
            # marcado como aproximado para que se dibuje punteado y sólo con el toggle.
            res = geo.query_comuna(comunas[0], region_hint)
            if res:
                out.append({**base, "comuna": comunas[0], "precision": "ciudad",
                            "lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])})
            else:
                out.append({**base, "comuna": comunas[0], "precision": "comuna", "lat": None, "lng": None})
        else:
            out.append({**base, "comuna": None, "precision": "sin_geo", "lat": None, "lng": None})
    return out


def region_hint_de(item):
    r = (item.get("region") or "")
    if re.search(r"metropolitana", r, re.I):
        return "Región Metropolitana"
    if r and not re.search(r"regiones", r, re.I):
        return r.replace("Región de ", "").replace("Región del ", "").replace("Región ", "")
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--no-net", action="store_true", help="sólo caché, sin llamar a Nominatim")
    a = ap.parse_args()
    outdir = os.path.join(ROOT, "output", a.mes)
    src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.json")
    items = json.load(open(src, encoding="utf-8"))
    geo = Geocoder(net=not a.no_net)
    n_ub = 0
    for idx, it in enumerate(items):
        it["id"] = slug_id(it["banco"], it.get("url"), it["comercio"])
        hint = region_hint_de(it)
        ubic = []
        for lug in it.get("lugares") or []:
            ubic += geocodificar_lugar(geo, lug, hint, it["comercio"])
        # comunas del item: de ubicaciones + texto de lugares + condiciones
        comunas = []
        for u in ubic:
            if u.get("comuna") and u["comuna"] not in comunas:
                comunas.append(u["comuna"])
        for c in comunas_en(" ".join(it.get("lugares") or [])):
            if c not in comunas:
                comunas.append(c)
        it["ubicaciones"] = ubic
        it["comunas"] = comunas
        n_ub += sum(1 for u in ubic if u.get("lat"))
        if (idx + 1) % 20 == 0:
            print(f"  {idx+1}/{len(items)} items, {geo.calls} llamadas", file=sys.stderr)
    geo.save()
    dst = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.geo.json")
    json.dump(items, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prec = {}
    for it in items:
        for u in it["ubicaciones"]:
            prec[u["precision"]] = prec.get(u["precision"], 0) + 1
    sin_com = sum(1 for it in items if not it["comunas"])
    print(f"OK {len(items)} items, {n_ub} puntos, precisión={prec}, sin comuna={sin_com}, nominatim calls={geo.calls}\n  {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
