import * as maplibregl from "maplibre-gl";
import { MapMouseEvent, NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useMemo, useRef, useState } from "react";
import { fmt } from "./model";

maplibregl.setWorkerUrl(workerUrl);

type Municipality = {
  codigo: string;
  municipio: string;
  poblacion: number;
  mayores65: number;
  mayores80: number;
  pct65: number | null;
  centrosMayores: number;
  centrosSalud: number;
  farmacias: number;
  mayoresPorCentroSalud: number | null;
  mayoresPorCentroMayores: number | null;
  horas35: number;
  estacionCalor: string;
  estacionPropia: boolean;
  indice: number | null;
  puesto: number;
};

type Collection = {
  type: "FeatureCollection";
  metadata: Record<string, string>;
  features: { type: "Feature"; properties: Municipality; geometry: unknown }[];
};

type Totals = {
  muestra: number;
  evaluables: number;
  pct_supera_limite: number;
  pct_se_arregla: number;
  pct_sin_alternativa: number;
};

type Impact = {
  principal: {
    limite_m: number;
    total: Totals;
    distritos: Record<
      string,
      {
        pct_mayores65: number;
        evaluables: number;
        pct_supera_limite: number;
        pct_supera_limite_ponderado_mayores: number;
        pct_se_arregla: number;
        pct_sin_alternativa: number;
        desvio_mediano_m: number | null;
      }
    >;
  };
  sensibilidad: Record<string, Totals>;
};

const indicators = {
  indice: { label: "Índice de prioridad", unit: "/100", digits: 1 },
  pct65: { label: "% de 65 años o más", unit: "%", digits: 1 },
  mayoresPorCentroSalud: {
    label: "Mayores por centro de salud",
    unit: "",
    digits: 0,
  },
  horas35: { label: "Horas ≥ 35 °C en 2025", unit: " h", digits: 0 },
} as const;
type Indicator = keyof typeof indicators;

const palette = ["#f3efe0", "#f1d39a", "#e7a25a", "#cf6a33", "#9e3b1f"];

const pct = (value: number) =>
  value.toLocaleString("es-ES", { maximumFractionDigits: 1 }) + " %";

function quantiles(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  return [0.2, 0.4, 0.6, 0.8].map(
    (q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))],
  );
}

function value(m: Municipality, key: Indicator) {
  const v = m[key];
  return typeof v === "number" ? v : null;
}

export default function Region() {
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [data, setData] = useState<Collection | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [indicator, setIndicator] = useState<Indicator>("indice");
  const [selected, setSelected] = useState<Municipality | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch("/municipios.geojson")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setFailed(true));
    fetch("/impacto.json")
      .then((r) => (r.ok ? r.json() : null))
      .then(setImpact)
      .catch(() => setImpact(null));
  }, []);

  const breaks = useMemo(() => {
    if (!data) return [];
    return quantiles(
      data.features
        .map((f) => value(f.properties, indicator))
        .filter((v): v is number => v !== null),
    );
  }, [data, indicator]);

  useEffect(() => {
    if (!data || !host.current || map.current) return;
    const m = new maplibregl.Map({
      container: host.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [-3.72, 40.5],
      zoom: 7.9,
    });
    map.current = m;
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("municipios", { type: "geojson", data: data as never });
      m.addLayer({
        id: "municipios",
        type: "fill",
        source: "municipios",
        paint: { "fill-color": palette[2], "fill-opacity": 0.78 },
      });
      m.addLayer({
        id: "bordes",
        type: "line",
        source: "municipios",
        paint: { "line-color": "#ffffff", "line-width": 0.6 },
      });
      m.addLayer({
        id: "seleccion",
        type: "line",
        source: "municipios",
        paint: { "line-color": "#193e34", "line-width": 2.5 },
        filter: ["==", ["get", "codigo"], ""],
      });
      m.on(
        "click",
        "municipios",
        (e: MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
        const p = e.features?.[0]?.properties as Municipality | undefined;
        if (p) {
          const full = data.features.find(
            (f) => f.properties.codigo === p.codigo,
          );
          setSelected(full ? full.properties : p);
        }
        },
      );
      m.on("mouseenter", "municipios", () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", "municipios", () => {
        m.getCanvas().style.cursor = "";
      });
      paint(m, indicator, breaks);
    });
    return () => {
      m.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  useEffect(() => {
    const m = map.current;
    if (m && m.isStyleLoaded() && m.getLayer("municipios"))
      paint(m, indicator, breaks);
  }, [indicator, breaks]);

  useEffect(() => {
    const m = map.current;
    if (m && m.getLayer("seleccion"))
      m.setFilter("seleccion", [
        "==",
        ["get", "codigo"],
        selected?.codigo || "",
      ]);
  }, [selected]);

  const ranking = useMemo(
    () =>
      data
        ? [...data.features]
            .map((f) => f.properties)
            .sort((a, b) => a.puesto - b.puesto)
        : [],
    [data],
  );
  const totals = useMemo(() => {
    if (!data) return null;
    const all = data.features.map((f) => f.properties);
    return {
      municipios: all.length,
      poblacion: all.reduce((s, m) => s + m.poblacion, 0),
      mayores: all.reduce((s, m) => s + m.mayores65, 0),
      centrosMayores: all.reduce((s, m) => s + m.centrosMayores, 0),
      centrosSalud: all.reduce((s, m) => s + m.centrosSalud, 0),
      farmacias: all.reduce((s, m) => s + m.farmacias, 0),
    };
  }, [data]);
  const spec = indicators[indicator];
  const show = (m: Municipality, key: Indicator) => {
    const v = value(m, key);
    return v === null
      ? "Sin dato"
      : v.toLocaleString("es-ES", {
          maximumFractionDigits: indicators[key].digits,
        }) + indicators[key].unit;
  };
  const principal = impact?.principal;

  return (
    <main className="region">
      <div className="page-intro">
        <div>
          <p className="kicker">COMUNIDAD DE MADRID · 179 MUNICIPIOS</p>
          <h1>Dónde hace falta llegar al fresco</h1>
          <p>
            Envejecimiento, servicios cercanos y calor, municipio a municipio,
            solo con datos abiertos de la Comunidad de Madrid. Sirve para
            decidir dónde llevar la herramienta después del piloto en la
            capital.
          </p>
        </div>
      </div>

      {principal && (
        <section className="impact" aria-label="Cifra de impacto">
          <div className="impact-lead">
            <p className="kicker">PILOTO · MADRID CAPITAL</p>
            <p className="impact-figure">
              {pct(principal.total.pct_supera_limite)}
            </p>
            <p>
              de los trayectos hasta el centro de salud más cercano obligan a
              caminar <strong>más de {principal.limite_m} m seguidos</strong>{" "}
              sin un banco por el camino directo.
            </p>
          </div>
          <div className="metrics impact-metrics">
            <div>
              <span>Se resuelve con un rodeo</span>
              <strong>{pct(principal.total.pct_se_arregla)}</strong>
            </div>
            <div>
              <span>No hay ninguna ruta que lo permita</span>
              <strong>{pct(principal.total.pct_sin_alternativa)}</strong>
            </div>
            <div>
              <span>Trayectos calculados</span>
              <strong>{fmt(principal.total.evaluables)}</strong>
              <small>21 distritos · muestra aleatoria con semilla fija</small>
            </div>
          </div>
          <p className="impact-note">
            Sensibilidad:{" "}
            {Object.entries(impact!.sensibilidad)
              .map(
                ([limit, t]) =>
                  `${limit} m → ${pct(t.pct_supera_limite)} sin cumplir, ${pct(t.pct_sin_alternativa)} sin alternativa`,
              )
              .join(" · ")}
            . Cuenta solo bancos municipales inventariados. Destino: registro
            de centros sanitarios de la Comunidad de Madrid.
          </p>
        </section>
      )}

      {failed && (
        <p className="notice">
          No se ha podido cargar la capa regional. Ejecuta{" "}
          <code>python -m ciudad.municipios</code> y recompila la web.
        </p>
      )}

      <div className="workspace region-workspace">
        <section className="planner" aria-label="Indicadores regionales">
          <h2>Indicador del mapa</h2>
          <div className="indicator-list" role="radiogroup">
            {(Object.keys(indicators) as Indicator[]).map((key) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={indicator === key}
                className="route-option"
                aria-pressed={indicator === key}
                onClick={() => setIndicator(key)}
              >
                <strong>{indicators[key].label}</strong>
              </button>
            ))}
          </div>
          <div className="region-legend" aria-label={`Leyenda: ${spec.label}`}>
            {palette.map((color, i) => (
              <span key={color}>
                <i style={{ background: color }} />
                {i === 0
                  ? `< ${fmtBreak(breaks[0], spec.digits)}`
                  : i === palette.length - 1
                    ? `≥ ${fmtBreak(breaks[i - 1], spec.digits)}`
                    : `${fmtBreak(breaks[i - 1], spec.digits)}–${fmtBreak(breaks[i], spec.digits)}`}
              </span>
            ))}
          </div>
          {selected ? (
            <div className="municipality">
              <p className="kicker">PUESTO {selected.puesto} DE 179</p>
              <h3>{selected.municipio}</h3>
              <dl>
                <dt>Índice de prioridad</dt>
                <dd>{show(selected, "indice")}</dd>
                <dt>Población (2025)</dt>
                <dd>{fmt(selected.poblacion)}</dd>
                <dt>65 años o más</dt>
                <dd>
                  {fmt(selected.mayores65)} · {show(selected, "pct65")}
                </dd>
                <dt>80 años o más</dt>
                <dd>{fmt(selected.mayores80)}</dd>
                <dt>Centros de salud y consultorios</dt>
                <dd>
                  {selected.centrosSalud}
                  {selected.mayoresPorCentroSalud
                    ? ` · ${fmt(selected.mayoresPorCentroSalud)} mayores por centro`
                    : ""}
                </dd>
                <dt>Centros para mayores</dt>
                <dd>{selected.centrosMayores}</dd>
                <dt>Farmacias</dt>
                <dd>{selected.farmacias}</dd>
                <dt>Horas ≥ 35 °C (2025)</dt>
                <dd>
                  {selected.horas35} h · estación de{" "}
                  {selected.estacionCalor}
                  {selected.estacionPropia ? "" : " (la más cercana)"}
                </dd>
              </dl>
            </div>
          ) : (
            <p className="hint">
              Pulsa un municipio en el mapa para ver su ficha.
            </p>
          )}
        </section>
        <div className="map-wrap region-map">
          <div ref={host} className="map" aria-label="Mapa de municipios" />
        </div>
      </div>

      {totals && (
        <section className="metrics region-totals" aria-label="Totales">
          <div>
            <span>Personas de 65 años o más</span>
            <strong>{fmt(totals.mayores)}</strong>
            <small>de {fmt(totals.poblacion)} residentes</small>
          </div>
          <div>
            <span>Centros de salud y consultorios</span>
            <strong>{fmt(totals.centrosSalud)}</strong>
          </div>
          <div>
            <span>Centros para mayores · farmacias</span>
            <strong>
              {fmt(totals.centrosMayores)} · {fmt(totals.farmacias)}
            </strong>
          </div>
        </section>
      )}

      <section className="results study region-table">
        <h2>Los 15 municipios con mayor prioridad</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Puesto</th>
                <th>Municipio</th>
                <th>Índice</th>
                <th>% 65+</th>
                <th>Mayores</th>
                <th>Mayores por centro de salud</th>
                <th>Centros para mayores</th>
                <th>Horas ≥ 35 °C</th>
              </tr>
            </thead>
            <tbody>
              {ranking.slice(0, 15).map((m) => (
                <tr key={m.codigo}>
                  <td>{m.puesto}</td>
                  <td>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setSelected(m)}
                    >
                      {m.municipio}
                    </button>
                  </td>
                  <td>{show(m, "indice")}</td>
                  <td>{show(m, "pct65")}</td>
                  <td>{fmt(m.mayores65)}</td>
                  <td>{show(m, "mayoresPorCentroSalud")}</td>
                  <td>{m.centrosMayores}</td>
                  <td>{m.horas35}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {principal && (
        <section className="results study region-table">
          <h2>Piloto en Madrid capital, por distrito</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Distrito</th>
                  <th>% 65+</th>
                  <th>Sin cumplir por el camino directo</th>
                  <th>Ponderado por mayores</th>
                  <th>Se arregla con rodeo</th>
                  <th>Sin alternativa</th>
                  <th>Rodeo mediano</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(principal.distritos)
                  .sort((a, b) => b[1].pct_supera_limite - a[1].pct_supera_limite)
                  .map(([name, d]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{pct(d.pct_mayores65)}</td>
                      <td>{pct(d.pct_supera_limite)}</td>
                      <td>{pct(d.pct_supera_limite_ponderado_mayores)}</td>
                      <td>{pct(d.pct_se_arregla)}</td>
                      <td>{pct(d.pct_sin_alternativa)}</td>
                      <td>
                        {d.desvio_mediano_m === null
                          ? "—"
                          : `${d.desvio_mediano_m} m`}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="source-panel">
        <h2>Cómo se calcula</h2>
        <p>
          El índice es la media de cuatro percentiles: porcentaje de 65 años o
          más, mayores por centro de salud, mayores por centro para mayores y
          horas a 35 °C o más en la estación regional más cercana. Son
          indicadores municipales agregados para priorizar, no diagnósticos
          individuales. Las horas de calor de los municipios sin estación
          propia se toman de la estación de la red regional más próxima.
        </p>
        <ul>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/poblacion_censada_por_edad_nacionalidad_y_sexo"
              target="_blank"
              rel="noreferrer"
            >
              Población censada por edad, nacionalidad y sexo
            </a>
            <span>{data?.metadata.poblacion}</span>
          </li>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/grado_envejecimiento_por_edad"
              target="_blank"
              rel="noreferrer"
            >
              Grado de envejecimiento por grupo de edad
            </a>
            <span>{data?.metadata.envejecimiento}</span>
          </li>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/centros_servicios_sociales_por_tipo"
              target="_blank"
              rel="noreferrer"
            >
              Centros de servicios sociales por tipo
            </a>
            <span>{data?.metadata.centrosSociales}</span>
          </li>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/centros_servicios_establecimientos_sanitarios"
              target="_blank"
              rel="noreferrer"
            >
              Centros, servicios y establecimientos sanitarios
            </a>
            <span>Registro vigente</span>
          </li>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/oficinas_farmacia"
              target="_blank"
              rel="noreferrer"
            >
              Oficinas de farmacia
            </a>
            <span>Registro vigente</span>
          </li>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/calidad_aire_datos_meteo_historico"
              target="_blank"
              rel="noreferrer"
            >
              Red de Calidad del Aire · datos meteorológicos horarios
            </a>
            <span>2025</span>
          </li>
          <li>
            <a
              href="https://datos.comunidad.madrid/dataset/secciones_censales"
              target="_blank"
              rel="noreferrer"
            >
              Secciones censales (geometría municipal)
            </a>
            <span>2019</span>
          </li>
        </ul>
      </section>
    </main>
  );
}

function fmtBreak(value: number | undefined, digits: number) {
  return value === undefined
    ? "—"
    : value.toLocaleString("es-ES", { maximumFractionDigits: digits });
}

function paint(m: maplibregl.Map, key: Indicator, breaks: number[]) {
  if (breaks.length < 4) return;
  m.setPaintProperty("municipios", "fill-color", [
    "case",
    ["==", ["typeof", ["get", key]], "number"],
    [
      "step",
      ["get", key],
      palette[0],
      breaks[0],
      palette[1],
      breaks[1],
      palette[2],
      breaks[2],
      palette[3],
      breaks[3],
      palette[4],
    ],
    "#d9ddd6",
  ]);
}
