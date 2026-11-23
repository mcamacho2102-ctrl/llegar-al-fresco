# ¿Se puede llegar al centro de salud sin caminar más de 200 m seguidos sin un banco?

**Resultado principal (Madrid capital, 21 distritos, 3.102 trayectos evaluables):**

- En el **88,1 %** de los trayectos, ir al centro de salud de atención primaria más cercano obliga a caminar más de 200 m seguidos sin un banco municipal en el camino directo.
- En el **27,6 %** se puede evitar dando un rodeo: la mediana del rodeo está entre 63 y 197 m según el distrito.
- En el **60,5 %** **no existe ninguna ruta** dentro de un recorrido razonable que permita parar cada 200 m.

Reproducir: `.venv/bin/python -m ciudad.impacto --todos --n 150 --limite 200 --semilla 2026` (36 s; la misma semilla produce el mismo CSV, con SHA-1 `fa556b90…`).

## Método

1. **Muestra.** 150 portales por distrito, aleatorios con la semilla 2026, del callejero municipal (215.542 portales). Se ponderan aparte por el número de residentes de 65 años o más de su sección censal (padrón municipal, octubre de 2026).
2. **Destino.** El *centro de salud* o *consultorio de atención primaria* más cercano en línea recta, según el **registro de centros, servicios y establecimientos sanitarios de la Comunidad de Madrid**: 129 centros en la capital.
3. **Rutas.** Se usa el mismo motor y la misma red peatonal que la aplicación (OSM, 701.604 tramos), evitando escaleras:
   - *Camino directo*: la ruta de distancia mínima.
   - *Ruta con descansos*: la de distancia mínima que nunca supera el límite sin pasar por un banco. Cuenta la ida y vuelta al asiento y explora como máximo el mayor de `max(400 m, 2 × línea recta + 200 m)` y 1,5 veces el camino directo (para no descartar rutas en trayectos sinuosos).
4. **Bancos.** Los 54.172 bancos municipales en estado OPERATIVO del inventario 2026 que están a 10 m o menos de un camino.
5. **Clasificación:**
   - `cumple_ya`: la ruta con descansos no alarga el camino directo más de 20 m.
   - `se_arregla_con_desvio`: existe, pero exige un rodeo mayor.
   - `no_hay_alternativa`: no existe dentro de lo explorado.
   - Se excluyen `sin_ruta` (punto a más de 150 m de la red principal conectada, sobre todo urbanizaciones nuevas de Vicálvaro aún sin calles en OSM: 48 casos) e `inconcluso` (búsqueda agotada: 0 casos). Los extremos solo se enganchan a la red principal conectada, nunca a un patio o recinto aislado.

## Qué cuenta como «cumple ya»

Una ruta con descansos «cumple ya» si no alarga el camino directo más de 20 m. Esos 20 m incluyen el paso lateral hasta el banco y la vuelta. Si además se descuenta todo el paso lateral (sea cual sea su longitud) y solo se cuenta el rodeo del itinerario, unos 80 trayectos (el 2,5 %) pasan a «cumple ya» y la cifra queda en **85,6 %** (25,0 % con rodeo + 60,5 % sin alternativa; este último no cambia). Mantenemos el 88,1 % como cifra principal porque, para quien necesita sentarse, el paso hasta el banco también se camina.

## Margen de error

Con 3.102 trayectos evaluables, el intervalo de confianza al 95 % (aproximación binomial) es de **±1,1 puntos** para el 88,1 % y de **±1,7 puntos** para el 60,5 %. La muestra está estratificada por distrito (150 portales por distrito, no proporcional a la población), así que el total da el mismo peso a cada distrito; la versión ponderada por mayores, por distrito, figura en la tabla.

## Sensibilidad al límite

| Límite sin descanso | No se cumple por el camino directo | Se arregla con rodeo | Sin alternativa |
|---|---|---|---|
| 150 m | 94,3 % | 16,0 % | 78,3 % |
| **200 m** | **88,1 %** | **27,6 %** | **60,5 %** |
| 300 m | 74,0 % | 42,8 % | 31,2 % |

## Por distrito (límite de 200 m)

| Distrito | % 65+ | No se cumple por el camino directo | Ponderado por mayores | Se arregla | Sin alternativa | Rodeo mediano |
|---|---|---|---|---|---|---|
| Barajas | 20,2 | 98,0 % | 97,4 % | 21,1 % | 76,9 % | 170 m |
| Hortaleza | 19,5 | 97,2 % | 96,0 % | 14,8 % | 82,4 % | 133 m |
| Ciudad Lineal | 23,0 | 95,2 % | 95,1 % | 22,6 % | 72,6 % | 103 m |
| Latina | 23,4 | 95,2 % | 95,3 % | 11,0 % | 84,2 % | 73 m |
| Fuencarral-El Pardo | 22,4 | 94,6 % | 95,2 % | 18,2 % | 76,4 % | 161 m |
| Carabanchel | 18,4 | 94,0 % | 93,0 % | 26,0 % | 68,0 % | 111 m |
| Moncloa-Aravaca | 23,1 | 93,1 % | 94,1 % | 17,2 % | 75,9 % | 102 m |
| Salamanca | 24,6 | 91,3 % | 91,2 % | 32,0 % | 59,3 % | 197 m |
| San Blas-Canillejas | 19,1 | 91,3 % | 92,0 % | 33,3 % | 58,0 % | 99 m |
| Villa de Vallecas | 14,5 | 90,4 % | 88,1 % | 45,9 % | 44,5 % | 148 m |
| Villaverde | 16,4 | 89,9 % | 87,7 % | 34,2 % | 55,7 % | 190 m |
| Usera | 16,5 | 89,3 % | 90,3 % | 22,7 % | 66,7 % | 183 m |
| Vicálvaro | 13,7 | 89,1 % | 85,3 % | 32,1 % | 56,9 % | 106 m |
| Puente de Vallecas | 18,1 | 86,7 % | 87,4 % | 30,7 % | 56,0 % | 141 m |
| Retiro | 27,7 | 85,2 % | 87,2 % | 32,2 % | 53,0 % | 134 m |
| Centro | 16,7 | 84,0 % | 86,1 % | 35,3 % | 48,7 % | 118 m |
| Chamartín | 24,3 | 84,0 % | 85,9 % | 30,7 % | 53,3 % | 184 m |
| Tetuán | 19,0 | 82,7 % | 82,5 % | 19,3 % | 63,3 % | 63 m |
| Moratalaz | 27,4 | 81,3 % | 79,0 % | 39,3 % | 42,0 % | 73 m |
| Arganzuela | 22,3 | 70,5 % | 71,9 % | 32,9 % | 37,6 % | 132 m |
| Chamberí | 24,5 | 68,9 % | 71,3 % | 27,0 % | 41,9 % | 104 m |

El detalle por trayecto está en `impacto_200m_n150_s2026_todos.csv`, y la sensibilidad en `impacto_150m_…` e `impacto_300m_…`.

## Límites (léelos antes de citar las cifras)

- **Solo bancos municipales inventariados.** No cuenta muros, escalones de portal, terrazas, marquesinas de autobús ni bancos de parques que falten en el inventario. La cifra es un límite superior de la dificultad *según el dato público*. Por eso conviene mejorar el inventario (ver MELODA y la validación en calle).
- **El centro más cercano en línea recta** no tiene por qué ser el asignado por tarjeta sanitaria (zona básica de salud).
- **Muestra por portales, no por personas.** La versión ponderada por mayores de la sección censal da valores parecidos (±4 puntos).
- **Red OSM.** Parte de la red discurre por el eje de la calle. El acceso del portal a la calle se aproxima en línea recta (hasta 150 m) y cuenta en la distancia.
- **200 m** es un umbral de referencia para personas que necesitan pararse con frecuencia, no un estándar normativo. La tabla de sensibilidad muestra cómo cambia la conclusión.
