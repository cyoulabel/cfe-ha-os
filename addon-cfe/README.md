# CFE Portal — Home Assistant Addon

Extrae automáticamente los datos de tu cuenta CFE y los publica como sensores en Home Assistant via MQTT Discovery.

## Sensores

| Sensor | |
|--------|---|
| `sensor.cfe_<nombre>_saldo` | Adeudo actual en MXN |
| `sensor.cfe_<nombre>_periodo` | Periodo de consumo |
| `sensor.cfe_<nombre>_fecha_limite` | Fecha límite de pago |
| `sensor.cfe_<nombre>_estado_recibo` | PAGADO / PENDIENTE |
| `sensor.cfe_<nombre>_num_servicio` | Número de servicio |
| `sensor.cfe_<nombre>_recibo_pdf` | Ruta del PDF descargado |

## Requisitos

- Home Assistant con Supervisor
- Addon **Mosquitto Broker** activo
- API key de [2captcha.com](https://2captcha.com) (~$3 USD dura meses)

## Instalación

Agregar como repositorio en HA:

```
https://github.com/cyoulabel/cfe-ha-os
```

**Configuración → Complementos → Tienda → ⋮ → Repositorios**

## Configuración

```yaml
cuentas:
  - nombre: "Casa"
    usuario: "tu_correo@mail.com"
    password: "tu_clave"
    num_servicio: "933161991716"  # opcional, del dropdown si tienes varias cuentas
captcha_api_key: "TU_API_KEY"
intervalo_horas: 24
dias_anticipo: 5        # días antes del próximo recibo para empezar a revisar
pdf_dir: "/config/www/cfe"
mqtt_host: core-mosquitto
mqtt_port: 1883
```

## Notas

El addon es inteligente con el schedule: una vez que detecta el recibo como **PAGADO** y descarga el PDF, duerme automáticamente hasta ~5 días antes del próximo periodo bimestral. Mientras el recibo esté **PENDIENTE** revisa cada `intervalo_horas`.

El captcha se resuelve via 2captcha (~$0.001 USD por ciclo).
