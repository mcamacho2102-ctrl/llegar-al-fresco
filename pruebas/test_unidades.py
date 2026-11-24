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


if __name__ == "__main__":
    unittest.main()
