// Santander: la API JSON está detrás de Akamai Bot Manager (curl/urllib -> 403).
// Hay que ejecutar este snippet DENTRO de un navegador que ya cargó
// https://banco.santander.cl/beneficios/descuentos-restaurantes
// (navegador integrado de Claude Code vía javascript_tool, o DevTools > Console).
//
// Tags de categoría conocidos (parámetro `tags=`):
//   cat-sabores      -> restaurantes / gastronomía (es el que usa la landing)
//   (otros posibles: cat-descuentos, cat-musica, cat-multiplica-millas ...)
//
// Devuelve un objeto {status, n, promos:[...]} ya aplanado. Guardar el
// resultado como JSON y pasarlo a scripts/process_santander.py.

(async () => {
  const TAG = 'cat-sabores';
  const r = await fetch(
    `/beneficios/promociones.json?per_page=9999&tags=${TAG}&custom_fields=true&order_by=updated_at&desc=true`,
    { credentials: 'include' }
  );
  const j = await r.json();
  const promos = j.promociones || [];
  const strip = (h) =>
    (h || '')
      .replace(/<li>/g, '\n- ')
      .replace(/<\/p>|<br\s*\/?>/g, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/\n{2,}/g, '\n')
      .trim();
  const out = promos.map((p) => {
    const cf = {};
    for (const [k, v] of Object.entries(p.custom_fields || {})) cf[k] = v && v.value;
    return {
      id: p.id,
      title: p.title,
      slug: p.slug,
      url: p.url,
      bajada: cf['Bajada externa'],
      vigencia: cf['Vigencia'],
      region_cf: cf['Región cobertura'],
      comuna_cf: cf['Comuna cobertura'],
      sitio: cf['Sitio web beneficio'],
      tags: p.tags,
      description: strip(p.description),
      start_date: p.start_date,
      end_date: p.end_date,
      discount: p.discount,
      location_street: p.location_street,
      lat: p.latitude,
      lng: p.longitude,
      published_at: p.published_at,
      updated_at: p.updated_at,
    };
  });
  return { status: r.status, n: promos.length, tag: TAG, promos: out };
})();
