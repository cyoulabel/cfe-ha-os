#!/usr/bin/env python3
"""
CFE Portal Addon para Home Assistant v1.1
Extrae: saldo, consumo kWh, fecha corte, fecha pago, recibo PDF
Resuelve captcha de imagen via 2captcha.com
Publica via MQTT Discovery
"""

import asyncio
import base64
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from twocaptcha import TwoCaptcha

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cfe_addon")

OPTIONS_FILE  = "/data/options.json"

CFE_LOGIN_URL = "https://app.cfe.mx/Aplicaciones/CCFE/MiEspacio/login.aspx"
CFE_BASE_URL  = "https://app.cfe.mx"

# ID conocido de la imagen captcha en el portal CFE
CAPTCHA_IMG_ID = "ctl00_MainContent_Imagemanual"


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_options() -> dict:
    with open(OPTIONS_FILE) as f:
        return json.load(f)

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower().strip()).strip("_")

def parse_monto(text: str) -> float | None:
    clean = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(clean)
    except ValueError:
        return None

def parse_fecha(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ── Captcha solver ────────────────────────────────────────────────────────────

async def resolver_captcha(page, api_key: str) -> str:
    """
    Extrae la imagen captcha del portal CFE y la resuelve con 2captcha.
    Retorna el texto del captcha.
    """
    log.info("  Extrayendo imagen captcha...")

    # Intentar obtener la imagen por su ID conocido primero
    img_base64 = None

    # Método 1: ID exacto conocido del portal CFE
    try:
        img_element = await page.query_selector(f'img[id="{CAPTCHA_IMG_ID}"]')
        if img_element:
            # Obtener src (puede ser base64 inline o URL relativa)
            src = await img_element.get_attribute("src")
            if src and src.startswith("data:image"):
                # Ya viene en base64
                img_base64 = src.split(",", 1)[1]
                log.info(f"  Captcha obtenido desde src base64 (id={CAPTCHA_IMG_ID})")
            elif src:
                # Es una URL — hacer screenshot del elemento
                img_bytes = await img_element.screenshot()
                img_base64 = base64.b64encode(img_bytes).decode()
                log.info(f"  Captcha obtenido por screenshot del elemento (id={CAPTCHA_IMG_ID})")
    except Exception as e:
        log.debug(f"  Método 1 falló: {e}")

    # Método 2: buscar cualquier img cerca de un input de captcha
    if not img_base64:
        try:
            captcha_selectors = [
                'img[id*="captcha" i]',
                'img[id*="Captcha" i]',
                'img[id*="manual" i]',
                'img[id*="codigo" i]',
            ]
            for sel in captcha_selectors:
                el = await page.query_selector(sel)
                if el:
                    img_bytes = await el.screenshot()
                    img_base64 = base64.b64encode(img_bytes).decode()
                    log.info(f"  Captcha obtenido con selector: {sel}")
                    break
        except Exception as e:
            log.debug(f"  Método 2 falló: {e}")

    if not img_base64:
        raise Exception(
            "No se encontró la imagen captcha. "
            "Activar debug_screenshots y verificar que el ID sigue siendo "
            f"'{CAPTCHA_IMG_ID}' en el portal."
        )

    # Enviar a 2captcha
    log.info("  Enviando captcha a 2captcha.com...")
    solver = TwoCaptcha(api_key)
    result = solver.normal(img_base64, caseSensitive=0)
    texto = result["code"]
    log.info(f"  Captcha resuelto: '{texto}'")
    return texto


# ── Scraper ──────────────────────────────────────────────────────────────────

class CFEScraper:
    def __init__(self, cuenta: dict, captcha_api_key: str, pdf_dir: str, debug: bool = False):
        self.nombre          = cuenta["nombre"]
        self.usuario         = cuenta["usuario"]
        self.password        = cuenta["password"]
        self.num_servicio    = cuenta.get("num_servicio", "").replace(" ", "")
        self.captcha_api_key = captcha_api_key
        self.pdf_dir         = pdf_dir
        self.slug            = slugify(self.nombre)
        self.debug           = debug
        self.data: dict      = {}

    async def scrape(self) -> dict:
        async with async_playwright() as p:
            # Usar el Chromium del sistema instalado via apt-get
            chromium_path = "/usr/bin/chromium"
            browser = await p.chromium.launch(
                executable_path=chromium_path,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            try:
                await self._login(page)
                await self._select_servicio(page)
                await self._extract_data(page)
                await self._download_pdf(page, context)
            except PlaywrightTimeout as e:
                log.error(f"[{self.nombre}] Timeout: {e}")
                self.data["error"] = f"timeout: {e}"
            except Exception as e:
                log.error(f"[{self.nombre}] Error: {e}", exc_info=True)
                self.data["error"] = str(e)
                if self.debug:
                    await self._screenshot(page, "error")
            finally:
                await browser.close()

        self.data["ultima_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        log.info(f"[{self.nombre}] Resultado: {self.data}")
        return self.data

    # ── Login ─────────────────────────────────────────────────────────────────

    async def _login(self, page):
        log.info(f"[{self.nombre}] Navegando a login.aspx...")
        await page.goto(CFE_LOGIN_URL, timeout=30000, wait_until="networkidle")

        if self.debug:
            await self._screenshot(page, "01_inicio")

        # Log de inputs disponibles — útil si CFE cambia selectores
        inputs = await page.eval_on_selector_all(
            "input:not([type='hidden'])",
            "els => els.map(e => ({id: e.id, name: e.name, type: e.type}))"
        )
        log.info(f"[{self.nombre}] Inputs en página: {inputs}")

        # ── Campo Usuario ────────────────────────────────────────────────────────
        # El portal CFE usa "Usuario:" — acepta correo o número de servicio
        usuario_selectors = [
            'input[id$="txtUsuario"]',
            'input[id*="suario"]',
            'input[placeholder*="Usuario"]',
            'input[placeholder*="Correo"]',
            'input[type="text"]:first-of-type',
        ]
        await self._fill_first(page, usuario_selectors, self.usuario, "Usuario")

        # ── Contraseña ───────────────────────────────────────────────────────
        password_selectors = [
            'input[type="password"]',
            'input[id$="txtContrasena"]',
            'input[id*="ontrasena"]',
            'input[id*="assword"]',
        ]
        await self._fill_first(page, password_selectors, self.password, "contraseña")

        if self.debug:
            await self._screenshot(page, "02_credenciales")

        # ── Resolver captcha ─────────────────────────────────────────────────
        texto_captcha = await resolver_captcha(page, self.captcha_api_key)

        captcha_input_selectors = [
            'input[id$="txtCaptcha"]',
            'input[id$="txtcodigo"]',
            'input[id$="txtCodigo"]',
            'input[id*="aptcha"]',
            'input[id*="odigo"]',
            # Fallback: el input de texto que no es Usuario ni password
            'input[type="text"]:last-of-type',
        ]
        await self._fill_first(page, captcha_input_selectors, texto_captcha, "captcha")

        if self.debug:
            await self._screenshot(page, "03_captcha_llenado")

        # ── Submit ───────────────────────────────────────────────────────────
        submit_selectors = [
            'input[type="submit"]',
            'input[id$="btnEntrar"]',
            'input[id$="btnLogin"]',
            'input[id$="btnAcceder"]',
            'button[type="submit"]',
            'input[value*="Entrar"]',
            'input[value*="Acceder"]',
        ]
        submitted = False
        for sel in submit_selectors:
            try:
                await page.click(sel, timeout=2000)
                log.info(f"  ✓ Submit: {sel}")
                submitted = True
                break
            except:
                continue
        if not submitted:
            raise Exception("No se encontró botón de submit.")

        await page.wait_for_load_state("networkidle", timeout=25000)
        await page.wait_for_timeout(2000)

        current_url = page.url
        log.info(f"[{self.nombre}] URL post-login: {current_url}")

        if self.debug:
            await self._screenshot(page, "04_post_login")

        if "login.aspx" in current_url.lower():
            # Captcha incorrecto o credenciales malas — verificar cuál
            page_text = (await page.inner_text("body")).lower()
            if any(p in page_text for p in ["captcha", "código incorrecto", "codigo incorrecto"]):
                raise Exception("Captcha incorrecto (2captcha erró). Se reintentará en el siguiente ciclo.")
            raise Exception(
                "Login fallido: seguimos en login.aspx. "
                "Verificar Usuario y contraseña, o activar debug_screenshots."
            )

        log.info(f"[{self.nombre}] Login exitoso ✓")

    async def _fill_first(self, page, selectors: list, value: str, campo: str):
        """Llena el primer selector que funcione, lanza excepción si ninguno funciona."""
        for sel in selectors:
            try:
                await page.fill(sel, value, timeout=2000)
                log.info(f"  ✓ {campo} llenado: {sel}")
                return
            except:
                continue
        raise Exception(
            f"No se encontró el campo '{campo}'. "
            "Activar debug_screenshots y revisar el log de inputs."
        )

    # ── Selección de servicio ────────────────────────────────────────────────

    async def _select_servicio(self, page):
        """
        Si la cuenta tiene múltiples servicios, selecciona el correcto
        del dropdown ddlServicios. Si num_servicio está vacío, usa el primero.
        """
        try:
            # Verificar que existe el dropdown
            dropdown = await page.query_selector('#ctl00_MainContent_ddlServicios')
            if not dropdown:
                return  # una sola cuenta, no hay dropdown

            if self.num_servicio:
                # Seleccionar la opción que contenga el número de servicio
                options = await page.eval_on_selector_all(
                    '#ctl00_MainContent_ddlServicios option',
                    "opts => opts.map(o => ({value: o.value, text: o.text}))"
                )
                log.info(f"[{self.nombre}] Servicios disponibles: {[o['text'] for o in options]}")

                match = None
                for opt in options:
                    if self.num_servicio in opt['value'].replace(' ', '') or                        self.num_servicio in opt['text'].replace(' ', ''):
                        match = opt['value']
                        break

                if match:
                    await page.select_option('#ctl00_MainContent_ddlServicios', value=match)
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    log.info(f"[{self.nombre}] Servicio seleccionado: {match}")
                else:
                    log.warning(f"[{self.nombre}] No se encontró servicio '{self.num_servicio}' en el dropdown, usando el primero")
            else:
                # Leer qué servicio está seleccionado por defecto
                selected = await page.eval_on_selector(
                    '#ctl00_MainContent_ddlServicios',
                    "el => el.options[el.selectedIndex].text"
                )
                log.info(f"[{self.nombre}] Usando servicio por defecto: {selected}")
        except Exception as e:
            log.debug(f"[{self.nombre}] _select_servicio: {e} (normal si hay un solo servicio)")

    # ── Extracción de datos ───────────────────────────────────────────────────

    async def _extract_data(self, page):
        log.info(f"[{self.nombre}] Extrayendo datos del dashboard...")

        # Esperar a que cargue el monto — ID exacto del portal CFE
        try:
            await page.wait_for_selector('#ctl00_MainContent_lblMonto', timeout=20000)
        except:
            await page.wait_for_timeout(5000)

        if self.debug:
            await self._screenshot(page, "05_dashboard")

        # IDs exactos obtenidos del HTML real del portal CFE (Mi Espacio)
        self.data["saldo"]         = await self._try_number(page, ['#ctl00_MainContent_lblMonto'])
        self.data["periodo"]       = await self._try_text(page,   ['#ctl00_MainContent_lblPeriodoConsumo'])
        self.data["fecha_limite"]  = await self._try_text(page,   ['#ctl00_MainContent_lblFechaLimite'])
        self.data["estado_recibo"] = await self._try_text(page,   ['#ctl00_MainContent_lblEstadoRecibo'])
        self.data["num_servicio"]  = await self._try_text(page,   ['#ctl00_MainContent_lblNumeroServicio'])
        self.data["nombre_cuenta"] = self.nombre
        self.data["error"]          = "OK"  # limpiar errores de intentos anteriores

        log.info(
            f"[{self.nombre}] "
            f"saldo={self.data.get('saldo')} | "
            f"periodo={self.data.get('periodo')} | "
            f"limite={self.data.get('fecha_limite')} | "
            f"estado={self.data.get('estado_recibo')}"
        )

    async def _try_number(self, page, selectors) -> float | None:
        for sel in selectors:
            try:
                text = await page.inner_text(sel, timeout=2000)
                val = parse_monto(text)
                if val is not None:
                    return val
            except:
                continue
        return None

    async def _try_text(self, page, selectors) -> str | None:
        for sel in selectors:
            try:
                text = await page.inner_text(sel, timeout=2000)
                cleaned = parse_fecha(text)
                if cleaned and len(cleaned) > 2:
                    return cleaned
            except:
                continue
        return None

    # ── Descarga PDF ──────────────────────────────────────────────────────────

    async def _download_pdf(self, page, context):
        Path(self.pdf_dir).mkdir(parents=True, exist_ok=True)

        # Nombre del PDF basado en el periodo del recibo
        # "20 MAR 26 al 19 MAY 26" → "20MAR26_19MAY26"
        periodo = self.data.get("periodo", "")
        if periodo:
            periodo_slug = periodo.replace(" al ", "_").replace(" ", "")
        else:
            periodo_slug = datetime.now().strftime("%Y%m")

        filename = f"{self.pdf_dir}/{self.slug}_{periodo_slug}.pdf"

        # Si ya existe el PDF de este periodo, no descargar de nuevo
        if Path(filename).exists():
            log.info(f"[{self.nombre}] PDF ya existe para periodo '{periodo}', omitiendo descarga")
            self.data["recibo_pdf"] = filename
            return

        log.info(f"[{self.nombre}] Descargando PDF periodo '{periodo}'...")

        # Esperar tabla de historial
        try:
            await page.wait_for_selector('#ctl00_MainContent_GVHistorial', timeout=10000)
            log.info(f"[{self.nombre}] GVHistorial encontrado")
        except Exception as e:
            log.info(f"[{self.nombre}] GVHistorial no encontrado: {e}")
            self.data["recibo_pdf"] = "no_encontrado"
            return

        # Método 1: click en enlace + expect_download
        try:
            async with page.expect_download(timeout=20000) as dl_info:
                await page.click('a[title="Descarga Pdf"]', timeout=5000)
            download = await dl_info.value
            await download.save_as(filename)
            self.data["recibo_pdf"] = filename
            log.info(f"[{self.nombre}] PDF guardado: {filename}")
            return
        except Exception as e:
            log.info(f"  Método 1 (click) falló: {e}")

        # Método 2: __doPostBack + expect_download
        try:
            async with page.expect_download(timeout=20000) as dl_info:
                await page.evaluate(
                    "__doPostBack('ctl00$MainContent$GVHistorial$ctl02$DescargaPDF', '')"
                )
            download = await dl_info.value
            await download.save_as(filename)
            self.data["recibo_pdf"] = filename
            log.info(f"[{self.nombre}] PDF guardado (postback): {filename}")
            return
        except Exception as e:
            log.info(f"  Método 2 (postback) falló: {e}")

        # Método 3: interceptar respuesta de red
        try:
            pdf_response = None
            async def capture_pdf(response):
                nonlocal pdf_response
                ct = response.headers.get("content-type", "")
                cd = response.headers.get("content-disposition", "")
                if "pdf" in ct.lower() or "pdf" in cd.lower():
                    pdf_response = response
                    log.info(f"  PDF detectado en red: {response.url[:80]}")
            page.on("response", capture_pdf)
            await page.evaluate(
                "__doPostBack('ctl00$MainContent$GVHistorial$ctl02$DescargaPDF', '')"
            )
            await page.wait_for_timeout(8000)
            page.remove_listener("response", capture_pdf)
            if pdf_response:
                pdf_bytes = await pdf_response.body()
                with open(filename, "wb") as f:
                    f.write(pdf_bytes)
                self.data["recibo_pdf"] = filename
                log.info(f"[{self.nombre}] PDF guardado (intercept): {filename}")
                return
            else:
                log.info(f"  Método 3: sin respuesta PDF en red")
        except Exception as e:
            log.info(f"  Método 3 (intercept) falló: {e}")

        log.warning(f"[{self.nombre}] PDF no descargado")
        self.data["recibo_pdf"] = "no_encontrado"

    # ── Debug screenshots ─────────────────────────────────────────────────────

    async def _screenshot(self, page, nombre: str):
        screenshots_dir = f"{self.pdf_dir}/debug"
        Path(screenshots_dir).mkdir(parents=True, exist_ok=True)
        path = f"{screenshots_dir}/{self.slug}_{nombre}.png"
        await page.screenshot(path=path, full_page=True)
        log.debug(f"  Screenshot: {path}")


# ── MQTT Publisher ────────────────────────────────────────────────────────────

class MQTTPublisher:
    def __init__(self, host, port, username=None, password=None):
        self.client = mqtt.Client(client_id="cfe_addon", clean_session=True)
        if username:
            self.client.username_pw_set(username, password)
        self.client.connect(host, port, keepalive=60)
        self.client.loop_start()
        log.info(f"MQTT conectado a {host}:{port}")

    def publish_discovery(self, slug: str, nombre: str):
        device = {
            "identifiers": [f"cfe_{slug}"],
            "name": f"CFE {nombre}",
            "manufacturer": "CFE",
            "model": "Portal CFE MX",
        }
        sensors = [
            {"key": "saldo",              "name": f"CFE {nombre} Saldo",           "unit": "MXN", "icon": "mdi:cash",                 "state_class": "measurement"},
            {"key": "periodo",            "name": f"CFE {nombre} Periodo",                        "icon": "mdi:calendar-range"},
            {"key": "fecha_limite",       "name": f"CFE {nombre} Fecha Límite",                   "icon": "mdi:calendar-alert"},
            {"key": "estado_recibo",      "name": f"CFE {nombre} Estado Recibo",                  "icon": "mdi:check-circle-outline"},
            {"key": "num_servicio",       "name": f"CFE {nombre} Núm. Servicio",                  "icon": "mdi:identifier"},
            {"key": "recibo_pdf",         "name": f"CFE {nombre} Recibo PDF",                     "icon": "mdi:file-pdf-box"},
            {"key": "ultima_actualizacion","name": f"CFE {nombre} Actualización",                 "icon": "mdi:update"},
            {"key": "error",              "name": f"CFE {nombre} Estado",                         "icon": "mdi:alert-circle-outline"},
        ]
        for s in sensors:
            uid = f"cfe_{slug}_{s['key']}"
            payload = {
                "name":         s["name"],
                "unique_id":    uid,
                "state_topic":  f"cfe/{slug}/{s['key']}",
                "icon":         s.get("icon"),
                "device":       device,
            }
            if "unit"         in s: payload["unit_of_measurement"] = s["unit"]
            if "device_class" in s: payload["device_class"]        = s["device_class"]
            if "state_class"  in s: payload["state_class"]         = s["state_class"]
            self.client.publish(f"homeassistant/sensor/{uid}/config", json.dumps(payload), retain=True)

        log.info(f"Discovery publicado para '{nombre}'")

    def publish_data(self, slug: str, data: dict):
        for key, value in data.items():
            self.client.publish(f"cfe/{slug}/{key}", str(value) if value is not None else "desconocido", retain=True)
        log.info(f"Datos publicados para '{slug}'")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()


# ── Main ──────────────────────────────────────────────────────────────────────

async def run_cycle(options: dict):
    cuentas         = options.get("cuentas", [])
    captcha_api_key = options.get("captcha_api_key", "")
    mqtt_host       = options.get("mqtt_host", "core-mosquitto")
    mqtt_port       = int(options.get("mqtt_port", 1883))
    mqtt_user       = options.get("mqtt_user") or None
    mqtt_pass       = options.get("mqtt_password") or None
    debug           = options.get("debug_screenshots", False)
    pdf_dir         = options.get("pdf_dir", "/share/cfe_recibos")

    if not captcha_api_key:
        log.error("captcha_api_key no configurado. Registrarse en 2captcha.com y agregar la API key en opciones.")
        return
    if not cuentas:
        log.warning("No hay cuentas configuradas.")
        return

    publisher = MQTTPublisher(mqtt_host, mqtt_port, mqtt_user, mqtt_pass)

    periodos_resultado = {}

    for cuenta in cuentas:
        log.info(f"─── {cuenta.get('nombre')} (Usuario: {cuenta.get('usuario','')[:4]}***) ───")
        slug = slugify(cuenta["nombre"])

        # Hasta 3 reintentos si el captcha falla
        max_intentos = 3
        for intento in range(1, max_intentos + 1):
            if intento > 1:
                log.info(f"  Reintento {intento}/{max_intentos} en 15 segundos...")
                await asyncio.sleep(15)

            scraper = CFEScraper(cuenta, captcha_api_key, pdf_dir=pdf_dir, debug=debug)
            data    = await scraper.scrape()

            # Si el error es de captcha, reintentar; cualquier otro error, no
            error = data.get("error", "")
            if "captcha" in error.lower() and intento < max_intentos:
                log.warning(f"  Captcha incorrecto, reintentando...")
                continue
            break  # Éxito o error no-captcha

        publisher.publish_discovery(slug, cuenta["nombre"])
        publisher.publish_data(slug, data)
        periodos_resultado[slug] = {
            "periodo":       data.get("periodo", ""),
            "estado_recibo": data.get("estado_recibo", ""),
            "pdf_ok":        data.get("recibo_pdf", "no_encontrado") not in ("no_encontrado", ""),
        }

    publisher.disconnect()
    log.info("✓ Ciclo completado.")


# Meses en español para parsear el periodo CFE
MESES_ES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12
}

def parse_fecha_cfe(texto: str):
    """'20 MAR 26' → datetime(2026, 3, 20)"""
    try:
        partes = texto.strip().split()
        dia = int(partes[0])
        mes = MESES_ES.get(partes[1].upper(), 0)
        anio = 2000 + int(partes[2])
        return datetime(anio, mes, dia)
    except:
        return None

def calcular_proximo_inicio(periodo: str):
    """
    '20 MAR 26 al 19 MAY 26' → próximo inicio esperado (inicio + 2 meses)
    """
    try:
        inicio_str = periodo.split(" al ")[0].strip()
        inicio = parse_fecha_cfe(inicio_str)
        if not inicio:
            return None
        # Sumar 2 meses
        mes = inicio.month + 2
        anio = inicio.year + (mes - 1) // 12
        mes = ((mes - 1) % 12) + 1
        return datetime(anio, mes, inicio.day)
    except:
        return None

def calcular_sleep(options: dict, ultimo_periodo: str, estado: str, pdf_ok: bool) -> float:
    """
    Lógica de sleep inteligente:
    - PAGADO + PDF descargado → dormir hasta (próximo periodo - dias_anticipo)
    - PENDIENTE o sin PDF     → revisar cada intervalo_horas (puede no haberse pagado)
    """
    intervalo_horas = int(options.get("intervalo_horas", 24))
    dias_anticipo   = int(options.get("dias_anticipo", 5))
    ahora           = datetime.now()

    pagado  = estado.upper() == "PAGADO" if estado else False
    pdf_listo = pdf_ok and ultimo_periodo

    if pagado and pdf_listo:
        proximo_inicio = calcular_proximo_inicio(ultimo_periodo)
        if proximo_inicio:
            fecha_despertar = proximo_inicio - timedelta(days=dias_anticipo)
            if fecha_despertar > ahora:
                segundos = (fecha_despertar - ahora).total_seconds()
                log.info(
                    f"Recibo PAGADO ✓ | "
                    f"Próximo recibo: {proximo_inicio.strftime('%d/%m/%Y')} | "
                    f"Revisando desde: {fecha_despertar.strftime('%d/%m/%Y')} | "
                    f"Durmiendo {segundos/3600:.1f}h ({segundos/86400:.1f} días)"
                )
                return segundos

    # PENDIENTE o no pudo descargar PDF → revisar normalmente
    razon = "PENDIENTE" if not pagado else "PDF pendiente"
    log.info(f"Estado: {razon} — próximo ciclo en {intervalo_horas}h")
    return intervalo_horas * 3600


def main():
    options = load_options()
    intervalo_horas = int(options.get("intervalo_horas", 24))

    log.info("=" * 55)
    log.info("  CFE Portal Addon v1.1  |  captcha: 2captcha.com")
    log.info(f"  Cuentas: {len(options.get('cuentas',[]))}  |  Intervalo: {intervalo_horas}h")
    log.info("=" * 55)

    ultimo_resultado = {}  # {slug: {periodo, estado, pdf_ok}}

    while True:
        try:
            resultado = asyncio.run(run_cycle(options))
            if isinstance(resultado, dict):
                ultimo_resultado.update(resultado)
        except Exception as e:
            log.error(f"Error en ciclo principal: {e}", exc_info=True)

        # Sleep inteligente: usa la primera cuenta como referencia
        ref = next(iter(ultimo_resultado.values()), {}) if ultimo_resultado else {}
        segundos = calcular_sleep(
            options,
            ultimo_periodo = ref.get("periodo", ""),
            estado         = ref.get("estado_recibo", ""),
            pdf_ok         = ref.get("pdf_ok", False),
        )
        time.sleep(segundos)


if __name__ == "__main__":
    main()
