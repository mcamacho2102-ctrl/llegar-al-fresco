import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Address from "./Address";
import BankPlanResults from "./BankPlan";
import Map from "./Map";
import Region from "./Region";
import Sencillo from "./Sencillo";
import Logo from "./Logo";
import Informe from "./Informe";
import {
  api,
  BankOption,
  BankPlan,
  fmt,
  Improvement,
  Info,
  madridNow,
  MapLayer,
  mapPlace,
  Place,
  point,
  Position,
  Preferences,
  Route,
  RouteQuery,
  RouteResponse,
  routeRequest,
  Step,
  Study,
} from "./model";
import { meters, progress } from "./navigation";
import "./style.css";

const noRoutes: Route[] = [];

const initial: Preferences = {
  pace: 1,
  rest: 200,
  width: null,
  slope: null,
  avoidStairs: true,
};
const interventions = {
  bench: "Añadir un banco",
  crossing: "Mejorar un rebaje",
  shade: "Añadir sombra",
};
const defaults = ["Plaza Virgen De La Paloma, 1", "Biblioteca Pedro Salinas"];
const exampleBank: Improvement = {
  kind: "bench",
  lon: -3.7103549,
  lat: 40.4096198,
};
const overlays = {
  sun: {
    name: "Sol y sombra",
    labels: ["Sol directo", "Sol parcial", "Sin sol directo", "Sin dato"],
  },
  widthM: {
    name: "Anchura de acera",
    labels: [
      "Menos de 1,5 m",
      "De 1,5 a menos de 1,8 m",
      "1,8 m o más",
      "Sin dato",
    ],
  },
  slopePct: {
    name: "Pendiente",
    labels: [
      "Más del 8 %",
      "Más del 4 y hasta el 8 %",
      "Hasta el 4 %",
      "Sin dato",
    ],
  },
};
const savedKey = "llegar-al-fresco-active";
type Candidate = {
  key: string;
  label: string;
  cost: number | null;
  study: Study;
};
type Saved = {
  origin: Place;
  destination: Place;
  route: Route;
  preferences?: Preferences;
};
function savedRoute(): Saved | null {
  try {
    const saved = localStorage.getItem(savedKey);
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null;
  }
}
function metric(value: number | null, unit: string) {
  return value === null ? "Sin dato" : fmt(value) + " " + unit;
}
function instruction({ action, label, turn }: Step) {
  if (turn)
    return (
      (turn === "left"
        ? "Gira a la izquierda hacia "
        : "Gira a la derecha hacia ") + label
    );
  return action === "rest"
    ? "Descansa en " + label
    : action === "cross"
      ? "Cruza por " + label
      : "Continúa por " + label;
}
function Details({ route }: { route: Route }) {
  return (
    <>
      <div className="metrics">
        <div>
          <span>Tramo más largo sin descanso</span>
          <strong>{metric(route.maxWithoutRest, "m")}</strong>
        </div>
        <div>
          <span>Bancos en el recorrido</span>
          <strong>{route.rests.length}</strong>
        </div>
        <div>
          <span>Menor ancho disponible</span>
          <strong>{metric(route.widthM, "m")}</strong>
          <small>
            {route.coverage.width}% con datos · medias o anchuras cartografiadas
          </small>
        </div>
        <div>
          <span>Mayor pendiente estimada</span>
          <strong>{metric(route.slopePct, "%")}</strong>
          <small>{route.coverage.slope}% con datos</small>
        </div>
        <div>
          <span>Subida / bajada estimadas</span>
          <strong>
            {metric(route.upM, "m")} / {metric(route.downM, "m")}
          </strong>
          <small>{route.coverage.elevation}% con sentido de pendiente</small>
        </div>
        <div>
          <span>Exposición directa al sol</span>
          <strong>{metric(route.sunMin, "min")}</strong>
          <small>
            {route.coverage.sun}% modelado · sobre todo altura de edificios
          </small>
          <small>
            Tramo continuo estimado: {metric(route.sunStretchMin, "min")}
          </small>
        </div>
      </div>
      {route.rests.length > 0 && (
        <div className="rest-list">
          <h3>Dónde puedes descansar</h3>
          <ol>
            {route.rests.map((rest, index) => (
              <li key={index}>
                <strong>{rest.label}</strong>
                <span>
                  {fmt(rest.fromRestM)} m desde la salida o la parada anterior
                  {rest.simulated ? " · simulación" : ""}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <details>
        <summary>Instrucciones de la ruta</summary>
        <ol className="steps">
          {route.steps.map((step, index) => (
            <li key={index}>
              {instruction(step)}{" "}
              {step.action === "walk" && <span>{fmt(step.distanceM)} m</span>}
            </li>
          ))}
          <li>Llega al destino.</li>
        </ol>
      </details>
      {!!route.nearbyServices?.length && (
        <details>
          <summary>Fuentes y aseos cerca del recorrido</summary>
          <ul>
            {route.nearbyServices.map((place) => (
              <li key={place.id}>
                {place.label} · {place.offsetM} m en línea recta
              </li>
            ))}
          </ul>
          <p className="form-note">
            El horario, el acceso y la distancia a pie quedan por confirmar.
          </p>
        </details>
      )}
      <details>
        <summary>Datos y límites del recorrido</summary>
        <p>
          Accesos a la red estimados en {fmt(route.connectionsM[0])} m al salir
          y {fmt(route.connectionsM[1])} m al llegar.
        </p>
        {route.barriers.length > 0 && (
          <ul>
            {route.barriers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <p>
          Confirma los cruces y los accesos que necesites. La sombra es una
          estimación geométrica y los descansos proceden del inventario
          municipal.
        </p>
      </details>
    </>
  );
}

function App() {
  const [saved] = useState(savedRoute);
  const [origin, setOrigin] = useState<Place | null>(saved?.origin || null),
    [destination, setDestination] = useState<Place | null>(
      saved?.destination || null,
    );
  const [automaticDeparture, setAutomaticDeparture] = useState(madridNow);
  const [chosenDeparture, setChosenDeparture] = useState<string | null>(null);
  const departure = chosenDeparture ?? automaticDeparture;
  const [preferences, setPreferences] = useState(saved?.preferences || initial);
  const [mode, setMode] = useState<"inicio" | "informe" | "walk" | "city" | "region">(
      () =>
        window.location.hash === "#region"
          ? "region"
          : window.location.hash === "#tecnicos"
            ? "informe"
            : window.location.hash === "#simulador"
              ? "city"
            : window.location.hash === "#detallado"
              ? "walk"
              : "inicio",
    ),
    [pick, setPick] = useState<"origin" | "destination" | "scenario" | null>(
      null,
    );
  const [kind, setKind] = useState<Improvement["kind"]>("bench"),
    [scenario, setScenario] = useState<Improvement | null>(null);
  const [result, setResult] = useState<
      (RouteResponse & { requestedDeparture: string }) | null
    >(null),
    [selected, setSelected] = useState(0),
    [baseline, setBaseline] = useState<RouteResponse | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [info, setInfo] = useState<Info | null>(null),
    [study, setStudy] = useState<Study | null>(null),
    [radius, setRadius] = useState(250);
  const [bankPlan, setBankPlan] = useState<BankPlan | null>(null);
  const bankPins = useMemo<Place[]>(
    () =>
      bankPlan
        ? [
            ...bankPlan.options.map((option, index) => ({
              id: option.id,
              label: `Banco ${index + 1} · ${option.label}`,
              coordinates: [
                option.scenario.lon,
                option.scenario.lat,
              ] as Position,
              kind: "bank-candidate",
            })),
            ...bankPlan.footfall.map((reading) => ({
              id: reading.id,
              label: reading.label + (reading.side ? " · " + reading.side : ""),
              coordinates: reading.coordinates,
              kind: "footfall",
            })),
          ]
        : [],
    [bankPlan],
  );
  const [candidates, setCandidates] = useState<Candidate[]>([]),
    [estimate, setEstimate] = useState("");
  const [position, setPosition] = useState<Position | null>(null),
    [navigation, setNavigation] = useState<Route | null>(saved?.route || null);
  const [walking, setWalking] = useState(false),
    [voice, setVoice] = useState(false),
    [progressM, setProgressM] = useState(0);
  const [navigationMessage, setNavigationMessage] = useState(
    saved ? "Ruta guardada. Pulsa Reanudar para usar la ubicación." : "",
  );
  const walkDistance = useRef(0);
  const [layer, setLayer] = useState<MapLayer>("route");
  useEffect(() => {
    let wasClosed: HTMLDetailsElement[] = [];
    const openText = () => {
      wasClosed = Array.from(
        document.querySelectorAll<HTMLDetailsElement>(
          ".results details:not([open]), .navigation details:not([open])",
        ),
      );
      wasClosed.forEach((item) => {
        item.open = true;
      });
    };
    const restore = () => {
      wasClosed.forEach((item) => {
        item.open = false;
      });
      wasClosed = [];
    };
    window.addEventListener("beforeprint", openText);
    window.addEventListener("afterprint", restore);
    return () => {
      window.removeEventListener("beforeprint", openText);
      window.removeEventListener("afterprint", restore);
    };
  }, []);
  const requestId = useRef(0),
    navi = useRef({
      badFixes: 0,
      firstBad: 0,
      lastReroute: 0,
      rerouting: false,
      spoken: -1,
      carry: 0,
      restAt: 0,
    });
  const layout = useRef<HTMLDivElement>(null);
  useEffect(() => {
    api<Info>("/api/info")
      .then(setInfo)
      .catch(() => {});
  }, []);
  const setOption = <K extends keyof Preferences>(
    key: K,
    value: Preferences[K],
  ) => setPreferences((old) => ({ ...old, [key]: value }));
  const buildQuery = (improvement: Improvement | null): RouteQuery | null => {
    if (!origin || !destination || chosenDeparture === "") return null;
    const requestedDeparture = chosenDeparture ?? madridNow();
    if (chosenDeparture === null && requestedDeparture !== automaticDeparture) {
      setAutomaticDeparture(requestedDeparture);
      setCandidates([]);
    }
    return {
      origin: point(origin.coordinates),
      destination: point(destination.coordinates),
      departure: requestedDeparture,
      preferences,
      scenario: improvement,
      register: false, // herramientas técnicas: no cuentan como demanda ciudadana
    };
  };
  const validRefugeDate = (requestedDeparture: string) => {
    if (
      !destination?.openFrom ||
      destination.openFrom.slice(0, 10) === requestedDeparture.slice(0, 10)
    )
      return true;
    setError(
      "Vuelve a buscar el refugio para la nueva fecha y confirmar su horario.",
    );
    return false;
  };
  const solve = async (improvement: Improvement | null = scenario) => {
    const query = buildQuery(mode === "city" ? improvement : null);
    if (!query) {
      setError("Selecciona un origen y un destino para calcular.");
      return;
    }
    if (!validRefugeDate(query.departure)) return;
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    setStudy(null);
    setBaseline(null);
    setResult(null);
    setNotice("");
    try {
      const [now, before] = await Promise.all([
        routeRequest<RouteResponse>("/api/routes", query),
        query.scenario
          ? routeRequest<RouteResponse>("/api/routes", {
              ...query,
              scenario: null,
            })
          : Promise.resolve(null),
      ]);
      if (requestId.current !== id) return;
      setResult({ ...now, requestedDeparture: query.departure });
      setBaseline(before);
      const compatible = now.routes.findIndex((r) => r.fitsRest);
      setSelected(compatible >= 0 ? compatible : 0);
    } catch (e) {
      if (requestId.current === id) setError((e as Error).message);
    } finally {
      if (requestId.current === id) setBusy(false);
    }
  };
  const invalidate = () => {
    requestId.current++;
    setResult(null);
    setBaseline(null);
    setStudy(null);
    setBankPlan(null);
    setBusy(false);
    setError("");
  };
  const selectPlace = (
    which: "origin" | "destination",
    place: Place | null,
  ) => {
    invalidate();
    setCandidates([]);
    (which === "origin" ? setOrigin : setDestination)(place);
  };
  const activateMap = (target: typeof pick) => {
    setPick(target);
    const el = layout.current;
    if (!el) return;
    if (window.innerWidth <= 860) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      const rect = el.getBoundingClientRect();
      if (rect.top < 0 || rect.bottom > window.innerHeight + 80) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  };
  const choosePoint = (coords: Position) => {
    if (pick === "origin" || pick === "destination") {
      selectPlace(
        pick,
        mapPlace(
          coords,
          pick === "origin" ? "Salida en el mapa" : "Destino en el mapa",
        ),
      );
      setPick(null);
    } else if (pick === "scenario") {
      const item = { kind, ...point(coords) };
      setScenario(item);
      setPick(null);
      void solve(item);
    }
  };
  const example = async () => {
    try {
      const [a, b] = await Promise.all(
        defaults.map((q) =>
          api<{ results: Place[] }>(
            "/api/addresses?q=" + encodeURIComponent(q),
          ),
        ),
      );
      if (!a.results[0] || !b.results[0])
        throw new Error("El recorrido de ejemplo no está disponible.");
      invalidate();
      setCandidates([]);
      setOrigin(a.results[0]);
      setDestination(b.results[0]);
      setPreferences(initial);
      if (chosenDeparture === null) setAutomaticDeparture(madridNow());
      setScenario(mode === "city" ? exampleBank : null);
      if (mode === "city") setRadius(500);
      setKind("bench");
      setNotice(
        mode === "city"
          ? "Ejemplo de Puerta de Toledo cargado. Puedes buscar ubicaciones para bancos."
          : "Ejemplo de Puerta de Toledo cargado. Pulsa Comparar rutas.",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const locate = () => {
    if (!navigator.geolocation) {
      setError(
        "Este navegador no ofrece ubicación. Busca una dirección o marca un punto.",
      );
      return;
    }
    setNotice("Buscando tu ubicación…");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setNotice(
          p.coords.accuracy > 65
            ? "Ubicación aproximada. Puedes ajustar la salida en el mapa."
            : "Ubicación elegida como salida.",
        );
        selectPlace(
          "origin",
          mapPlace([p.coords.longitude, p.coords.latitude], "Mi ubicación"),
        );
      },
      () => {
        setNotice("");
        setError(
          "No se pudo obtener tu ubicación. Puedes escribir la dirección.",
        );
      },
      { timeout: 12000, enableHighAccuracy: true },
    );
  };
  const recommendBanks = async () => {
    const query = buildQuery(null);
    if (!query || !preferences.rest) {
      setError("Elige salida, destino y un máximo de metros sin descanso.");
      return;
    }
    if (!validRefugeDate(query.departure)) return;
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    setNotice("Comparando ubicaciones para un banco…");
    setPick(null);
    try {
      const value = await routeRequest<BankPlan>("/api/bank-plan", {
        ...query,
        radiusM: radius,
      });
      if (id === requestId.current) {
        setBankPlan(value);
        setNotice("");
      }
    } catch (e) {
      if (id === requestId.current) {
        setError((e as Error).message);
        setNotice("");
      }
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  };
  const simulateBank = (option: BankOption) => {
    setKind("bench");
    setScenario(option.scenario);
    setPick(null);
    void solve(option.scenario);
  };
  const computeStudy = async () => {
    const query = buildQuery(scenario);
    if (!query || !scenario) {
      setError("Elige puntos de ruta, hora de salida y una intervención.");
      return;
    }
    if (!validRefugeDate(query.departure)) return;
    const id = ++requestId.current;
    setBusy(true);
    setError("");
    try {
      const value = await routeRequest<Study>("/api/study", {
        ...query,
        radiusM: radius,
      });
      if (id === requestId.current) setStudy(value);
    } catch (e) {
      if (id === requestId.current) setError((e as Error).message);
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  };
  const saveCandidate = () => {
    if (!study || !scenario) return;
    const cost = Number(estimate);
    const key = JSON.stringify(scenario);
    const label =
      interventions[scenario.kind] +
      " · " +
      scenario.lat.toFixed(5) +
      ", " +
      scenario.lon.toFixed(5);
    setCandidates((old) => [
      ...old.filter((row) => row.key !== key),
      {
        key,
        label,
        cost: cost > 0 && Number.isFinite(cost) ? cost : null,
        study,
      },
    ]);
  };
  const exportCSV = () => {
    if (!study) return;
    const columns = [
      "Distrito",
      "Sección",
      "Población agregada de sección",
      "Personas de 65 años o más en la sección",
      "Ruta antes (m)",
      "Ruta después (m)",
      "Máximo sin descanso antes (m)",
      "Máximo sin descanso después (m)",
      "Sol antes (min)",
      "Sol después (min)",
      "Búsqueda limitada",
    ];
    const rows = study.rows.map((r) => [
      r.district,
      r.section,
      r.sectionResidents ?? "",
      r.sectionOlder ?? "",
      r.before?.meters ?? "",
      r.after?.meters ?? "",
      r.before?.maxWithoutRest ?? "",
      r.after?.maxWithoutRest ?? "",
      r.before?.sunMin ?? "",
      r.after?.sunMin ?? "",
      r.limited ? "sí" : "no",
    ]);
    const esc = (s: unknown) => '"' + String(s).replace(/"/g, '""') + '"';
    const url = URL.createObjectURL(
      new Blob(
        [
          "\ufeff",
          [columns, ...rows].map((row) => row.map(esc).join(";")).join("\n"),
        ],
        { type: "text/csv;charset=utf-8" },
      ),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "llegar-al-fresco-estudio.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const route = result?.routes[selected];
  const begin = (selectedRoute: Route) => {
    if (!origin || !destination || !navigator.geolocation) return;
    const preferencesMet = selectedRoute.fitsRest;
    if (!preferencesMet) {
      setError(
        "Elige un recorrido que respete tu límite de descanso para iniciar la navegación.",
      );
      return;
    }
    setNavigation(selectedRoute);
    setProgressM(0);
    walkDistance.current = 0;
    navi.current = {
      badFixes: 0,
      firstBad: 0,
      lastReroute: 0,
      rerouting: false,
      spoken: -1,
      carry: 0,
      restAt: 0,
    };
    try {
      localStorage.setItem(
        savedKey,
        JSON.stringify({
          origin,
          destination,
          route: selectedRoute,
          preferences,
        }),
      );
    } catch {
      /* Storage may be disabled. */
    }
    setNavigationMessage("Esperando una posición precisa…");
    setWalking(true);
  };
  const stop = () => {
    setWalking(false);
    setNavigation(null);
    setPosition(null);
    setProgressM(0);
    try {
      localStorage.removeItem(savedKey);
    } catch {
      /* Storage may be disabled. */
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  };
  useEffect(() => {
    if (!walking || !navigation || !destination) return;
    let disposed = false;
    const watch = navigator.geolocation.watchPosition(
      async (fix) => {
        if (disposed) return;
        const coords: Position = [fix.coords.longitude, fix.coords.latitude];
        setPosition(coords);
        if (fix.coords.accuracy > 65) {
          setNavigationMessage(
            "GPS impreciso. Sigue consultando las instrucciones.",
          );
          return;
        }
        const p = progress(
          coords,
          navigation.geometry.coordinates,
          walkDistance.current,
        );
        const time = Date.now(),
          state = navi.current;
        if (p.distance > Math.max(30, fix.coords.accuracy * 2)) {
          state.badFixes++;
          if (state.badFixes === 1) state.firstBad = time;
          if (
            state.badFixes >= 3 &&
            time - state.firstBad >= 12000 &&
            !state.rerouting &&
            time - state.lastReroute > 30000
          ) {
            state.lastReroute = time;
            state.rerouting = true;
            if (!navigator.onLine) {
              state.rerouting = false;
              setNavigationMessage(
                "Sin conexión. Conservamos las instrucciones de la ruta guardada.",
              );
              return;
            }
            setNavigationMessage("Buscando una alternativa desde tu posición…");
            try {
              const used = Math.max(
                0,
                state.carry + walkDistance.current - state.restAt,
              );
              const update = await routeRequest<RouteResponse>("/api/routes", {
                origin: point(coords),
                destination: point(destination.coordinates),
                departure: madridNow(),
                preferences,
                scenario: null,
                live: true,
                initialSinceRest: used,
              });
              if (disposed) return;
              if (update.routes[0]) {
                const next = update.routes[0];
                setNavigation(next);
                setProgressM(0);
                walkDistance.current = 0;
                state.carry = used;
                state.restAt = 0;
                state.spoken = -1; // la voz vuelve a anunciar desde el primer paso
                setNavigationMessage("Trayecto actualizado.");
                try {
                  localStorage.setItem(
                    savedKey,
                    JSON.stringify({
                      origin: mapPlace(coords, "Salida actualizada"),
                      destination,
                      route: next,
                      preferences,
                    }),
                  );
                } catch {}
              } else
                setNavigationMessage(
                  "No encontramos una alternativa que cumpla tus límites.",
                );
            } catch {
              if (!disposed)
                setNavigationMessage(
                  "No se pudo actualizar la ruta. Consulta las instrucciones guardadas.",
                );
            } finally {
              state.rerouting = false;
            }
          }
          return;
        }
        state.badFixes = 0;
        walkDistance.current = p.at;
        setProgressM(p.at);
        const next = navigation.steps.findIndex(
          (s) =>
            s.atM > p.at - 4 &&
            (s.action !== "rest" || s.atM > state.restAt + 2),
        );
        if (
          meters(coords, destination.coordinates) <
          Math.max(15, fix.coords.accuracy)
        ) {
          setNavigationMessage(
            "Estás cerca del destino. Comprueba la entrada.",
          );
        } else {
          const remaining =
            preferences.rest == null
              ? null
              : preferences.rest -
                Math.max(0, state.carry + p.at - state.restAt);
          const nextText =
            next >= 0
              ? instruction(navigation.steps[next])
              : "Continúa hacia el destino.";
          setNavigationMessage(
            remaining !== null && remaining < 0
              ? "Has alcanzado tu límite sin descanso. " + nextText
              : nextText,
          );
        }
        if (
          voice &&
          next >= 0 &&
          next !== state.spoken &&
          navigation.steps[next].atM - p.at < 45 &&
          "speechSynthesis" in window
        ) {
          state.spoken = next;
          const signal = new SpeechSynthesisUtterance(
            instruction(navigation.steps[next]),
          );
          signal.lang = "es-ES";
          window.speechSynthesis.speak(signal);
        }
      },
      () =>
        setNavigationMessage(
          "Ubicación no disponible. Puedes seguir la lista de pasos.",
        ),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 },
    );
    return () => {
      disposed = true;
      navigator.geolocation.clearWatch(watch);
    };
  }, [walking, navigation, destination, voice, preferences]);
  const comparable = (response: RouteResponse | null) => {
    const compatible = response?.routes.filter((r) => r.fitsRest);
    return (
      compatible?.find(
        (r) => r.style === (kind === "shade" ? "shade" : "comfort"),
      ) || compatible?.[0]
    );
  };
  const current = comparable(baseline),
    proposed = comparable(result);
  return (
    <>
      <header>
        <a href="#" className="brand" aria-label="Llegar al fresco, inicio">
          <Logo />
        </a>
        {mode === "inicio" ? (
          <button
            type="button"
            className="link-button tecnicos-link"
            onClick={() => {
              setMode("informe");
              invalidate();
            }}
          >
            Para ayuntamientos →
          </button>
        ) : (
        <nav aria-label="Herramientas para técnicos">
          <button
            type="button"
            className="volver"
            onClick={() => {
              setMode("inicio");
              invalidate();
              setScenario(null);
            }}
          >
            ← App ciudadana
          </button>
          <button
            type="button"
            aria-pressed={mode === "informe"}
            onClick={() => {
              setMode("informe");
              invalidate();
              setScenario(null);
            }}
          >
            Informe de uso
          </button>
          <button
            type="button"
            aria-pressed={mode === "walk"}
            onClick={() => {
              setMode("walk");
              invalidate();
              setScenario(null);
            }}
          >
            Recorrido detallado
          </button>
          <button
            type="button"
            disabled={!!navigation}
            aria-pressed={mode === "city"}
            onClick={() => {
              setMode("city");
              invalidate();
            }}
          >
            Simulador de mejoras
          </button>
          <button
            type="button"
            disabled={!!navigation}
            aria-pressed={mode === "region"}
            onClick={() => {
              setMode("region");
              invalidate();
              setScenario(null);
            }}
          >
            Mapa regional
          </button>
        </nav>
        )}
        {mode !== "inicio" && (
          <a href="#fuentes" className="sources-link">
            Fuentes
          </a>
        )}
      </header>
      {mode === "inicio" ? (
        <Sencillo
          onProfessional={() => {
            setMode("informe");
            invalidate();
            window.scrollTo({ top: 0 });
          }}
        />
      ) : mode === "informe" ? (
        <Informe
          onSimulate={async (at?: Position, destino?: string) => {
            setMode("city");
            invalidate();
            window.scrollTo({ top: 0 });
            if (!at) return;
            // Banco estratégico del informe: el banco en ese punto, la zona alrededor y,
            // como destino, el lugar más cercano del tipo que más se repite allí.
            const kindOf = ["salud", "farmacia", "mayores", "biblioteca"].includes(destino || "")
              ? destino
              : "salud";
            try {
              const { results } = await api<{ results: Place[] }>(
                `/api/nearby?kind=${kindOf}&lon=${at[0]}&lat=${at[1]}&n=1`,
              );
              setOrigin(mapPlace(at, "Punto del banco estratégico"));
              if (results[0]) setDestination(results[0]);
              setScenario({ kind: "bench", lon: at[0], lat: at[1] });
              setKind("bench");
              setRadius(500);
              setNotice(
                "Banco estratégico cargado. Pulsa «Evaluar zona» para medir cuántos portales de alrededor ganan una ruta con él.",
              );
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      ) : mode === "region" ? (
        <Region />
      ) : (
      <main>
        <div className="page-intro">
          <div>
            <p className="kicker">MADRID CAPITAL</p>
            <h1>
              {mode === "walk" ? "Planifica tu paseo" : "Mejora un recorrido"}
            </h1>
            <p>
              {mode === "walk"
                ? "Compara itinerarios según tus descansos, las cuestas y la sombra."
                : "Simula un banco, un rebaje o sombra y mide qué cambia antes de intervenir."}
            </p>
          </div>
          <button
            className="secondary"
            disabled={!!navigation}
            onClick={() => void example()}
          >
            Cargar ejemplo
          </button>
        </div>
        <div className="workspace">
          <section className="planner" aria-label="Configurar recorrido">
            <div className="section-title">
              <h2>Origen y destino</h2>
              <button
                className="link-button"
                type="button"
                disabled={!!navigation}
                onClick={locate}
              >
                Usar mi ubicación
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void solve();
              }}
            >
              <fieldset disabled={!!navigation}>
                <Address
                  label="Salida"
                  value={origin}
                  onChange={(p) => selectPlace("origin", p)}
                  onMap={() => activateMap("origin")}
                />
                <Address
                  label="Llegada"
                  departure={departure}
                  value={destination}
                  onChange={(p) => selectPlace("destination", p)}
                  onMap={() => activateMap("destination")}
                />
                {!!destination?.hours && (
                  <p className="form-note">
                    Horario publicado: {destination.hours}
                    {destination.url && (
                      <>
                        {" "}
                        <a
                          href={destination.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Consultar programa
                        </a>
                        .
                      </>
                    )}
                  </p>
                )}
                <div className="departure-heading">
                  <label htmlFor="when">
                    Salida prevista <small>hora de Madrid</small>
                  </label>
                  {chosenDeparture !== null && (
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        setChosenDeparture(null);
                        setAutomaticDeparture(madridNow());
                        invalidate();
                        setCandidates([]);
                      }}
                    >
                      Usar la hora actual
                    </button>
                  )}
                </div>
                <input
                  id="when"
                  type="datetime-local"
                  required
                  value={departure}
                  onInput={(e) => {
                    setChosenDeparture(e.currentTarget.value);
                    invalidate();
                    setCandidates([]);
                  }}
                />
                <div className="rest-setting">
                  <label htmlFor="rest">Máximo sin descanso</label>
                  <select
                    id="rest"
                    value={preferences.rest ?? ""}
                    onChange={(e) => {
                      setOption(
                        "rest",
                        e.target.value ? Number(e.target.value) : null,
                      );
                      invalidate();
                      setCandidates([]);
                    }}
                  >
                    <option value="">Sin límite</option>
                    {[
                      50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000,
                    ].map((x) => (
                      <option key={x} value={x}>
                        {x} metros
                      </option>
                    ))}
                  </select>
                </div>
                <div className="stairs-setting">
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={preferences.avoidStairs}
                      aria-describedby="stairs-coverage"
                      onChange={(e) => {
                        setOption("avoidStairs", e.target.checked);
                        invalidate();
                        setCandidates([]);
                      }}
                    />
                    Evitar escaleras
                  </label>
                  <p id="stairs-coverage" className="form-note">
                    Se aplica a las escaleras registradas en OpenStreetMap.
                  </p>
                </div>
                <details className="preferences">
                  <summary>Más preferencias</summary>
                  <label>
                    Ritmo del paseo
                    <select
                      value={preferences.pace}
                      onChange={(e) => {
                        setOption("pace", Number(e.target.value));
                        invalidate();
                        setCandidates([]);
                      }}
                    >
                      <option value=".65">Tranquilo</option>
                      <option value="1">Habitual</option>
                      <option value="1.35">Ágil</option>
                    </select>
                  </label>
                  <label>
                    Ancho imprescindible
                    <select
                      value={preferences.width ?? ""}
                      onChange={(e) => {
                        setOption(
                          "width",
                          e.target.value ? Number(e.target.value) : null,
                        );
                        invalidate();
                        setCandidates([]);
                      }}
                    >
                      <option value="">Preferir acera ancha</option>
                      <option value="1.2">Al menos 1,2 m documentados</option>
                      <option value="1.5">Al menos 1,5 m documentados</option>
                      <option value="1.8">Al menos 1,8 m documentados</option>
                    </select>
                  </label>
                  <label>
                    Pendiente máxima imprescindible
                    <select
                      value={preferences.slope ?? ""}
                      onChange={(e) => {
                        setOption(
                          "slope",
                          e.target.value ? Number(e.target.value) : null,
                        );
                        invalidate();
                        setCandidates([]);
                      }}
                    >
                      <option value="">Preferir menos cuestas</option>
                      <option value="4">4% documentado</option>
                      <option value="6">6% documentado</option>
                      <option value="8">8% documentado</option>
                    </select>
                  </label>
                  <p className="form-note">
                    Los límites imprescindibles excluyen tramos sin ancho o
                    pendiente documentados.
                  </p>
                </details>
                <button
                  className="primary"
                  type="submit"
                  disabled={busy || !departure}
                >
                  {busy ? "Calculando…" : "Comparar rutas"}
                </button>
              </fieldset>
              {!!notice && (
                <p role="status" className="form-note">
                  {notice}
                </p>
              )}
              {!!error && (
                <p role="alert" className="error">
                  {error}
                </p>
              )}
            </form>
            {mode === "city" && (
              <section className="municipal" aria-label="Simular intervención">
                <h2>Intervención</h2>
                <label htmlFor="intervention">Tipo de mejora</label>
                <select
                  id="intervention"
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value as Improvement["kind"]);
                    setScenario(null);
                    invalidate();
                  }}
                >
                  {Object.entries(interventions).map(([k, name]) => (
                    <option key={k} value={k}>
                      {name}
                    </option>
                  ))}
                </select>
                <button
                  className="secondary"
                  onClick={() => activateMap("scenario")}
                >
                  Situar en el mapa
                </button>
                <button
                  className="link-button"
                  disabled={!scenario}
                  onClick={() => {
                    setScenario(null);
                    void solve(null);
                  }}
                >
                  Quitar intervención
                </button>
                <label htmlFor="radius">Radio de estudio</label>
                <select
                  id="radius"
                  value={radius}
                  disabled={busy}
                  onChange={(e) => {
                    setRadius(Number(e.target.value));
                    setStudy(null);
                    setBankPlan(null);
                    setCandidates([]);
                  }}
                >
                  {[100, 250, 500].map((n) => (
                    <option key={n} value={n}>
                      {n} metros
                    </option>
                  ))}
                </select>
                <button
                  className="secondary"
                  disabled={!scenario || busy || !origin || !destination}
                  onClick={() => void computeStudy()}
                >
                  Evaluar zona
                </button>
                <p className="form-note">
                  El radio se mide desde la salida y mantiene los mismos
                  portales cuando cambias la intervención.
                </p>
                <div className="bank-plan-controls">
                  <button
                    type="button"
                    className="secondary"
                    disabled={
                      busy ||
                      !origin ||
                      !destination ||
                      !departure ||
                      preferences.rest === null
                    }
                    onClick={() => void recommendBanks()}
                  >
                    Buscar ubicaciones para bancos
                  </button>
                  {preferences.rest === null && (
                    <p className="form-note">
                      Fija un máximo sin descanso para buscar ubicaciones.
                    </p>
                  )}
                  {bankPlan && (
                    <a href="#priorizar-bancos">Ver comparación de bancos</a>
                  )}
                </div>
              </section>
            )}
          </section>
          <section
            className={
              bankPins.length ? "map-panel with-bank-plan" : "map-panel"
            }
            ref={layout}
            aria-label="Mapa y navegación"
          >
            {pick && (
              <div className="map-command" role="status">
                Marca{" "}
                {pick === "scenario"
                  ? "dónde quieres situar la mejora"
                  : pick === "origin"
                    ? "la salida"
                    : "el destino"}{" "}
                en el mapa.{" "}
                <button onClick={() => setPick(null)}>Cancelar</button>
              </div>
            )}
            <Map
              origin={origin}
              destination={destination}
              scenario={mode === "city" ? scenario : null}
              routes={navigation ? [navigation] : result?.routes || noRoutes}
              additionalPoints={bankPins}
              selected={navigation ? 0 : selected}
              layer={layer}
              placing={pick !== null}
              position={position}
              onPick={choosePoint}
            />
            {!pick && !!(navigation || route)?.segments?.length && (
              <label className="map-layer">
                Capa del recorrido
                <select
                  value={layer}
                  onChange={(e) => setLayer(e.target.value as MapLayer)}
                >
                  <option value="route">Itinerarios y paradas</option>
                  {Object.entries(overlays).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div
              className={layer === "route" ? "legend" : "legend thematic"}
              aria-label="Leyenda del mapa"
            >
              {layer === "route"
                ? [
                    "Recorrido elegido",
                    "Alternativa",
                    "Banco",
                    "Simulación",
                  ].map((label) => (
                    <span key={label}>
                      <i /> {label}
                    </span>
                  ))
                : overlays[layer].labels.map((label) => (
                    <span key={label}>
                      <i /> {label}
                    </span>
                  ))}
              {bankPlan?.options.length ? (
                <span className="legend-candidate">
                  <i /> Banco candidato
                </span>
              ) : null}
              {bankPlan?.footfall.length ? (
                <span className="legend-footfall">
                  <i /> Punto de aforo
                </span>
              ) : null}
            </div>
          </section>
        </div>
        {mode === "city" && bankPlan && (
          <BankPlanResults
            plan={bankPlan}
            busy={busy}
            onSimulate={simulateBank}
          />
        )}
        {navigation && (
          <section className="navigation" aria-label="Navegación activa">
            <div className="section-title">
              <h2>Navegación a pie</h2>
              <button className="secondary" onClick={stop}>
                Terminar
              </button>
            </div>
            <p role="status">{navigationMessage}</p>
            <div className="button-row">
              {!walking && (
                <button className="primary" onClick={() => begin(navigation)}>
                  Reanudar
                </button>
              )}
              <button
                className="secondary"
                onClick={() => {
                  navi.current.restAt = progressM;
                  navi.current.carry = 0;
                  setNavigationMessage("Descanso registrado.");
                }}
              >
                He descansado
              </button>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={voice}
                  onChange={(e) => setVoice(e.target.checked)}
                />{" "}
                Indicaciones por voz
              </label>
            </div>
            <Details route={navigation} />
          </section>
        )}
        {result && (
          <section
            id="resultados"
            className="results"
            aria-label="Comparación de rutas"
          >
            <div className="section-title">
              <h2>Compara tus opciones</h2>
              <button className="secondary" onClick={() => window.print()}>
                Imprimir ruta
              </button>
            </div>
            {result.weather && (
              <p className="weather">
                <strong>{fmt(result.weather.temperatureC)} °C</strong> ·{" "}
                {result.weather.issued ? (
                  <>
                    Previsión municipal de AEMET para las{" "}
                    {result.weather.at.slice(11)}. Emitida el{" "}
                    {result.weather.issued.replace("T", " a las ")}.
                  </>
                ) : (
                  <>
                    Observación histórica del 1 de julio de 2025.{" "}
                    {result.weather.source}. La estación está fuera del
                    recorrido.
                  </>
                )}
              </p>
            )}
            {!result.weather && (
              <p className="form-note">
                Sin previsión disponible para la hora seleccionada. La
                estimación de sombra sigue disponible si hay datos de
                superficie.
              </p>
            )}
            {result.limited && (
              <p className="form-note">
                La búsqueda de alguna alternativa alcanzó su límite de cálculo.
              </p>
            )}
            {!result.limited &&
              result.routes.length > 0 &&
              !result.routes.some((r) => r.fitsRest) && (
                <p className="form-note">
                  No encontramos una alternativa dentro de tu límite de descanso
                  en hasta {fmt(result.alternativeMaxM)} m de recorrido.
                </p>
              )}
            {!result.routes.length && (
              <p className="error">
                No encontramos un recorrido con las condiciones seleccionadas y
                la información disponible. Puedes revisar los límites
                imprescindibles o cambiar los puntos.
              </p>
            )}
            <div
              className="route-options"
              role="group"
              aria-label="Escoger ruta"
            >
              {result.routes.map((r, i) => (
                <button
                  className="route-option"
                  key={r.style}
                  aria-pressed={i === selected}
                  onClick={() => setSelected(i)}
                >
                  <strong>{r.label}</strong>
                  <span>
                    {fmt(r.meters)} m · {fmt(r.durationMin)} min
                  </span>
                  <small>
                    {r.fitsRest
                      ? "Hasta " + fmt(r.maxWithoutRest) + " m sin descanso"
                      : "Supera tu límite sin descanso"}
                  </small>
                  {r.barriers.includes("Escaleras cartografiadas") && (
                    <small className="route-stairs">
                      Incluye escaleras cartografiadas
                    </small>
                  )}
                </button>
              ))}
            </div>
            {route &&
              destination?.openFrom &&
              destination.openUntil &&
              (() => {
                const arrival = new Date(
                  Date.parse(result.requestedDeparture + "Z") +
                    route.durationMin * 60000,
                )
                  .toISOString()
                  .slice(0, 16);
                return (
                  (arrival < destination.openFrom ||
                    arrival >= destination.openUntil) && (
                    <p className="form-note">
                      La llegada calculada queda fuera del horario publicado del
                      refugio.
                    </p>
                  )
                );
              })()}
            {route && (
              <>
                <p className="print-only">
                  {origin?.label} → {destination?.label} · {fmt(route.meters)} m
                  · {route.label}
                </p>
                <Details route={route} />
                {mode === "walk" && !navigation && (
                  <button
                    className="primary start"
                    onClick={() => begin(route)}
                    disabled={!route.fitsRest || !navigator.geolocation}
                  >
                    Empezar a caminar
                  </button>
                )}
              </>
            )}
            {baseline && (
              <div className="comparison">
                <h3>Efecto de la intervención en este trayecto</h3>
                <p>
                  Antes:{" "}
                  {current
                    ? `${fmt(current.meters)} m · ${fmt(current.maxWithoutRest)} m seguidos sin descanso`
                    : "sin ruta encontrada que cumpla el límite"}
                  .
                </p>
                <p>
                  Después:{" "}
                  {proposed
                    ? `${fmt(proposed.meters)} m · ${fmt(proposed.maxWithoutRest)} m seguidos sin descanso`
                    : "sin ruta encontrada que cumpla el límite"}
                  .
                </p>
                {current && proposed && (
                  <p>
                    Variación del tramo sin descanso:{" "}
                    {fmt(proposed.maxWithoutRest - current.maxWithoutRest)} m.
                    Variación estimada al sol:{" "}
                    {current.sunMin === null || proposed.sunMin === null
                      ? "sin dato"
                      : fmt(proposed.sunMin - current.sunMin) + " min"}
                    .
                  </p>
                )}
              </div>
            )}
          </section>
        )}
        {study && (
          <section className="results study" aria-label="Estudio municipal">
            <div className="section-title">
              <h2>Impacto estimado en la zona</h2>
              <div className="button-row">
                <button className="secondary" onClick={exportCSV}>
                  Descargar CSV
                </button>
                <button className="secondary" onClick={() => window.print()}>
                  Imprimir / PDF
                </button>
              </div>
            </div>
            <p>
              <strong>
                {study.newPaths} de {study.completed}
              </strong>{" "}
              orígenes evaluados ganan un recorrido dentro del límite. Radio de{" "}
              {study.radiusM} m.
              {study.completed < study.sample && (
                <>
                  {" "}
                  Quedan {study.sample - study.completed} orígenes con cálculo
                  parcial.
                </>
              )}
            </p>
            <p>
              {study.reducedRestPaths} acortan el tramo más largo sin descanso ·{" "}
              {study.reducedSunPaths} reducen la exposición estimada al sol ·{" "}
              {study.lostPaths} pierden la opción encontrada.
            </p>
            <div className="button-row">
              <label htmlFor="estimated-cost">
                Coste estimado (€), opcional
              </label>
              <input
                id="estimated-cost"
                type="number"
                min="0"
                value={estimate}
                onChange={(e) => setEstimate(e.target.value)}
              />
              <button className="secondary" onClick={saveCandidate}>
                Añadir a la comparación
              </button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Distrito</th>
                    <th>Sección</th>
                    <th>Máx. antes</th>
                    <th>Máx. después</th>
                    <th>Sol antes / después</th>
                  </tr>
                </thead>
                <tbody>
                  {study.rows.map((r, i) => (
                    <tr key={i}>
                      <td>{r.district}</td>
                      <td>
                        {r.section}
                        {r.sectionResidents != null && (
                          <small>
                            {" "}
                            · {fmt(r.sectionResidents)} residentes
                            {r.sectionOlder != null && (
                              <> · {fmt(r.sectionOlder)} de 65 años o más</>
                            )}
                          </small>
                        )}
                      </td>
                      <td>
                        {r.before
                          ? metric(r.before.maxWithoutRest, "m")
                          : r.limited
                            ? "Búsqueda limitada"
                            : "Sin ruta"}
                      </td>
                      <td>
                        {r.after
                          ? metric(r.after.maxWithoutRest, "m")
                          : r.limited
                            ? "Búsqueda limitada"
                            : "Sin ruta"}
                      </td>
                      <td>
                        {metric(r.before?.sunMin ?? null, "min")} /{" "}
                        {metric(r.after?.sunMin ?? null, "min")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="form-note">
              Cada búsqueda limita la longitud máxima de la alternativa para
              acotar el desvío. Los recuentos corresponden a portales
              muestreados y las mejoras son hipótesis de planificación.
            </p>
          </section>
        )}
        {mode === "city" && candidates.length > 0 && (
          <section
            className="results study"
            aria-label="Comparación de inversiones"
          >
            <div className="section-title">
              <h2>Comparación de inversiones</h2>
              <button className="secondary" onClick={() => setCandidates([])}>
                Vaciar comparación
              </button>
            </div>
            <p className="form-note">
              Las actuaciones se evalúan por separado con la misma muestra de
              portales, destino, horario y preferencias. Los importes se
              introducen manualmente.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Intervención</th>
                    <th>Opciones nuevas</th>
                    <th>Menor tramo sin descanso</th>
                    <th>Menos sol</th>
                    <th>Coste</th>
                    <th>Opciones nuevas / 1.000 €</th>
                  </tr>
                </thead>
                <tbody>
                  {[...candidates]
                    .sort((a, b) => b.study.newPaths - a.study.newPaths)
                    .map((row) => (
                      <tr key={row.key}>
                        <td>{row.label}</td>
                        <td>
                          {row.study.newPaths} de {row.study.completed}
                        </td>
                        <td>{row.study.reducedRestPaths}</td>
                        <td>{row.study.reducedSunPaths}</td>
                        <td>{metric(row.cost, "€")}</td>
                        <td>
                          {row.cost && row.study.completed === row.study.sample
                            ? fmt((1000 * row.study.newPaths) / row.cost)
                            : "Sin dato comparable"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        <section id="fuentes" className="source-panel">
          <h2>Procedencia de los datos</h2>
          <p>
            {info
              ? fmt(info.portals) +
                " portales, " +
                fmt(info.networkEdges) +
                " tramos de red y " +
                fmt(info.benchConnections) +
                " bancos vinculados a caminos. Extracto OSM: " +
                info.version.osm
              : "Las fuentes estarán disponibles cuando el servidor pueda cargarse."}
          </p>
          <ul>
            {info?.sources.map((s) => (
              <li key={s.label}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.label}
                </a>
                <span>{s.date}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
      )}
      <footer>
        <span>Llegar al fresco</span>
        <span>Madrid capital · Datos abiertos</span>
      </footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
if ("serviceWorker" in navigator)
  void navigator.serviceWorker.register("/sw.js").catch(() => {});
