import { useEffect, useId, useState } from "react";
import { api, Place } from "./model";
export default function Address({
  label,
  value,
  onChange,
  onMap,
  departure,
}: {
  label: string;
  departure?: string;
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
  useEffect(() => {
    if (value) {
      setText(value.label);
      setOpened(false);
      setStatus("");
    }
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
  }, [text, opened, value, departure]);
  const select = (place: Place) => {
    onChange(place);
    setOpened(false);
    setResults([]);
    setStatus("");
  };
  const show = opened && !value && text.trim().length >= 3;
  return (
    <div className="address">
      <label htmlFor={id}>{label}</label>
      <div className="address-line">
        <input
          id={id}
          role="combobox"
          autoComplete="off"
          placeholder="Calle y número o lugar"
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
      {show && (
        <div className="search-hint" role="status">
          {status}
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
