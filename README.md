# DescuentosTarjetas — scraping mensual de descuentos en restaurantes

Objetivo: cada mes (inicio de mes, cuando los bancos renuevan promociones) generar una tabla + mapa
con **lugar específico · horario · tope máximo · días · tarjeta** de los descuentos en restaurantes,
con link al banco para verificar y filtros por comuna / día / tarjeta.

Bancos cubiertos hoy: **Banco Falabella (CMR/Débito)**, **Santander** y **BCI**. Diseñado para agregar más.

## Estructura

```
scripts/
  rsc.py                      util: extrae payload RSC de páginas Next.js (Falabella)
  common.py                   esquema común + heurísticas (días, horario, tope, lugares)
  scrape_falabella.py         Falabella: lista + páginas de detalle -> JSON + MD
  scrape_bci.py               BCI: intercepta la API bciplus con Playwright -> JSON + MD
  santander_fetch_playwright.py  Santander: baja el JSON con Chrome headless (pasa Akamai)
  descubrir_api.py            reconocimiento: qué API usa una landing de beneficios (banco nuevo)
  build_diff.py               altas/bajas/cambios vs el mes anterior -> badges en la app
  santander_fetch_browser.js  Santander: snippet que se ejecuta EN EL NAVEGADOR (Akamai bloquea curl)
  process_santander.py        Santander: JSON crudo -> esquema común -> JSON + MD
  build_report.py             combina bancos -> descuentos_<cat>_<mes>.md / .csv / .json
  geocode.py                  lugares -> lat/lng + comuna (Nominatim/OSM + diccionario de malls + caché)
  screenshots.py              captura la página del banco de cada descuento (Playwright) -> screens/
  build_app.py                app HTML: filtros (banco/día/tarjeta/comuna/texto) + tabla + mapa Leaflet
data/geocache.json            caché Nominatim persistente (no borrar: ahorra ~200 consultas/mes)
output/AAAA-MM/               resultados de cada mes (histórico)
  descuentos_restaurantes_AAAA-MM.html   <- LA APP (doble clic; mapa requiere internet)
  descuentos_restaurantes_AAAA-MM.md/.csv/.json/.geo.json
  screens/<id>.png + _log.json           capturas de evidencia
```

## Procedimiento mensual (≈20 min, casi todo desatendido)

1. **Falabella** (HTTP puro):
   ```bash
   python scripts/scrape_falabella.py --categoria restaurantes
   ```
   Lista `https://www.bancofalabella.cl/descuentos/restaurantes` es Next.js SSR: datos embebidos en
   `self.__next_f.push(...)` (`benefitCardsData`); detalle `/descuentos/detalle/<slug>` trae
   `benefitData` (condiciones rich-text, legal, tarjetas, días, tope, región). Se parsea con
   `raw_decode` sobre `{"benefitData":` (el split por líneas falla en ~14/95).

2. **Santander** (API tras Akamai Bot Manager → curl/urllib = 403; hay que estar en un navegador):
   - **Recomendado (automático)**: `python scripts/santander_fetch_playwright.py --mes AAAA-MM`
     — abre la landing con Chrome headless (pasa Akamai) y deja
     `output/AAAA-MM/santander_raw_cat-sabores.json`. Si Akamai lo bloquea, reintentar con `--headed`.
   - Alternativa manual: abrir la landing en el navegador integrado de Claude Code y ejecutar
     `scripts/santander_fetch_browser.js` (`javascript_tool`); guardar el resultado en esa misma ruta
     (sirve tal cual el `tool-results/*.txt` que deja Claude Code cuando la salida es grande).
     Ojo: el navegador integrado se colgó con esta landing en sept-2026; por eso el camino Playwright.
   - `python scripts/process_santander.py output/AAAA-MM/santander_raw_cat-sabores.json`
   - Tags útiles: días (`lunes`…`domingo`), tarjetas (`wm-limited`, `exclusivo-amex`,
     `todas-las-tarjetas`, `life-y-debito`), cobertura (`metropolitana`, `regiones`). El campo
     "Comuna cobertura" viene lleno en muchos → se usa para el filtro por comuna.
     **Días: el texto manda** (los tags a veces quedan desactualizados, p.ej. Don Carlos).

3. **BCI** (API `api.bciplus.cl/bff-loyalty-beneficios/v1/offers`, responde 401 fuera del navegador):
   ```bash
   python scripts/scrape_bci.py --mes AAAA-MM
   ```
   Abre la landing con Playwright e intercepta las 3 páginas de la API (~288 ofertas, ~76 con tag
   "Restaurantes"). Trae % de descuento, días (`scheduling.dayRecurrence`), comuna y región en tags.
   OJO: `titulo` es texto promocional ("Viernes - Maitencillo"); el nombre real está en
   `comercio.nombre`. El tope sólo viene en el texto.

4. **Reporte, mapa y app**:
   ```bash
   python scripts/build_report.py --mes AAAA-MM
   python scripts/geocode.py --mes AAAA-MM          # ~3 min la 1ª vez, después casi todo del caché
   # opcional (evidencia con fecha; ~10 min):
   python scripts/screenshots.py --mes AAAA-MM --only falabella
   python scripts/screenshots.py --mes AAAA-MM --only santander --channel chrome --idle-timeout 4000
   python scripts/build_diff.py --mes AAAA-MM    # altas/bajas/cambios vs mes anterior
   python scripts/build_app.py --mes AAAA-MM
   python scripts/build_artifact.py --mes AAAA-MM
   ```
   Abrir `output/AAAA-MM/descuentos_restaurantes_AAAA-MM.html`.

### Qué muestra la app
- **Tipo de local** en cada fila/tarjeta (Falabella: `commerceInfoDescription`; Santander: primera
  línea de la descripción; BCI: primera línea).
- **📍 Cerca de mí**: GPS del navegador, radio 1/3/5/10 km, orden por cercanía, círculo en el mapa.
- **Badges NUEVO / CAMBIÓ** vs el mes anterior + filtros rápidos (de `build_diff.py`).
- **PWA**: `publish_site.py` genera `manifest.webmanifest`, `sw.js` e iconos → en el celular se
  instala con "Agregar a pantalla de inicio" y funciona offline (menos los tiles del mapa).

## Publicar (GitHub Pages, gratis, se ve desde el celular)

URL pública: **https://vpenaandes.github.io/descuentos-tarjetas/** (redirige al mes más reciente;
`/AAAA-MM/` para un mes específico). Repo: https://github.com/vpenaandes/descuentos-tarjetas (público;
Pages sirve `main:/docs`). Las capturas van comprimidas a JPEG (~26 MB/mes); las PNG crudas quedan
fuera del repo (`.gitignore`).

```bash
python scripts/publish_site.py --mes AAAA-MM     # arma docs/AAAA-MM/ + docs/index.html
git add -A && git commit -m "Descuentos AAAA-MM" && git push
```
Pages tarda ~1 min en reflejar el push. Si algún mes no se quiere publicar con capturas:
`--no-screens`.

### Versión privada (Artifact de claude.ai, sólo con tu login)
https://claude.ai/code/artifact/294813f4-b9cb-48f4-a68f-96b9adcc25d5 — tarjetas móviles, día "hoy"
preseleccionado, filtros, links Verificar/Maps, condiciones. Sin mapa ni capturas (claude.ai bloquea
recursos externos). Regenerar y republicar cada mes:
```bash
python scripts/build_artifact.py --mes AAAA-MM      # -> output/AAAA-MM/descuentos_restaurantes_AAAA-MM_artifact.html
# luego: herramienta Artifact de Claude Code con ese archivo y url=<la de arriba> para mantener el link
```
Nota GitHub: la cuenta es plan Free → Pages sólo funciona con repo público; con repo privado el sitio se
apaga (probado 2026-08-22). Para página privada gratis con mapa: Cloudflare Pages + Access (requiere cuenta).

## Plan de verificación (no confundir local, no confiar ciegamente en la heurística)

1. **Fuente siempre a un clic (lo principal)**: cada fila/popup tiene "Verificar ↗" → abre DIRECTO la
   página de ese restaurante en el banco (deep link por slug). El nombre del comercio también es link.
   Cada ubicación tiene "Maps ↗" → Google Maps en el punto (o la dirección si no hay punto).
   Las capturas (paso 3) son OPCIONALES: sólo evidencia congelada con fecha, útil porque Santander
   borra promos vencidas y los bancos cambian locales a mitad de mes. Si apura, saltar ese paso.
2. **Texto íntegro del banco**: botón "Condiciones" muestra tal cual lo que publicó el banco (fuente de
   verdad). Si la heurística dejó "—" en lugar/horario, ahí está la respuesta.
3. **Capturas de pantalla** (`screenshots.py`, Playwright): botón "Captura" abre
   `screens/<id>.png` con fecha de captura. Falabella: Chromium headless OK. Santander: Chromium
   headless es bloqueado por Akamai ("Internet Connection Error") → usar `--channel chrome`
   (Chrome instalado, headless pasa) o `--headed`. El script detecta páginas bloqueadas/vacías y las
   deja marcadas `ok:false` para reintentar; re-correr el script sólo reintenta las que faltan.
4. **Precisión del mapa** (badge en cada punto):
   - `exacta` = OSM devolvió el número de casa · `mall` = recinto conocido (diccionario `MALLS` en
     `geocode.py`) · `calle` = sólo la calle (±cuadras; verificar) · `ciudad`/`nombre`/`zona` =
     aproximado, se dibujan punteados y sólo con el toggle "mostrar ubicaciones aproximadas".
   - Por nombre sólo se acepta si OSM devuelve un local gastronómico cuyo nombre contiene la frase
     completa (evita "Social" → Ministerio de Desarrollo Social).
5. **Diff mes a mes** (pendiente): comparar `descuentos_*.json` de dos meses → altas/bajas/cambios de
   condiciones. Los JSON quedan en `output/AAAA-MM/` para eso.
6. **Muestreo manual**: antes de usar un descuento caro, abrir el link. Los bancos cambian locales y
   topes sin aviso.

## Calidad / limitaciones conocidas (ago-2026)

- Falabella: 95 beneficios; ~16 sin dirección (cadenas / "exclusivo presencial"). Patrón típico
  "40% CMR / 30% Débito"; tope casi siempre "Sin tope". Multilocal con días distintos por local
  ("Mallplaza Egaña: lunes a jueves") → se listan todos; el filtro por día usa la unión.
- Santander: 83 beneficios; tope explícito casi siempre; ~7 sin lugar (online/delivery).
- Horario casi nunca publicado; cuando sí (Panchita "hasta las 17:00", Open Kennedy "desde 19:00") se
  captura en `horario` o queda en el texto del local.
- Geocodificación: ~200 puntos; ~70 exacta, ~85 mall, ~35 calle, resto aprox/sin geo. Nominatim
  1 req/s.

## Bancos evaluados y descartados (sept-2026)

- **Banco de Chile**: `www.bancochile.cl/personas/beneficios` responde 302 en loop y
  `ERR_HTTP2_PROTOCOL_ERROR` con Playwright → bloquea automatización. Pendiente reintentar.
- **Scotiabank**: los descuentos viven en `scotiarewards.cl/scclubfront`, que exige login de cliente.
  No se automatiza (no se usan credenciales del usuario).

## Cómo agregar otro banco

0. `python scripts/descubrir_api.py <url-landing>` → dice si los datos están en el HTML, en un XHR
   JSON (guarda cada respuesta) o si hay que renderizar.
1. `scripts/scrape_<banco>.py` (o fetch por navegador + `process_<banco>.py`) que produzca
   `output/AAAA-MM/<banco>_<categoria>.json` con el esquema de `common.py` (docstring).
2. `build_report.py` lo toma automáticamente (glob `*_<categoria>.json`); geocode/app también.
3. En `build_app.py`, `tarjetas_filtro()` necesita una rama para normalizar nombres de tarjetas.
4. Reutilizar `common.dias_desde_texto / tope_desde_texto / lugares_desde_texto / horario_desde_texto`.

Candidatos: BCI, Banco de Chile, Scotiabank, Itaú, Tenpo/MACH.

## Historial

- 2026-08-22: primera corrida. Falabella 95, Santander 83 (178). Geocodificación + app + capturas.
- 2026-09-01: septiembre. Falabella 94, Santander 82, BCI 76 (252). Fetch Santander automatizado con
  Playwright; se agregó BCI, tipo de local, "Cerca de mí" (GPS), PWA instalable, diff mes a mes e
  IDs estables por URL (antes dependían del índice y desparejaban las capturas).
