import { useEffect, useMemo, useState } from "react";
import Address from "./Address";
import Map from "./Map";
import {
  api,
  fmt,
  madridNow,
  MapLayer,
  mapPlace,
  Place,
  point,
  Position,
  Route,
  RouteResponse,
  routeRequest,
  Step,
} from "./model";

type Kind = "salud" | "farmacia" | "mayores" | "biblioteca";
type Nearby = Place & { straightM: number };

const DESTINATIONS: { kind: Kind; icon: string; label: string }[] = [
  { kind: "salud", icon: "🏥", label: "Centro de salud" },
  { kind: "farmacia", icon: "💊", label: "Farmacia" },
  { kind: "mayores", icon: "🏠", label: "Centro de mayores" },
  { kind: "biblioteca", icon: "📚", label: "Biblioteca" },
];
const LIMITS = [100, 150, 200, 300];
const MORE_LIMITS = [400, 500, 600, 750, 1000, 1250, 1500, 2000];
const LAYERS: {
  key: MapLayer;
  label: string;
  help: string;
  legend: [string, string, string];
}[] = [
  { key: "route", label: "Ruta", help: "El camino y dónde sentarte.", legend: ["", "", ""] },
  {
    key: "sun",
    label: "Sol y sombra",
    help: "Calculado a la hora de salida, principalmente con la altura de los edificios.",
    legend: ["Sombra", "Sol a ratos", "Sol directo"],
  },
  {
    key: "slopePct",
    label: "Cuestas",
    help: "Inclinación de cada tramo.",
    legend: ["Llano", "Cuesta suave", "Cuesta fuerte"],
  },
  {
    key: "widthM",
    label: "Ancho de acera",
    help: "Ancho de la acera medida más cercana.",
    legend: ["Ancha", "Justa", "Estrecha"],
  },
];
// Las pruebas automáticas abren la app con «?sin-registro» para no contar en el informe.
const NO_REGISTER = new URLSearchParams(window.location.search).has("sin-registro");
const EXAMPLE = {
  origin: "Plaza Virgen De La Paloma, 1",
  destination: "Biblioteca Pedro Salinas",
  departure: "2025-07-01T14:00",
};

function instruction({ action, label, turn }: Step) {
  if (turn) return (turn === "left" ? "Gira a la izquierda hacia " : "Gira a la derecha hacia ") + label;
  if (action === "rest") return "Siéntate en el banco de " + label;
  if (action === "cross") return "Cruza por " + label;
  return "Sigue por " + label;
}
const minutes = (value: number) => {
  const m = Math.max(1, Math.round(value));
  return m === 1 ? "1 minuto" : `${m} minutos`;
};
const times = (n: number) => (n === 1 ? "1 vez" : `${n} veces`);

export default function Sencillo({ onProfessional }: { onProfessional: () => void }) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [limit, setLimit] = useState<number | null>(200);
  const [when, setWhen] = useState<"now" | "other">("now");
  const [departure, setDeparture] = useState(madridNow());
  const [picking, setPicking] = useState<"origin" | "destination" | null>(null);
  const [kind, setKind] = useState<Kind | null>(null);
  const [options, setOptions] = useState<Nearby[]>([]);
  const [otherDestination, setOtherDestination] = useState(false);
  const [result, setResult] = useState<RouteResponse | null>(null);
  const [layer, setLayer] = useState<MapLayer>("route");
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [purpose, setPurpose] = useState<Kind | "direccion">("direccion");
  const [stairs, setStairs] = useState(true);
  const [minWidth, setMinWidth] = useState<number | null>(null);
  const [maxSlope, setMaxSlope] = useState<number | null>(null);
  const [pace, setPace] = useState(1);
  const [prefer, setPrefer] = useState<"comfort" | "shade">("comfort");
  const advancedCount =
    Number(!stairs) + Number(minWidth !== null) + Number(maxSlope !== null) + Number(pace !== 1) + Number(prefer !== "comfort");

  // Al llegar un resultado nuevo, llevar la pantalla hasta él (cuando ya está pintado).
  useEffect(() => {
    if (!result) return;
    const frame = window.requestAnimationFrame(() =>
      document.getElementById("resultado")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [result]);

  const [speaking, setSpeaking] = useState(false);
  const stopSpeaking = () => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  };
  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  const summary = (route: Route) => {
    const parts = [
      `Ruta de ${fmt(route.meters)} metros, unos ${minutes(route.durationMin)}.`,
      route.rests.length
        ? `Te sentarás ${times(route.rests.length)}: ` +
          route.rests.map((r, i) => `${i + 1}, banco de ${r.label}, a los ${Math.round(r.atM)} metros`).join("; ") + "."
        : "No hace falta parar.",
    ];
    return parts.join(" ");
  };

  const speak = (route: Route) => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel();
    const lines = [
      summary(route),
      ...route.steps.map((step) =>
        instruction(step) + (step.action === "walk" ? `, ${Math.round(step.distanceM)} metros.` : "."),
      ),
      "Has llegado.",
    ];
    const voice = synth.getVoices().find((v) => v.lang.startsWith("es"));
    lines.forEach((text, index) => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "es-ES";
      utterance.rate = 0.9;
      if (voice) utterance.voice = voice;
      if (index === lines.length - 1) utterance.onend = () => setSpeaking(false);
      synth.speak(utterance);
    });
    setSpeaking(true);
  };

  const shareLink = () => {
    if (!origin || !destination) return window.location.origin;
    const q = new URLSearchParams({
      o: origin.coordinates.map((v) => v.toFixed(6)).join(","),
      d: destination.coordinates.map((v) => v.toFixed(6)).join(","),
      on: origin.label === "Mi ubicación" ? "Salida" : origin.label,
      dn: destination.label,
      l: limit === null ? "0" : String(limit),
    });
    return `${window.location.origin}/?${q.toString()}`;
  };

  const share = async (route: Route) => {
    const text =
      `${destination?.label || "Ruta"} · ${summary(route)} ` +
      "La he preparado con Llegar al fresco, rutas a pie con sitios para sentarse.";
    const url = shareLink();
    try {
      if (navigator.share) {
        await navigator.share({ title: "Llegar al fresco", text, url });
        return;
      }
    } catch {
      return; // cancelado por la persona
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(text + " " + url)}`, "_blank", "noopener");
  };

  // Enlace compartido: ?o=lon,lat&d=lon,lat&on=…&dn=…&l=200 abre la misma ruta.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const parse = (value: string | null): Position | null => {
      const parts = (value || "").split(",").map(Number);
      return parts.length === 2 && parts.every(Number.isFinite) ? [parts[0], parts[1]] : null;
    };
    const o = parse(params.get("o"));
    const d = parse(params.get("d"));
    if (!o || !d) return;
    const from = mapPlace(o, params.get("on") || "Salida compartida");
    const to = mapPlace(d, params.get("dn") || "Llegada compartida");
    const shared = Number(params.get("l"));
    const max = shared === 0 ? null : LIMITS.concat(MORE_LIMITS).includes(shared) ? shared : 200;
    setOrigin(from);
    setDestination(to);
    setOtherDestination(true);
    setLimit(max);
    void search(from, to, max, madridNow(), false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = () => {
    stopSpeaking();
    setResult(null);
    setLayer("route");
    setError("");
  };

  // Destinos cercanos del tipo elegido, desde la salida.
  useEffect(() => {
    if (!kind || !origin) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    const [lon, lat] = origin.coordinates;
    api<{ results: Nearby[] }>(
      `/api/nearby?kind=${kind}&lon=${lon}&lat=${lat}&n=3`,
      { signal: controller.signal },
    )
      .then((data) => setOptions(data.results))
      .catch((e) => {
        if (!controller.signal.aborted)
          setError((e as Error).message || "No hemos podido buscar lugares cercanos.");
      });
    return () => controller.abort();
  }, [kind, origin]);

  const locate = () => {
    if (!navigator.geolocation) {
      setError("Este navegador no da la ubicación. Escribe la dirección.");
      return;
    }
    setMessage("Buscando dónde estás…");
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        setMessage("");
        reset();
        const coords: Position = [p.coords.longitude, p.coords.latitude];
        try {
          const { dentro } = await api<{ dentro: boolean }>(`/api/dentro?lon=${coords[0]}&lat=${coords[1]}`);
          if (!dentro) {
            setError(
              "Estás fuera de Madrid capital. Por ahora la aplicación solo cubre el municipio de Madrid: escribe una dirección de Madrid.",
            );
            return;
          }
        } catch {
          /* si no se puede comprobar, se intenta igualmente */
        }
        setOrigin(mapPlace(coords, "Mi ubicación"));
      },
      () => {
        setMessage("");
        setError("No se pudo saber dónde estás. Escribe la dirección.");
      },
      { timeout: 12000, enableHighAccuracy: true },
    );
  };

  const search = async (
    from = origin,
    to = destination,
    max = limit,
    at = when === "now" ? madridNow() : departure,
    register = true,
  ) => {
    if (!from || !to) {
      setError("Indica desde dónde sales y a dónde vas.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await routeRequest<RouteResponse>("/api/routes", {
        origin: point(from.coordinates),
        destination: point(to.coordinates),
        departure: at,
        preferences: { pace, rest: max, width: minWidth, slope: maxSlope, avoidStairs: stairs },
        scenario: null,
        purpose,
        register: register && !NO_REGISTER,
      } as never);
      setResult(data);
      setLayer("route");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const example = async () => {
    try {
      const [a, b] = await Promise.all(
        [EXAMPLE.origin, EXAMPLE.destination].map((q) =>
          api<{ results: Place[] }>("/api/addresses?q=" + encodeURIComponent(q)),
        ),
      );
      if (!a.results[0] || !b.results[0]) throw new Error("El ejemplo no está disponible.");
      setOrigin(a.results[0]);
      setDestination(b.results[0]);
      setKind(null);
      setOtherDestination(true);
      setLimit(200);
      setStairs(true);
      setMinWidth(null);
      setMaxSlope(null);
      setPace(1);
      setPrefer("comfort");
      setWhen("other");
      setDeparture(EXAMPLE.departure);
      await search(a.results[0], b.results[0], 200, EXAMPLE.departure, false);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const routes = result?.routes || [];
  const shortest = routes.find((r) => r.style === "distance") || null;
  const recommended: Route | null = useMemo(() => {
    const fitting = routes.filter((r) => r.fitsRest);
    return (
      fitting.find((r) => r.style === prefer) ||
      fitting.find((r) => r.style === "comfort") ||
      fitting.find((r) => r.style === "shade") ||
      fitting[0] ||
      null
    );
  }, [routes, prefer]);
  const closest = routes.find((r) => r.style === "closest") || null;
  const shown = recommended || closest || shortest;
  const selectedIndex = shown ? routes.indexOf(shown) : 0;
  const mapRoutes = result ? routes : [];
  const layerInfo = LAYERS.find((l) => l.key === layer)!;
  const ready = !!origin && !!destination;

  return (
    <main className="sencillo">
      <div className="hero-simple">
        <h1>¿A dónde quieres ir?</h1>
        <p>Te buscamos un camino con sitios para sentarte y con sombra.</p>
      </div>

      {/* Paso 1 */}
      <section className="paso" aria-labelledby="paso1">
        <h2 id="paso1">
          <span className="num">1</span> ¿Desde dónde sales?
        </h2>
        <Address
          label="Tu dirección"
          value={origin}
          onChange={(p) => {
            reset();
            setOrigin(p);
          }}
          onMap={() => setPicking("origin")}
        />
        <button type="button" className="grande secundario" onClick={locate}>
          📍 Usar mi ubicación
        </button>
        {message && <p className="aviso">{message}</p>}
      </section>

      {/* Paso 2 */}
      <section className="paso" aria-labelledby="paso2">
        <h2 id="paso2">
          <span className="num">2</span> ¿A dónde vas?
        </h2>
        <div className="botones-destino">
          {DESTINATIONS.map((d) => (
            <button
              key={d.kind}
              type="button"
              className="grande opcion"
              aria-pressed={kind === d.kind && !otherDestination}
              onClick={() => {
                reset();
                setOtherDestination(false);
                setDestination(null);
                setKind(d.kind);
              }}
            >
              <span aria-hidden="true">{d.icon}</span> {d.label}
            </button>
          ))}
          <button
            type="button"
            className="grande opcion"
            aria-pressed={otherDestination}
            onClick={() => {
              reset();
              setKind(null);
              setDestination(null);
              setOtherDestination(true);
            }}
          >
            ✏️ Otra dirección
          </button>
        </div>
        {kind && !otherDestination && !origin && (
          <p className="aviso" role="alert">
            Primero dinos desde dónde sales (paso 1) y te enseñamos los más cercanos.
          </p>
        )}
        {kind && !otherDestination && origin && options.length === 0 && (
          <p className="aviso" role="status">Buscando los más cercanos…</p>
        )}
        {kind && !otherDestination && origin && options.length > 0 && (
          <div className="cercanos">
            <p>Los más cercanos a tu salida:</p>
            {options.map((place) => (
              <button
                key={place.id}
                type="button"
                className="cercano"
                aria-pressed={destination?.id === place.id}
                onClick={() => {
                  reset();
                  setDestination(place);
                  if (kind) setPurpose(kind);
                }}
              >
                <strong>{place.label.split(" · ").slice(0, 2).join(" · ")}</strong>
                <small>
                  a {fmt(place.straightM)} m en línea recta
                  {place.hours ? " · " + place.hours.slice(0, 60) : ""}
                </small>
              </button>
            ))}
          </div>
        )}
        {otherDestination && (
          <Address
            label="Dirección o lugar de llegada"
            value={destination}
            onChange={(p) => {
              reset();
              setDestination(p);
              setPurpose("direccion");
            }}
            onMap={() => setPicking("destination")}
          />
        )}
      </section>

      {/* Paso 3 */}
      <section className="paso" aria-labelledby="paso3">
        <h2 id="paso3">
          <span className="num">3</span> ¿Cuánto puedes andar sin sentarte?
        </h2>
        <div className="botones-limite" role="radiogroup" aria-labelledby="paso3">
          {LIMITS.map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={limit === value}
              className="grande opcion"
              onClick={() => {
                reset();
                setLimit(value);
              }}
            >
              {value} m
            </button>
          ))}
          <button
            type="button"
            role="radio"
            aria-checked={limit === null}
            className="grande opcion"
            onClick={() => {
              reset();
              setLimit(null);
            }}
          >
            No necesito parar
          </button>
        </div>
        <label className="otra-distancia">
          Otra distancia:{" "}
          <select
            value={limit !== null && MORE_LIMITS.includes(limit) ? String(limit) : ""}
            onChange={(e) => {
              if (!e.target.value) return;
              reset();
              setLimit(Number(e.target.value));
            }}
          >
            <option value="">Elegir…</option>
            {MORE_LIMITS.map((value) => (
              <option key={value} value={value}>
                {value >= 1000 ? `${fmt(value / 1000)} km` : `${value} m`}
              </option>
            ))}
          </select>
        </label>
        <details className="cuando avanzadas">
          <summary>
            Opciones avanzadas{advancedCount ? ` (${advancedCount} activas)` : ""}
          </summary>
          <label className="check-grande">
            <input type="checkbox" checked={stairs} onChange={(e) => { reset(); setStairs(e.target.checked); }} />
            Evitar escaleras
          </label>
          <p className="opcion-titulo">Ancho mínimo de acera</p>
          <div className="botones-limite">
            {([null, 1.2, 1.5, 1.8] as (number | null)[]).map((v) => (
              <button key={String(v)} type="button" className="opcion" aria-pressed={minWidth === v}
                onClick={() => { reset(); setMinWidth(v); }}>
                {v === null ? "Sin mínimo" : `${fmt(v)} m${v === 1.2 ? " · andador" : v === 1.5 ? " · silla de ruedas" : ""}`}
              </button>
            ))}
          </div>
          <p className="opcion-titulo">Cuesta máxima</p>
          <div className="botones-limite">
            {([null, 4, 6, 8, 10] as (number | null)[]).map((v) => (
              <button key={String(v)} type="button" className="opcion" aria-pressed={maxSlope === v}
                onClick={() => { reset(); setMaxSlope(v); }}>
                {v === null ? "Sin límite" : `${v} %${v === 4 ? " · casi llano" : ""}`}
              </button>
            ))}
          </div>
          <p className="opcion-titulo">Tu ritmo al andar</p>
          <div className="botones-limite">
            {([[0.7, "Despacio"], [1, "Normal"], [1.3, "Ligero"]] as [number, string][]).map(([v, label]) => (
              <button key={v} type="button" className="opcion" aria-pressed={pace === v}
                onClick={() => { reset(); setPace(v); }}>
                {label}
              </button>
            ))}
          </div>
          <p className="opcion-titulo">Prefiero</p>
          <div className="botones-limite">
            <button type="button" className="opcion" aria-pressed={prefer === "comfort"} onClick={() => setPrefer("comfort")}>
              Menos esfuerzo
            </button>
            <button type="button" className="opcion" aria-pressed={prefer === "shade"} onClick={() => setPrefer("shade")}>
              Más sombra
            </button>
          </div>
          <p className="nota">
            Ancho y cuesta usan la acera medida por el Ayuntamiento y el relieve del IGN. Los tramos sin
            dato no se descartan; lo verás en «Más detalles».
          </p>
        </details>
        <details className="cuando">
          <summary>¿Cuándo sales? {when === "now" ? "Ahora" : departure.replace("T", " a las ")}</summary>
          <div className="botones-limite">
            <button
              type="button"
              className="opcion"
              aria-pressed={when === "now"}
              onClick={() => {
                reset();
                setWhen("now");
              }}
            >
              Ahora
            </button>
            <button
              type="button"
              className="opcion"
              aria-pressed={when === "other"}
              onClick={() => {
                reset();
                setWhen("other");
              }}
            >
              Otro día u hora
            </button>
          </div>
          {when === "other" && (
            <input
              type="datetime-local"
              value={departure}
              onChange={(e) => {
                reset();
                setDeparture(e.target.value);
              }}
              aria-label="Día y hora de salida"
            />
          )}
        </details>
      </section>

      <div className="buscar">
        <button
          type="button"
          className="grande principal"
          disabled={!ready || busy}
          onClick={() => void search()}
        >
          {busy ? "Buscando tu ruta…" : "Buscar mi ruta"}
        </button>
        {!ready && <p className="pista">Completa los pasos 1 y 2.</p>}
        <button type="button" className="link-button grande-enlace" onClick={() => void example()}>
          Ver un ejemplo
        </button>
        <p className="privacidad">
          Para ayudar a tu ayuntamiento a decidir dónde poner bancos, guardamos sin tu dirección ni
          ningún dato personal en qué tramos del camino faltó un banco.
        </p>
      </div>
      {error && (
        <p className="error-simple" role="alert">
          {error}
        </p>
      )}

      {/* Resultado */}
      {result && (
        <section id="resultado" className="resultado" aria-live="polite">
          {result && !shown && (
            <div className="frase">
              <h2>No hemos encontrado ningún camino</h2>
              <p>Prueba con otro punto de salida o de llegada cercano, o quita alguna opción avanzada.</p>
            </div>
          )}
          {result && shown && (result.tooFar || (result.relaxed && result.relaxed.length > 0)) && (
            <div className="aviso-ruta" role="status">
              {result.tooFar && (
                <p>
                  <strong>Es un trayecto largo para ir a pie</strong> ({fmt(Math.round((result.straightM || 0) / 100) / 10)} km en línea recta).
                  Te recomendamos transporte público. Te mostramos el camino a pie más corto por si lo necesitas.
                </p>
              )}
              {result.relaxed?.includes("width") && (
                <p>
                  <strong>No hay ningún camino con aceras de al menos {fmt(minWidth || 0)} m</strong> entre estos puntos,
                  según las aceras medidas por el Ayuntamiento. Te mostramos el mejor camino disponible: revisa el
                  ancho en la capa «Ancho de acera».
                </p>
              )}
              {result.relaxed?.includes("slope") && (
                <p>
                  <strong>No hay ningún camino con cuestas de {maxSlope} % o menos.</strong> Te mostramos el mejor camino
                  disponible: revisa las cuestas en la capa «Cuestas».
                </p>
              )}
            </div>
          )}
          {result && shown && (
            <div className="frase">
              {recommended ? (
                <>
                  <h2>
                    {fmt(recommended.meters)} m · unos {minutes(recommended.durationMin)}
                  </h2>
                  {limit === null || recommended.rests.length === 0 ? (
                    <p>
                      {limit === null
                        ? "Camino directo, sin límite de descanso."
                        : `No necesitas parar: ningún tramo pasa de ${limit} m.`}
                    </p>
                  ) : (
                    <p>
                      Te sentarás <strong>{times(recommended.rests.length)}</strong>. Nunca andarás
                      más de <strong>{fmt(Math.round(recommended.maxWithoutRest))} m</strong> sin un
                      banco.
                    </p>
                  )}
                  {recommended.rests.length > 0 && (
                    <ol className="descansos">
                      {recommended.rests.map((rest, i) => (
                        <li key={i}>
                          <span className="pin-mini">{i + 1}</span>
                          <span>
                            Banco de <strong>{rest.label}</strong>
                            <small> · a los {fmt(Math.round(rest.atM))} m</small>
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                  {shortest && shortest !== recommended && limit !== null && (
                    <p className="comparacion">
                      El camino más corto mide {fmt(shortest.meters)} m, pero tiene{" "}
                      {fmt(Math.round(shortest.maxWithoutRest))} m seguidos sin ningún banco.
                    </p>
                  )}
                </>
              ) : closest ? (
                <>
                  <p className="kicker-aviso">No hay ninguna ruta con un banco cada {limit} m</p>
                  <h2>
                    La mejor posible: como mucho {fmt(Math.round(closest.maxWithoutRest))} m sin sentarte
                  </h2>
                  <p>
                    {fmt(closest.meters)} m · unos {minutes(closest.durationMin)}.{" "}
                    {closest.rests.length
                      ? <>Te sentarás <strong>{times(closest.rests.length)}</strong>.</>
                      : "No hay ningún banco por el camino."}
                  </p>
                  {closest.rests.length > 0 && (
                    <ol className="descansos">
                      {closest.rests.map((rest, i) => (
                        <li key={i}>
                          <span className="pin-mini">{i + 1}</span>
                          <span>
                            Banco de <strong>{rest.label}</strong>
                            <small> · a los {fmt(Math.round(rest.atM))} m</small>
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                  {shortest && (
                    <p className="comparacion">
                      El camino más corto mide {fmt(shortest.meters)} m, con{" "}
                      {fmt(Math.round(shortest.maxWithoutRest))} m seguidos sin ningún banco.
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className="kicker-aviso">No hay ninguna ruta con un banco cada {limit} m</p>
                  <h2>{fmt(shown.meters)} m sin ningún banco por el camino</h2>
                  <p>
                    No hemos encontrado bancos que acorten el tramo más largo. Prueba con otro destino
                    cercano o lleva un bastón asiento.
                  </p>
                </>
              )}
              <div className="chips">
                {result.weather && (
                  <span className="chip">
                    🌡️ {fmt(result.weather.temperatureC)} °C
                  </span>
                )}
                {shown.sunMin !== null && (
                  <span className="chip">☀️ Al sol unos {minutes(shown.sunMin)}</span>
                )}
                <span className="chip">
                  {shown.slopePct !== null && shown.slopePct > 8 ? "⛰️ Alguna cuesta fuerte" : "🚶 Sin cuestas fuertes"}
                </span>
                {stairs && <span className="chip">🚫 Sin escaleras</span>}
                {minWidth && <span className="chip">↔️ Aceras de {fmt(minWidth)} m o más</span>}
                {maxSlope && <span className="chip">📐 Cuestas de {maxSlope} % como mucho</span>}
              </div>
            </div>
          )}

          {result && (
            <div className="capas" role="radiogroup" aria-label="Qué ver en el mapa">
              {LAYERS.map((l) => (
                <button
                  key={l.key}
                  type="button"
                  role="radio"
                  aria-checked={layer === l.key}
                  className="capa"
                  onClick={() => setLayer(l.key)}
                >
                  {l.label}
                </button>
              ))}
            </div>
          )}
          {result && (
            <div className="leyenda-simple">
              <span>{layerInfo.help}</span>
              {layer === "route" ? (
                <>
                  <span><i className="sw a">A</i> Salida</span>
                  <span><i className="sw b">B</i> Llegada</span>
                  <span><i className="sw r">1</i> Banco para sentarte</span>
                  <span><i className="ln" /> Tu ruta</span>
                  <span><i className="ln alt" /> Otra opción</span>
                </>
              ) : (
                <>
                  <span><i className="ln ok" /> {layerInfo.legend[0]}</span>
                  <span><i className="ln mid" /> {layerInfo.legend[1]}</span>
                  <span><i className="ln bad" /> {layerInfo.legend[2]}</span>
                  <span><i className="ln none" /> Sin dato</span>
                </>
              )}
            </div>
          )}
          <div className="mapa-simple">
            <Map
              origin={origin}
              destination={destination}
              routes={mapRoutes}
              additionalPoints={[]}
              selected={selectedIndex}
              layer={layer}
              placing={false}
              scenario={null}
              position={null}
              simple
              showPois={showAll}
              onPick={() => undefined}
            />
          </div>
          {result && (
            <label className="ver-todo">
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              Ver también todos los bancos, fuentes y aseos de la zona (acerca el mapa)
            </label>
          )}

          {result && shown && (
            <>
              <details className="mas">
                <summary>Indicaciones paso a paso</summary>
                <ol className="pasos-ruta">
                  {shown.steps.map((step, i) => (
                    <li key={i}>
                      {instruction(step)}
                      {step.action === "walk" && <small> · {fmt(Math.round(step.distanceM))} m</small>}
                    </li>
                  ))}
                  <li>Has llegado.</li>
                </ol>
              </details>
              <details className="mas">
                <summary>Más detalles</summary>
                <ul className="detalles">
                  <li>
                    Cuesta más fuerte: <strong>{shown.slopePct === null ? "sin dato" : fmt(shown.slopePct) + " %"}</strong>
                    {shown.upM !== null && ` · subes ${fmt(shown.upM)} m y bajas ${fmt(shown.downM ?? 0)} m`}
                  </li>
                  <li>
                    Acera más estrecha: <strong>{shown.widthM === null ? "sin dato" : fmt(shown.widthM) + " m"}</strong>{" "}
                    <small>(dato en el {shown.coverage.width} % del camino)</small>
                  </li>
                  <li>
                    Tramo más largo al sol: <strong>{shown.sunStretchMin === null ? "sin dato" : minutes(shown.sunStretchMin)}</strong>
                  </li>
                  <li>Cruces de calle: <strong>{shown.crossings}</strong></li>
                  {!!shown.nearbyServices?.length && (
                    <li>
                      Fuentes y aseos cerca:{" "}
                      {shown.nearbyServices.slice(0, 4).map((s) => s.label).join(" · ")}
                    </li>
                  )}
                  {result.weather && <li><small>Temperatura: {result.weather.source}</small></li>}
                </ul>
                <p className="nota">
                  Bancos del inventario municipal. La sombra es una estimación. Comprueba en la calle
                  lo que necesites.
                </p>
              </details>
              <div className="acciones">
                {"speechSynthesis" in window && (
                  <button
                    type="button"
                    className="grande secundario"
                    aria-pressed={speaking}
                    onClick={() => (speaking ? stopSpeaking() : speak(shown))}
                  >
                    {speaking ? "⏹️ Parar" : "🔊 Escuchar indicaciones"}
                  </button>
                )}
                <button type="button" className="grande secundario" onClick={() => void share(shown)}>
                  📤 Compartir ruta
                </button>
                <button type="button" className="grande secundario" onClick={() => window.print()}>
                  🖨️ Imprimir
                </button>
                <button
                  type="button"
                  className="grande secundario"
                  onClick={() => {
                    reset();
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                >
                  Buscar otra ruta
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {picking && (
        <div
          className="selector-mapa"
          role="dialog"
          aria-modal="true"
          aria-label={picking === "origin" ? "Marcar la salida en el mapa" : "Marcar la llegada en el mapa"}
          onKeyDown={(e) => e.key === "Escape" && setPicking(null)}
        >
          <div className="selector-cabecera">
            <p>
              <strong>Toca en el mapa {picking === "origin" ? "dónde sales" : "a dónde vas"}</strong>
              <span>O mueve el mapa y pulsa «Usar el centro del mapa».</span>
            </p>
            <button type="button" className="grande secundario" onClick={() => setPicking(null)} autoFocus>
              Cancelar
            </button>
          </div>
          <div className="selector-cuerpo">
            <Map
              origin={picking === "destination" ? origin : null}
              destination={picking === "origin" ? destination : null}
              routes={[]}
              additionalPoints={[]}
              selected={0}
              layer="route"
              placing
              scenario={null}
              position={null}
              simple
              showPois={false}
              onPick={(p: Position) => {
                reset();
                const target = picking;
                const place = mapPlace(p, target === "origin" ? "Punto de salida en el mapa" : "Punto de llegada en el mapa");
                if (target === "origin") setOrigin(place);
                else {
                  setDestination(place);
                  setPurpose("direccion");
                }
                setPicking(null);
                // Confirmar con la dirección más cercana («Junto a Calle de Toledo, 46»).
                api<{ label: string | null }>(`/api/cerca?lon=${p[0]}&lat=${p[1]}`)
                  .then(({ label }) => {
                    if (!label) return;
                    const named = mapPlace(p, label);
                    if (target === "origin") setOrigin((old) => (old?.id === place.id ? named : old));
                    else setDestination((old) => (old?.id === place.id ? named : old));
                  })
                  .catch(() => undefined);
              }}
            />
            <div className="mira" aria-hidden="true">+</div>
          </div>
        </div>
      )}

      <p className="profesional">
        ¿Trabajas en un ayuntamiento?{" "}
        <button type="button" className="link-button" onClick={onProfessional}>
          Herramientas para técnicos →
        </button>
      </p>
    </main>
  );
}
