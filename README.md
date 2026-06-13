# CFE Portal — Home Assistant Addon

Addon para Home Assistant que extrae automáticamente los datos de tu cuenta CFE y los publica como sensores via MQTT Discovery.

## ¿Qué hace?

Entra al portal [app.cfe.mx](https://app.cfe.mx/Aplicaciones/CCFE/MiEspacio/login.aspx) con tus credenciales, resuelve el captcha automáticamente via [2captcha.com](https://2captcha.com) y publica en Home Assistant:

| Sensor | Descripción |
|--------|-------------|
| `sensor.cfe_<nombre>_saldo` | Adeudo actual en MXN |
| `sensor.cfe_<nombre>_consumo` | Consumo del periodo en kWh |
| `sensor.cfe_<nombre>_fecha_de_corte` | Fecha de corte del periodo |
| `sensor.cfe_<nombre>_limite_de_pago` | Fecha límite para pagar |
| `sensor.cfe_<nombre>_recibo_pdf` | Ruta local del recibo descargado |
| `sensor.cfe_<nombre>_actualizacion` | Timestamp de la última consulta |

Soporta **múltiples cuentas** CFE desde una sola instalación.

## Requisitos

- Home Assistant con Supervisor (HAOS o Supervised)
- Addon **Mosquitto Broker** instalado y activo
- Cuenta en [2captcha.com](https://2captcha.com) con saldo (~$3 USD dura meses con uso normal)

## Instalación

1. Copiar la carpeta `addon-cfe` a `/addons/` en tu instancia de HA (via SSH o Samba)
2. En HA: **Configuración → Complementos → Tienda de complementos → ⋮ → Verificar actualizaciones**
3. El addon aparece en la sección **Complementos locales** — clic en Instalar
4. Ir a la pestaña **Configuración** y llenar credenciales
5. Iniciar el addon

## Configuración

```yaml
cuentas:
  - nombre: "Casa"       # Nombre libre, se usa como prefijo del sensor
    rpu: "123456789012"  # RPU de 12 dígitos (aparece en tu recibo)
    password: "tu_clave"
captcha_api_key: "TU_API_KEY_2CAPTCHA"
intervalo_horas: 12      # Cada cuántas horas consultar el portal
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: ""
mqtt_password: ""
debug_screenshots: false  # true para guardar capturas en /share/cfe_recibos/debug/
```

### Múltiples cuentas

```yaml
cuentas:
  - nombre: "Casa"
    rpu: "123456789012"
    password: "pass1"
  - nombre: "Taller"
    rpu: "987654321098"
    password: "pass2"
```

Cada cuenta genera su propio dispositivo MQTT con sensores independientes.

## Detalles técnicos

- **Scraping**: [Playwright](https://playwright.dev/) con Chromium headless — necesario porque el portal CFE es una aplicación ASP.NET WebForms con JavaScript
- **Captcha**: imagen estática (180×60px) resuelta via API de 2captcha. Costo estimado: < $0.01 USD/mes con consultas cada 12 horas
- **PDF**: los recibos se descargan en `/share/cfe_recibos/<nombre>_<AAAAMM>.pdf`
- **Arquitecturas**: `amd64`, `aarch64` (Raspberry Pi 4/5)

## Solución de problemas

**El captcha falla ocasionalmente** — es normal, 2captcha tiene ~97% de precisión en imágenes simples. El addon lo detecta y reintenta en el siguiente ciclo.

**Los datos no se extraen (saldo/consumo aparecen vacíos)** — CFE puede cambiar el HTML de su dashboard. Activar `debug_screenshots: true`, revisar las capturas en `/share/cfe_recibos/debug/` e identificar los nuevos selectores CSS.

**Sigue en login.aspx después del submit** — verificar que el RPU y la contraseña son correctos entrando manualmente al portal.

## Costo estimado de 2captcha

| Frecuencia | Captchas/mes | Costo aprox. |
|------------|-------------|--------------|
| Cada 12h, 1 cuenta | ~60 | $0.006 USD |
| Cada 6h, 2 cuentas | ~240 | $0.024 USD |
| Cada 1h, 1 cuenta | ~720 | $0.07 USD |

Precio de referencia: $1 USD por 1,000 captchas de imagen en 2captcha.com
