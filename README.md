# Llegar al fresco

[![Pruebas](https://github.com/mcamacho2102-ctrl/llegar-al-fresco/actions/workflows/pruebas.yml/badge.svg)](https://github.com/mcamacho2102-ctrl/llegar-al-fresco/actions/workflows/pruebas.yml)

**Rutas a pie para quien necesita sentarse por el camino, y una herramienta para que los ayuntamientos decidan dónde poner el próximo banco.** Proyecto para DATAMAD 2026.

- 🌐 **Demo:** https://llegaralfresco.outofthemark.com · plan B local: `scripts/arrancar.sh`
- 📦 **Datos compilados:** [Release v1.0-datamad](https://github.com/mcamacho2102-ctrl/llegar-al-fresco/releases/tag/v1.0-datamad)
- 📄 Licencia del código: [Apache-2.0](LICENSE) · datos: [DATA-LICENSE.md](DATA-LICENSE.md)

## El problema, en una cifra

> En Madrid capital, en el **88,1 %** de los trayectos hasta el centro de salud más cercano hay que caminar **más de 200 m seguidos sin un banco** por el camino directo. En el **60,5 %** no existe **ninguna** ruta que permita parar cada 200 m.

Son 3.102 trayectos calculados en los 21 distritos con una muestra aleatoria reproducible. El destino es el centro de salud de atención primaria más cercano según el registro de la Comunidad de Madrid, y se cuentan los 54.172 bancos municipales operativos. Con 300 m de límite, la cifra baja al 74,0 %.

**Por qué 200 m es un umbral prudente, no exagerado.** La guía oficial británica de accesibilidad peatonal ([*Inclusive Mobility*, Department for Transport, 2021](https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/1044542/inclusive-mobility-a-guide-to-best-practice-on-access-to-pedestrian-and-transport-infrastructure.pdf), §3.4 y §4.5) recomienda andar como máximo 50 m sin descansar si se usa bastón, 100 m con movilidad reducida sin bastón y 150 m en silla de ruedas, y pide **un asiento cada 50 m como máximo** en zonas peatonales de uso habitual. Según el estudio que cita, la mitad de las personas con alguna discapacidad que pueden andar no pasan de 200 m sin parar. Con 200 m la cifra se queda corta, si acaso. Metodología, sensibilidad y límites: [resultados/impacto/METODOLOGIA.md](resultados/impacto/METODOLOGIA.md).

En la Comunidad viven **1,34 millones de personas de 65 años o más** (1.342.648 en los 179 municipios, según la *Población censada por edad* de la Comunidad, 2025). Para muchas de ellas, con artrosis, EPOC, insuficiencia cardiaca o simplemente con muchos años, la pregunta no es «¿cuánto tardo?», sino **«¿dónde me puedo sentar?»**. Y en verano, «¿por dónde hay sombra?».

## Qué hace

| Para quién | Qué ofrece |
|---|---|
| **Personas mayores y sus familias** · *App ciudadana* (pantalla inicial) | Tres pasos grandes. Una ruta que **nunca supera los metros sin descanso que elijas** (de 100 m a 2 km); si no existe, la que **menos metros seguidos** te hace andar sin sentarte. Opciones avanzadas: escaleras, ancho mínimo de acera, cuesta máxima, ritmo y preferencia por sombra, con sombra calculada hora a hora, sin escaleras, con pendiente y ancho de acera, y con fuentes y aseos cerca. Destinos: **centros de salud, centros de día y residencias, farmacias y bibliotecas** de los registros de la Comunidad. Indicaciones habladas paso a paso (con «Repetir», «Siguiente» y voz más lenta), impresión en papel con el mapa y **«Que mi familia me siga»**: un enlace temporal para que un familiar vea en directo por dónde vas y qué bancos has pasado. Instalada como app, la ruta en curso sigue disponible sin conexión (la búsqueda de rutas nuevas y el mapa base necesitan internet). |
| **Ayuntamientos** · *Para ayuntamientos → Informe de uso* | De cada consulta se guarda, de forma anónima, **dónde faltó un banco** en el camino directo (no la dirección de salida). El informe agrupa esos huecos y señala los **bancos estratégicos**: los que evitarían más rodeos o harían posible rutas que hoy no existen. Exportable a CSV. Mientras no hay usuarios, se muestra una simulación etiquetada. |
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

Qué falla en cada uno y qué pediríamos a la Comunidad: [CALIDAD-DATOS.md](CALIDAD-DATOS.md), una autoevaluación con las dimensiones de MELODA.

Se combinan con datos del Ayuntamiento de Madrid (callejero, bancos, fuentes, padrón, aforos, accesibilidad viaria, alturas de edificios), del IGN (MDT05, CartoCiudad), de AEMET y de OpenStreetMap (red peatonal).

## Por qué es viable

- **Funciona hoy** sobre Madrid capital completa: 215.542 portales, 701.604 tramos y 54.172 bancos. En un portátil, la mayoría de rutas se calculan en menos de un segundo. En la demo pública, sobre la CPU compartida de un servidor modesto, tardan unos segundos, con un tope de 10 s (`SEGUNDOS_RUTA`). El servicio ocupa unos 850–930 MB de RAM, así que basta un servidor de 2 GB (unos 5–30 €/mes, según la CPU).
- **Es reproducible.** Los datos se rehacen desde las fuentes públicas con los comandos de [Reconstruir los datos](#reconstruir-los-datos), y `ciudad.comprobar` verifica los resultados. La cifra de impacto se repite byte a byte con la misma semilla.
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

El `Dockerfile` construye la web y sirve FastAPI en el puerto 8080. También hay un `fly.toml` para Fly.io (2 GB). La demo pública corre en un contenedor aislado (ver `despliegue/`). Las llamadas a `/api/` se limitan por IP (`LIMITE_PETICIONES`, 600 por minuto por defecto). El límite vive en memoria, así que asume un solo proceso de uvicorn.

### Reconstruir los datos

```sh
.venv/bin/python -m ciudad.fuentes      # descarga las fuentes públicas
.venv/bin/python -m ciudad.preparar     # red, índices, destinos (incluye ciudad.regional)
.venv/bin/python -m ciudad.relieve      # cotas del MDT05
.venv/bin/python -m ciudad.nombres      # nombres de centros sanitarios desde OSM
.venv/bin/python -m ciudad.municipios   # capa regional de los 179 municipios
.venv/bin/python -m ciudad.impacto --todos --n 150   # cifra de impacto (unos 40 s)
.venv/bin/python -m ciudad.sdm          # destinos como Smart Data Models · PointOfInterest, validados
.venv/bin/python -m ciudad.uso_demo     # informe municipal de demostración (3.096 consultas simuladas)
.venv/bin/python -m ciudad.anchos       # ancho de acera más cercana en una red ya compilada
```

El registro de uso vive en `datos/uso/consultas.sqlite` (debe ser escribible en el servidor; se desactiva con `USO_REGISTRO=0`). Qué se guarda y qué no: `ciudad/uso.py`.

**Interoperabilidad.** `resultados/smart-data-models/` contiene los 2.630 destinos regionales (centros para mayores, farmacias, centros de salud y bibliotecas) como entidades [PointOfInterest](https://github.com/smart-data-models/dataModel.PointOfInterest) NGSI-LD, validadas contra el esquema oficial. El servidor MCP de `mcp/` permite que un asistente de IA use la herramienta con datos verificables.

`ciudad.regional` puede ejecutarse solo, para actualizar centros para mayores y farmacias sobre una compilación existente. Los ficheros de entrada y las capas compiladas están excluidos de Git. El código trabaja en UTM ETRS89 30N y sirve coordenadas lon/lat. SQLite FTS5 indexa portales y destinos. La interfaz usa React, TypeScript, MapLibre y Vite.

## Demostración

**App ciudadana** (la pantalla inicial). Escribe *Plaza de Santa Bárbara 8* como salida, pulsa **Centro de salud** y elige el primero (C. S. Justicia). Pon el límite en **150 m** y, en *¿Cuándo sales?*, elige el **1 de julio de 2025 a las 14:00**. La ruta corta mide 618 m e incluye un tramo de 467 m sin ningún banco. La alternativa mide 794 m y pasa por 6 bancos, sin superar nunca 143 m sin sentarse. El resultado muestra la observación regional de 33,6 °C de la estación de Majadahonda. Debajo del mapa, las capas muestran sol y sombra, cuestas, ancho de acera, y fuentes y aseos.

**Para ayuntamientos →** abre el **Informe de uso** con la simulación de 3.096 consultas (etiquetada como simulada). **Simular este banco →** lleva al **Simulador de mejoras**, donde **Evaluar zona** calcula, sobre portales muestreados, el acceso con y sin la actuación. **Buscar ubicaciones para bancos** propone hasta tres candidatos, ordenados por nuevas rutas compatibles, mejora de los tramos sin descanso y residentes de 65 años o más. Ejemplo: de la Calle de Europa, 8 al C. S. Núñez Morgado hay 341 m seguidos sin banco y ninguna ruta lo evita; con un banco simulado a mitad de camino, nunca más de 184 m.

En **Recorrido detallado**, **Cargar ejemplo** y **Comparar rutas** comparan Plaza de la Virgen de la Paloma, 1 → Biblioteca Pedro Salinas: 238 m por la ruta corta y 316 m con banco, con un máximo de 168,7 m sin parar. Para **evitar escaleras**, busca **Calle de los Mancebos, 3 → Calle de Segovia, 16** con **Sin límite**: 297 m con escaleras y 387 m evitándolas.

En **Mapa regional**, pulsa cualquier municipio o elige el indicador del mapa. La tabla ordena los 15 municipios con más prioridad y la del piloto muestra la cifra de impacto por distrito.

Los aforos horarios corresponden a enero–junio de 2024 ([permanentes](https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas/downloads), [campañas](https://datos.madrid.es/dataset/300197-0-aforo-trafico/downloads)). Si falta cobertura, el aforo se muestra como desconocido.

## Qué significa cada dato

- **Direcciones y accesos.** El buscador local usa el callejero municipal y los registros regionales de centros sanitarios, centros para mayores, farmacias y bibliotecas. Si no hay resultados, CartoCiudad se consulta con una acción explícita. Los enlaces a la red se aproximan en línea recta, con un máximo de 150 m, y solo a la red principal conectada (nunca a un patio o recinto aislado). Si un punto queda fuera de Madrid o lejos de cualquier calle, el mensaje lo dice.
- **Descansos.** Los bancos operativos se conectan a caminos cartografiados a un máximo de 10 m. El desvío hasta el asiento y el regreso cuentan en la distancia. La búsqueda distingue entre un cálculo inconcluso y la ausencia de alternativa.
- **Anchura, pendiente y cruces.** Anchura y pendiente OSM explícitas permiten filtros estrictos. La acera municipal aporta valores medios y el MDT05 estima subidas y bajadas. Se muestra qué porcentaje del recorrido tiene datos.
- **Sombra y meteorología.** La proyección solar usa sobre todo la altura de los edificios (492.776 polígonos); de los árboles solo entran las pocas copas de OSM con dimensiones (21), así que la sombra del arbolado apenas se modela. Intervalos de 15 minutos sobre terreno plano. AEMET aporta el pronóstico horario y la red regional, la observación histórica.
- **Equipamientos.** Fuentes y aseos cercanos al trayecto, con acceso por confirmar. CentroCentro y Matadero tienen fichas históricas del verano de 2026. Que un centro esté registrado no significa que esté abierto en ese momento ni que sea un refugio climático.
- **Seguimiento para familiares.** La posición solo vive en la memoria del servidor: no se escribe en disco ni en el registro de uso, caduca a las 3 horas y se borra 30 minutos después de llegar. Solo quien inició el seguimiento (con su clave) puede mover el punto.
- **Navegación y privacidad.** La ubicación requiere permiso del navegador. La ruta activa se guarda en el dispositivo y se borra al terminar. La API recibe origen y destino solo para calcular, y el servidor desactiva los registros de acceso.
- **Estudios municipales.** Hasta 16 portales de cuadrículas de 75 m, con la misma función de coste para ambos recorridos. Las cifras cuentan portales muestreados. Los costes los introduce el analista.

## Limitaciones conocidas

- **Bancos según el inventario municipal.** No sabemos si cada banco está en buen estado, a la sombra o ocupado. Tampoco cuentan muros, marquesinas ni terrazas. La cifra de impacto es la dificultad *según el dato público*.
- **Sombra aproximada.** Se calcula sobre terreno plano con la altura de los edificios. El arbolado casi no entra, porque solo 21 copas de OSM tienen dimensiones.
- **Tolerancia de 20 m en la cifra.** Si no se cuenta el paso lateral hasta el banco, el 88,1 % baja al 85,6 %. El 60,5 % sin alternativa no cambia. Detalle en la [metodología](resultados/impacto/METODOLOGIA.md).
- **El informe municipal de la demo es una simulación** (3.096 consultas generadas con `ciudad.uso_demo`), etiquetada como tal hasta que haya uso real.
- **Sin validar aún en la calle** con personas mayores. Es el primer paso del piloto.
- **Centro de salud más cercano en línea recta**, no el asignado por zona básica de salud.

## Pruebas

Sin datos ni servidor (lo que corre la CI de GitHub): `python -m unittest pruebas.test_unidades`, `npm --prefix web run build` y `node comprobar-rutas.js`.

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
