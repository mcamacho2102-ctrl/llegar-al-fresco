import { useEffect, useMemo, useState } from "react";
import Map from "./Map";
import { mapPlace, Position, Route } from "./model";

/** Vista del familiar: sigue en un mapa el trayecto de quien le ha compartido el enlace. */
type Datos = {
  origen: string;
  destino: string;
  geometria: Position[];
  bancos: { nombre: string; punto: Position; aM: number }[];
  posicion: { punto: Position; precision: number; hora: string } | null;
  terminado: { llegado: boolean; hora: string } | null;
  caduca: string;
  ahora: string;
};

const metros = (a: Position, b: Position) => {
  const k = Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
  return Math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540);
};

/** Metros recorridos sobre la ruta: el punto de la línea más cercano a la posición. */
function avance(linea: Position[], p: Position) {
  let mejor = { d: Infinity, en: 0 };
  let acumulado = 0;
  for (let i = 0; i < linea.length - 1; i++) {
    const [a, b] = [linea[i], linea[i + 1]];
    const largo = metros(a, b) || 1e-9;
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) /
      ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 || 1e-18)));
    const q: Position = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    const d = metros(p, q);
    if (d < mejor.d) mejor = { d, en: acumulado + t * largo };
    acumulado += largo;
  }
  return { ...mejor, total: acumulado };
}

function hace(hora: string, ahora: string) {
  const s = Math.max(0, Math.round((Date.parse(ahora) - Date.parse(hora)) / 1000));
  if (s < 60) return `hace ${s} s`;
  const m = Math.round(s / 60);
  return m === 1 ? "hace 1 minuto" : `hace ${m} minutos`;
}

export default function Seguir({ id }: { id: string }) {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let vivo = true;
    const pedir = async () => {
      try {
        const r = await fetch(`/api/seguimiento/${encodeURIComponent(id)}`);
        const j = await r.json();
        if (!vivo) return;
        if (!r.ok) {
          setError(j.detail || "No se puede ver este seguimiento.");
          return;
        }
        setDatos(j);
        setError("");
      } catch {
        if (vivo) setError("Sin conexión. Volvemos a intentarlo en unos segundos.");
      }
    };
    void pedir();
    const t = window.setInterval(pedir, 10000);
    return () => {
      vivo = false;
      window.clearInterval(t);
    };
  }, [id]);

  const ruta = useMemo(() => {
    if (!datos) return [];
    return [
      {
        label: "Ruta",
        style: "comfort",
        geometry: { type: "LineString", coordinates: datos.geometria },
        rests: datos.bancos.map((b) => ({ label: b.nombre, coordinates: b.punto, atM: b.aM, fromRestM: 0, simulated: false })),
        segments: [],
      } as unknown as Route,
    ];
  }, [datos]);

  const estado = useMemo(() => {
    if (!datos?.posicion) return null;
    const a = avance(datos.geometria, datos.posicion.punto);
    const pasados = datos.bancos.filter((b) => b.aM <= a.en + 15).length;
    const quedan = Math.max(0, Math.round(a.total - a.en));
    return { ...a, pasados, quedan, fuera: a.d > Math.max(60, datos.posicion.precision) };
  }, [datos]);

  const origen = datos ? mapPlace(datos.geometria[0], datos.origen) : null;
  const destino = datos ? mapPlace(datos.geometria[datos.geometria.length - 1], datos.destino) : null;

  return (
    <main className="sencillo seguir">
      <header className="seguir-cabecera">
        <img src="/logo.svg" alt="" width={44} height={44} />
        <div>
          <strong>Llegar al fresco</strong>
          <span>Seguimiento en directo</span>
        </div>
      </header>
      {error && !datos && <p className="aviso">{error}</p>}
      {datos && (
        <>
          <section className="frase seguir-frase" aria-live="polite">
            <h2>
              {datos.terminado
                ? datos.terminado.llegado
                  ? "✅ Ha llegado"
                  : "El seguimiento ha terminado"
                : datos.posicion
                  ? "🚶 De camino"
                  : "Esperando la primera posición…"}
            </h2>
            <p>
              De <strong>{datos.origen}</strong> a <strong>{datos.destino}</strong>.
            </p>
            {estado && !datos.terminado && (
              <ul className="seguir-datos">
                <li>
                  Ha pasado por <strong>{estado.pasados}</strong> de {datos.bancos.length} bancos del camino.
                </li>
                <li>
                  Le quedan unos <strong>{estado.quedan} m</strong>.
                </li>
                {estado.fuera && <li>⚠️ Ahora mismo está a unos {Math.round(estado.d)} m de la ruta prevista.</li>}
              </ul>
            )}
            {datos.posicion && (
              <p className="seguir-hora">
                Última posición {hace(datos.posicion.hora, datos.ahora)}
                {datos.posicion.precision > 0 && ` · precisión ±${datos.posicion.precision} m`}
              </p>
            )}
            {error && <p className="aviso">{error}</p>}
          </section>
          <div className="mapa-simple">
            <Map
              origin={origen}
              destination={destino}
              routes={ruta}
              additionalPoints={[]}
              selected={0}
              layer="route"
              placing={false}
              scenario={null}
              position={datos.posicion?.punto || null}
              simple
              showPois={false}
              onPick={() => undefined}
            />
          </div>
          <p className="nota">
            Se actualiza solo cada 10 segundos. Solo ves este trayecto; el seguimiento se apaga al
            llegar o como mucho a las 3 horas, y no se guarda en ningún sitio.
          </p>
        </>
      )}
    </main>
  );
}
