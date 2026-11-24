# Calidad de los datos de la Comunidad de Madrid que usamos

Es una **autoevaluación** hecha al reutilizar los datos. Sigue las dimensiones del modelo [MELODA](https://www.meloda.org) (licencia, acceso, formato, modelo de datos, geolocalización y actualización), pero **no es la puntuación oficial**: la del Observatorio está en [spain.meloda.org](https://spain.meloda.org). Las cifras salen de los ficheros descargados por `ciudad.fuentes` (noviembre de 2026) y se pueden recomprobar.

**Lo que es igual para los nueve conjuntos:**
- **Licencia:** reutilización según la Ley 37/2007 y las condiciones del portal, citando la fuente.
- **Acceso:** descarga directa sin registro desde el catálogo CKAN de datos.comunidad.madrid.
- **Formato:** CSV separado por «;».

| Conjunto | Geolocalización | Modelo de datos | Problemas que nos encontramos |
|---|---|---|---|
| Centros, servicios y establecimientos sanitarios | Coordenadas X/Y en el 99,4 % de 46.196 filas | Una fila por oferta asistencial: 46.196 filas para 15.908 centros | **No trae el nombre del centro**, solo el tipo y la dirección. Lo completamos con OpenStreetMap (`ciudad.nombres`). Además, los nombres de columna tienen erratas (`dependecia_funcional`, `oferta_asistecial`, `direccion_informacon_adicional`) |
| Registro de centros de atención social | Coordenadas en el 96,8 % de 2.633 centros | Dirección desglosada y bien estructurada | Unos 85 centros sin coordenadas |
| Oficinas de farmacia | Coordenadas en el 99,9 % de 2.958 farmacias | Sencillo y completo | No incluye el horario ni las guardias, que es lo que más se pregunta |
| Bibliotecas y servicios de lectura | **Sin coordenadas** | Dirección en texto libre | Codificación Windows-1252, a diferencia del resto (UTF-8). Hay que geolocalizar cruzando la dirección con el callejero. El horario viene en texto libre |
| Calidad del aire · meteorología horaria | Solo el código de la estación, sin coordenadas en el fichero | Formato ancho: 24 pares de columnas hora/validación por fila | No tiene estaciones dentro de la capital, porque allí mide la red municipal. Usamos Majadahonda |
| Población censada por edad | Código de municipio INE | Formato largo y ordenado, con el estado de cada dato | Ninguno relevante: es el mejor modelado de los nueve |
| Grado de envejecimiento por edad | Código de municipio INE | Igual que el anterior | Ninguno relevante |
| Centros de servicios sociales por tipo | Código de municipio INE | Igual que el anterior | Da recuentos agregados, no centros localizables |
| Secciones censales | Geometría (shapefile) | Estándar | **Seccionado de 2019**: siete años de retraso respecto al padrón que se cruza con él |

## Qué pediríamos a la Comunidad

1. **Nombre del centro** en el registro sanitario, y una versión con una fila por centro (hoy hay que agruparlas por `centro_nro_registro`).
2. **Coordenadas** en el listado de bibliotecas, y UTF-8 como en el resto del catálogo.
3. **Seccionado censal actualizado.**
4. **Un inventario de mobiliario urbano** (bancos y sombra) con un modelo común para todos los municipios, de la familia *Smart Data Models*, igual que ya exportamos los destinos como `PointOfInterest` (ver `resultados/smart-data-models/`). Hoy solo lo publica el Ayuntamiento de Madrid, y es lo que impide llevar la herramienta a los otros 178 municipios sin trabajo de campo.
