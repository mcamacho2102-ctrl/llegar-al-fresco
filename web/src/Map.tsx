import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { GeoJSONSource, Map as MapLibre, NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { Feature, FeatureCollection, LineString, Point } from "geojson";
import { api, Improvement, MapLayer, Place, Position, Route } from "./model";
maplibregl.setWorkerUrl(workerUrl);

const empty = (): FeatureCollection => ({
  type: "FeatureCollection",
  features: [],
});
const marker = (
  coordinates: Position,
  kind: string,
  label: string,
): Feature<Point> => ({
  type: "Feature",
  geometry: { type: "Point", coordinates },
  properties: { kind, label },
});
export default function Map({
  origin,
  destination,
  routes,
  additionalPoints,
  selected,
  layer,
  placing,
  scenario,
  position,
  onPick,
  simple = false,
  showPois = true,
}: {
  origin: Place | null;
  destination: Place | null;
  routes: Route[];
  additionalPoints: Place[];
  selected: number;
  layer: MapLayer;
  placing: boolean;
  scenario: Improvement | null;
  position: Position | null;
  onPick: (p: Position) => void;
  /** Modo ciudadano: marcadores grandes y solo los bancos de la ruta. */
  simple?: boolean;
  /** Muestra todos los bancos, fuentes y aseos de la vista (a partir de zoom 14). */
  showPois?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null),
    map = useRef<MapLibre | null>(null),
    click = useRef(onPick),
    poisWanted = useRef(showPois),
    placingRef = useRef(placing),
    refreshPois = useRef<() => void>(() => {});
  const [ready, setReady] = useState(false),
    [failed, setFailed] = useState(false);
  click.current = onPick;
  poisWanted.current = showPois;
  placingRef.current = placing;
  useEffect(() => {
    try {
      const m = new maplibregl.Map({
        container: host.current!,
        center: [-3.704, 40.415],
        zoom: 12.9,
        // Teselas vectoriales gratuitas de OpenFreeMap (datos © OpenStreetMap).
        style: "https://tiles.openfreemap.org/styles/positron",
      });
      map.current = m;
      m.addControl(new NavigationControl({ showCompass: false }), "top-right");
      m.on("click", (event) =>
        click.current([event.lngLat.lng, event.lngLat.lat]),
      );
      m.on("load", () => {
        for (const id of ["pois", "routes", "segments", "pins"])
          m.addSource(id, { type: "geojson", data: empty() });
        m.addLayer({
          id: "pois",
          type: "circle",
          source: "pois",
          paint: {
            "circle-radius": 3.5,
            "circle-color": [
              "match",
              ["get", "kind"],
              "bench",
              "#1e7e5f",
              "drinking_water",
              "#2a82a7",
              "toilets",
              "#784dab",
              "refuge",
              "#cf8b23",
              "elderly",
              "#b0457a",
              "pharmacy",
              "#1e7e5f",
              "#657868",
            ],
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 1,
          },
        });
        m.addLayer({
          id: "halo",
          type: "line",
          source: "routes",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#fff", "line-width": simple ? 13 : 9 },
        });
        m.addLayer({
          id: "routes",
          type: "line",
          source: "routes",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ["case", ["get", "active"], "#0e5242", "#9bada5"],
            "line-width": ["case", ["get", "active"], simple ? 8 : 6, 3],
          },
        });
        m.addLayer({
          id: "segments",
          type: "line",
          source: "segments",
          paint: {
            "line-color": [
              "match",
              ["get", "class"],
              "high",
              "#b8592a",
              "middle",
              "#cf8b23",
              "low",
              "#1e7e5f",
              "#9aa5a0",
            ],
            "line-width": simple ? 8 : 6,
          },
        });
        m.addLayer({
          id: "pins",
          type: "circle",
          source: "pins",
          paint: {
            "circle-radius": [
              "match",
              ["get", "kind"],
              "rest",
              6,
              "footfall",
              7,
              9,
            ],
            "circle-color": [
              "match",
              ["get", "kind"],
              "destination",
              "#8e4320",
              "scenario",
              "#cf8b23",
              "bank-candidate",
              "#8e4320",
              "footfall",
              "#67438e",
              "position",
              "#237ac3",
              "#0e5242",
            ],
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 2,
          },
        });
        const popup = (event: maplibregl.MapMouseEvent) => {
          if (placingRef.current) return;
          const found = m.queryRenderedFeatures(event.point, {
            layers: ["pins", "pois"],
          })[0];
          if (found?.properties?.label)
            new maplibregl.Popup()
              .setLngLat(event.lngLat)
              .setText(found.properties.label)
              .addTo(m);
        };
        m.on("click", popup);
        let pending: AbortController | undefined;
        const refresh = async () => {
          pending?.abort();
          if (m.getZoom() < 14 || !poisWanted.current) {
            (m.getSource("pois") as GeoJSONSource).setData(empty());
            return;
          }
          const b = m.getBounds();
          pending = new AbortController();
          try {
            const result = await api<{ features: Place[] }>(
              `/api/points?w=${b.getWest()}&s=${b.getSouth()}&e=${b.getEast()}&n=${b.getNorth()}`,
              { signal: pending.signal },
            );
            (m.getSource("pois") as GeoJSONSource).setData({
              type: "FeatureCollection",
              features: result.features.map((p) =>
                marker(p.coordinates, p.kind, p.label),
              ),
            });
          } catch {
            /* The route and its textual equivalent remain available. */
          }
        };
        m.on("moveend", refresh);
        refreshPois.current = () => void refresh();
        void refresh();
        setReady(true);
      });
      return () => {
        m.remove();
        map.current = null;
      };
    } catch {
      setFailed(true);
    }
  }, []);
  useEffect(() => {
    if (ready) refreshPois.current();
  }, [ready, showPois]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    const features: Feature<LineString>[] = routes
      .map<Feature<LineString>>((route, index) => ({
        type: "Feature",
        geometry: route.geometry,
        properties: { active: index === selected },
      }))
      .sort(
        (a, b) => Number(a.properties?.active) - Number(b.properties?.active),
      );
    (m.getSource("routes") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features,
    });
  }, [ready, routes, selected]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const segments = layer === "route" ? [] : routes[selected]?.segments || [];
    const features: Feature<LineString>[] = segments.map((segment) => {
      const value = layer === "route" ? null : segment[layer];
      let classification = "unknown";
      if (value !== null) {
        if (layer === "sun")
          classification =
            value === 1 ? "high" : value === 0 ? "low" : "middle";
        if (layer === "widthM")
          classification =
            value < 1.5 ? "high" : value < 1.8 ? "middle" : "low";
        if (layer === "slopePct")
          classification = value > 8 ? "high" : value > 4 ? "middle" : "low";
      }
      return {
        type: "Feature",
        geometry: { type: "LineString", coordinates: segment.coordinates },
        properties: { class: classification },
      };
    });
    (map.current.getSource("segments") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features,
    });
  }, [ready, routes, selected, layer]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    const routePoints = routes.length
      ? routes.flatMap((r) => r.geometry.coordinates)
      : [origin?.coordinates, destination?.coordinates].filter(
          (p): p is Position => !!p,
        );
    const points = [
      ...routePoints,
      ...additionalPoints.map((place) => place.coordinates),
    ];
    if (points.length > 1) {
      const bounds = new maplibregl.LngLatBounds(points[0], points[0]);
      points.forEach((p) => bounds.extend(p));
      m.fitBounds(bounds, { padding: 44, maxZoom: 16, duration: 300 });
    } else if (points.length === 1)
      m.easeTo({ center: points[0], zoom: 15, duration: 250 });
  }, [ready, routes, origin, destination, additionalPoints]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const features: Feature<Point>[] = additionalPoints
      .filter((place) => place.kind !== "bank-candidate")
      .map((place) => marker(place.coordinates, place.kind, place.label));
    if (origin && !simple)
      features.push(marker(origin.coordinates, "origin", origin.label));
    if (destination && !simple)
      features.push(
        marker(destination.coordinates, "destination", destination.label),
      );
    if (scenario)
      features.push(
        marker(
          [scenario.lon, scenario.lat],
          "scenario",
          "Intervención simulada",
        ),
      );
    if (position)
      features.push(marker(position, "position", "Tu posición aproximada"));
    if (!simple)
      for (const rest of routes[selected]?.rests || [])
        features.push(marker(rest.coordinates, "rest", rest.label));
    (map.current.getSource("pins") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features,
    });
  }, [
    ready,
    origin,
    destination,
    routes,
    selected,
    scenario,
    position,
    additionalPoints,
    simple,
  ]);
  useEffect(() => {
    // Modo ciudadano: salida «A», llegada «B» y bancos de la ruta numerados.
    const current = map.current;
    if (!ready || !current || !simple) return;
    const pin = (
      coordinates: Position,
      className: string,
      text: string,
      label: string,
    ) => {
      const element = document.createElement("div");
      element.className = "simple-pin " + className;
      element.textContent = text;
      element.setAttribute("role", "img");
      element.setAttribute("aria-label", label);
      return new maplibregl.Marker({ element })
        .setLngLat(coordinates)
        .setPopup(new maplibregl.Popup({ offset: 22 }).setText(label))
        .addTo(current);
    };
    const markers = [
      ...(routes[selected]?.rests || []).map((rest, index) =>
        pin(
          rest.coordinates,
          "pin-rest",
          String(index + 1),
          `Descanso ${index + 1}: banco en ${rest.label}`,
        ),
      ),
      ...(origin ? [pin(origin.coordinates, "pin-a", "A", "Salida: " + origin.label)] : []),
      ...(destination
        ? [pin(destination.coordinates, "pin-b", "B", "Llegada: " + destination.label)]
        : []),
    ];
    return () => markers.forEach((item) => item.remove());
  }, [ready, simple, origin, destination, routes, selected]);
  useEffect(() => {
    const current = map.current;
    if (!ready || !current) return;
    const markers = additionalPoints
      .filter((place) => place.kind === "bank-candidate")
      .map((place, index) => {
        const element = document.createElement("button");
        element.type = "button";
        element.className = "bank-pin";
        element.textContent = String(index + 1);
        element.setAttribute("aria-label", place.label);
        return new maplibregl.Marker({ element })
          .setLngLat(place.coordinates)
          .setPopup(new maplibregl.Popup().setText(place.label))
          .addTo(current);
      });
    return () => markers.forEach((marker) => marker.remove());
  }, [ready, additionalPoints]);

  useEffect(() => {
    if (!ready || !map.current) return;
    map.current.getCanvas().style.cursor = placing ? "crosshair" : "";
  }, [ready, placing]);

  return (
    <div className={placing ? "map-wrap placing" : "map-wrap"}>
      {placing && ready && (
        <button
          type="button"
          className="map-center secondary"
          onClick={() => {
            const center = map.current?.getCenter();
            if (center) onPick([center.lng, center.lat]);
          }}
        >
          Usar el centro del mapa
        </button>
      )}
      {failed ? (
        <p>
          El mapa no está disponible. Puedes consultar las rutas en el listado.
        </p>
      ) : (
        <div
          className="map"
          ref={host}
          aria-label="Mapa de recorridos de Madrid"
        />
      )}
    </div>
  );
}
