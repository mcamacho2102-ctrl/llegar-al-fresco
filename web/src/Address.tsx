import { useEffect, useId, useRef, useState } from "react";
import { api, Place, Position } from "./model";
import {
  borrarSitio,
  escucharSitios,
  guardarSitio,
  leerSitios,
  MiSitio,
  mismoSitio,
} from "./misSitios";

/* Tipos mínimos de la Web Speech API (no vienen en todas las versiones de lib.dom). */
interface AlternativaVoz {
  transcript: string;
}
interface FraseVoz {
  readonly isFinal: boolean;
  readonly length: number;
  [indice: number]: AlternativaVoz;
}
interface EventoResultadoVoz {
  readonly resultIndex: number;
  readonly results: { readonly length: number; [indice: number]: FraseVoz };
}
interface ReconocimientoVoz {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: EventoResultadoVoz) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type ConstructorVoz = new () => ReconocimientoVoz;
const Voz: ConstructorVoz | undefined = (() => {
  try {
    const w = window as unknown as {
      SpeechRecognition?: ConstructorVoz;
      webkitSpeechRecognition?: ConstructorVoz;
    };
    return w.SpeechRecognition || w.webkitSpeechRecognition;
  } catch {
    return undefined;
  }
})();
const ERRORES_VOZ: Record<string, string> = {
  "not-allowed":
    "No tenemos permiso para usar el micrófono. Puedes escribir la dirección o darle permiso en el navegador.",
  "service-not-allowed":
    "Este navegador no deja buscar hablando. Puedes escribir la dirección.",
  "no-speech": "No te he oído. Pulsa 🎤 y habla cerca del móvil.",
  "audio-capture": "No encontramos el micrófono. Puedes escribir la dirección.",
  network: "Para buscar hablando hace falta conexión a internet.",
};
const NOMBRES_RAPIDOS = ["🏠 Casa", "🩺 Médico", "💊 Farmacia"];
/** Evita que el campo pierda el foco (y se cierre la lista) al tocar un botón. */
const sinPerderFoco = (e: { preventDefault: () => void }) => e.preventDefault();

export default function Address({
  label,
  value,
  onChange,
  onMap,
  departure,
  near,
}: {
  label: string;
  departure?: string;
  /** Punto desde el que ordenar los negocios por cercanía (la salida, al buscar la llegada). */
  near?: Position | null;
  value: Place | null;
  onChange: (place: Place | null) => void;
  onMap: () => void;
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [active, setActive] = useState(-1);
  const [opened, setOpened] = useState(false);
  const [status, setStatus] = useState("");
  const cerca = near ? near.map((v) => v.toFixed(5)).join(",") : "";
  // Buscar hablando
  const [escuchando, setEscuchando] = useState(false);
  const [oido, setOido] = useState("");
  const [voz, setVoz] = useState("");
  const reconocimiento = useRef<ReconocimientoVoz | null>(null);
  const paradoAMano = useRef(false);
  const alCambiar = useRef(onChange);
  alCambiar.current = onChange;
  // Mis sitios
  const [sitios, setSitios] = useState<MiSitio[]>(leerSitios);
  const [verSitios, setVerSitios] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState("");
  useEffect(() => escucharSitios(() => setSitios(leerSitios())), []);
  useEffect(() => () => reconocimiento.current?.abort(), []);
  useEffect(() => {
    if (value) {
      setText(value.label);
      setOpened(false);
      setStatus("");
    }
  }, [value]);
  useEffect(() => {
    setGuardando(false);
    setAviso("");
    if (value) setVerSitios(false);
  }, [value]);
  useEffect(() => {
    if (!opened || value || text.trim().length < 3) return;
    const controller = new AbortController();
    setResults([]);
    setStatus("Buscando direcciones…");
    setActive(-1);
    const timer = window.setTimeout(async () => {
      try {
        const { results } = await api<{ results: Place[] }>(
          "/api/addresses?" +
            new URLSearchParams({
              q: text,
              ...(departure ? { at: departure } : {}),
              ...(cerca ? { cerca } : {}),
            }),
          { signal: controller.signal },
        );
        setResults(results);
        setStatus(
          results.length
            ? `${results.length} resultados`
            : "No hemos encontrado esa dirección.",
        );
      } catch (e) {
        if (!controller.signal.aborted)
          setStatus(
            "El buscador no está disponible. Puedes marcar el punto en el mapa.",
          );
      }
    }, 210);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [text, opened, value, departure, cerca]);
  const select = (place: Place) => {
    onChange(place);
    setOpened(false);
    setResults([]);
    setStatus("");
  };
  const show = opened && !value && text.trim().length >= 3;

  const parar = () => {
    // Lo ya dicho se reconoce igualmente; si no se dijo nada, no es un error.
    paradoAMano.current = true;
    reconocimiento.current?.stop();
  };
  const escuchar = () => {
    if (!Voz) return;
    if (reconocimiento.current) {
      parar();
      return;
    }
    paradoAMano.current = false;
    let entendido = false;
    let fallo = false;
    try {
      const rec = new Voz();
      rec.lang = "es-ES";
      rec.interimResults = true;
      rec.continuous = false;
      rec.maxAlternatives = 1;
      rec.onresult = (e) => {
        let final = "";
        let provisional = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const frase = e.results[i];
          const dicho = frase && frase[0] ? frase[0].transcript : "";
          if (frase && frase.isFinal) final += dicho;
          else provisional += dicho;
        }
        if (provisional.trim()) setOido(provisional.trim());
        const limpio = final.trim().replace(/[.。]+$/, "");
        if (limpio) {
          entendido = true;
          // Igual que si se hubiera escrito en el campo.
          setText(limpio);
          alCambiar.current(null);
          setOpened(true);
          setVoz("");
        }
      };
      rec.onerror = (e) => {
        if (e.error === "aborted") return;
        fallo = true;
        setVoz(
          ERRORES_VOZ[e.error] ||
            "No hemos podido escucharte. Puedes escribir la dirección.",
        );
      };
      rec.onend = () => {
        reconocimiento.current = null;
        setEscuchando(false);
        setOido("");
        if (!entendido && !fallo && !paradoAMano.current)
          setVoz("No te he entendido. Pulsa 🎤 y vuelve a intentarlo.");
      };
      reconocimiento.current = rec;
      setVoz("");
      setOido("");
      setVerSitios(false);
      rec.start();
      setEscuchando(true);
    } catch {
      reconocimiento.current = null;
      setEscuchando(false);
      setVoz("No hemos podido usar el micrófono. Puedes escribir la dirección.");
    }
  };

  const vacio = !value && text.trim() === "";
  const panelSitios =
    sitios.length > 0 && vacio && !escuchando && (verSitios || opened);
  const guardado = value ? sitios.find((s) => mismoSitio(s.place, value)) : undefined;
  const guardarComo = (nombre: string) => {
    if (!value) return;
    const quitado = guardarSitio(nombre, value);
    setGuardando(false);
    if (quitado === false) {
      setAviso(
        "No se ha podido guardar en este móvil (quizá estás en modo privado).",
      );
      return;
    }
    setSitios(leerSitios());
    setAviso(
      quitado
        ? `Guardado en tus sitios. Como solo caben 6, hemos quitado «${quitado.nombre}».`
        : "",
    );
  };
  const hint = escuchando
    ? "🎤 Te escucho… di la dirección o el sitio" + (oido ? `: «${oido}»` : "")
    : voz || status;

  return (
    <div className="address">
      <label htmlFor={id}>{label}</label>
      <div className={"address-line" + (Voz ? " con-voz" : "")}>
        <input
          id={id}
          role="combobox"
          autoComplete="off"
          placeholder="Calle y número, lugar o negocio"
          aria-expanded={show && results.length > 0}
          aria-controls={id + "-results"}
          aria-autocomplete="list"
          aria-activedescendant={
            show && active >= 0 ? id + "-option-" + active : undefined
          }
          value={text}
          onFocus={() => !value && setOpened(true)}
          onBlur={() => window.setTimeout(() => setOpened(false), 150)}
          onChange={(e) => {
            setText(e.target.value);
            onChange(null);
            setOpened(true);
            setVoz("");
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpened(false);
              return;
            }
            if (e.key === "ArrowDown" && results.length) {
              e.preventDefault();
              setOpened(true);
              setActive((active + 1) % results.length);
            }
            if (e.key === "ArrowUp" && results.length) {
              e.preventDefault();
              setActive((active - 1 + results.length) % results.length);
            }
            if (e.key === "Enter" && active >= 0 && results[active] && show) {
              e.preventDefault();
              select(results[active]);
            }
          }}
        />
        {Voz && (
          <button
            className={"place-button boton-voz" + (escuchando ? " escuchando" : "")}
            type="button"
            onMouseDown={sinPerderFoco}
            onClick={escuchar}
            aria-label={escuchando ? "Parar de escuchar" : "Buscar hablando"}
            title={escuchando ? "Parar de escuchar" : "Buscar hablando"}
          >
            <span aria-hidden="true">{escuchando ? "⏹" : "🎤"}</span>
          </button>
        )}
        <button
          className="place-button"
          type="button"
          onClick={onMap}
          aria-label={"Marcar " + label.toLowerCase() + " en el mapa"}
          title="Marcar en el mapa"
        >
          Mapa
        </button>
      </div>
      {sitios.length > 0 && vacio && !escuchando && (
        <button
          className="link-button mis-sitios-abrir"
          type="button"
          aria-expanded={panelSitios}
          onMouseDown={sinPerderFoco}
          onClick={() => {
            if (panelSitios) {
              setVerSitios(false);
              setOpened(false);
            } else setVerSitios(true);
          }}
        >
          ⭐ Mis sitios
        </button>
      )}
      {panelSitios && (
        <div className="mis-sitios" role="group" aria-label="Tus sitios guardados">
          {sitios.map((s) => (
            <div className="mi-sitio" key={s.nombre}>
              <button
                type="button"
                className="mi-sitio-elegir"
                onMouseDown={sinPerderFoco}
                onClick={() => {
                  setVerSitios(false);
                  select(s.place);
                }}
              >
                <strong>{s.nombre}</strong>
                <small>{s.place.label}</small>
              </button>
              <button
                type="button"
                className="mi-sitio-borrar"
                aria-label={`Borrar «${s.nombre}» de tus sitios`}
                title="Borrar de tus sitios"
                onMouseDown={sinPerderFoco}
                onClick={() => {
                  setVerSitios(true);
                  let seguro = true;
                  try {
                    seguro = window.confirm(`¿Quitar «${s.nombre}» de tus sitios?`);
                  } catch {
                    seguro = true;
                  }
                  if (seguro && borrarSitio(s.nombre)) setSitios(leerSitios());
                }}
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>
          ))}
          <p className="mis-sitios-nota">
            Se guardan solo en este móvil. No se envían a ningún servidor.
          </p>
        </div>
      )}
      {show && results.length > 0 && (
        <ul id={id + "-results"} role="listbox">
          {results.map((item, index) => (
            <li
              key={item.id}
              id={id + "-option-" + index}
              role="option"
              aria-selected={index === active}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(index)}
              onClick={() => select(item)}
            >
              <strong>{item.label}</strong>
              <small>{item.district || item.source}</small>
            </li>
          ))}
        </ul>
      )}
      {(show || escuchando || !!voz) && (
        <div
          className={"search-hint" + (escuchando ? " voz-escuchando" : "")}
          role="status"
        >
          {hint}
        </div>
      )}
      {escuchando && (
        <button
          className="link-button voz-parar"
          type="button"
          onMouseDown={sinPerderFoco}
          onClick={parar}
        >
          ⏹ Parar
        </button>
      )}
      {value && (
        <div className="guardar-sitio">
          {guardado ? (
            <p className="search-hint" role="status">
              ⭐ Guardado en tus sitios como «{guardado.nombre}»
            </p>
          ) : guardando ? (
            <div role="group" aria-label="¿Cómo quieres llamar a este sitio?">
              <p className="search-hint">¿Cómo lo llamamos?</p>
              <div className="guardar-opciones">
                {NOMBRES_RAPIDOS.map((nombre) => (
                  <button
                    key={nombre}
                    type="button"
                    className="place-button"
                    onClick={() => guardarComo(nombre)}
                  >
                    {nombre}
                  </button>
                ))}
                <button
                  type="button"
                  className="place-button"
                  onClick={() => {
                    let escrito: string | null = null;
                    try {
                      escrito = window.prompt(
                        "Escribe un nombre corto para este sitio (por ejemplo: Hija, Parque, Mercado)",
                        "",
                      );
                    } catch {
                      escrito = null;
                    }
                    const nombre = (escrito || "").trim().slice(0, 20);
                    if (nombre) guardarComo("📍 " + nombre);
                  }}
                >
                  ✏️ Otro…
                </button>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setGuardando(false)}
                >
                  Cancelar
                </button>
              </div>
              <p className="mis-sitios-nota">
                Se guardan solo en este móvil. No se envían a ningún servidor.
              </p>
            </div>
          ) : (
            <button
              type="button"
              className="link-button guardar-abrir"
              onClick={() => {
                setAviso("");
                setGuardando(true);
              }}
            >
              ☆ Guardar este sitio
            </button>
          )}
          {aviso && (
            <p className="search-hint" role="status">
              {aviso}
            </p>
          )}
        </div>
      )}
      {show && status.startsWith("No hemos") && (
        <button
          className="link-button search-hint"
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={async () => {
            try {
              setStatus("Consultando CartoCiudad…");
              const result = await api<{ results: Place[] }>(
                "/api/addresses/external?q=" + encodeURIComponent(text),
                { method: "POST" },
              );
              setResults(result.results);
              setStatus(
                result.results.length
                  ? "Resultados de CartoCiudad"
                  : "Sin coincidencias. Marca el portal en el mapa.",
              );
            } catch (e) {
              setStatus((e as Error).message);
            }
          }}
        >
          Buscar esta dirección en CartoCiudad (IGN)
        </button>
      )}
    </div>
  );
}
