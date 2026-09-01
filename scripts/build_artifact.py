"""Versión móvil/privada de la app para publicar como Artifact de claude.ai.

Uso:
    python scripts/build_artifact.py [--mes AAAA-MM] [--categoria restaurantes]

Diferencias con build_app.py: sin mapa ni capturas (claude.ai bloquea recursos externos),
layout de tarjetas (celular), filtro de día preseleccionado en "hoy", todo inline.
Salida: output/<mes>/descuentos_<cat>_<mes>_artifact.html
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from build_app import tarjetas_filtro, norm  # noqa: E402
from common import slug_id  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--categoria", default="restaurantes")
    ap.add_argument("--site", default="https://vpenaandes.github.io/descuentos-tarjetas/")
    a = ap.parse_args()
    outdir = os.path.join(ROOT, "output", a.mes)
    src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.geo.json")
    if not os.path.exists(src):
        src = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}.json")
    items = json.load(open(src, encoding="utf-8"))
    diff_path = os.path.join(outdir, f"cambios_{a.categoria}_{a.mes}.json")
    diff = json.load(open(diff_path, encoding="utf-8")) if os.path.exists(diff_path) else {"altas": [], "cambios": {}, "prev": None}
    data = []
    for idx, it in enumerate(items):
        it["id"] = slug_id(it["banco"], it.get("url"), it["comercio"])  # recalcular: los .geo.json viejos traen ids por índice
        ubic = [{"q": u.get("nombre") or u.get("consulta"), "lat": u.get("lat"), "lng": u.get("lng"),
                 "c": u.get("comuna"), "p": u.get("precision")} for u in (it.get("ubicaciones") or []) if u.get("lat")]
        data.append({"id": it["id"], "b": it["banco"], "n": it["comercio"], "d": it["descuento"], "t": it["tope"],
                     "dias": it["dias"], "h": it["horario"], "lug": it["lugares"], "tj": it["tarjetas"],
                     "tf": tarjetas_filtro(it), "mod": it["modalidad"], "reg": it["region"], "vig": it["vigencia"],
                     "cond": it["condiciones"], "url": it["url"], "com": it.get("comunas") or [], "ub": ubic,
                     "tipo": it.get("tipo", ""), "nuevo": it["id"] in set(diff.get("altas") or []),
                     "chg": (diff.get("cambios") or {}).get(it["id"]) or None})
    meta = {"mes": a.mes, "categoria": a.categoria, "generado": dt.date.today().isoformat(), "n": len(data),
            "bancos": sorted({d["b"] for d in data}), "tarjetas": sorted({t for d in data for t in d["tf"]}),
            "comunas": sorted({c for d in data for c in d["com"]}), "site": a.site,
            "prev": diff.get("prev"), "n_nuevos": sum(1 for d in data if d["nuevo"]), "n_chg": sum(1 for d in data if d["chg"])}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__META__", json.dumps(meta, ensure_ascii=False))
    dst = os.path.join(outdir, f"descuentos_{a.categoria}_{a.mes}_artifact.html")
    open(dst, "w", encoding="utf-8").write(html)
    print(f"OK {len(data)} items -> {dst} ({os.path.getsize(dst)//1024} KB)", file=sys.stderr)


TEMPLATE = r"""<title>Descuentos Restaurantes</title>
<meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@1,9..144,500&family=Manrope:wght@400;500;700&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
:root{
  --bg:#F6F8F5; --surface:#FFFFFF; --surface2:#EEF2EC; --ink:#1E2722; --muted:#5E6B64; --line:#D9E0DB;
  --accent:#2B5F8A; --accent-ink:#FFFFFF; --hl:#FFF4C7; --fal:#0E7A3B; --san:#EC0000;
  --ok:#1F7A4C; --ok-bg:#E3F3EA; --warn:#8A5A00; --warn-bg:#FFF0CC; --bad:#9B2C2C; --bad-bg:#FBE3E3;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#141917; --surface:#1C2320; --surface2:#242D29; --ink:#E6ECE8; --muted:#9AA8A0; --line:#2F3A35;
  --accent:#8DB6E3; --accent-ink:#0F1A24; --hl:#3A3418; --fal:#3FB46C; --san:#FF5A5A;
  --ok:#7FD1A3; --ok-bg:#16301F; --warn:#F2C46B; --warn-bg:#3A2E10; --bad:#F28B8B; --bad-bg:#3A1A1A;
}}
:root[data-theme="dark"]{
  --bg:#141917; --surface:#1C2320; --surface2:#242D29; --ink:#E6ECE8; --muted:#9AA8A0; --line:#2F3A35;
  --accent:#8DB6E3; --accent-ink:#0F1A24; --hl:#3A3418; --fal:#3FB46C; --san:#FF5A5A;
  --ok:#7FD1A3; --ok-bg:#16301F; --warn:#F2C46B; --warn-bg:#3A2E10; --bad:#F28B8B; --bad-bg:#3A1A1A;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Manrope,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:0 14px 60px}
header{padding:18px 0 6px}
header h1{font:italic 500 30px/1.1 Fraunces,Georgia,serif;margin:0;letter-spacing:-.01em;text-wrap:balance}
header h1 span{color:var(--muted);font-size:22px}
header p{margin:6px 0 0;color:var(--muted);font-size:13px}
#filters{position:sticky;top:0;z-index:10;background:var(--bg);padding:10px 0 8px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:8px}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);min-width:52px}
.chip{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 11px;font-size:13px;cursor:pointer;user-select:none;line-height:1.2}
.chip:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.chip.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent);font-weight:700}
.chip.fal.on{background:var(--fal);border-color:var(--fal);color:#fff}
.chip.san.on{background:var(--san);border-color:var(--san);color:#fff}
select,input[type=search]{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:10px;padding:7px 10px;font:inherit;font-size:14px;flex:1;min-width:140px}
.count{font-size:13px;color:var(--muted)}
.count b{color:var(--ink)}
.cards{display:flex;flex-direction:column;gap:10px;padding-top:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 14px;display:grid;grid-template-columns:1fr auto;gap:4px 12px}
.card.today{border-color:var(--accent)}
.name{font-weight:700;font-size:16px;grid-column:1}
.name a{color:inherit;text-decoration:none;border-bottom:1px dotted var(--muted)}
.bank{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:1px}
.bank.fal{background:var(--fal)}.bank.san{background:var(--san)}
.disc{grid-column:2;grid-row:1 / span 2;text-align:right;font-variant-numeric:tabular-nums}
.disc b{font-size:22px;display:block;line-height:1}
.disc small{color:var(--muted);font-size:12px}
.sub{color:var(--muted);font-size:12px;grid-column:1}
.tipo{grid-column:1 / -1;font-size:13px;color:var(--ink);opacity:.85;margin-top:2px}
.badge{font-size:10px;border-radius:5px;padding:1px 5px;margin-left:5px;font-weight:700;vertical-align:1px}
.badge.new{background:var(--ok-bg);color:var(--ok)}
.badge.chg{background:var(--warn-bg);color:var(--warn)}
.dist{font-size:11px;background:var(--surface2);border-radius:5px;padding:0 5px;margin-left:5px;font-variant-numeric:tabular-nums}
.days{display:flex;gap:3px;grid-column:1 / -1;margin-top:4px}
.d{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 0;width:30px;text-align:center;color:var(--muted)}
.d.on{background:var(--surface2);color:var(--ink);border-color:var(--ink);font-weight:700}
.d.hoy.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.lug{grid-column:1 / -1;margin:4px 0 0;padding:0;list-style:none;font-size:13px}
.lug li{padding:2px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:baseline}
.lug a{color:var(--accent);text-decoration:none;font-size:12px;white-space:nowrap}
.com{font-size:11px;background:var(--surface2);border-radius:5px;padding:0 6px;color:var(--muted)}
.tj{grid-column:1 / -1;font-size:12px;color:var(--muted)}
.acts{grid-column:1 / -1;display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.btn{border:1px solid var(--line);background:var(--surface2);color:var(--ink);border-radius:9px;padding:6px 11px;font:inherit;font-size:13px;cursor:pointer;text-decoration:none}
.btn.primary{background:var(--accent);color:var(--accent-ink);border-color:var(--accent);font-weight:700}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.cond{grid-column:1 / -1;display:none;margin-top:6px}
.cond.open{display:block}
.cond pre{white-space:pre-wrap;font:12px/1.5 "IBM Plex Mono",Consolas,monospace;background:var(--surface2);border-radius:10px;padding:10px;margin:0;max-height:340px;overflow:auto}
.cond .meta{font-size:12px;color:var(--muted);margin-bottom:4px}
.hor{grid-column:1 / -1;font-size:13px;color:var(--warn);background:var(--warn-bg);border-radius:8px;padding:3px 8px;margin-top:4px}
footer{margin-top:28px;font-size:12px;color:var(--muted);line-height:1.6}
footer a{color:var(--accent)}
.empty{padding:30px 10px;text-align:center;color:var(--muted)}
@media (prefers-reduced-motion:no-preference){ .card{transition:border-color .15s} }
</style>
<div class="wrap">
<header>
  <h1>Descuentos restaurantes <span id="mes"></span></h1>
  <p id="meta"></p>
</header>
<div id="filters">
  <div class="row"><span class="lbl">Día</span><span id="f-dia" class="row"></span></div>
  <div class="row"><span class="lbl">Banco</span><span id="f-banco" class="row"></span></div>
  <div class="row"><span class="lbl">Tarjeta</span><span id="f-tarj" class="row"></span></div>
  <div class="row"><span class="lbl">Comuna</span><select id="sel-com"><option value="">Todas las comunas…</option></select><span id="f-com" class="row"></span></div>
  <div class="row"><span class="lbl">Cerca</span><button class="chip" id="geoloc" type="button">📍 Cerca de mí</button>
    <select id="radio" style="flex:0 0 auto;min-width:90px"><option value="1">1 km</option><option value="3" selected>3 km</option><option value="5">5 km</option><option value="10">10 km</option></select>
    <span class="count" id="geostat"></span></div>
  <div class="row" id="f-flags"></div>
  <div class="row"><span class="lbl">Buscar</span><input type="search" id="q" placeholder="comercio, tipo, dirección…"><button class="chip" id="clear">Limpiar</button></div>
  <div class="count"><b id="count"></b> beneficios</div>
</div>
<div class="cards" id="cards"></div>
<footer>
  Fuente: páginas de beneficios de cada banco, capturadas el <span id="gen"></span>. "Verificar" abre la página exacta del restaurante en el banco; confirma días, tope y local ahí antes de ir.
  Versión completa con mapa y capturas: <a id="site" target="_blank"></a>.
</footer>
</div>
<script>
const DATA = __DATA__;
const META = __META__;
const DIAS = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"];
const HOY = DIAS[(new Date().getDay()+6)%7];
const bk = b => b==="Banco Falabella"?"fal":"san";
const esc = s => String(s??"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const normtxt = s => (s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
const gmaps = u => u.lat ? `https://www.google.com/maps/search/?api=1&query=${u.lat},${u.lng}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(u.q+", Chile")}`;
const state = {banco:new Set(), dia:new Set([HOY]), tarj:new Set(), com:new Set(), q:"", me:null, radio:3, soloNuevos:false, soloChg:false};
function haversine(a,b,c,d){ const t=x=>x*Math.PI/180; const s=Math.sin(t(c-a)/2)**2+Math.cos(t(a))*Math.cos(t(c))*Math.sin(t(d-b)/2)**2; return 2*6371*Math.asin(Math.sqrt(s)); }
function distOf(d){ if(!state.me||!d.ub.length) return null; let best=null; for(const u of d.ub){ const km=haversine(state.me[0],state.me[1],u.lat,u.lng); if(best===null||km<best) best=km; } return best; }
function fmtKm(km){ return km<1 ? Math.round(km*1000)+" m" : km.toFixed(1)+" km"; }

document.getElementById("mes").textContent = META.mes;
document.getElementById("meta").textContent = `${META.n} beneficios · ${META.bancos.map(b=>b.replace("Banco ","")).join(" + ")} · hoy es ${HOY.toLowerCase()}` + (META.prev?` · vs ${META.prev}: ${META.n_nuevos} nuevos`:"");
document.getElementById("gen").textContent = META.generado;
const siteA = document.getElementById("site"); siteA.href = META.site; siteA.textContent = META.site.replace(/^https?:\/\//,"");

function chip(parent,label,cls,on,onclick){ const c=document.createElement("button"); c.type="button"; c.className="chip "+(cls||"")+(on?" on":""); c.textContent=label; c.onclick=()=>onclick(c); parent.appendChild(c); return c; }
function toggle(set,v,c){ if(set.has(v)){set.delete(v);c.classList.remove("on");} else {set.add(v);c.classList.add("on");} render(); }
const fd=document.getElementById("f-dia");
DIAS.forEach(d=>chip(fd, d===HOY? "Hoy ("+d.slice(0,3)+")" : d.slice(0,3), "", state.dia.has(d), c=>toggle(state.dia,d,c)));
const fb=document.getElementById("f-banco");
META.bancos.forEach(b=>chip(fb,b.replace("Banco ",""),bk(b),false,c=>toggle(state.banco,b,c)));
const ft=document.getElementById("f-tarj");
META.tarjetas.forEach(t=>chip(ft,t,"",false,c=>toggle(state.tarj,t,c)));
const sc=document.getElementById("sel-com");
META.comunas.concat(["(sin comuna: cadena / online)"]).forEach(c=>{const o=document.createElement("option");o.value=c;o.textContent=c;sc.appendChild(o);});
sc.onchange=()=>{ if(sc.value){ const c=sc.value; sc.value=""; if(state.com.has(c)) return; state.com.add(c); chip(document.getElementById("f-com"),c+" ✕","",true,x=>{state.com.delete(c);x.remove();render();}); render(); } };
document.getElementById("q").oninput=e=>{state.q=normtxt(e.target.value);render();};
const ff=document.getElementById("f-flags");
if(META.n_nuevos) chip(ff, `✨ Nuevos (${META.n_nuevos})`, "", false, c=>{ state.soloNuevos=!state.soloNuevos; c.classList.toggle("on"); render(); });
if(META.n_chg) chip(ff, `⚠ Cambió (${META.n_chg})`, "", false, c=>{ state.soloChg=!state.soloChg; c.classList.toggle("on"); render(); });
document.getElementById("radio").onchange=e=>{ state.radio=+e.target.value; if(state.me) render(); };
document.getElementById("geoloc").onclick=function(){
  const st=document.getElementById("geostat"), btn=this;
  if(state.me){ state.me=null; st.textContent=""; btn.textContent="📍 Cerca de mí"; btn.classList.remove("on"); render(); return; }
  if(!navigator.geolocation){ st.textContent="sin geolocalización"; return; }
  st.textContent="ubicando…";
  navigator.geolocation.getCurrentPosition(
    pos=>{ state.me=[pos.coords.latitude,pos.coords.longitude]; st.textContent="ordenado por cercanía"; btn.textContent="📍 Quitar"; btn.classList.add("on"); render(); },
    err=>{ st.textContent = err.code===1?"permiso denegado":"no se pudo ubicar"; },
    {enableHighAccuracy:true,timeout:10000,maximumAge:60000});
};
document.getElementById("clear").onclick=()=>{ state.banco.clear();state.dia.clear();state.tarj.clear();state.com.clear();state.q="";state.soloNuevos=false;state.soloChg=false; document.querySelectorAll(".chip.on").forEach(c=>c.classList.remove("on")); document.getElementById("f-com").innerHTML=""; document.getElementById("q").value=""; render(); };

function pass(d){
  if(state.banco.size && !state.banco.has(d.b)) return false;
  if(state.dia.size && ![...state.dia].some(x=>d.dias.includes(x))) return false;
  if(state.tarj.size && ![...state.tarj].some(x=>d.tf.includes(x))) return false;
  if(state.com.size){ const sin = state.com.has("(sin comuna: cadena / online)") && d.com.length===0; if(!sin && ![...state.com].some(x=>d.com.includes(x))) return false; }
  if(state.q){ const hay=normtxt([d.n,d.tipo,d.b,d.d,d.t,d.h,d.lug.join(" "),d.tj.join(" "),d.cond,d.com.join(" ")].join(" ")); if(!hay.includes(state.q)) return false; }
  if(state.soloNuevos && !d.nuevo) return false;
  if(state.soloChg && !d.chg) return false;
  if(state.me){ const km=distOf(d); if(km===null || km>state.radio) return false; }
  return true;
}
function card(d){
  const days=DIAS.map(x=>`<span class="d ${d.dias.includes(x)?"on":""} ${x===HOY?"hoy":""}">${x.slice(0,2)}</span>`).join("");
  const lug=d.lug.length? `<ul class="lug">${d.lug.map((l,i)=>{const u=d.ub.find(u=>normtxt(l).includes(normtxt(u.q))||normtxt(u.q).includes(normtxt(l).split(":")[0]))||{q:l}; return `<li>${esc(l)} <a href="${gmaps(u)}" target="_blank" rel="noopener">Maps ↗</a></li>`;}).join("")}</ul>` : `<div class="sub">Lugar no publicado — ver condiciones</div>`;
  const coms=d.com.length? `<div class="tj">${d.com.map(c=>`<span class="com">${esc(c)}</span>`).join(" ")}</div>`:"";
  return `<article class="card ${d.dias.includes(HOY)?"today":""}">
    <div class="name"><span class="bank ${bk(d.b)}"></span><a href="${d.url}" target="_blank" rel="noopener">${esc(d.n)}</a>${d.nuevo?'<span class="badge new">NUEVO</span>':""}${d.chg?'<span class="badge chg">CAMBIÓ</span>':""}</div>
    <div class="disc"><b>${esc(d.d.split(" (")[0])}</b><small>tope ${esc(d.t||"—")}</small></div>
    <div class="sub">${esc(d.b)} · ${esc(d.mod||"")}${d.reg?" · "+esc(d.reg):""}${(()=>{const k=distOf(d);return k===null?"":`<span class="dist">${fmtKm(k)}</span>`;})()}</div>
    ${d.tipo?`<div class="tipo">${esc(d.tipo)}</div>`:""}
    <div class="days">${days}</div>
    ${d.h?`<div class="hor">⏱ ${esc(d.h)}</div>`:""}
    ${lug}${coms}
    <div class="tj">Tarjetas: ${esc(d.tf.join(", "))}</div>
    <div class="acts"><a class="btn primary" href="${d.url}" target="_blank" rel="noopener">Verificar en ${esc(d.b.replace("Banco ",""))} ↗</a><button class="btn" type="button" onclick="this.closest('.card').querySelector('.cond').classList.toggle('open')">Condiciones</button></div>
    <div class="cond"><div class="meta">${d.chg?`Cambios vs ${esc(META.prev||"")}: ${Object.entries(d.chg).map(([k,v])=>`<b>${esc(k)}</b> ${esc(v.antes||"—")} → ${esc(v.ahora||"—")}`).join(" · ")}<br>`:""}Vigencia: ${esc(d.vig||"—")} · Descuento completo: ${esc(d.d)}</div><pre>${esc(d.cond||"(sin texto)")}</pre></div>
  </article>`;
}
function render(){
  let cur=DATA.filter(pass);
  cur = state.me ? cur.sort((a,b)=>(distOf(a)??1e9)-(distOf(b)??1e9)) : cur.sort((a,b)=>a.n.localeCompare(b.n,"es"));
  document.getElementById("count").textContent=cur.length;
  document.getElementById("cards").innerHTML = cur.length? cur.map(card).join("") : `<div class="empty">Nada con esos filtros. Prueba otro día o quita la comuna.</div>`;
}
render();
</script>
"""

if __name__ == "__main__":
    main()
