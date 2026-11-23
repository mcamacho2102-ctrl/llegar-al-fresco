# Llegar al fresco

**Rutas a pie para quien necesita sentarse por el camino, y una herramienta para que los ayuntamientos decidan dónde poner el próximo banco.** Proyecto para DATAMAD 2026.

- 🌐 **Demo:** https://llegaralfresco.outofthemark.com (también https://llegaralfresco.95-217-181-34.sslip.io) · plan B local: `scripts/arrancar.sh`
- 📦 **Datos compilados:** [Release v1.0-datamad](https://github.com/mcamacho2102-ctrl/llegar-al-fresco/releases/tag/v1.0-datamad)
- 📄 Licencia del código: [Apache-2.0](LICENSE) · datos: [DATA-LICENSE.md](DATA-LICENSE.md)

## El problema, en una cifra

> En Madrid capital, en el **88,1 %** de los trayectos hasta el centro de salud más cercano hay que caminar **más de 200 m seguidos sin un banco** por el camino directo. En el **60,5 %** no existe **ninguna** ruta que permita parar cada 200 m.

Son 3.102 trayectos calculados en los 21 distritos con una muestra aleatoria reproducible. El destino es el centro de salud de atención primaria más cercano según el registro de la Comunidad de Madrid, y se cuentan los 54.172 bancos municipales operativos. Con 300 m de límite, la cifra baja al 74,0 %. Metodología, sensibilidad y límites: [resultados/impacto/METODOLOGIA.md](resultados/impacto/METODOLOGIA.md).

En la Comunidad viven **1,34 millones de personas de 65 años o más**. Para muchas de ellas, con artrosis, EPOC, insuficiencia cardiaca o simplemente con muchos años, la pregunta no es «¿cuánto tardo?», sino **«¿dónde me puedo sentar?»**. Y en verano, «¿por dónde hay sombra?».

## Qué hace

| Para quién | Qué ofrece |
|---|---|
| **Personas mayores y sus familias** · *Mi recorrido* | Tres pasos grandes. Una ruta que **nunca supera los metros sin descanso que elijas** (de 100 m a 2 km); si no existe, la que **menos metros seguidos** te hace andar sin sentarte. Opciones avanzadas: escaleras, ancho mínimo de acera, cuesta máxima, ritmo y preferencia por sombra, con sombra calculada hora a hora, sin escaleras, con pendiente y ancho de acera, y con fuentes y aseos cerca. Destinos: **centros de salud, centros de día y residencias, farmacias y bibliotecas** de los registros de la Comunidad. Navegación paso a paso; funciona sin conexión una vez instalada. |
| **Ayuntamientos** · *Informe de uso* | De cada consulta se guarda, de forma anónima, **dónde faltó un banco** en el camino directo (no la dirección de salida). El informe agrupa esos huecos y señala los **bancos estratégicos**: los que evitarían más rodeos o harían posible rutas que hoy no existen. Exportable a CSV. Mientras no hay usuarios, se muestra una simulación etiquetada. |
| **Ayuntamientos** · *Simulador de mejoras* | **Simula un banco, un rebaje o sombra** y mide sobre una muestra de portales cuántos trayectos nuevos se hacen posibles. **Busca automáticamente las mejores ubicaciones** para nuevos bancos, con mayores residentes y aforos peatonales. Compara coste por ruta habilitada. |
| **Comunidad de Madrid** · *Mapa regional* | Clasificación de los **179 municipios** según envejecimiento, mayores por centro de salud, mayores por centro para mayores y horas a 35 °C o más. Sirve para decidir dónde desplegar después. **Usa solo datos de la Comunidad.** |

## Datos de la Comunidad de Madrid que usa

| Conjunto (datos.comunidad.madrid) | Para qué sirve en el producto |
|---|---|
| [Centros, servicios y establecimientos sanitarios](https://datos.comunidad.madrid/dataset/centros_servicios_establecimientos_sanitarios) | Destinos buscables (8.876 en la capital); destino de la cifra de impacto; centros de salud por municipio |
| [Registro de centros de atención social](https://datos.comunidad.madrid/dataset/atencion_social_registro_centros) | 440 centros de día, residencias y hogares de mayores como destinos |
| [Oficinas de farmacia](https://datos.comunidad.madrid/dataset/oficinas_farmacia) | 1.811 farmacias como destinos (sustituyen a las de OSM) y farmacias por municipio |
| [Bibliotecas y servicios de lectura](https://datos.comunidad.madrid/dataset/spacm_listado_bibliotecas_servicios_lectura) | 250 bibliotecas con horario como destinos frescos |
| [Red de Calidad del Aire · datos meteorológicos horarios](https://datos.comunidad.madrid/dataset/calidad_aire_datos_meteo_historico) | Temperatura observada en la demostración (1/7/2025: 33,6 °C) y horas a 35 °C o más por municipio |
| [Población censada por edad, nacionalidad y sexo](https://datos.comunidad.madrid/dataset/poblacion_censada_por_edad_nacionalidad_y_sexo) | Mayores de 65 y 80 años por municipio |
| [Grado de envejecimiento por edad](https://datos.comunidad.madrid/dataset/grado_envejecimiento_por_edad) | % de 65 años o más por municipio |
| [Centros de servicios sociales por tipo](https://datos.comunidad.madrid/dataset/centros_servicios_sociales_por_tipo) | Centros para mayores por municipio |
| [Secciones censales](https://datos.comunidad.madrid/dataset/secciones_censales) | Geometría de los 179 municipios |

Se combinan con datos del Ayuntamiento de Madrid (callejero, bancos, fuentes, padrón, aforos, accesibilidad viaria, alturas de edificios), del IGN (MDT05, CartoCiudad), de AEMET y de OpenStreetMap (red peatonal).

## Por qué es viable

- **Funciona hoy** sobre Madrid capital completa: 215.542 portales, 701.604 tramos y 54.172 bancos. Calcula una ruta en menos de un segundo. El servidor ocupa unos 930 MB de RAM, así que basta un servidor pequeño (unos 5–30 €/mes).
- **Es reproducible.** Tres comandos rehacen todos los datos desde las fuentes públicas (`ciudad.fuentes`, `ciudad.preparar`, `ciudad.relieve`), y `ciudad.comprobar` verifica los resultados.
- **Se puede llevar a otros municipios** con su callejero, su inventario de bancos y OSM. El mapa regional indica por dónde empezar.
- **Modelo:** la app ciudadana es gratuita y el núcleo es abierto. Los ayuntamientos pagan la implantación y los estudios de ubicación de mobiliario, y se ofrece integración a teleasistencia, asociaciones de mayores y empresas de información (sector infomediario).

---

## Arranque local

Requiere Python 3.9–3.12 y Node 22 o posterior. Desde la raíz del proyecto:

```sh
scripts/descargar_datos.sh                        # datos compilados de la Release (o reconstrúyelos, abajo)
scripts/arrancar.sh                               # crea el entorno, compila la web y abre http://localhost:8768
```

O paso a paso:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
.venv/bin/python -m uvicorn ciudad.servicio:app --host 127.0.0.1 --port 8768 --no-access-log
```

El backend sirve también la interfaz compilada. Para el mapa base (OpenFreeMap) y la previsión de AEMET se necesita internet. La versión anterior para Puerta de Toledo se abre con `python3 -m http.server 8765 --directory dist`, y sus pruebas con `node comprobar-rutas.js`.

### Despliegue público

El `Dockerfile` construye la web y sirve FastAPI en el puerto 8080. También hay un `fly.toml` para Fly.io (2 GB). La demo pública corre en un contenedor aislado (ver `despliegue/`). Las llamadas a `/api/` se limitan por IP (`LIMITE_PETICIONES`, 600 por minuto por defecto).

### Reconstruir los datos

```sh
.venv/bin/python -m ciudad.fuentes      # descarga las fuentes públicas
.venv/bin/python -m ciudad.preparar     # red, índices, destinos (incluye ciudad.regional)
.venv/bin/python -m ciudad.relieve      # cotas del MDT05
.venv/bin/python -m ciudad.municipios   # capa regional de los 179 municipios
.venv/bin/python -m ciudad.impacto --todos --n 150   # cifra de impacto (36 s)
.venv/bin/python -m ciudad.sdm          # destinos como Smart Data Models · PointOfInterest, validados
.venv/bin/python -m ciudad.uso_demo     # informe municipal de demostración (3.096 consultas simuladas)
.venv/bin/python -m ciudad.anchos       # ancho de acera más cercana en una red ya compilada
```

El registro de uso vive en `datos/uso/consultas.sqlite` (debe ser escribible en el servidor; se desactiva con `USO_REGISTRO=0`). Qué se guarda y qué no: `ciudad/uso.py`.

**Interoperabilidad.** `resultados/smart-data-models/` contiene los 2.630 destinos regionales (centros para mayores, farmacias, centros de salud y bibliotecas) como entidades [PointOfInterest](https://github.com/smart-data-models/dataModel.PointOfInterest) NGSI-LD, validadas contra el esquema oficial. El servidor MCP de `mcp/` permite que un asistente de IA use la herramienta con datos verificables.

`ciudad.regional` puede ejecutarse solo, para actualizar centros para mayores y farmacias sobre una compilación existente. Los ficheros de entrada y las capas compiladas están excluidos de Git. El código trabaja en UTM ETRS89 30N y sirve coordenadas lon/lat. SQLite FTS5 indexa portales y destinos. La interfaz usa React, TypeScript, MapLibre y Vite.

## Demostración

En **Mi recorrido**, pulsa **Cargar ejemplo** y **Comparar rutas**. La Plaza de la Virgen de la Paloma, 1 y la Biblioteca Pedro Salinas están a 238 m por la ruta corta. Con un límite de 200 m sin descanso, la alternativa con banco mide 316 m y su tramo continuo más largo es de 168,7 m. Para reproducir las condiciones históricas, elige el **1 de julio de 2025 a las 14:00**: el resultado muestra la observación regional de 33,6 °C de la estación de Majadahonda.

En **Panel municipal**, vuelve a pulsar **Cargar ejemplo** y **Comparar rutas**. El banco hipotético acorta la alternativa en 77 m, hasta 239 m, con un máximo de 158,3 m sin parar. **Evaluar zona** calcula, sobre portales muestreados, el acceso al mismo destino con y sin la actuación. **Buscar ubicaciones para bancos** propone hasta tres candidatos, ordenados por nuevas rutas compatibles, mejora de los tramos sin descanso y residentes de 65 años o más.

Para **Evitar escaleras**, busca **Calle de los Mancebos, 3 → Calle de Segovia, 16** con **Sin límite** de descanso: 297 m con escaleras y 387 m evitándolas.

En **Mapa regional**, pulsa cualquier municipio o elige el indicador del mapa. La tabla ordena los 15 municipios con más prioridad y la del piloto muestra la cifra de impacto por distrito.

Los aforos horarios corresponden a enero–junio de 2024 ([permanentes](https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas/downloads), [campañas](https://datos.madrid.es/dataset/300197-0-aforo-trafico/downloads)). Si falta cobertura, el aforo se muestra como desconocido.

## Qué significa cada dato

- **Direcciones y accesos.** El buscador local usa el callejero municipal y los registros regionales de centros sanitarios, centros para mayores, farmacias y bibliotecas. Si no hay resultados, CartoCiudad se consulta con una acción explícita. Los enlaces a la red se aproximan en línea recta, con un máximo de 150 m, y solo a la red principal conectada (nunca a un patio o recinto aislado). Si un punto queda fuera de Madrid o lejos de cualquier calle, el mensaje lo dice.
- **Descansos.** Los bancos operativos se conectan a caminos cartografiados a un máximo de 10 m. El desvío hasta el asiento y el regreso cuentan en la distancia. La búsqueda distingue entre un cálculo inconcluso y la ausencia de alternativa.
- **Anchura, pendiente y cruces.** Anchura y pendiente OSM explícitas permiten filtros estrictos. La acera municipal aporta valores medios y el MDT05 estima subidas y bajadas. Se muestra qué porcentaje del recorrido tiene datos.
- **Sombra y meteorología.** La proyección solar usa sobre todo la altura de los edificios (492.776 polígonos); de los árboles solo entran las pocas copas de OSM con dimensiones (21), así que la sombra del arbolado apenas se modela. Intervalos de 15 minutos sobre terreno plano. AEMET aporta el pronóstico horario y la red regional, la observación histórica.
- **Equipamientos.** Fuentes y aseos cercanos al trayecto, con acceso por confirmar. CentroCentro y Matadero tienen fichas históricas del verano de 2026. Que un centro esté registrado no significa que esté abierto en ese momento ni que sea un refugio climático.
- **Navegación y privacidad.** La ubicación requiere permiso del navegador. La ruta activa se guarda en el dispositivo y se borra al terminar. La API recibe origen y destino solo para calcular, y el servidor desactiva los registros de acceso.
- **Estudios municipales.** Hasta 16 portales de cuadrículas de 75 m, con la misma función de coste para ambos recorridos. Las cifras cuentan portales muestreados. Los costes los introduce el analista.

## Pruebas

Con el servidor en marcha: `python3 pruebas/banco_api.py` (75 comprobaciones de la API), `python pruebas/banco_web.py` (recorridos por perfiles en un navegador real y auditoría de accesibilidad axe; necesita Playwright) y `.venv/bin/python -m ciudad.banco_pruebas` (uso adversarial). Ninguna prueba cuenta en el informe de uso.

## Verificación

Con el servidor en marcha, ejecuta `.venv/bin/python -m ciudad.comprobar [URL]`. Comprueba:
- un portal por distrito;
- destinos regionales;
- fecha de refugio y observación histórica;
- descansos e imposibilidad dentro de un límite real;
- retirada del banco;
- evaluación de actuaciones sobre la misma muestra.

Los estados de aceras, bancos, pasos y accesos deben corroborarse sobre el terreno. Queda pendiente probar la navegación con GPS en la calle y con personas mayores o con movilidad reducida.

## Fuentes y licencias

Atribuciones completas en [DATA-LICENSE.md](DATA-LICENSE.md).

- **Comunidad de Madrid:** los conjuntos de la tabla de arriba.
- **Ayuntamiento de Madrid:**
  - [callejero](https://datos.madrid.es/dataset/200075-0-callejero);
  - [bancos](https://datos.madrid.es/dataset/300095-0-mobiliario-bancos/downloads);
  - [fuentes](https://datos.madrid.es/dataset/300051-0-fuentes/downloads);
  - [padrón](https://datos.madrid.es/dataset/200076-0-padron);
  - [accesibilidad viaria](https://sigma.madrid.es/hosted/rest/services/GEOPORTAL/ACCESIBILIDAD_VIARIA/MapServer/layers);
  - [alturas](https://geoportal.madrid.es/IDEAM_WBGEOPORTAL/dataset.iam?id=ALTURAS_EDIFICIOS);
  - [Protección Civil](https://geoportal.madrid.es/IDEAM_WBGEOPORTAL/dataset.iam?id=RECURSOS_PROTECCION_CIVIL).
- **IGN:** [MDT05](https://datos.gob.es/es/catalogo/e0dat0002-modelo-digital-del-terreno-con-paso-de-malla-de-5-metros-mdt05-de-espana1) y [CartoCiudad](https://www.cartociudad.es/web/portal/).
- **AEMET:** [predicción horaria para Madrid](https://www.aemet.es/es/eltiempo/prediccion/municipios/horas/madrid-id28079).
- **OpenStreetMap:** red peatonal © [colaboradores de OpenStreetMap](https://www.openstreetmap.org/copyright), vía [Geofabrik](https://download.geofabrik.de/europe/spain/madrid.html). Las bases de datos derivadas quedan sujetas a ODbL.
- **Mapa base:** [OpenFreeMap](https://openfreemap.org).
- **Referentes:** se revisaron [OasisMadrid](https://github.com/ariaslombardero/Oasis-Madrid) y [CurbShade](https://github.com/davidmariscalf/CurbShade) como referentes de diseño y metodología. El motor y la preparación se escribieron para este proyecto. [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) se usa bajo BSD-3-Clause.
