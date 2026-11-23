# ¿Se puede llegar al centro de salud sin caminar más de 200 m seguidos sin un banco?

**Resultado principal (Madrid capital, 21 distritos, 2.989 trayectos evaluables):**

- En el **87,8 %** de los trayectos, ir al centro de salud de atención primaria más cercano obliga a caminar más de 200 m seguidos sin un banco municipal en el camino directo.
- En el **27,5 %** se puede evitar dando un rodeo: la mediana del rodeo está entre 63 y 197 m según el distrito.
- En el **60,3 %** **no existe ninguna ruta** dentro de un recorrido razonable que permita parar cada 200 m.

Reproducir: `.venv/bin/python -m ciudad.impacto --todos --n 150 --limite 200 --semilla 2026` (36 s; la misma semilla produce el mismo CSV, con SHA-1 `810f4075…`).

## Método

1. **Muestra.** 150 portales por distrito, aleatorios con la semilla 2026, del callejero municipal (215.542 portales). Se ponderan aparte por el número de residentes de 65 años o más de su sección censal (padrón municipal, octubre de 2026).
2. **Destino.** El *centro de salud* o *consultorio de atención primaria* más cercano en línea recta, según el **registro de centros, servicios y establecimientos sanitarios de la Comunidad de Madrid**: 129 centros en la capital.
3. **Rutas.** Se usa el mismo motor y la misma red peatonal que la aplicación (OSM, 701.604 tramos), evitando escaleras:
   - *Camino directo*: la ruta de distancia mínima.
   - *Ruta con descansos*: la de distancia mínima que nunca supera el límite sin pasar por un banco. Cuenta la ida y vuelta al asiento y explora como máximo `max(400 m, 2 × línea recta + 200 m)`.
4. **Bancos.** Los 54.172 bancos municipales en estado OPERATIVO del inventario 2026 que están a 10 m o menos de un camino.
5. **Clasificación:**
   - `cumple_ya`: la ruta con descansos no alarga el camino directo más de 20 m.
   - `se_arregla_con_desvio`: existe, pero exige un rodeo mayor.
   - `no_hay_alternativa`: no existe dentro de lo explorado.
   - Se excluyen `sin_ruta` (portal o centro a más de 60 m de la red: 161 casos) e `inconcluso` (búsqueda agotada: 0 casos).

## Sensibilidad al límite

| Límite sin descanso | No se cumple por el camino directo | Se arregla con rodeo | Sin alternativa |
|---|---|---|---|
| 150 m | 94,1 % | 15,9 % | 78,2 % |
| **200 m** | **87,8 %** | **27,5 %** | **60,3 %** |
| 300 m | 73,5 % | 42,2 % | 31,2 % |

## Por distrito (límite de 200 m)

| Distrito | % 65+ | No se cumple por el camino directo | Ponderado por mayores | Se arregla | Sin alternativa | Rodeo mediano |
|---|---|---|---|---|---|---|
| Barajas | 20,2 | 97,8 % | 97,3 % | 21,6 % | 76,3 % | 170 m |
| Hortaleza | 19,5 | 97,1 % | 96,0 % | 15,0 % | 82,1 % | 133 m |
| Ciudad Lineal | 23,0 | 95,1 % | 95,0 % | 22,9 % | 72,2 % | 103 m |
| Latina | 23,4 | 95,1 % | 95,2 % | 9,8 % | 85,3 % | 76 m |
| Fuencarral-El Pardo | 22,4 | 94,4 % | 94,9 % | 18,9 % | 75,5 % | 161 m |
| Carabanchel | 18,4 | 93,9 % | 92,9 % | 25,9 % | 68,0 % | 130 m |
| Moncloa-Aravaca | 23,1 | 92,7 % | 93,8 % | 17,5 % | 75,2 % | 102 m |
| Salamanca | 24,6 | 91,3 % | 91,1 % | 32,2 % | 59,1 % | 197 m |
| San Blas-Canillejas | 19,1 | 91,0 % | 91,7 % | 34,0 % | 56,9 % | 99 m |
| Villaverde | 16,4 | 89,5 % | 87,3 % | 34,3 % | 55,2 % | 186 m |
| Usera | 16,5 | 89,3 % | 90,2 % | 22,1 % | 67,1 % | 183 m |
| Villa de Vallecas | 14,5 | 89,3 % | 86,4 % | 50,0 % | 39,3 % | 148 m |
| Vicálvaro | 13,7 | 88,8 % | 84,9 % | 33,6 % | 55,2 % | 109 m |
| Puente de Vallecas | 18,1 | 86,7 % | 87,4 % | 30,7 % | 56,0 % | 141 m |
| Retiro | 27,7 | 84,7 % | 86,7 % | 28,5 % | 56,2 % | 85 m |
| Centro | 16,7 | 84,6 % | 86,6 % | 34,9 % | 49,7 % | 122 m |
| Chamartín | 24,3 | 83,3 % | 85,1 % | 31,2 % | 52,1 % | 135 m |
| Tetuán | 19,0 | 82,6 % | 82,5 % | 18,8 % | 63,8 % | 63 m |
| Moratalaz | 27,4 | 80,8 % | 78,5 % | 39,7 % | 41,1 % | 73 m |
| Chamberí | 24,5 | 68,3 % | 70,9 % | 25,5 % | 42,8 % | 84 m |
| Arganzuela | 22,3 | 67,9 % | 69,5 % | 34,3 % | 33,6 % | 132 m |

El detalle por trayecto está en `impacto_200m_n150_s2026_todos.csv`, y la sensibilidad en `impacto_150m_…` e `impacto_300m_…`.

## Límites (léelos antes de citar las cifras)

- **Solo bancos municipales inventariados.** No cuenta muros, escalones de portal, terrazas, marquesinas de autobús ni bancos de parques que falten en el inventario. La cifra es un límite superior de la dificultad *según el dato público*. Por eso conviene mejorar el inventario (ver MELODA y la validación en calle).
- **El centro más cercano en línea recta** no tiene por qué ser el asignado por tarjeta sanitaria (zona básica de salud).
- **Muestra por portales, no por personas.** La versión ponderada por mayores de la sección censal da valores parecidos (±4 puntos).
- **Red OSM.** Parte de la red discurre por el eje de la calle. Los accesos a más de 60 m quedan fuera.
- **200 m** es un umbral de referencia para personas que necesitan pararse con frecuencia, no un estándar normativo. La tabla de sensibilidad muestra cómo cambia la conclusión.
