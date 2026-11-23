#!/usr/bin/env python3
"""Banco de pruebas en navegador (Playwright): recorridos por perfiles y accesibilidad.

    python pruebas/banco_web.py [http://127.0.0.1:8768] [carpeta_capturas]

Necesita playwright con Chromium. Usa axe-core (cdnjs) para la auditoría de accesibilidad.
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8768").rstrip("/")
HOME = "/?sin-registro"  # las pruebas no cuentan en el informe de uso
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else "pruebas/capturas")
SHOTS.mkdir(parents=True, exist_ok=True)
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
RESULTS = []
GL = ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"]


def record(area, name, status, detail=""):
    RESULTS.append({"area": area, "prueba": name, "estado": status, "detalle": detail})
    print(f"[{status:5}] {area} · {name}{' · ' + detail if detail else ''}", flush=True)


def axe(page, label):
    try:
        page.add_script_tag(url=AXE)
        result = page.evaluate(
            "async () => (await axe.run(document, {resultTypes: ['violations']})).violations"
            ".map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, help: v.help,"
            " ejemplo: v.nodes[0] && v.nodes[0].target.join(' ')}))"
        )
    except Exception as e:  # sin red o CSP
        record("Accesibilidad", f"axe · {label}", "AVISO", f"no se pudo ejecutar: {e}")
        return
    serious = [v for v in result if v["impact"] in ("serious", "critical")]
    status = "FALLO" if serious else ("AVISO" if result else "OK")
    detail = "; ".join(f"{v['id']} ({v['impact']}, {v['n']}): {v['ejemplo']}" for v in result[:6])
    record("Accesibilidad", f"axe · {label}", status, detail or "sin incidencias")


def small_targets(page, scope="main"):
    return page.evaluate(
        """(scope) => [...document.querySelectorAll(scope + ' button, ' + scope + ' a, ' + scope + ' input, ' + scope + ' select, ' + scope + ' summary')]
        .filter(e => e.offsetParent !== null)
        .map(e => { const r = e.getBoundingClientRect(); return {t: (e.innerText || e.getAttribute('aria-label') || e.type || '').trim().slice(0, 30), w: Math.round(r.width), h: Math.round(r.height)}; })
        .filter(x => (x.h < 44 || x.w < 44) && x.t !== 'checkbox')""",
        scope,
    )


def overflow(page):
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def min_font(page, selector):
    return page.evaluate(
        """(sel) => Math.min(...[...document.querySelectorAll(sel + ' *')].filter(e => e.offsetParent !== null && e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())).map(e => parseFloat(getComputedStyle(e).fontSize)))""",
        selector,
    )


def fill_address(page, index, text):
    box = page.locator(".paso input[role=combobox]").nth(index)
    box.click()
    box.fill(text)
    page.wait_for_selector("[role=option]", timeout=8000)
    page.locator("[role=option]").first.click()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=GL)

        # ---------- Persona: persona mayor en móvil ----------
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, bypass_csp=True)  # axe
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        t = time.perf_counter()
        page.goto(BASE + HOME, wait_until="networkidle")
        load = time.perf_counter() - t
        timing = page.evaluate("JSON.stringify(performance.getEntriesByType('navigation')[0].toJSON())")
        nav = json.loads(timing)
        transfer = page.evaluate("performance.getEntriesByType('resource').reduce((s, r) => s + (r.transferSize || 0), 0)")
        record("Rendimiento", "Carga inicial en móvil", "OK" if load < 4 else "AVISO",
               f"{load:.1f} s hasta red en reposo · DOMContentLoaded {nav['domContentLoadedEventEnd']:.0f} ms · {transfer/1e6:.1f} MB transferidos")
        record("Mayores", "Sin desbordamiento horizontal (390 px)", "OK" if overflow(page) <= 0 else "FALLO", f"{overflow(page)} px")
        small = small_targets(page)
        record("Mayores", "Botones de al menos 44 × 44 px", "OK" if not small else "AVISO", json.dumps(small[:6], ensure_ascii=False))
        mf = min_font(page, "main.sencillo")
        record("Mayores", "Letra mínima en la pantalla principal", "OK" if mf >= 15 else "AVISO", f"{mf:.0f} px")
        axe(page, "inicio móvil")

        # Botón de destino sin salida
        page.get_by_role("button", name="Centro de salud").click()
        msg = page.locator(".error-simple").inner_text() if page.locator(".error-simple").count() else ""
        record("Mayores", "Aviso si elige destino antes de la salida", "OK" if "paso 1" in msg else "FALLO", msg[:80])
        search_btn = page.get_by_role("button", name="Buscar mi ruta")
        record("Mayores", "Buscar desactivado sin datos (y explicado)", "OK" if search_btn.is_disabled() and page.locator(".pista").count() else "FALLO")

        # Flujo completo
        fill_address(page, 0, "Calle de Toledo 46")
        page.get_by_role("button", name="Centro de salud").click()
        page.wait_for_selector(".cercano", timeout=8000)
        page.locator(".cercano").first.click()
        page.get_by_role("radio", name="150 m").click()
        t = time.perf_counter()
        search_btn.click()
        page.wait_for_selector(".frase", timeout=30000)
        record("Mayores", "Flujo completo: dirección → centro de salud → 150 m", "OK", f"{time.perf_counter() - t:.1f} s · «{page.locator('.frase h2').inner_text()}»")
        page.screenshot(path=str(SHOTS / "mayor_resultado.png"), full_page=True)
        mf = min_font(page, ".frase")
        record("Mayores", "Letra mínima en el resultado", "OK" if mf >= 15 else "AVISO", f"{mf:.0f} px")
        axe(page, "resultado móvil")
        top = page.evaluate("document.getElementById('resultado').getBoundingClientRect().top")
        record("Mayores", "Desplaza la pantalla hasta el resultado", "OK" if top < 500 else "AVISO", f"resultado a {top:.0f} px del borde superior")

        # Capas
        for name in ("Sol y sombra", "Cuestas", "Ancho de acera", "Ruta"):
            page.get_by_role("radio", name=name).click()
            time.sleep(0.4)
        record("Mayores", "Cambiar entre las 4 capas", "OK" if not errors else "FALLO", "; ".join(errors[:2]))

        # Opciones avanzadas: ancho 1,5 m
        page.locator("summary", has_text="Opciones avanzadas").click()
        page.get_by_role("button", name="1,5 m · silla de ruedas").click()
        search_btn.click()
        time.sleep(4)
        shown = page.locator(".frase").count()
        err = page.locator(".error-simple").inner_text() if page.locator(".error-simple").count() else ""
        warn = page.locator(".aviso-ruta").inner_text() if page.locator(".aviso-ruta").count() else ""
        record("Movilidad reducida", "Ancho mínimo 1,5 m: respuesta comprensible", "OK" if shown and (warn or True) else "FALLO",
               (warn or (page.locator(".frase h2").inner_text() if shown else err or "la pantalla no muestra nada"))[:120])
        page.screenshot(path=str(SHOTS / "silla_ruedas.png"), full_page=True)
        ctx.close()

        # ---------- Persona: familiar que marca puntos en el mapa (escritorio, CSP activa) ----------
        ctx = browser.new_context(viewport={"width": 1280, "height": 860})
        page = ctx.new_page()
        csp = []
        page.on("console", lambda m: csp.append(m.text) if "Content Security Policy" in m.text else None)
        page.goto(BASE + HOME, wait_until="networkidle")
        page.locator(".paso").nth(0).get_by_role("button", name="Mapa").click()
        overlay = page.locator(".selector-mapa")
        box = overlay.bounding_box() if overlay.count() else None
        full = box and box["width"] >= 1200 and box["height"] >= 800
        record("Familias", "«Mapa» abre selector a pantalla completa", "OK" if full else "FALLO", str(box))
        time.sleep(2)
        # Nota: una captura de pantalla aquí (CDP) impide que el clic siguiente fije el punto
        # en Chromium sin GPU; la captura del selector se hace en la segunda apertura.
        page.get_by_role("button", name="Usar el centro del mapa").wait_for(timeout=15000)
        page.get_by_role("button", name="Usar el centro del mapa").click()
        page.locator(".selector-mapa").wait_for(state="detached", timeout=10000)
        label = page.locator(".paso input[role=combobox]").first.input_value()
        record("Familias", "Usar el centro del mapa como salida", "OK" if "mapa" in label.lower() else "FALLO", label)
        page.get_by_role("button", name="Otra dirección").click()
        page.locator(".paso").nth(1).get_by_role("button", name="Mapa").click()
        time.sleep(2)
        page.screenshot(path=str(SHOTS / "selector_mapa.png"))
        page.keyboard.press("Escape")
        record("Familias", "Escape cierra el selector", "OK" if not page.locator(".selector-mapa").count() else "AVISO")
        fill_address(page, 1, "Plaza Mayor 1")
        page.get_by_role("button", name="Buscar mi ruta").click()
        page.wait_for_selector(".frase, .error-simple", timeout=30000)
        record("Familias", "Ruta desde un punto del mapa", "OK" if page.locator(".frase").count() else "FALLO",
               page.locator(".frase h2, .error-simple").first.inner_text()[:90])
        # Impresión
        page.emulate_media(media="print")
        page.screenshot(path=str(SHOTS / "impresion.png"), full_page=True)
        page.emulate_media(media="screen")
        record("Familias", "Vista de impresión generada", "OK", "revisar captura impresion.png")
        record("Seguridad", "La política CSP no bloquea nada de la app", "OK" if not csp else "FALLO", "; ".join(csp[:2])[:160])
        ctx.close()

        # ---------- Buscar por nombre ----------
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(BASE + HOME, wait_until="networkidle")
        page.get_by_role("button", name="Otra dirección").click()
        box = page.locator(".paso input[role=combobox]").nth(1)
        box.click(); box.fill("Gregorio Marañón")
        try:
            page.wait_for_selector("[role=option]", timeout=6000)
            top = page.locator("[role=option]").first.inner_text()
        except Exception:
            top = ""
        record("Mayores", "Buscar «Gregorio Marañón» por su nombre", "OK" if "Marañ" in top else "FALLO", top.replace("\n", " ")[:90])
        ctx.close()

        # ---------- Teclado ----------
        ctx = browser.new_context(viewport={"width": 1280, "height": 860})
        page = ctx.new_page()
        page.goto(BASE + HOME, wait_until="networkidle")
        reached = None
        for i in range(60):
            page.keyboard.press("Tab")
            focus = page.evaluate("document.activeElement && (document.activeElement.innerText || document.activeElement.getAttribute('aria-label') || document.activeElement.tagName)")
            if focus and "Centro de salud" in focus:
                reached = i + 1
                break
        record("Teclado", "Se llega a los destinos con Tab", "OK" if reached else "FALLO", f"{reached} pulsaciones")
        visible = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        record("Teclado", "Foco visible", "OK" if visible != "none" else "FALLO", visible)
        ctx.close()

        # ---------- Reflujo a 320 px y zoom ----------
        ctx = browser.new_context(viewport={"width": 320, "height": 640})
        page = ctx.new_page()
        page.goto(BASE + HOME, wait_until="networkidle")
        record("Accesibilidad", "Reflujo a 320 px (WCAG 1.4.10)", "OK" if overflow(page) <= 0 else "FALLO", f"{overflow(page)} px")
        page.evaluate("document.body.style.zoom = '2'")
        time.sleep(0.5)
        record("Accesibilidad", "Zoom al 200 % sin cortar contenido", "OK" if overflow(page) <= 1 else "AVISO", f"{overflow(page)} px de desbordamiento")
        ctx.close()

        # ---------- Geolocalización ----------
        for name, coords, expect in (("en Madrid", {"latitude": 40.4168, "longitude": -3.7038}, "ok"),
                                     ("en Barcelona", {"latitude": 41.3851, "longitude": 2.1734}, "error")):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, geolocation=coords, permissions=["geolocation"])
            page = ctx.new_page()
            page.goto(BASE + HOME, wait_until="networkidle")
            page.get_by_role("button", name="Usar mi ubicación").click()
            time.sleep(1.5)
            value = page.locator(".paso input[role=combobox]").first.input_value()
            if expect == "ok":
                record("Ubicación", f"Usar mi ubicación {name}", "OK" if value else "FALLO", value)
            else:
                err = page.locator(".error-simple").inner_text() if page.locator(".error-simple").count() else ""
                listed = page.locator(".cercano").count()
                record("Ubicación", f"Usar mi ubicación {name}", "OK" if "Madrid" in err and not value else "FALLO",
                       f"aviso: «{err[:90]}» · salida rellenada: «{value}»")
            ctx.close()

        # ---------- Técnicos municipales ----------
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, bypass_csp=True)  # axe
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + HOME, wait_until="networkidle")
        page.get_by_role("button", name="Para ayuntamientos →").click()
        page.wait_for_selector(".informe-kpis", timeout=15000)
        record("Ayuntamientos", "Informe de uso carga", "OK", page.locator(".informe-kpis").inner_text().replace("\n", " ")[:120])
        axe(page, "informe")
        with page.expect_download() as dl:
            page.get_by_role("link", name="Descargar CSV").click()
        record("Ayuntamientos", "Descarga CSV", "OK", dl.value.suggested_filename)
        page.get_by_role("button", name="Simulador de mejoras", exact=True).click()
        page.get_by_role("button", name="Cargar ejemplo").click()
        time.sleep(1.5)
        page.get_by_role("button", name="Comparar rutas").first.click()
        time.sleep(4)
        page.get_by_role("button", name="Buscar ubicaciones para bancos").first.click()
        page.wait_for_selector(".bank-plan", timeout=60000)
        record("Ayuntamientos", "Simulador: buscar ubicaciones", "OK", f"{page.locator('.bank-options > *').count()} candidatos")
        page.get_by_role("button", name="Mapa regional").click()
        page.wait_for_selector(".impact", timeout=15000)
        axe(page, "mapa regional")
        record("Ayuntamientos", "Sin errores de JavaScript en la zona técnica", "OK" if not errors else "FALLO", "; ".join(errors[:2]))
        ctx.close()
        browser.close()

    counts = {s: sum(1 for r in RESULTS if r["estado"] == s) for s in ("OK", "AVISO", "FALLO")}
    print("\nRESUMEN", counts)
    Path("pruebas/resultado_web.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1))
    return 1 if counts["FALLO"] else 0


if __name__ == "__main__":
    sys.exit(main())
