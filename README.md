# Llegar al fresco

Prototipo para DATAMAD 2026. Compara una ruta peatonal con una que incorpora descansos, y permite añadir un banco hipotético para comparar el resultado. Zona piloto de Puerta de Toledo, Madrid.

## Ejecutar

Ejecute `python3 -m http.server 8765 --directory dist` desde esta carpeta y abra http://localhost:8765. Es necesaria conexión a internet para cargar Leaflet y el mapa base. Las rutas se calculan en el navegador; no se envían ubicaciones a un servidor propio.

Los datos procesados para el piloto están incluidos en `dist/data.json` y `dist/insolacion.json`. `preparar.py` permite volver a generar el primero con las fuentes originales en `datos/`, Python 3 y pyproj. La carpeta de datos de origen está excluida del repositorio por su tamaño.

## Método y limitaciones

La red procede de la API de OpenStreetMap, descargada el 19/11/2026 para un área limitada. Se excluyen vías con acceso peatonal prohibido y escaleras etiquetadas. No se garantiza que el resto sea accesible. Los bancos del inventario municipal de 2026 se convierten de ETRS89 UTM 30N a latitud/longitud y se conectan al nodo de la red más próximo cuando está a 35 m o menos. El acceso al banco y el retorno a ese nodo se aproximan en línea recta y se incluyen dos veces en la longitud. Las conexiones entre origen/destino y la red son aproximaciones en línea recta. Los pasos de calles y barreras no pueden garantizarse con estos datos.

La búsqueda utiliza Dijkstra con un estado de distancia acumulada desde el último descanso. Se redondean los tramos hacia arriba en incrementos de 5 m para aplicar el máximo de forma conservadora. Puede descartarse una alternativa factible por el redondeo o por la conexión a nodos. La ruta directa no incorpora paradas, por eso su mayor tramo sin descanso equivale a su longitud. La simulación agrega un banco ficticio de forma temporal y recalcula la alternativa.

La insolación se presenta como capa municipal estacional, no como cálculo para una hora ni como evaluación térmica de la ruta. La temperatura del ejemplo es una observación de la estación regional de Majadahonda, 1/7/2025, magnitud 83, franja h14, valor 33,6 °C validado. No representa la temperatura en la ruta. Los centros sanitarios se identifican por tipo y dirección, son públicos o privados. La biblioteca regional se localizó usando la geometría OSM y su correspondencia por nombre; debe contrastarse sobre el terreno. Los horarios y el estado efectivo de bancos, aceras y destinos no están confirmados en tiempo real.

## Fuentes y licencias

- Comunidad de Madrid, centros sanitarios, bibliotecas y meteorología: https://datos.comunidad.madrid/dataset/centros_servicios_establecimientos_sanitarios , https://datos.comunidad.madrid/dataset/spacm_listado_bibliotecas_servicios_lectura y https://datos.comunidad.madrid/dataset/calidad_aire_datos_meteo_historico. Consultadas el 19/11/2026.
- Ayuntamiento de Madrid, bancos 2026 y capa de accesibilidad viaria: https://datos.madrid.es/dataset/300095-0-mobiliario-bancos y https://sigma.madrid.es/hosted/rest/services/GEOPORTAL/ACCESIBILIDAD_VIARIA/MapServer/layers. Consultadas el 19/11/2026.
- Red peatonal © colaboradores de OpenStreetMap, ODbL: https://www.openstreetmap.org/copyright. La redistribución de la base de datos derivada debe cumplir las condiciones de ODbL.
- Leaflet, BSD-2-Clause: https://github.com/Leaflet/Leaflet. Mapa base © OpenStreetMap.
- El algoritmo se escribió para este prototipo. Se revisaron los proyectos Oasis-Madrid y CurbShade como referencias, sin copiar código.

Antes de publicación general, validar horarios, datos cartográficos, licencias de redistribución y accesibilidad con usuarios. La geometría y los datos originales no aseguran que un recorrido sea seguro.

## Comprobación

`node comprobar-rutas.js` verifica rutas sin bancos, desviaciones, dos descansos, límites y simulación. El prototipo no se ha validado con personas mayores ni se ha contrastado físicamente cada banco o destino.
