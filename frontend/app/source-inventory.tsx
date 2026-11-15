const sources = [
  { name: 'Agua y cuencas', description: 'Landsat y JRC permiten contrastar la superficie de los lagos. MapBiomas Agua distingue agua natural y artificial. HydroBASINS delimita la cuenca de aporte.',
    links: [['MapBiomas Bolivia', 'https://bolivia.mapbiomas.org/'], ['HydroBASINS', 'https://www.hydrosheds.org/products/hydrobasins']] },
  { name: 'Clima', description: 'NASA POWER y CHIRPS aportan series históricas y NOAA aporta el índice ONI. El contraste de GPM, CHIRPS y ERA5-Land requiere Earth Engine.',
    links: [['NASA POWER', 'https://power.larc.nasa.gov/docs/services/api/'], ['Catálogo Earth Engine', 'https://developers.google.com/earth-engine/datasets/catalog']] },
  { name: 'Vegetación y actividad humana', description: 'El atlas provincial usa la lluvia y el verdor del archivo de vegetacion-agua. Hansen y MapBiomas registran cambios de bosque y uso del suelo. WorldPop y VIIRS añaden señales de actividad humana.',
    links: [['Hansen GFC', 'https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13'], ['WorldPop', 'https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop']] },
  { name: 'Incendios y observaciones recientes', description: 'El archivo MODIS muestra focos históricos. FIRMS requiere clave para consultar detecciones recientes. En las fichas, CMR busca archivos de HLS, OPERA, GPM, SWOT, MODIS, VIIRS, AIRS, OMI y SMAP, además de GLDAS y MERRA-2.',
    links: [['NASA FIRMS', 'https://firms.modaps.eosdis.nasa.gov/api/'], ['NASA Earthdata', 'https://search.earthdata.nasa.gov/']] },
] as const;

export function SourceInventory() {
  return <section id="fuentes-observatorio" className="source-inventory" tabIndex={-1} aria-labelledby="sources-title">
    <div className="mission-section-heading"><h2 id="sources-title">Fuentes y cobertura</h2>
      <p>El mapa, las gráficas y las fichas muestran qué fuente se utilizó y a qué fecha corresponde cada dato.</p></div>
    <div className="source-grid">{sources.map(({ name, description, links }) => <article className="panel" key={name}>
      <h3>{name}</h3><p>{description}</p>
      <div>{links.map(([label, href]) => <a key={label} href={href} target="_blank" rel="noreferrer">{label}</a>)}</div>
    </article>)}</div>
    <details className="panel detail-method">
      <summary>Recursos para ampliar el análisis</summary>
      <p>El inventario también propone visores, servicios de extracción, escenarios climáticos y fuentes locales para contrastar datos. Estos recursos todavía no generan alertas en el observatorio.</p>
      <div className="source-resource-links">
        {[
          ['Giovanni', 'https://giovanni.gsfc.nasa.gov/giovanni/'], ['Hydrology Time Series y GES DISC', 'https://disc.gsfc.nasa.gov/'],
          ['AppEEARS', 'https://appeears.earthdatacloud.nasa.gov/'], ['Clima histórico NOAA', 'https://www.ncei.noaa.gov/cdo-web/'],
          ['NASA Worldview', 'https://worldview.earthdata.nasa.gov/'], ['KNMI Climate Explorer', 'https://climexp.knmi.nl/'],
          ['Amazon Mining Watch', 'https://www.amazonminingwatch.org/'], ['Escenarios NEX-GDDP-CMIP6', 'https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6'],
          ['Radar RADARSAT (CSA)', 'https://www.asc-csa.gc.ca/eng/satellites/radarsat/faq.asp'],
        ].map(([label, href]) => <a key={label} href={href} target="_blank" rel="noreferrer">{label}</a>)}
      </div>
    </details>
  </section>;
}
