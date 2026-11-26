import { Place } from "./model";

/** Sitios favoritos guardados solo en este dispositivo (nunca se envían al servidor). */
export interface MiSitio {
  nombre: string;
  place: Place;
}

const CLAVE = "mis-sitios";
const EVENTO = "mis-sitios-cambio";
export const MAX_SITIOS = 6;

const esPlace = (p: unknown): p is Place => {
  if (!p || typeof p !== "object") return false;
  const x = p as Partial<Place>;
  return (
    typeof x.label === "string" &&
    Array.isArray(x.coordinates) &&
    x.coordinates.length === 2 &&
    x.coordinates.every((n) => typeof n === "number" && Number.isFinite(n))
  );
};

/** Copia solo los campos conocidos del sitio (sin distancias ni datos sueltos). */
const limpiar = (p: Place): Place => {
  const copia: Place = {
    id: String(p.id || p.coordinates.join(",")),
    label: p.label,
    kind: typeof p.kind === "string" ? p.kind : "point",
    coordinates: [p.coordinates[0], p.coordinates[1]],
  };
  for (const k of ["district", "source", "hours", "openFrom", "openUntil", "url"] as const)
    if (typeof p[k] === "string") copia[k] = p[k];
  return copia;
};

export function leerSitios(): MiSitio[] {
  try {
    const crudo = window.localStorage.getItem(CLAVE);
    if (!crudo) return [];
    const datos: unknown = JSON.parse(crudo);
    if (!Array.isArray(datos)) return [];
    return datos
      .filter(
        (s): s is MiSitio =>
          !!s &&
          typeof s === "object" &&
          typeof (s as MiSitio).nombre === "string" &&
          esPlace((s as MiSitio).place),
      )
      .slice(0, MAX_SITIOS)
      .map((s) => ({ nombre: s.nombre.slice(0, 30), place: limpiar(s.place) }));
  } catch {
    return [];
  }
}

function escribir(sitios: MiSitio[]): boolean {
  try {
    window.localStorage.setItem(CLAVE, JSON.stringify(sitios));
  } catch {
    return false;
  }
  try {
    window.dispatchEvent(new Event(EVENTO));
  } catch {
    // Sin avisos entre buscadores: no es grave.
  }
  return true;
}

export const mismoSitio = (a: Place, b: Place) =>
  a.id === b.id ||
  (Math.abs(a.coordinates[0] - b.coordinates[0]) < 1e-6 &&
    Math.abs(a.coordinates[1] - b.coordinates[1]) < 1e-6);

/**
 * Guarda (o renombra) un sitio. Si ya hay uno con el mismo nombre, lo sustituye.
 * Devuelve el sitio que se ha quitado por falta de hueco, `null` si no se quitó
 * ninguno, o `false` si el navegador no deja guardar (p. ej. modo privado).
 */
export function guardarSitio(nombre: string, place: Place): MiSitio | null | false {
  const nuevo: MiSitio = { nombre: nombre.slice(0, 30), place: limpiar(place) };
  const resto = leerSitios().filter(
    (s) => s.nombre !== nuevo.nombre && !mismoSitio(s.place, nuevo.place),
  );
  const quitado = resto.length >= MAX_SITIOS ? resto[resto.length - 1] : null;
  const lista = [nuevo, ...resto].slice(0, MAX_SITIOS);
  return escribir(lista) ? quitado : false;
}

export function borrarSitio(nombre: string): boolean {
  return escribir(leerSitios().filter((s) => s.nombre !== nombre));
}

/** Avisa cuando cambian los sitios (en este buscador, en otro de la página o en otra pestaña). */
export function escucharSitios(alCambiar: () => void): () => void {
  const enOtraPestana = (e: StorageEvent) => {
    if (e.key === null || e.key === CLAVE) alCambiar();
  };
  window.addEventListener(EVENTO, alCambiar);
  window.addEventListener("storage", enOtraPestana);
  return () => {
    window.removeEventListener(EVENTO, alCambiar);
    window.removeEventListener("storage", enOtraPestana);
  };
}
