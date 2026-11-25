import { useEffect, useMemo, useRef, useState } from "react";
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
type Nearby = Place & { straightM: number; walkM?: number | null };

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

const nombreVia = (label: string) => (/^tramo peatonal$/i.test(label) ? "el tramo peatonal" : label);
function instruction({ action, label, turn }: Step) {
  const via = nombreVia(label);
  if (turn) return (turn === "left" ? "Gira a la izquierda hacia " : "Gira a la derecha hacia ") + via;
  if (action === "rest") return "Siéntate en el banco de " + label;
  if (action === "cross") return "Cruza por " + via;
  return "Sigue por " + via;
}
/** Junta pasos seguidos iguales («Cruza por Calle San Cipriano» cinco veces → una). */
function compactSteps(steps: Step[]): Step[] {
  const out: Step[] = [];
  for (const step of steps) {
    const prev = out[out.length - 1];
    if (prev && step.action !== "rest" && !step.turn && prev.action === step.action && prev.label === step.label) {
      out[out.length - 1] = { ...prev, distanceM: prev.distanceM + step.distanceM };
    } else out.push({ ...step });
  }
  return out;
}
/** Texto pensado para el oído: nombres de calle naturales y sin abreviaturas. */
function hablado(text: string) {
  return text
    .replace(/\b(Del|De|La|Las|Los|El|Y)\b(?=\s)/g, (w, _m, i) => (i === 0 ? w : w.toLowerCase()))
    .replace(/\bS\/N\b/gi, "sin número")
    .replace(/\bC\. ?S\.(?=\s)/g, "centro de salud")
    .replace(/\bAvda\.?(?=\s)/gi, "avenida")
    .replace(/\bPza\.?(?=\s)/gi, "plaza")
    .replace(/(\d) m\b/g, "$1 metros")
    .replace(/ · /g, ", ");
}
const pasoHablado = (step: Step) =>
  instruction(step) + (step.action === "walk" && step.distanceM >= 5 ? `, ${Math.round(step.distanceM)} metros.` : ".");
const minutes = (value: number) => {
  const m = Math.max(1, Math.round(value));
  return m === 1 ? "1 minuto" : `${m} minutos`;
};
const about = (value: number) => {
  const m = Math.max(1, Math.round(value));
  return m === 1 ? "1 minuto" : `unos ${m} minutos`;
};
const times = (n: number) => (n === 1 ? "1 vez" : `${n} veces`);
// Tramo real más largo sin banco junto al camino (el servidor lo calcula para el camino directo).
const gapOf = (route: Route) => route.maxGapM ?? route.maxWithoutRest;

/** Mejor voz en español disponible: las neuronales/mejoradas suenan mucho más claras. */
function bestSpanishVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis?.getVoices() || [];
  const spanish = voices.filter((v) => v.lang.toLowerCase().startsWith("es"));
  const score = (v: SpeechSynthesisVoice) => {
    const name = v.name.toLowerCase();
    let points = 0;
    if (/natural|neural|online|premium|enhanced|mejorad/.test(name)) points += 50; // Edge, iOS, macOS
    if (/google/.test(name)) points += 40; // Chrome (voz en red)
    if (/m[oó]nica|paulina|marisol|elvira|alvaro|álvaro|jorge|lucía|lucia|elena/.test(name)) points += 20;
    if (v.lang === "es-ES") points += 15;
    if (!v.localService) points += 5;
    return points;
  };
  return spanish.sort((a, b) => score(b) - score(a))[0];
}

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

  useEffect(() => {
    let closed: HTMLDetailsElement[] = [];
    const before = () => {
      closed = Array.from(document.querySelectorAll<HTMLDetailsElement>(".resultado details.mas:not([open])"));
      closed.forEach((d) => (d.open = true));
    };
    const after = () => {
      closed.forEach((d) => (d.open = false));
      closed = [];
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  const [speaking, setSpeaking] = useState(false);
  const [guia, setGuia] = useState<number | null>(null);
  const [despacio, setDespacio] = useState(() => {
    try {
      return localStorage.getItem("voz-despacio") === "1";
    } catch {
      return false;
    }
  });
  const turnoVoz = useRef(0);
  const stopSpeaking = () => {
    turnoVoz.current++;
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  };
  /** Lee frase a frase con una pausa breve entre ellas: se entiende mejor y nunca se corta. */
  const decir = (lines: string[]) => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.cancel();
    const turno = ++turnoVoz.current;
    const voice = bestSpanishVoice();
    const una = (i: number) => {
      if (turno !== turnoVoz.current) return;
      if (i >= lines.length) {
        setSpeaking(false);
        return;
      }
      const u = new SpeechSynthesisUtterance(hablado(lines[i]));
      u.lang = voice?.lang || "es-ES";
      if (voice) u.voice = voice;
      u.rate = despacio ? 0.78 : 0.93;
      u.pitch = 1;
      u.volume = 1;
      u.onend = () => window.setTimeout(() => una(i + 1), 400);
      u.onerror = () => turno === turnoVoz.current && setSpeaking(false);
      synth.speak(u);
    };
    setSpeaking(true);
    una(0);
  };
  useEffect(() => {
    // Las voces se cargan tarde en algunos navegadores: pedirlas al montar.
    window.speechSynthesis?.getVoices();
    return () => window.speechSynthesis?.cancel();
  }, []);

  const summary = (route: Route) => {
    const parts = [
      `Ruta de ${fmt(route.meters)} metros, ${about(route.durationMin)}.`,
      route.rests.length
        ? `Te sentarás ${times(route.rests.length)}: ` +
          route.rests.map((r, i) => `${i + 1}, banco de ${r.label}, a los ${Math.round(r.atM)} metros`).join("; ") + "."
        : "No hace falta parar.",
    ];
    return parts.join(" ");
  };

  const leerTodo = (route: Route) => decir([summary(route), ...compactSteps(route.steps).map(pasoHablado), "Has llegado."]);
  const decirPaso = (route: Route, i: number) => {
    const pasos = compactSteps(route.steps);
    const j = Math.max(0, Math.min(pasos.length - 1, i));
    setGuia(j);
    decir([`Paso ${j + 1} de ${pasos.length}.`, pasoHablado(pasos[j]) + (j === pasos.length - 1 ? " Después, has llegado." : "")]);
  };
  const empezarGuia = (route: Route) => {
    setGuia(0);
    const pasos = compactSteps(route.steps);
    decir([summary(route), "Vamos paso a paso. Pulsa Siguiente cuando quieras el próximo.", `Paso 1 de ${pasos.length}.`, pasoHablado(pasos[0])]);
  };

  // ------------------------------------------------------------------ seguimiento en directo
  type Seguimiento =
    | { fase: "explica" }
    | { fase: "activo"; id: string; clave: string; url: string; estado: string };
  const [seguimiento, setSeguimiento] = useState<Seguimiento | null>(null);
  const vigia = useRef<number | null>(null);
  const ultimoEnvio = useRef<{ t: number; p: Position } | null>(null);
  const pantalla = useRef<{ release: () => Promise<void> } | null>(null);
  const distancia = (a: Position, b: Position) =>
    Math.hypot((a[0] - b[0]) * 84500, (a[1] - b[1]) * 111200);
  const pararVigia = () => {
    if (vigia.current !== null) navigator.geolocation?.clearWatch(vigia.current);
    vigia.current = null;
    void pantalla.current?.release().catch(() => undefined);
    pantalla.current = null;
  };
  useEffect(() => () => pararVigia(), []);
  const terminarSeguimiento = async (llegado = false) => {
    const actual = seguimiento;
    pararVigia();
    setSeguimiento(null);
    if (actual?.fase === "activo")
      await fetch(`/api/seguimiento/${actual.id}/fin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clave: actual.clave, llegado }),
      }).catch(() => undefined);
  };
  const enviarEnlace = async (url: string) => {
    const text = `Sigue mi camino hasta ${destination?.label || "mi destino"} con Llegar al fresco:`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "Sigue mi camino", text, url });
        return;
      }
    } catch {
      return;
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(text + " " + url)}`, "_blank", "noopener");
  };
  const empezarSeguimiento = async (route: Route) => {
    if (!navigator.geolocation || !origin || !destination) {
      setError("Este navegador no permite compartir la ubicación.");
      return;
    }
    try {
      const r = await fetch("/api/seguimiento", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origen: origin.label,
          destino: destination.label,
          geometria: route.geometry.coordinates,
          bancos: route.rests.map((x) => ({ nombre: x.label, punto: x.coordinates, aM: x.atM })),
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "No se ha podido empezar el seguimiento.");
      const url = `${window.location.origin}/?seguir=${j.id}`;
      setSeguimiento({ fase: "activo", id: j.id, clave: j.clave, url, estado: "Esperando tu posición…" });
      try {
        // Mantener la pantalla encendida: con la pantalla apagada, la web no puede enviar la posición.
        const wl = (navigator as unknown as { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void> }> } }).wakeLock;
        pantalla.current = wl ? await wl.request("screen") : null;
      } catch {
        pantalla.current = null;
      }
      ultimoEnvio.current = null;
      const llegada = destination.coordinates;
      vigia.current = navigator.geolocation.watchPosition(
        async (pos) => {
          const p: Position = [pos.coords.longitude, pos.coords.latitude];
          const ahora = Date.now();
          const previo = ultimoEnvio.current;
          if (previo && ahora - previo.t < 12000 && distancia(previo.p, p) < 25) return;
          ultimoEnvio.current = { t: ahora, p };
          const res = await fetch(`/api/seguimiento/${j.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clave: j.clave, lon: p[0], lat: p[1], precision: pos.coords.accuracy || 0 }),
          }).catch(() => null);
          const hora = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
          setSeguimiento((s) =>
            s?.fase === "activo"
              ? { ...s, estado: res?.ok ? `Compartiendo tu posición · enviada a las ${hora}` : "No se ha podido enviar tu posición; lo intentamos de nuevo." }
              : s,
          );
          if (distancia(p, llegada) < 35) {
            pararVigia();
            await fetch(`/api/seguimiento/${j.id}/fin`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ clave: j.clave, llegado: true }),
            }).catch(() => undefined);
            setSeguimiento((s) => (s?.fase === "activo" ? { ...s, estado: "✅ Has llegado. Tu familia ya lo ve." } : s));
          }
        },
        (err) =>
          setSeguimiento((s) =>
            s?.fase === "activo"
              ? { ...s, estado: err.code === 1 ? "Sin permiso de ubicación: actívalo para que puedan seguirte." : "Buscando tu ubicación…" }
              : s,
          ),
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 30000 },
      );
    } catch (e) {
      setError((e as Error).message);
      setSeguimiento(null);
    }
  };

  const shareLink = () => {
    if (!origin || !destination) return window.location.origin;
    const q = new URLSearchParams({
      o: origin.coordinates.map((v) => v.toFixed(6)).join(","),
      d: destination.coordinates.map((v) => v.toFixed(6)).join(","),
      on: origin.label.startsWith("Mi ubicación") ? "Salida" : origin.label,
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
    // &t=AAAA-MM-DDTHH:MM fija la hora de salida (por ejemplo, para enseñar un día de calor pasado).
    const t = params.get("t") || "";
    const at = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t) ? t : madridNow();
    if (at === t) {
      setWhen("other");
      setDeparture(t);
    }
    void search(from, to, max, at, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = () => {
    stopSpeaking();
    setGuia(null);
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
    if (!window.isSecureContext) {
      setError(
        "La ubicación solo funciona abriendo la página segura (https://llegaralfresco.outofthemark.com). Mientras, escribe la dirección.",
      );
      return;
    }
    if (!navigator.geolocation) {
      setError("Este navegador no da la ubicación. Escribe la dirección.");
      return;
    }
    setError("");
    setMessage("Buscando dónde estás…");
    const found = async (p: GeolocationPosition) => {
      reset();
      setMessage(
        p.coords.accuracy > 300
          ? `Ubicación aproximada (unos ${fmt(Math.round(p.coords.accuracy / 50) * 50)} m de margen). Si no es tu sitio, escribe la dirección.`
          : "",
      );
      const coords: Position = [p.coords.longitude, p.coords.latitude];
      try {
        const { dentro, red, calle } = await api<{
          dentro: boolean;
          red?: boolean;
          calle?: { coordinates: Position; distanceM: number };
        }>(`/api/dentro?lon=${coords[0]}&lat=${coords[1]}`);
        if (dentro && red === false && calle) {
          setMessage(
            `El camino a pie más cercano está a unos ${fmt(Math.round(calle.distanceM / 10) * 10)} m de donde estás: saldremos desde allí.`,
          );
          setOrigin(mapPlace(calle.coordinates, "Mi ubicación (camino más cercano)"));
          return;
        }
        if (!dentro) {
          setMessage("");
          setError(
            "Estás fuera de Madrid capital. Por ahora la aplicación solo cubre el municipio de Madrid: escribe una dirección de Madrid.",
          );
          return;
        }
        if (red === false) {
          setMessage("");
          setError(
            "Tu ubicación queda lejos de cualquier calle o camino del mapa (puede que estés en un parque grande, un recinto o el campo). Escribe la dirección o márcala en el mapa.",
          );
          return;
        }
      } catch {
        /* si no se puede comprobar, se intenta igualmente */
      }
      setOrigin(mapPlace(coords, "Mi ubicación"));
    };
    const fail = (e: GeolocationPositionError) => {
      setMessage("");
      setError(
        e.code === e.PERMISSION_DENIED
          ? "El teléfono no deja ver tu ubicación. En iPhone: Ajustes › Privacidad › Localización › Safari › «Al usar la app». En Android: toca el candado junto a la dirección › Permisos › Ubicación. Mientras, escribe la dirección."
          : "No hemos podido saber dónde estás ahora mismo (poca señal). Vuelve a intentarlo o escribe la dirección.",
      );
    };
    // Primero una posición rápida (wifi o antena); si no llega a tiempo, se insiste con el GPS.
    navigator.geolocation.getCurrentPosition(
      found,
      (e) => {
        if (e.code === e.PERMISSION_DENIED) return fail(e);
        navigator.geolocation.getCurrentPosition(found, fail, { timeout: 25000, enableHighAccuracy: true, maximumAge: 0 });
      },
      { timeout: 10000, enableHighAccuracy: false, maximumAge: 120000 },
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
                  {place.walkM ? `a ${fmt(place.walkM)} m andando` : `a ${fmt(place.straightM)} m en línea recta`}
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
        {busy && (
          <p className="pista" role="status">
            Estamos comparando caminos con bancos y sombra. Puede tardar unos segundos.
          </p>
        )}
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
          {result && shown && origin && destination && (
            <div className="print-only cabecera-impresa">
              <strong>Llegar al fresco</strong> · {origin.label} → {destination.label}
              <br />
              {limit === null ? "Sin límite de descanso" : `Como mucho ${limit} m sin sentarte`} · salida{" "}
              {(when === "now" ? madridNow() : departure).replace("T", " a las ")} · llegaralfresco.outofthemark.com
            </div>
          )}
          {result && !shown && (
            <div className="frase">
              <h2>No hemos encontrado ningún camino</h2>
              <p>Prueba con otro punto de salida o de llegada cercano, o quita alguna opción avanzada.</p>
            </div>
          )}
          {result && shown && (result.tooFar || result.farConnectionM || (result.relaxed && result.relaxed.length > 0)) && (
            <div className="aviso-ruta" role="status">
              {result.tooFar && (
                <p>
                  <strong>Es un trayecto largo para ir a pie</strong> (
                  {result.walkM
                    ? `${fmt(Math.round(result.walkM / 100) / 10)} km andando`
                    : `${fmt(Math.round((result.straightM || 0) / 100) / 10)} km en línea recta`}
                  ).
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
              {result.farConnectionM && (
                <p>
                  <strong>El camino a pie más cercano queda a unos {fmt(Math.round(result.farConnectionM / 10) * 10)} m</strong>{" "}
                  de una de las direcciones (puede ser una urbanización nueva o un recinto que el mapa aún no recorre). El
                  recorrido empieza o termina allí.
                </p>
              )}
              {result.relaxed?.includes("stairs") && (
                <p>
                  <strong>No hemos encontrado ningún camino sin escaleras hasta aquí.</strong> Te mostramos el mejor camino
                  disponible, que tiene escaleras. Si no puedes subirlas, elige otro destino o pide ayuda.
                </p>
              )}
            </div>
          )}
          {result && shown && (
            <div className="frase">
              {recommended ? (
                <>
                  <h2>
                    {fmt(recommended.meters)} m · {about(recommended.durationMin)}
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
                  {shortest && shortest !== recommended && limit !== null && gapOf(shortest) > limit && (
                    <p className="comparacion">
                      El camino más corto mide {fmt(shortest.meters)} m, pero tiene un tramo de{" "}
                      {fmt(Math.round(gapOf(shortest)))} m seguidos sin ningún banco.
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
                    {fmt(closest.meters)} m · {about(closest.durationMin)}.{" "}
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
                  {shortest && limit !== null && gapOf(shortest) > Math.max(limit, closest.maxWithoutRest) && (
                    <p className="comparacion">
                      El camino más corto mide {fmt(shortest.meters)} m, con un tramo de{" "}
                      {fmt(Math.round(gapOf(shortest)))} m seguidos sin ningún banco.
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
                  <span className="chip">☀️ Al sol {about(shown.sunMin)}</span>
                )}
                <span className="chip">
                  {shown.slopePct !== null && shown.slopePct > 8 ? "⛰️ Alguna cuesta fuerte" : "🚶 Sin cuestas fuertes"}
                </span>
                {stairs && !result.relaxed?.includes("stairs") && <span className="chip">🚫 Sin escaleras</span>}
                {minWidth && !result.relaxed?.includes("width") && (
                  <span className="chip">↔️ Aceras de {fmt(minWidth)} m o más</span>
                )}
                {maxSlope && !result.relaxed?.includes("slope") && (
                  <span className="chip">📐 Cuestas de {maxSlope} % como mucho</span>
                )}
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
                  {compactSteps(shown.steps).map((step, i) => (
                    <li key={i} className={guia === i ? "paso-actual" : undefined}>
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
              {guia !== null && (() => {
                const pasos = compactSteps(shown.steps);
                const paso = pasos[Math.min(guia, pasos.length - 1)];
                return (
                  <div className="guia-voz" role="region" aria-label="Indicaciones habladas">
                    <p className="guia-num">Paso {guia + 1} de {pasos.length}</p>
                    <p className="guia-texto">
                      {instruction(paso)}
                      {paso.action === "walk" && paso.distanceM >= 5 && <small> · {fmt(Math.round(paso.distanceM))} m</small>}
                    </p>
                    <div className="guia-botones">
                      <button type="button" className="grande secundario" disabled={guia === 0} onClick={() => decirPaso(shown, guia - 1)}>⏮️ Anterior</button>
                      <button type="button" className="grande secundario" onClick={() => decirPaso(shown, guia)}>🔁 Repetir</button>
                      <button type="button" className="grande" disabled={guia >= pasos.length - 1} onClick={() => decirPaso(shown, guia + 1)}>Siguiente ⏭️</button>
                    </div>
                    <div className="guia-extra">
                      <label>
                        <input
                          type="checkbox"
                          checked={despacio}
                          onChange={(e) => {
                            setDespacio(e.target.checked);
                            try {
                              localStorage.setItem("voz-despacio", e.target.checked ? "1" : "0");
                            } catch {
                              /* sin almacenamiento */
                            }
                          }}
                        />{" "}
                        Hablar más despacio
                      </label>
                      <button type="button" className="link-button" onClick={() => (speaking ? stopSpeaking() : leerTodo(shown))}>
                        {speaking ? "⏹️ Callar" : "Leer toda la ruta seguida"}
                      </button>
                    </div>
                  </div>
                );
              })()}
              {seguimiento?.fase === "explica" && (
                <div className="seguimiento" role="region" aria-label="Que tu familia te siga">
                  <h3>👪 Que tu familia te siga</h3>
                  <p>
                    Te damos un enlace para enviar por WhatsApp. Quien lo abra verá en un mapa por dónde vas y por qué banco
                    pasas, hasta que llegues.
                  </p>
                  <ul className="detalles">
                    <li>Solo durante este trayecto: se apaga al llegar o, como mucho, a las 3 horas.</li>
                    <li>No se guarda en ningún sitio y puedes pararlo cuando quieras.</li>
                    <li>Mantén esta pantalla abierta mientras caminas.</li>
                  </ul>
                  <div className="guia-botones">
                    <button type="button" className="grande" onClick={() => void empezarSeguimiento(shown)}>Empezar a compartir</button>
                    <button type="button" className="grande secundario" onClick={() => setSeguimiento(null)}>Ahora no</button>
                  </div>
                </div>
              )}
              {seguimiento?.fase === "activo" && (
                <div className="seguimiento activo" role="region" aria-label="Seguimiento en directo" aria-live="polite">
                  <h3>👪 Tu familia puede seguirte</h3>
                  <p>{seguimiento.estado}</p>
                  <div className="guia-botones">
                    <button type="button" className="grande" onClick={() => void enviarEnlace(seguimiento.url)}>📤 Enviar el enlace</button>
                    <button type="button" className="grande secundario" onClick={() => void terminarSeguimiento(false)}>⏹️ Dejar de compartir</button>
                  </div>
                  <p className="nota">Enlace: {seguimiento.url}</p>
                </div>
              )}
              <div className="acciones">
                {"speechSynthesis" in window && (
                  <button
                    type="button"
                    className="grande secundario"
                    aria-pressed={guia !== null}
                    onClick={() => {
                      if (guia === null) empezarGuia(shown);
                      else {
                        stopSpeaking();
                        setGuia(null);
                      }
                    }}
                  >
                    {guia === null ? "🔊 Escuchar indicaciones" : "✖️ Cerrar indicaciones habladas"}
                  </button>
                )}
                {!seguimiento && "geolocation" in navigator && (
                  <button type="button" className="grande secundario" onClick={() => setSeguimiento({ fase: "explica" })}>
                    👪 Que mi familia me siga
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
