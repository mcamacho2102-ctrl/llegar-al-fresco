"""Pruebas unitarias rápidas, sin datos ni servidor (las corre la CI de GitHub).

    python -m unittest pruebas.test_unidades
"""

import unittest
from collections import defaultdict, deque
from types import SimpleNamespace

from ciudad import servicio
from ciudad.uso import Registro


def peticion(headers, host="10.0.0.1"):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


class LimiteDePeticiones(unittest.TestCase):
    def test_corta_al_llegar_al_limite_y_libera_tras_un_minuto(self):
        calls = defaultdict(deque)
        self.assertFalse(any(servicio.over_limit(calls, "a", 3, t) for t in (0, 1, 2)))
        self.assertTrue(servicio.over_limit(calls, "a", 3, 3))
        self.assertFalse(servicio.over_limit(calls, "b", 3, 3), "cada cliente tiene su ventana")
        self.assertFalse(servicio.over_limit(calls, "a", 3, 61.5), "la ventana es de 60 s")


class IpDelCliente(unittest.TestCase):
    def setUp(self):
        self.antes = (servicio.TRUST_PROXY, servicio.ON_FLY)

    def tearDown(self):
        servicio.TRUST_PROXY, servicio.ON_FLY = self.antes

    def test_sin_proxy_ignora_cabeceras(self):
        servicio.TRUST_PROXY, servicio.ON_FLY = False, False
        r = peticion({"x-forwarded-for": "1.2.3.4", "fly-client-ip": "5.6.7.8"})
        self.assertEqual(servicio.client_ip(r), "10.0.0.1")

    def test_detras_de_caddy_no_se_fia_de_fly_client_ip(self):
        servicio.TRUST_PROXY, servicio.ON_FLY = True, False
        r = peticion({"x-forwarded-for": "1.2.3.4", "fly-client-ip": "inventada"})
        self.assertEqual(servicio.client_ip(r), "1.2.3.4")

    def test_en_fly_usa_fly_client_ip(self):
        servicio.TRUST_PROXY, servicio.ON_FLY = True, True
        r = peticion({"x-forwarded-for": "1.2.3.4", "fly-client-ip": "5.6.7.8"})
        self.assertEqual(servicio.client_ip(r), "5.6.7.8")


class ClasificacionDeConsultas(unittest.TestCase):
    classify = staticmethod(lambda *a: Registro.classify(None, *a))

    def test_casos(self):
        corta = {"meters": 300}
        self.assertEqual(self.classify(corta, None, None), "sin_limite")
        self.assertEqual(self.classify(corta, None, 200), "sin_alternativa")
        self.assertEqual(self.classify(corta, {"meters": 320}, 200), "cumple", "tolerancia de 20 m")
        self.assertEqual(self.classify(corta, {"meters": 321}, 200), "rodeo")


class SeguimientoEnDirecto(unittest.TestCase):
    def setUp(self):
        servicio._seguimientos.clear()
        self.nuevo = servicio.crear_seguimiento(servicio.SeguimientoNuevo(
            origen="A", destino="B", geometria=[[-3.61, 40.403], [-3.608, 40.408]],
            bancos=[{"nombre": "Banco 1", "punto": [-3.609, 40.405], "aM": 200}]))

    def test_ciclo_completo(self):
        ident, clave = self.nuevo["id"], self.nuevo["clave"]
        self.assertIsNone(servicio.ver_seguimiento(ident)["posicion"])
        servicio.mover_seguimiento(ident, servicio.PosicionCompartida(clave=clave, lon=-3.609, lat=40.404, precision=12))
        visto = servicio.ver_seguimiento(ident)
        self.assertEqual(visto["posicion"]["punto"], [-3.609, 40.404])
        self.assertNotIn("clave", visto, "la clave nunca se devuelve a quien sigue")
        servicio.terminar_seguimiento(ident, servicio.FinSeguimiento(clave=clave, llegado=True))
        self.assertTrue(servicio.ver_seguimiento(ident)["terminado"]["llegado"])

    def test_sin_clave_no_se_mueve(self):
        with self.assertRaises(servicio.HTTPException) as e:
            servicio.mover_seguimiento(self.nuevo["id"], servicio.PosicionCompartida(clave="x" * 20, lon=-3.6, lat=40.4))
        self.assertEqual(e.exception.status_code, 403)

    def test_caduca(self):
        from datetime import timedelta
        servicio._seguimientos[self.nuevo["id"]]["caduca"] -= timedelta(hours=4)
        with self.assertRaises(servicio.HTTPException) as e:
            servicio.ver_seguimiento(self.nuevo["id"])
        self.assertEqual(e.exception.status_code, 404)

    def test_identificador_raro(self):
        with self.assertRaises(servicio.HTTPException):
            servicio.ver_seguimiento("../../etc")


class Buscador(unittest.TestCase):
    """Orden de resultados y etiquetas, sin datos ni red."""

    calle = {"label": "Calle Mayor, 1", "kind": "address", "source": "Callejero municipal", "coordinates": [-3.707, 40.416]}
    centro = {"label": "Centro de Salud Justicia — Centro de salud · Calle de Regueros 3", "kind": "health",
              "source": "Comunidad de Madrid", "coordinates": [-3.695, 40.425]}
    negocio = {"label": "Mercadona · Calle de Alcalá, 120", "kind": "address",
               "source": "Supermercado · a 300 m · OpenStreetMap", "coordinates": [-3.67, 40.42]}
    lugar = {"label": "Museo Nacional del Prado", "kind": "address", "source": "Lugar · CartoCiudad (IGN)",
             "coordinates": [-3.6925, 40.4138]}

    def test_con_numero_manda_el_callejero(self):
        r = servicio.mezclar("calle mayor 1", [self.calle], [self.lugar], [self.negocio])
        self.assertEqual(r[0]["label"], "Calle Mayor, 1")

    def test_por_nombre_primero_el_destino_propio_y_luego_negocios(self):
        r = servicio.mezclar("centro de salud justicia", [self.centro], [self.lugar], [self.negocio])
        self.assertEqual(r[0]["kind"], "health")
        self.assertIn("OpenStreetMap", r[1]["source"])

    def test_sin_duplicados_cercanos(self):
        cerca = dict(self.lugar, label="Museo del Prado", source="Museo · OpenStreetMap")
        r = servicio.mezclar("museo del prado", [], [self.lugar], [cerca])
        self.assertEqual(len(r), 1)

    def test_etiquetas(self):
        from ciudad.negocios import categoria, suave
        self.assertEqual(servicio.bonito("MUSEO NACIONAL DEL PRADO, Madrid"), "Museo Nacional del Prado")
        self.assertEqual(servicio.bonito("CALLE MAYOR 1 B", True), "Calle Mayor, 1 B")
        self.assertEqual(suave("Calle Del Butron, 16"), "Calle del Butron, 16")
        self.assertEqual(categoria({"shop": "supermarket"}), "Supermercado")
        self.assertIsNone(categoria({"amenity": "bench"}))


class NecesitoSentarme(unittest.TestCase):
    """Banco más cercano con una ciudad de mentira (sin datos)."""

    def test_nombre_del_banco(self):
        self.assertEqual(
            servicio.nombre_banco("Calle Riscos De Polanco 5", 58), "Banco en Calle Riscos de Polanco 5 · a 60 m"
        )
        self.assertEqual(servicio.nombre_banco("", 3), "Banco · a pocos pasos")
        self.assertEqual(
            servicio.nombre_banco("Paseo Paseo Puerta Del Angel 1", 62), "Banco en Paseo Puerta del Angel 1 · a 60 m"
        )

    def test_tres_mas_cercanos_sin_repetir_grupo_ni_pasar_de_400_m(self):
        from scipy.spatial import cKDTree

        x, y = servicio.TO_METERS.transform(-3.7038, 40.4168)
        pois = [
            {"id": "b1", "label": "Calle Mayor 1", "kind": "bench", "x": x + 50, "y": y},
            {"id": "b2", "label": "Calle Mayor 1", "kind": "bench", "x": x + 55, "y": y},  # mismo grupo
            {"id": "f1", "label": "Fuente", "kind": "drinking_water", "x": x + 5, "y": y},
            {"id": "b3", "label": "Calle Arenal 2", "kind": "bench", "x": x, "y": y + 120},
            {"id": "b4", "label": "Calle Sal 3", "kind": "bench", "x": x - 200, "y": y},
            {"id": "b5", "label": "Calle Lejos 4", "kind": "bench", "x": x + 300, "y": y},
            {"id": "b6", "label": "Calle Fuera 5", "kind": "bench", "x": x + 450, "y": y},
        ]
        city = SimpleNamespace(
            pois=pois,
            poi_tree=cKDTree([(p["x"], p["y"]) for p in pois]),
            locate=lambda lon, lat, **_: object(),
        )
        r = servicio.bancos_cerca(city, -3.7038, 40.4168)
        self.assertEqual([b["id"] for b in r], ["b1", "b3", "b4"])
        self.assertEqual(r[0]["straightM"], 50)
        self.assertEqual(r[0]["label"], "Banco en Calle Mayor 1 · a 50 m")
        self.assertAlmostEqual(r[0]["coordinates"][1], 40.4168, places=4)
        self.assertEqual(servicio.bancos_cerca(city, -3.7038, 40.4168, reach=40), [])


if __name__ == "__main__":
    unittest.main()
