## Configuración

| Campo | Descripción | Default |
|-------|-------------|---------|
| `usuario` | Correo o usuario del portal CFE | — |
| `password` | Contraseña del portal CFE | — |
| `num_servicio` | Número de servicio (opcional, si tienes varias cuentas en el mismo usuario) | — |
| `captcha_api_key` | API key de [2captcha.com](https://2captcha.com) | — |
| `intervalo_horas` | Frecuencia de revisión cuando el recibo está pendiente | `24` |
| `dias_anticipo` | Días antes del próximo periodo para empezar a buscar el nuevo recibo | `5` |
| `pdf_dir` | Ruta donde se guardan los recibos PDF | `/config/www/cfe` |
| `mqtt_host` | Host del broker MQTT | `core-mosquitto` |
| `mqtt_port` | Puerto del broker MQTT | `1883` |
| `debug_screenshots` | Guarda capturas de pantalla en `<pdf_dir>/debug/` para diagnóstico | `false` |

## Comportamiento de revisión

El addon ajusta automáticamente cada cuándo revisa el portal:

- **Recibo PAGADO + PDF descargado** → duerme hasta `dias_anticipo` días antes del próximo periodo bimestral.
- **Recibo PENDIENTE** → revisa cada `intervalo_horas` hasta detectar el pago.
- **Nuevo periodo detectado** → descarga el PDF inmediatamente.

## PDF

Los recibos se nombran con el periodo: `casa_20MAR26_19MAY26.pdf`. Si el archivo ya existe, no vuelve a descargarlo.

Con `pdf_dir: /config/www/cfe` el recibo es accesible en:
```
http://<IP-HA>:8123/local/cfe/casa_20MAR26_19MAY26.pdf
```

## Captcha

El portal CFE usa captcha de imagen. Se resuelve automáticamente via [2captcha.com](https://2captcha.com). Si falla (raro), el addon reintenta hasta 3 veces antes de esperar al siguiente ciclo.

Costo aproximado: **< $0.10 USD/mes** con uso normal.
