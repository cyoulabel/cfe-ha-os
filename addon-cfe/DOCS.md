# CFE Portal Addon

Extrae automáticamente datos de tu cuenta CFE y los publica en Home Assistant via MQTT Discovery.

## Sensores creados por cuenta

| Sensor | Unidad | Descripción |
|--------|--------|-------------|
| `sensor.cfe_<nombre>_saldo` | MXN | Adeudo actual |
| `sensor.cfe_<nombre>_consumo` | kWh | Consumo del periodo |
| `sensor.cfe_<nombre>_fecha_de_corte` | — | Fecha de corte del periodo |
| `sensor.cfe_<nombre>_limite_de_pago` | — | Fecha límite para pagar |
| `sensor.cfe_<nombre>_recibo_pdf` | — | Ruta del PDF en `/share/cfe_recibos/` |
| `sensor.cfe_<nombre>_actualizacion` | — | Timestamp de la última consulta |

## Configuración (options.json)

```json
{
  "cuentas": [
    {
      "nombre": "Privada Muñoz",
      "rpu": "TU_RPU_AQUI",
      "password": "TU_PASSWORD"
    }
  ],
  "intervalo_horas": 12,
  "mqtt_host": "core-mosquitto",
  "mqtt_port": 1883,
  "mqtt_user": "",
  "mqtt_password": "",
  "debug_screenshots": false
}
```

## Notas importantes

### RPU vs Email
El portal CFE acepta tanto el RPU (número de 12 dígitos en tu recibo) como el correo
con el que te registraste. Usa el mismo que usas al entrar manualmente.

### Ajuste de selectores
Si CFE cambia su portal, los selectores CSS pueden fallar. Para diagnosticar:
1. Activa `debug_screenshots: true` en opciones
2. Los screenshots se guardan en `/share/cfe_recibos/debug/`
3. Compara con el HTML del portal actual y ajusta en `cfe_scraper.py`

### PDF
Los recibos se guardan en `/share/cfe_recibos/<nombre>_<AAAAMM>.pdf`
Accesibles desde HA en `/local/cfe_recibos/` si mapeas el share.

### Múltiples cuentas
```json
{
  "cuentas": [
    { "nombre": "Casa",   "rpu": "123456789012", "password": "pass1" },
    { "nombre": "Taller", "rpu": "987654321098", "password": "pass2" }
  ]
}
```
Cada cuenta genera su propio dispositivo MQTT con sensores independientes.

## Instalación

1. Copiar carpeta `addon-cfe` a `/addons/` en tu HA
2. Supervisor → Add-on Store → (esquina superior derecha) → Check for updates
3. Aparece como addon local → Instalar
4. Configurar credenciales en la pestaña Configuración
5. Iniciar
