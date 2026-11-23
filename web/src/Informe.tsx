import * as maplibregl from "maplibre-gl";
import { NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef, useState } from "react";
import { api, fmt, Position } from "./model";

maplibregl.setWorkerUrl(workerUrl);

type Hueco = {
  coordinates: Position;
  calle: string;
  consultas: number;
  sinAlternativa: number;
  rodeoTotalM: number;
  huecoMedianoM: number;
  destinos: Record<string, number>;
};
type Zona = { calle: string; consultas: number; coordinates: Position; huecoMedianoM: number };
type Report = {
  consultas: number;
  periodo: [string, string] | null;
  cumplen: number;
  conRodeo: number;
  sinAlternativa: number;
  rodeoTotalM: number;
  rodeoMedianoM: number | null;
  limites: Record<string, number>;
  destinos: Record<string, number>;
  horas: Record<string, number>;
  huecos: Hueco[];
  zonasSinBancos: Zona[];
  huecoLargoM: number;
  huecosOcultos: number;
  minimoConsultas: number;
  demo: boolean;
  hayDemo: boolean;
};

const DEST: Record<string, string> = {
  salud: "Centro de salud",
  farmacia: "Farmacia",
  mayores: "Centro de mayores",
  biblioteca: "Biblioteca",
  direccion: "Otra dirección",
};
const pct = (part: number, total: number) =>
  total ? (100 * part / total).toLocaleString("es-ES", { maximumFractionDigits: 1 }) + " %" : "—";

function Bars({ data, label }: { data: Record<string, number>; label: (k: string) => string }) {
  const max = Math.max(1, ...Object.values(data));
  return (
    <ul className="barras">
      {Object.entries(data).map(([key, value]) => (
        <li key={key}>
          <span>{label(key)}</span>
          <i style={{ width: `${(100 * value) / max}%` }} />
          <b>{fmt(value)}</b>
        </li>
      ))}
    </ul>
  );
}

export default function Informe({
  onSimulate,
}: {
  onSimulate: (at?: Position, destino?: string) => void;
}) {
  const [demo, setDemo] = useState<boolean | null>(null);
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const hasData = data !== null;

  useEffect(() => {
    const load = async () => {
      try {
        let wanted = demo;
        if (wanted === null) {
          const real = await api<Report>("/api/informe");
          wanted = real.consultas < 50 && real.hayDemo;
          if (!wanted) {
            setData(real);
            setDemo(false);
            return;
          }
          setDemo(true);
          return;
        }
        setData(await api<Report>(`/api/informe?demo=${wanted ? "true" : "false"}`));
        setError("");
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void load();
  }, [demo]);

  useEffect(() => {
    if (!host.current || map.current) return;
    const m = new maplibregl.Map({
      container: host.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [-3.69, 40.42],
      zoom: 10.6,
    });
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.current = m;
    m.on("load", () => {
      m.addSource("huecos", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({
        id: "huecos",
        type: "circle",
        source: "huecos",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "consultas"], 3, 6, 20, 18],
          "circle-color": ["case", [">", ["get", "bloqueadas"], ["/", ["get", "consultas"], 2]], "#b8592a", "#cf8b23"],
          "circle-opacity": 0.85,
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2,
        },
      });
      m.on("click", "huecos", (e) => {
        const p = e.features?.[0]?.properties;
        if (p)
          new maplibregl.Popup()
            .setLngLat(e.lngLat)
            .setText(`${p.calle || "Tramo sin nombre"} · ${p.consultas} consultas sin banco`)
            .addTo(m);
      });
    });
    return () => {
      m.remove();
      map.current = null;
    };
  }, [hasData]);

  useEffect(() => {
    const m = map.current;
    if (!m || !data) return;
    const apply = () => {
      const source = m.getSource("huecos") as maplibregl.GeoJSONSource | undefined;
      if (!source) return;
      source.setData({
        type: "FeatureCollection",
        features: data.huecos.map((h) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: h.coordinates },
          properties: { calle: h.calle, consultas: h.consultas, bloqueadas: h.sinAlternativa },
        })),
      });
      if (data.huecos.length) {
        const b = new maplibregl.LngLatBounds(data.huecos[0].coordinates, data.huecos[0].coordinates);
        data.huecos.forEach((h) => b.extend(h.coordinates));
        m.fitBounds(b, { padding: 50, maxZoom: 14, duration: 300 });
      }
    };
    if (m.isStyleLoaded() && m.getSource("huecos")) apply();
    else m.once("idle", apply);
  }, [data, hasData]);

  const focus = (coordinates: Position) => {
    map.current?.flyTo({ center: coordinates, zoom: 16.5 });
    host.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <main className="informe">
      <div className="page-intro">
        <div>
          <p className="kicker">PARA AYUNTAMIENTOS · INFORME DE USO</p>
          <h1>Dónde falta un banco, según la gente</h1>
          <p>
            Cada vez que alguien busca una ruta guardamos, de forma anónima, en qué tramos del
            camino directo le faltó un banco. Este informe junta esas consultas y señala los
            <strong> bancos estratégicos</strong>: los que evitarían más rodeos.
          </p>
        </div>
      </div>

      {data?.hayDemo && (
        <div className="fuente-datos" role="group" aria-label="Origen de los datos">
          <button type="button" className="opcion" aria-pressed={demo === false} onClick={() => setDemo(false)}>
            Consultas reales
          </button>
          <button type="button" className="opcion" aria-pressed={demo === true} onClick={() => setDemo(true)}>
            Demostración (simulación)
          </button>
        </div>
      )}
      {demo && (
        <p className="aviso">
          <strong>Datos de demostración.</strong> Simulación de 3.096 consultas: portales aleatorios de
          los 21 distritos hacia el centro de salud, farmacia, centro de mayores o biblioteca más
          cercano, con límites sin descanso variados, verano de 2025. Con usuarios reales, el
          informe se construye solo.
        </p>
      )}
      {error && <p className="notice">{error}</p>}

      {data && (
        <>
          <section className="metrics informe-kpis" aria-label="Resumen">
            <div>
              <span>Consultas</span>
              <strong>{fmt(data.consultas)}</strong>
              <small>{data.periodo ? `del ${data.periodo[0]} al ${data.periodo[1]}` : "sin datos todavía"}</small>
            </div>
            <div>
              <span>Tuvieron que dar un rodeo</span>
              <strong>{pct(data.conRodeo, data.consultas)}</strong>
              <small>{data.rodeoMedianoM ? `rodeo mediano ${fmt(data.rodeoMedianoM)} m` : ""}</small>
            </div>
            <div>
              <span>Sin ninguna ruta con bancos</span>
              <strong>{pct(data.sinAlternativa, data.consultas)}</strong>
              <small>no existe camino que cumpla su límite</small>
            </div>
            <div>
              <span>Metros de rodeo acumulados</span>
              <strong>{fmt(Math.round(data.rodeoTotalM / 100) / 10)} km</strong>
              <small>caminados de más por falta de un banco</small>
            </div>
          </section>

          <div className="informe-mapa">
            <div ref={host} className="map" role="region" aria-label="Mapa de bancos estratégicos" />
          </div>
          <p className="leyenda-informe">
            <span><i className="dot mid" /> Banco que ahorra rodeos</span>
            <span><i className="dot bad" /> Banco que haría posible una ruta que hoy no existe</span>
            <span>El tamaño indica cuántas consultas pasan por ahí.</span>
          </p>

          <section className="results study">
            <div className="section-title">
              <h2>Bancos estratégicos</h2>
              <a className="secondary boton-enlace" href={`/api/informe.csv?demo=${demo ? "true" : "false"}`}>
                Descargar CSV
              </a>
            </div>
            <p className="form-note">
              Puntos del camino directo donde un banco evitaría superar el límite de descanso que la
              gente eligió. Solo se muestran los que se repiten en {data.minimoConsultas} consultas o más
              ({fmt(data.huecosOcultos)} puntos con menos consultas no se muestran, por privacidad).
            </p>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla desplazable">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Dónde</th>
                    <th>Consultas</th>
                    <th>Sin otra ruta</th>
                    <th>Rodeo acumulado</th>
                    <th>Tramo sin banco</th>
                    <th>Destinos</th>
                    <th><span className="solo-lector">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.huecos.map((h, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>{h.calle || "Tramo peatonal sin nombre"}</td>
                      <td>{h.consultas}</td>
                      <td>{h.sinAlternativa}</td>
                      <td>{fmt(h.rodeoTotalM)} m</td>
                      <td>{fmt(h.huecoMedianoM)} m</td>
                      <td>
                        {Object.entries(h.destinos)
                          .map(([k, v]) => `${DEST[k] || k} (${v})`)
                          .join(", ")}
                      </td>
                      <td>
                        <button type="button" className="link-button" onClick={() => focus(h.coordinates)}>
                          Ver
                        </button>{" "}
                        <button
                          type="button"
                          className="link-button"
                          onClick={() =>
                            onSimulate(
                              h.coordinates,
                              Object.entries(h.destinos).sort((a, b) => b[1] - a[1])[0]?.[0],
                            )
                          }
                        >
                          Simular este banco →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="form-note">
              Para comprobar el efecto de un banco concreto sobre una zona, usa el{" "}
              <button type="button" className="link-button" onClick={() => onSimulate()}>
                simulador de mejoras
              </button>
              .
            </p>
          </section>

          {data.zonasSinBancos.length > 0 && (
            <section className="results study">
              <h2>Zonas sin bancos</h2>
              <p className="form-note">
                Calles donde el camino directo pasa más de {fmt(data.huecoLargoM)} m sin ningún banco: no
                se arreglan con uno, piden un plan de mobiliario para la zona.
              </p>
              <ul className="zonas">
                {data.zonasSinBancos.map((z) => (
                  <li key={z.calle}>
                    <button type="button" className="link-button" onClick={() => focus(z.coordinates)}>
                      {z.calle}
                    </button>{" "}
                    · {z.consultas} consultas · tramo mediano {fmt(z.huecoMedianoM)} m sin banco
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="informe-graficos">
            <div className="results study">
              <h2>A dónde va la gente</h2>
              <Bars data={data.destinos} label={(k) => DEST[k] || k} />
            </div>
            <div className="results study">
              <h2>Cuánto pueden andar sin sentarse</h2>
              <Bars data={data.limites} label={(k) => `${k} m`} />
            </div>
            <div className="results study">
              <h2>A qué hora salen</h2>
              <Bars data={data.horas} label={(k) => `${k}:00`} />
            </div>
          </section>

          <section id="fuentes" className="source-panel">
            <h2>Qué se guarda y qué no</h2>
            <p>
              De cada ruta se guarda el tipo de destino, el límite elegido, la longitud del camino directo
              y de la ruta con descansos, y la posición de los tramos sin banco del camino directo. No se
              guarda la dirección de salida, ni la IP, ni ningún identificador. Los puntos con menos de{" "}
              {data.minimoConsultas} consultas no se muestran.
            </p>
          </section>
        </>
      )}
    </main>
  );
}
