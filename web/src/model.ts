export type Position = [number, number];
export interface Place {
  id: string;
  label: string;
  kind: string;
  coordinates: Position;
  district?: string;
  source?: string;
  hours?: string;
  openFrom?: string;
  openUntil?: string;
  url?: string;
}
export interface Rest {
  label: string;
  coordinates: Position;
  atM: number;
  fromRestM: number;
  simulated: boolean;
}
export interface Step {
  action: "walk" | "cross" | "rest";
  label: string;
  coordinates: Position;
  distanceM: number;
  atM: number;
  turn?: "left" | "right";
}
export type MapLayer = "route" | "sun" | "widthM" | "slopePct";
export interface RouteSegment {
  coordinates: Position[];
  sun: number | null;
  widthM: number | null;
  slopePct: number | null;
}
export interface Route {
  label: string;
  style: string;
  geometry: { type: "LineString"; coordinates: Position[] };
  meters: number;
  durationMin: number;
  maxWithoutRest: number;
  /** Tramo real más largo sin banco junto al camino (solo el camino directo). */
  maxGapM?: number;
  fitsRest: boolean;
  widthM: number | null;
  slopePct: number | null;
  upM: number | null;
  downM: number | null;
  sunMin: number | null;
  sunStretchMin: number | null;
  segments?: RouteSegment[];
  coverage: { width: number; slope: number; elevation: number; sun: number };
  rests: Rest[];
  steps: Step[];
  nearbyServices?: (Place & { offsetM: number })[];
  barriers: string[];
  connectionsM: [number, number];
  crossings: number;
}
export interface Preferences {
  pace: number;
  rest: number | null;
  width: number | null;
  slope: number | null;
  avoidStairs: boolean;
}
export interface Improvement {
  kind: "bench" | "crossing" | "shade";
  lon: number;
  lat: number;
}
export interface RouteQuery {
  origin: { lon: number; lat: number };
  destination: { lon: number; lat: number };
  departure: string;
  preferences: Preferences;
  scenario: Improvement | null;
  live?: boolean;
  initialSinceRest?: number;
  /** Solo la app ciudadana alimenta el informe de uso. */
  register?: boolean;
}
export interface RouteResponse {
  routes: Route[];
  relaxed?: ("width" | "slope")[];
  tooFar?: boolean;
  straightM?: number;
  walkM?: number | null;
  limited: boolean;
  alternativeMaxM: number;
  weather: {
    temperatureC: number;
    at: string;
    issued: string | null;
    source: string;
  } | null;
  version: { built: string; osm: string };
  scenario: Improvement | null;
}
export interface Study {
  rows: {
    section: string;
    district: string;
    before: StudyMetric | null;
    after: StudyMetric | null;
    limited: boolean;
    sectionResidents?: number | null;
    sectionOlder?: number | null;
  }[];
  sample: number;
  radiusM: number;
  newPaths: number;
  lostPaths: number;
  completed: number;
  reducedRestPaths: number;
  reducedSunPaths: number;
  version: RouteResponse["version"];
}
export interface Footfall {
  id: string;
  label: string;
  side: string;
  coordinates: Position;
  kind: "permanent" | "campaign";
  source: string;
  count: number | null;
  period: string | null;
  distanceM: number;
  hour?: string;
  dayType?: string;
  days?: number;
}
export interface BankOption {
  id: string;
  label: string;
  scenario: Improvement;
  newPaths: number;
  lostPaths: number;
  reducedGaps: number;
  pairedPaths: number;
  medianReductionM: number | null;
  newSections: number;
  olderInNewSections: number | null;
  widthM: number | null;
  sunFraction: number | null;
  footfall: Footfall | null;
}
export interface BankPlan {
  sample: number;
  completed: number;
  baselinePaths: number;
  sitesTested: number;
  radiusM: number;
  restM: number;
  olderInSampleSections: number | null;
  options: BankOption[];
  footfall: Footfall[];
}
export interface StudyMetric {
  meters: number;
  maxWithoutRest: number;
  sunMin: number | null;
}
export interface Info {
  version: RouteResponse["version"];
  sources: { label: string; url: string; date: string }[];
  networkEdges: number;
  benchConnections: number;
  portals: number;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch {
    // Un proxy (502/504) o una caída pueden devolver HTML en vez de JSON.
    throw new Error(
      response.ok
        ? "Respuesta inesperada del servidor. Vuelve a intentarlo."
        : "El servidor no está disponible ahora mismo. Vuelve a intentarlo en un momento.",
    );
  }
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Revisa los datos del recorrido.",
    );
  return data;
}
export function routeRequest<T>(
  url: string,
  query: RouteQuery & { radiusM?: number },
) {
  return api<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
}
export const point = ([lon, lat]: Position) => ({ lon, lat });
export const mapPlace = (
  coordinates: Position,
  label = "Punto en el mapa",
): Place => ({ id: coordinates.join(","), coordinates, label, kind: "point" });
export const madridNow = () =>
  new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Madrid",
    dateStyle: "short",
    timeStyle: "short",
  })
    .format(new Date())
    .replace(" ", "T");
export const fmt = (n: number) =>
  n.toLocaleString("es-ES", { maximumFractionDigits: 1 });
