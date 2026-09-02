"""Genera la app HTML (filtros + tabla + mapa) de un mes.

Uso:
    python scripts/build_app.py [--mes AAAA-MM] [--categoria restaurantes]

Entrada: output/<mes>/descuentos_<cat>_<mes>.geo.json (de geocode.py; si no existe usa .json sin mapa)
         output/<mes>/screens/_log.json (opcional, de screenshots.py)
Salida : output/<mes>/descuentos_<cat>_<mes>.html  -> abrir con doble clic.

La app es un archivo único con los datos embebidos. Usa Leaflet + OpenStreetMap desde CDN
(necesita internet para el mapa; la tabla funciona offline).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import slug_id  # noqa: E402


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def tarjetas_filtro(item):
    """Normaliza tarjetas a etiquetas cortas para el filtro."""
    out = []
    b = item["banco"]
    txt = " ".join(item.get("tarjetas") or [])
    if b == "Banco Falabella":
        m = {"CMR Mastercard Elite": "CMR Elite", "CMR Mastercard Premium": "CMR Premium",
             "CMR Mastercard": "CMR", "Tarjeta Débito Banco Falabella": "Débito Falabella"}
        for t in item.get("tarjetas") or []:
            out.append(m.get(t, t))
    elif b == "BCI":
        t = txt.lower()
        if re.search(r"black|signature|infinite", t):
            out.append("BCI Premium (Black/Signature/Infinite)")
        if re.search(r"cr[ée]dito", t):
            out.append("BCI Crédito")
        if re.search(r"d[ée]bito", t):
            out.append("BCI Débito")
        if not out:
            out = ["BCI (ver condiciones)"]
    else:
        t = txt.lower()
        if re.search(r"worldmember limited|wm limited", t):
            out.append("Santander WM Limited")
        if re.search(r"american express|amex", t):
            out.append("Santander Amex")
        if re.search(r"platinum", t):
            out.append("Santander Platinum")
        if re.search(r"\blife\b", t):
            out.append("Santander Life")
        if re.search(r"cr[ée]dito", t):
            out.append("Santander Crédito")
        if re.search(r"d[ée]bito", t):
            out.append("Santander Débito")
        if not out:
            out = ["Santander (ver condiciones)"]
    return list(dict.fromkeys(out))


def referencias(items):
    """Puntos de referencia para elegir "desde dónde" sin GPS: malls conocidos y
    centros de comuna que ya estén geocodificados en los datos del mes."""
    from geocode import MALLS
    refs = []
    vistos = set()
    for _k, (nombre, _dir, comuna, lat, lng) in MALLS.items():
        if nombre not in vistos and lat and lng:
            vistos.add(nombre)
            refs.append({"n": nombre, "g": "Centros comerciales / barrios", "lat": lat, "lng": lng, "c": comuna})
    porcomuna = {}
    for it in items:
        for u in it.get("ubicaciones") or []:
            c = u.get("comuna")
            if c and u.get("lat") and c not in porcomuna:
                porcomuna[c] = (u["lat"], u["lng"])
    for c, (lat, lng) in sorted(porcomuna.items()):
        refs.append({"n": c, "g": "Comunas", "lat": lat, "lng": lng, "c": c})
    return refs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    a = ap.parse_args()
    outdir = os.path.join(ROOT, "output", a.mes)
    src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.geo.json")
    if not os.path.exists(src):
        print("(sin .geo.json: mapa vacío; corre geocode.py)", file=sys.stderr)
        src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.json")
    items = json.load(open(src, encoding="utf-8"))
    diff_path = os.path.join(outdir, f"cambios_{a.categoria}_{a.mes}.json")
    diff = json.load(open(diff_path, encoding="utf-8")) if os.path.exists(diff_path) else {"altas": [], "cambios": {}, "prev": None}
    log_path = os.path.join(outdir, "screens", "_log.json")
    shots = json.load(open(log_path, encoding="utf-8")) if os.path.exists(log_path) else {}
    data = []
    for idx, it in enumerate(items):
        it["id"] = slug_id(it["banco"], it.get("url"), it["comercio"])  # recalcular: los .geo.json viejos traen ids por índice
        sh = shots.get(it["id"])
        data.append({
            "id": it["id"], "banco": it["banco"], "comercio": it["comercio"], "tipo": it.get("tipo", ""), "descuento": it["descuento"],
            "pct": it.get("descuento_pct"), "tope": it["tope"], "dias": it["dias"], "horario": it["horario"],
            "lugares": it["lugares"], "tarjetas": it["tarjetas"], "tf": tarjetas_filtro(it),
            "modalidad": it["modalidad"], "region": it["region"], "vigencia": it["vigencia"],
            "condiciones": it["condiciones"], "url": it["url"], "comunas": it.get("comunas") or [],
            "ubic": [u for u in (it.get("ubicaciones") or []) if u.get("lat")],
            "shot": (f"screens/{it['id']}.png" if sh and sh.get("ok") else None),
            "shot_ts": (sh or {}).get("ts"),
            "nuevo": it["id"] in set(diff.get("altas") or []),
            "cambios": (diff.get("cambios") or {}).get(it["id"]) or None,
        })
    meta = {"mes": a.mes, "categoria": a.categoria, "generado": dt.date.today().isoformat(), "n": len(data),
            "refs": referencias(items),
            "bancos": sorted({d["banco"] for d in data}),
            "tarjetas": sorted({t for d in data for t in d["tf"]}),
            "comunas": sorted({c for d in data for c in d["comunas"]}),
            "prev": diff.get("prev"), "n_nuevos": sum(1 for d in data if d["nuevo"]),
            "n_cambios": sum(1 for d in data if d["cambios"])}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__META__", json.dumps(meta, ensure_ascii=False))
    dst = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.html")
    open(dst, "w", encoding="utf-8").write(html)
    n_pts = sum(len(d["ubic"]) for d in data)
    n_sh = sum(1 for d in data if d["shot"])
    print(f"OK {len(data)} items, {n_pts} puntos en mapa, {n_sh} capturas -> {dst}", file=sys.stderr)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Descuentos restaurantes</title>
<link rel="manifest" href="../manifest.webmanifest">
<meta name="theme-color" content="#2563eb">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Descuentos">
<link rel="apple-touch-icon" href="../icon-180.png">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--muted:#6b7280;--line:#e5e7eb;--fal:#0e7a3b;--san:#ec0000;--bci:#f5a300;--acc:#2563eb;--hl:#fff7cc}
*{box-sizing:border-box}
body{margin:0;font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header{padding:12px 16px;background:var(--card);border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:10px 24px;align-items:baseline}
header h1{font-size:18px;margin:0}
header .meta{color:var(--muted);font-size:12px}
#filters{padding:10px 16px;background:var(--card);border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;position:sticky;top:0;z-index:1000}
.fgroup{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.fgroup label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-right:4px}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:3px 10px;cursor:pointer;font-size:13px;user-select:none}
.chip.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.chip.fal.on{background:var(--fal);border-color:var(--fal)}
.chip.san.on{background:var(--san);border-color:var(--san)}
.chip.bci.on{background:var(--bci);border-color:var(--bci);color:#1d2330}
input[type=text]{border:1px solid var(--line);border-radius:8px;padding:5px 9px;font-size:13px;min-width:200px}
select{border:1px solid var(--line);border-radius:8px;padding:5px 9px;font-size:13px;max-width:220px}
.toggle{font-size:12px;color:var(--muted);display:flex;gap:4px;align-items:center;cursor:pointer}
#count{font-weight:600}
#main{display:grid;grid-template-columns:minmax(0,1fr) 44%;gap:0;height:calc(100vh - 110px)}
#tablewrap{overflow:auto;padding:0 8px 40px 16px}
#map{height:100%;position:sticky;top:0;border-left:1px solid var(--line)}
table{border-collapse:collapse;width:100%;background:var(--card)}
th{position:sticky;top:0;background:#f1f3f6;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);padding:8px 8px;border-bottom:1px solid var(--line);z-index:1}
td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}
tr.row:hover{background:#fafbff}
tr.row.sel{background:var(--hl)}
tr.det td{background:#fbfbfd;padding:8px 12px 12px}
.bk{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.bk.fal{background:var(--fal)}.bk.san{background:var(--san)}.bk.bci{background:var(--bci)}
.name{font-weight:600}
.name a{color:inherit;text-decoration:none;border-bottom:1px dotted #999}
.name a:hover{color:var(--acc)}
.days{display:flex;gap:2px;flex-wrap:wrap}
.d{font-size:10px;border:1px solid var(--line);border-radius:4px;padding:0 4px;color:#aaa}
.d.on{background:#e8f0ff;color:#1e40af;border-color:#c7d7fe;font-weight:600}
.small{font-size:12px;color:var(--muted)}
.lug{font-size:12px;margin:0;padding-left:14px}
.lug li{margin:0}
.com{display:inline-block;font-size:10px;background:#eef2f7;border-radius:4px;padding:0 5px;margin:1px 2px 0 0;color:#374151}
.tj{font-size:11px;display:inline-block;background:#f3f4f6;border-radius:4px;padding:1px 5px;margin:1px 2px 0 0}
.btn{border:1px solid var(--line);background:#fff;border-radius:6px;padding:3px 8px;font-size:12px;cursor:pointer;margin:1px 2px 1px 0;white-space:nowrap}
.btn:hover{border-color:var(--acc);color:var(--acc)}
.btn[disabled]{opacity:.45;cursor:not-allowed}
pre.cond{white-space:pre-wrap;font:12px/1.45 ui-monospace,Consolas,monospace;background:#fff;border:1px solid var(--line);border-radius:6px;padding:8px;margin:6px 0;max-height:320px;overflow:auto}
.badge{font-size:10px;border-radius:5px;padding:1px 5px;margin-left:5px;font-weight:700;letter-spacing:.02em}
.badge.new{background:#dcfce7;color:#166534}
.badge.chg{background:#fef9c3;color:#854d0e;cursor:help}
.dist{font-size:11px;background:#e8f0ff;color:#1e40af;border-radius:5px;padding:0 5px;margin-left:4px;font-variant-numeric:tabular-nums}
.prec{font-size:10px;border-radius:3px;padding:0 4px;background:#e5e7eb;color:#374151;margin-left:4px}
.prec.exacta,.prec.mall{background:#dcfce7;color:#166534}.prec.calle{background:#fef9c3;color:#854d0e}.prec.ciudad,.prec.nombre,.prec.zona{background:#fee2e2;color:#991b1b}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:flex-start;justify-content:center;z-index:5000;overflow:auto;padding:20px}
#modal .box{background:#fff;border-radius:10px;max-width:1100px;width:100%;padding:12px}
#modal img{max-width:100%;display:block;border:1px solid var(--line)}
#modal .bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:10px;flex-wrap:wrap}
.leaflet-popup-content{font-size:13px;line-height:1.35}
.leaflet-popup-content b{font-size:14px}
.mk{width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.35)}
.mk.fal{background:var(--fal)}.mk.san{background:var(--san)}.mk.bci{background:var(--bci)}
.mk.aprox{background:#fff!important;border:2px dashed #555}
.legend{background:#fff;padding:6px 8px;border-radius:6px;font-size:12px;box-shadow:0 1px 4px rgba(0,0,0,.2);line-height:1.6}
.viewtabs{display:none}
#ftoggle{display:none}
@media (max-width:1000px){
  #main{display:block;height:auto}
  #tablewrap{padding:0 6px 80px}
  #map{display:none;height:calc(100vh - 120px);position:relative;border-left:0;border-top:1px solid var(--line)}
  body.view-map #tablewrap{display:none}
  body.view-map #map{display:block}
  .viewtabs{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .viewtabs button{border:0;background:#fff;padding:6px 14px;font-size:13px;cursor:pointer}
  .viewtabs button.on{background:var(--acc);color:#fff}
  #ftoggle{display:inline-block}
  #filters.collapsed .fgroup.col, #filters.collapsed .toggle{display:none}
  th:nth-child(4),td:nth-child(4){display:none}
  td,th{padding:6px 5px}
}
</style>
</head>
<body>
<header>
  <h1>Descuentos restaurantes · <span id="mes"></span></h1>
  <span class="meta" id="metatxt"></span>
  <span class="meta">Verificación: cada fila enlaza a la página del banco (fuente); “Condiciones” muestra el texto íntegro capturado; “Captura” abre el screenshot si existe.</span>
</header>
<div id="filters">
  <div class="fgroup"><span class="viewtabs"><button type="button" id="vt-list" class="on" onclick="setView('list')">Lista</button><button type="button" id="vt-map" onclick="setView('map')">Mapa</button></span>
    <button class="btn" id="ftoggle" type="button">Filtros ▾</button></div>
  <div class="fgroup" id="f-dia"><label>Día</label></div>
  <div class="fgroup col" id="f-banco"><label>Banco</label></div>
  <div class="fgroup col" id="f-tarj"><label>Tarjeta</label></div>
  <div class="fgroup col"><label>Comuna</label><select id="sel-com"><option value="">(agregar comuna…)</option></select><span id="f-com" class="fgroup"></span></div>
  <div class="fgroup col"><label>Buscar</label><input type="text" id="q" placeholder="comercio, tipo, lugar, condición…"></div>
  <div class="fgroup"><label>Desde</label>
    <select id="ref"><option value="">— sin punto de referencia —</option></select>
    <button class="btn" id="pickmap" type="button" title="Fijar el punto haciendo clic en el mapa">Elegir en el mapa</button>
    <button class="btn" id="geoloc" type="button">📍 Mi ubicación</button>
    <select id="radio" title="radio de búsqueda"><option value="1">1 km</option><option value="3" selected>3 km</option><option value="5">5 km</option><option value="10">10 km</option></select>
    <span class="small" id="geostat"></span></div>
  <div class="fgroup" id="f-flags"></div>
  <label class="toggle"><input type="checkbox" id="tg-aprox"> mostrar ubicaciones aproximadas (ciudad/por nombre)</label>
  <label class="toggle"><input type="checkbox" id="tg-geo"> sólo con punto en mapa</label>
  <button class="btn" id="clear">Limpiar filtros</button>
  <span class="small"><span id="count"></span> beneficios</span>
</div>
<div id="main">
  <div id="tablewrap">
    <table>
      <thead><tr><th>Comercio</th><th>Tipo</th><th>Dcto / Tope</th><th>Días</th><th>Horario</th><th>Lugar · comuna</th><th>Tarjetas</th><th>Acciones</th></tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
  <div id="map"></div>
</div>
<div id="modal"><div class="box"><div class="bar"><b id="m-title"></b><span><span class="small" id="m-ts"></span> <a id="m-url" target="_blank" class="btn">Abrir en el banco ↗</a> <button class="btn" id="m-close">Cerrar ✕</button></span></div><img id="m-img" alt="captura"><p id="m-nota" class="small"></p></div></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const DATA = __DATA__;
const META = __META__;
const DIAS = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"];
const state = {banco:new Set(), dia:new Set(), tarj:new Set(), com:new Set(), q:"", aprox:false, geo:false, sel:null, me:null, radio:3, soloNuevos:false, soloCambios:false};
const R = 6371;
function haversine(a,b,c,d){ const t=x=>x*Math.PI/180; const s=Math.sin(t(c-a)/2)**2+Math.cos(t(a))*Math.cos(t(c))*Math.sin(t(d-b)/2)**2; return 2*R*Math.asin(Math.sqrt(s)); }
function distOf(d){ if(!state.me) return null; let best=null; for(const u of d.ubic){ if(isAprox(u)&&!state.aprox) continue; const km=haversine(state.me[0],state.me[1],u.lat,u.lng); if(best===null||km<best) best=km; } return best; }
function fmtKm(km){ return km<1 ? Math.round(km*1000)+" m" : km.toFixed(1)+" km"; }
const bk = b => b==="Banco Falabella"?"fal":(b==="BCI"?"bci":"san");
const esc = s => String(s??"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const normtxt = s => (s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();

document.getElementById("mes").textContent = META.mes;
document.getElementById("metatxt").textContent = `${META.n} beneficios · ${META.bancos.join(" + ")} · generado ${META.generado}` + (META.prev?` · vs ${META.prev}: ${META.n_nuevos} nuevos, ${META.n_cambios} con cambios`:"");

function chip(parent, label, cls, onclick){ const c=document.createElement("span"); c.className="chip "+(cls||""); c.textContent=label; c.onclick=()=>onclick(c); parent.appendChild(c); return c; }
const fb = document.getElementById("f-banco");
META.bancos.forEach(b=>chip(fb,b.replace("Banco ",""),bk(b),c=>{toggleSet(state.banco,b,c);render();}));
const fd = document.getElementById("f-dia");
DIAS.forEach(d=>chip(fd,d.slice(0,3),"",c=>{toggleSet(state.dia,d,c);render();}));
chip(fd,"Hoy","",c=>{const h=DIAS[(new Date().getDay()+6)%7]; [...fd.children].forEach(x=>x.classList.remove("on")); state.dia.clear(); state.dia.add(h); [...fd.children].find(x=>x.textContent===h.slice(0,3))?.classList.add("on"); render();});
const ft = document.getElementById("f-tarj");
META.tarjetas.forEach(t=>chip(ft,t,"",c=>{toggleSet(state.tarj,t,c);render();}));
const ff = document.getElementById("f-flags");
if(META.n_nuevos) chip(ff, `✨ Nuevos (${META.n_nuevos})`, "", c=>{ state.soloNuevos=!state.soloNuevos; c.classList.toggle("on"); render(); });
if(META.n_cambios) chip(ff, `⚠ Cambió (${META.n_cambios})`, "", c=>{ state.soloCambios=!state.soloCambios; c.classList.toggle("on"); render(); });
const sc = document.getElementById("sel-com");
META.comunas.concat(["(sin comuna: cadena / online / sin dirección)"]).forEach(c=>{const o=document.createElement("option");o.value=c;o.textContent=c;sc.appendChild(o);});
sc.onchange=()=>{ if(sc.value){ addCom(sc.value); sc.value=""; } };
function addCom(c){ if(state.com.has(c)) return; state.com.add(c); const ch=chip(document.getElementById("f-com"),c+" ✕","on",x=>{state.com.delete(c);x.remove();render();}); render(); }
function toggleSet(set,v,c){ if(set.has(v)){set.delete(v);c.classList.remove("on");} else {set.add(v);c.classList.add("on");} }
document.getElementById("q").oninput = e=>{state.q=normtxt(e.target.value);render();};
document.getElementById("tg-aprox").onchange = e=>{state.aprox=e.target.checked;render();};
document.getElementById("tg-geo").onchange = e=>{state.geo=e.target.checked;render();};
document.getElementById("clear").onclick = ()=>{ selRef.value=""; setRef(null); state.banco.clear();state.dia.clear();state.tarj.clear();state.com.clear();state.q="";state.aprox=false;state.geo=false; document.querySelectorAll(".chip.on").forEach(c=>c.classList.remove("on")); document.getElementById("f-com").innerHTML=""; document.getElementById("q").value=""; document.getElementById("tg-aprox").checked=false; document.getElementById("tg-geo").checked=false; render(); };

// ---- mapa
const map = L.map("map",{preferCanvas:true}).setView([-33.43,-70.61],11);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
const cluster = L.markerClusterGroup({maxClusterRadius:40, disableClusteringAtZoom:15});
map.addLayer(cluster);
const legend = L.control({position:"bottomleft"});
legend.onAdd=()=>{const d=L.DomUtil.create("div","legend");d.innerHTML='<span class="mk fal" style="display:inline-block;vertical-align:middle"></span> Falabella &nbsp; <span class="mk san" style="display:inline-block;vertical-align:middle"></span> Santander &nbsp; <span class="mk bci" style="display:inline-block;vertical-align:middle"></span> BCI<br><span class="mk aprox" style="display:inline-block;vertical-align:middle"></span> aproximado (ciudad / por nombre)<br><span class="small">exacta = OSM con número · mall = recinto · calle = sin número (±cuadras)</span>';return d;};
legend.addTo(map);
const markersById = {};
function isAprox(u){ return ["ciudad","nombre","zona"].includes(u.precision); }
function popup(d,u){
  return `<b>${esc(d.comercio)}</b> <span class="small">${esc(d.banco)}</span><br>
  ${d.tipo?`<i>${esc(d.tipo)}</i><br>`:""}
  <b>${esc(d.descuento)}</b> · tope ${esc(d.tope||"—")}<br>
  Días: ${d.dias.join(", ")||"—"}${d.horario?`<br>Horario: ${esc(d.horario)}`:""}<br>
  Lugar: ${esc(u.nombre||u.consulta)} <span class="prec ${u.precision}">${u.precision}</span>${u.comuna?` · ${esc(u.comuna)}`:""}<br>
  Tarjetas: ${d.tf.join(", ")}<br>
  <a href="${d.url}" target="_blank">Verificar en el banco ↗</a> · <a href="${gmaps(u)}" target="_blank">Google Maps ↗</a> · <a href="#" onclick="selectRow('${d.id}');return false;">ver fila</a>`;
}
function gmaps(u){ return u.lat ? `https://www.google.com/maps/search/?api=1&query=${u.lat},${u.lng}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((u.consulta||"")+", Chile")}`; }

// ---- filtro
function pass(d){
  if(state.banco.size && !state.banco.has(d.banco)) return false;
  if(state.dia.size && ![...state.dia].some(x=>d.dias.includes(x))) return false;
  if(state.tarj.size && ![...state.tarj].some(x=>d.tf.includes(x))) return false;
  if(state.com.size && ![...state.com].some(x=>d.comunas.includes(x))) return false;
  if(state.geo && !d.ubic.some(u=>state.aprox||!isAprox(u))) return false;
  if(state.q){ const hay = normtxt([d.comercio,d.tipo,d.banco,d.descuento,d.tope,d.horario,d.lugares.join(" "),d.tarjetas.join(" "),d.condiciones,d.comunas.join(" ")].join(" ")); if(!hay.includes(state.q)) return false; }
  if(state.soloNuevos && !d.nuevo) return false;
  if(state.soloCambios && !d.cambios) return false;
  if(state.me){ const km=distOf(d); if(km===null || km>state.radio) return false; }
  return true;
}

function rowHtml(d){
  const days = DIAS.map(x=>`<span class="d ${d.dias.includes(x)?"on":""}">${x.slice(0,2)}</span>`).join("");
  const lug = d.lugares.length? `<ul class="lug">${d.lugares.map(l=>`<li>${esc(l)}</li>`).join("")}</ul>` : `<span class="small">— (ver condiciones)</span>`;
  const coms = d.comunas.map(c=>`<span class="com">${esc(c)}</span>`).join("");
  const tj = d.tf.map(t=>`<span class="tj">${esc(t)}</span>`).join("");
  const hasPt = d.ubic.some(u=>state.aprox||!isAprox(u));
  return `<tr class="row" id="r-${d.id}" onclick="selectRow('${d.id}',true)">
    <td><span class="bk ${bk(d.banco)}"></span><span class="name"><a href="${d.url}" target="_blank" title="Abrir en ${esc(d.banco)}" onclick="event.stopPropagation()">${esc(d.comercio)}</a></span>${d.nuevo?'<span class="badge new">NUEVO</span>':""}${d.cambios?`<span class="badge chg" title="${esc(Object.keys(d.cambios).join(", "))} cambió vs ${esc(META.prev||"")}">CAMBIÓ</span>`:""}<div class="small">${esc(d.banco)} · ${esc(d.modalidad||"")}${(()=>{const k=distOf(d);return k===null?"":`<span class="dist">${fmtKm(k)}</span>`;})()}</div></td>
    <td class="small tipo">${esc(d.tipo||"—")}</td>
    <td><b>${esc(d.descuento)}</b><div class="small">Tope: ${esc(d.tope||"—")}</div></td>
    <td><div class="days">${days}</div></td>
    <td class="small">${esc(d.horario||"—")}</td>
    <td>${lug}<div>${coms}</div></td>
    <td>${tj}</td>
    <td><button class="btn" onclick="event.stopPropagation();toggleDet('${d.id}')">Condiciones</button><br>
        <a class="btn" href="${d.url}" target="_blank" onclick="event.stopPropagation()">Verificar ↗</a><br>
        <button class="btn" ${d.shot?"":"disabled title='sin captura: correr scripts/screenshots.py'"} onclick="event.stopPropagation();showShot('${d.id}')">Captura</button><br>
        <button class="btn" ${hasPt?"":"disabled title='sin punto geocodificado'"} onclick="event.stopPropagation();selectRow('${d.id}',true)">Mapa</button></td>
  </tr>
  <tr class="det" id="d-${d.id}" style="display:none"><td colspan="8">
    ${d.cambios?`<div class="small">Cambios vs ${esc(META.prev||"")}: ${Object.entries(d.cambios).map(([k,v])=>`<b>${esc(k)}</b>: <s>${esc(v.antes||"—")}</s> → ${esc(v.ahora||"—")}`).join(" · ")}</div>`:""}
    <div class="small">Vigencia: ${esc(d.vigencia||"—")} · Región: ${esc(d.region||"—")} · Fuente: <a href="${d.url}" target="_blank">${esc(d.url)}</a></div>
    <pre class="cond">${esc(d.condiciones||"(sin texto)")}</pre>
    ${d.ubic.length?`<div class="small">Ubicaciones: ${d.ubic.map(u=>`${esc(u.nombre||u.consulta)} <span class="prec ${u.precision}">${u.precision}</span>${u.comuna?" · "+esc(u.comuna):""} <a href="${gmaps(u)}" target="_blank">Maps ↗</a>`).join(" | ")}</div>`:""}
  </td></tr>`;
}

let current = [];
function render(){
  current = DATA.filter(pass);
  if(state.me) current.sort((a,b)=>(distOf(a)??1e9)-(distOf(b)??1e9));
  document.getElementById("count").textContent = current.length;
  document.getElementById("tb").innerHTML = current.map(rowHtml).join("");
  cluster.clearLayers(); for (const k in markersById) delete markersById[k];
  const pts=[];
  current.forEach(d=>{
    d.ubic.forEach(u=>{
      if(isAprox(u) && !state.aprox) return;
      const ic = L.divIcon({className:"", html:`<div class="mk ${bk(d.banco)} ${isAprox(u)?"aprox":""}"></div>`, iconSize:[14,14], iconAnchor:[7,7]});
      const m = L.marker([u.lat,u.lng],{icon:ic}).bindPopup(popup(d,u));
      cluster.addLayer(m); (markersById[d.id]=markersById[d.id]||[]).push(m); pts.push([u.lat,u.lng]);
    });
  });
  lastPts = pts;
  fitCurrent();
}
let lastPts = [];
function fitCurrent(){
  if(!lastPts.length || map.getContainer().offsetWidth===0) return;
  const b = L.latLngBounds(lastPts);
  // si los puntos abarcan medio país, centrar en Santiago (la mayoría) en vez de zoom 4
  if(b.getNorth()-b.getSouth() > 3){ const rm = lastPts.filter(p=>p[0]>-33.75 && p[0]<-33.2 && p[1]>-70.95 && p[1]<-70.4); if(rm.length){ map.fitBounds(L.latLngBounds(rm).pad(0.1),{maxZoom:13}); return; } }
  map.fitBounds(b.pad(0.15),{maxZoom:14});
}
const isMobile = () => window.matchMedia("(max-width:1000px)").matches;
function setView(v){
  document.body.classList.toggle("view-map", v==="map");
  document.getElementById("vt-list").classList.toggle("on", v!=="map");
  document.getElementById("vt-map").classList.toggle("on", v==="map");
  if(v==="map"){ setTimeout(()=>{ map.invalidateSize(); fitCurrent(); }, 60); }
}
window.addEventListener("resize", ()=>{ map.invalidateSize(); });
let meMarker=null, meCircle=null;
// --- punto de referencia (sirve cuando el navegador no da ubicación)
const REFS = META.refs || [];
const selRef = document.getElementById("ref");
(() => {
  const grupos = {};
  REFS.forEach((r,i)=>{ (grupos[r.g] = grupos[r.g] || []).push({...r, i}); });
  for(const g of Object.keys(grupos)){
    const og=document.createElement("optgroup"); og.label=g;
    grupos[g].sort((a,b)=>a.n.localeCompare(b.n,"es")).forEach(r=>{
      const o=document.createElement("option"); o.value=String(r.i); o.textContent=r.n; og.appendChild(o);
    });
    selRef.appendChild(og);
  }
})();
function setRef(lat,lng,label,persist=true){
  state.me = (lat===null) ? null : [lat,lng];
  drawMe();
  const st=document.getElementById("geostat");
  st.textContent = state.me ? ("desde " + (label||"punto elegido")) : "";
  document.getElementById("geoloc").textContent = "📍 Mi ubicación";
  if(persist){ try{ state.me ? localStorage.setItem("ref", JSON.stringify({lat,lng,label})) : localStorage.removeItem("ref"); }catch(e){} }
  render();
  if(state.me && isMobile()) setView("map");
}
selRef.onchange = ()=>{
  if(selRef.value===""){ setRef(null); return; }
  const r=REFS[+selRef.value]; if(r) setRef(r.lat, r.lng, r.n);
};
let pickMode=false;
document.getElementById("pickmap").onclick = function(){
  pickMode=!pickMode;
  this.classList.toggle("on", pickMode);
  this.textContent = pickMode ? "Haz clic en el mapa…" : "Elegir en el mapa";
  map.getContainer().style.cursor = pickMode ? "crosshair" : "";
  if(pickMode && isMobile()) setView("map");
};
map.on("click", e=>{
  if(!pickMode) return;
  pickMode=false;
  const b=document.getElementById("pickmap");
  b.classList.remove("on"); b.textContent="Elegir en el mapa"; map.getContainer().style.cursor="";
  selRef.value="";
  setRef(e.latlng.lat, e.latlng.lng, "punto elegido en el mapa");
});
try{
  const saved=JSON.parse(localStorage.getItem("ref")||"null");
  if(saved && typeof saved.lat==="number"){ setRef(saved.lat, saved.lng, saved.label, false); }
}catch(e){}
const _r=document.getElementById("radio"); if(_r) _r.onchange = e=>{ state.radio=+e.target.value; if(state.me){ drawMe(); render(); } };
function drawMe(){
  if(meMarker) map.removeLayer(meMarker); if(meCircle) map.removeLayer(meCircle);
  if(!state.me) return;
  meMarker = L.circleMarker(state.me,{radius:7,color:"#1d4ed8",weight:3,fillColor:"#3b82f6",fillOpacity:.9}).addTo(map).bindPopup("Estás aquí");
  meCircle = L.circle(state.me,{radius:state.radio*1000,color:"#1d4ed8",weight:1,fillColor:"#3b82f6",fillOpacity:.06}).addTo(map);
}
const _g=document.getElementById("geoloc"); if(_g) _g.onclick = ()=>{
  const st=document.getElementById("geostat");
  if(state.me){ selRef.value=""; setRef(null); return; }
  if(!navigator.geolocation){ st.textContent="tu navegador no da ubicación"; return; }
  st.textContent="ubicando…";
  navigator.geolocation.getCurrentPosition(
    pos=>{ selRef.value=""; setRef(pos.coords.latitude, pos.coords.longitude, "mi ubicación"); document.getElementById("geoloc").textContent="📍 Quitar ubicación"; },
    err=>{ st.textContent = (err.code===1 ? "permiso denegado" : "no se pudo ubicar") + " — usa \"Desde\" o \"Elegir en el mapa\""; selRef.focus(); },
    {enableHighAccuracy:true, timeout:10000, maximumAge:60000});
};
const ftoggle = document.getElementById("ftoggle");
ftoggle.onclick = ()=>{ const f=document.getElementById("filters"); f.classList.toggle("collapsed"); ftoggle.textContent = f.classList.contains("collapsed") ? "Filtros ▾" : "Filtros ▴"; };
if(isMobile()){ document.getElementById("filters").classList.add("collapsed"); }
function toggleDet(id){ const e=document.getElementById("d-"+id); e.style.display = e.style.display==="none"?"":"none"; }
function selectRow(id, fromTable){
  document.querySelectorAll("tr.row.sel").forEach(r=>r.classList.remove("sel"));
  const r=document.getElementById("r-"+id); if(!r) return; r.classList.add("sel");
  if(!fromTable) r.scrollIntoView({block:"center",behavior:"smooth"});
  const ms = markersById[id]||[];
  if(!ms.length) return;
  const go = ()=>{ const b=L.latLngBounds(ms.map(m=>m.getLatLng())); if(ms.length===1){ map.setView(ms[0].getLatLng(), Math.max(map.getZoom(),16)); cluster.zoomToShowLayer(ms[0],()=>ms[0].openPopup()); } else map.fitBounds(b.pad(0.3)); };
  if(isMobile() && !document.body.classList.contains("view-map")){ document.body.classList.add("view-map"); document.getElementById("vt-list").classList.remove("on"); document.getElementById("vt-map").classList.add("on"); setTimeout(()=>{ map.invalidateSize(); go(); }, 80); }
  else go();
}
function showShot(id){
  const d = DATA.find(x=>x.id===id); if(!d) return;
  document.getElementById("m-title").textContent = d.comercio+" — "+d.banco;
  document.getElementById("m-ts").textContent = d.shot_ts? "captura "+d.shot_ts : "";
  document.getElementById("m-url").href = d.url;
  const img=document.getElementById("m-img"); img.src = d.shot||""; img.style.display = d.shot?"block":"none";
  document.getElementById("m-nota").textContent = d.shot? "Si la página del banco cambió después de esta fecha, la captura puede estar desactualizada: usa “Abrir en el banco”." : "No hay captura para este beneficio (correr scripts/screenshots.py).";
  document.getElementById("modal").style.display="flex";
}
document.getElementById("m-close").onclick=()=>document.getElementById("modal").style.display="none";
document.getElementById("modal").onclick=e=>{ if(e.target.id==="modal") e.target.style.display="none"; };
render();
if("serviceWorker" in navigator){ window.addEventListener("load", ()=>navigator.serviceWorker.register("../sw.js").catch(()=>{})); }
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
