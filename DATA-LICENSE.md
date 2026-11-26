# Licencias de los datos

El **código** de este repositorio se publica bajo [Apache-2.0](LICENSE). Los **datos** que usa o genera tienen sus propias condiciones, que se resumen aquí. Al redistribuir capas derivadas conserva estas atribuciones.

| Fuente | Conjuntos | Condiciones |
|---|---|---|
| Comunidad de Madrid · [datos.comunidad.madrid](https://datos.comunidad.madrid/catalogo/) | Centros, servicios y establecimientos sanitarios; bibliotecas y servicios de lectura; calidad del aire: datos meteorológicos históricos; y los conjuntos regionales que se listan en el README | Reutilización según la [Ley 37/2007](https://www.boe.es/buscar/act.php?id=BOE-A-2007-20555) y las condiciones del portal. Citar «Fuente: Comunidad de Madrid» y la fecha de extracción |
| Ayuntamiento de Madrid · [datos.madrid.es](https://datos.madrid.es) y Geoportal | Callejero, bancos, fuentes de agua, padrón, aforos peatonales, accesibilidad viaria, alturas de edificios, recursos de Protección Civil | [Condiciones de uso del portal](https://datos.madrid.es/portal/site/egob/menuitem.400a817358ce98c34e937436a8a409a0/?vgnextoid=108804d4aab90410VgnVCM100000171f5a0aRCRD) (atribución). Citar «Ayuntamiento de Madrid» |
| OpenStreetMap · vía [Geofabrik](https://download.geofabrik.de/europe/spain/madrid.html) | Red peatonal, escaleras, barreras, arbolado, aseos y negocios y lugares con nombre del buscador | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). © colaboradores de OpenStreetMap. **Las bases de datos derivadas (`grafo.npz`, `obstaculos.*`, `lugares.sqlite`) quedan sujetas a ODbL** |
| IGN · CNIG | MDT05 y CartoCiudad | [CC BY 4.0](https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf). «© Instituto Geográfico Nacional» |
| AEMET | Predicción horaria por municipio | [Aviso legal de AEMET](https://www.aemet.es/es/nota_legal) (atribución). «© AEMET» |
| Mapa base | Teselas vectoriales | Ver la atribución que aparece en el propio mapa |

Los datos se usan tal como se publicaron en la fecha de extracción que registra `datos/ciudad/version.json`. Los estados de bancos, aceras, pasos y accesos pueden haber cambiado y deben comprobarse sobre el terreno.
