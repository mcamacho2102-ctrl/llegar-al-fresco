# Cómo contribuir

Gracias por el interés. El proyecto está abierto a correcciones de datos, mejoras del motor y adaptaciones a otros municipios.

## Lo que más ayuda

- **Corregir datos en la calle.** Avisa si un banco no existe, está roto o no da sombra, o si falta un paso o una acera. Abre un *issue* con la dirección, una foto si puedes y la fecha.
- **Llevarlo a otro municipio.** Hacen falta su callejero, su inventario de bancos y la red de OpenStreetMap. El [mapa regional](README.md#qué-hace) dice por dónde empezar.
- **Probarlo con personas mayores** y contarnos qué no se entiende.

## Antes de abrir un *pull request*

1. Sigue el [arranque local](README.md#arranque-local).
2. Pasa las pruebas rápidas, que no necesitan datos: `python -m unittest pruebas.test_unidades`. Pasa también `npm --prefix web run build`.
3. Si cambias el motor, arranca el servidor y pasa `python3 pruebas/banco_api.py` y `.venv/bin/python -m ciudad.comprobar`. Si el cambio afecta a la cifra de impacto, vuelve a calcularla (ver [metodología](resultados/impacto/METODOLOGIA.md)) y explica la diferencia.
4. No subas datos personales, claves ni los datos compilados: van en la Release.

## Licencias

El código se publica con [Apache-2.0](LICENSE). Los datos derivados siguen las licencias de sus fuentes ([DATA-LICENSE.md](DATA-LICENSE.md)); los derivados de OpenStreetMap, ODbL.
