# Avisos de aurora en Montréal

Piloto personal en Python para dos teléfonos Android. El calendario cubre del **9 de noviembre al 27 de diciembre de 2026**, inclusive, en hora de Montréal. La configuración inicial evalúa Anse-à-l’Orme y Cap-Saint-Jacques. Los avisos están en español.

## Pruebas locales

Desde esta carpeta, con Python 3.11 o posterior, ejecuta estos comandos. El proyecto usa la biblioteca estándar.

```powershell
python -m unittest discover -s tests -v
python -m aurora --demo
python -m aurora
```

`--demo` muestra los cuatro tipos de aviso con datos ficticios, sin red. El último comando lee los datos públicos durante el periodo del piloto. Ambos modos muestran resultados sin publicar ni modificar el historial.

## Activación por los dos destinatarios

1. **GitHub.** Crea un repositorio dedicado y sube esta carpeta, incluida `.github/workflows/aurora.yml`, a la rama predeterminada. Habilita GitHub Actions y comprueba que el `GITHUB_TOKEN` del flujo pueda hacer `push` a esa rama. Si una regla de protección lo bloquea, usa un repositorio dedicado cuya política permita escribir el historial. En un repositorio privado, verifica los minutos disponibles y bloquea el gasto excedente antes de activarlo. [Cuotas por plan](https://docs.github.com/en/billing/reference/product-usage-included) · [Límites de gasto](https://docs.github.com/en/billing/how-tos/set-up-budgets)
2. **ntfy.** Cada persona que dé su consentimiento instala ntfy en Android, habilita las notificaciones y se suscribe al mismo tema en el servidor `https://ntfy.sh`. Una sola persona genera el nombre con el comando de abajo y lo comparte en privado con la otra. En GitHub, abre **Settings → Secrets and variables → Actions → Secrets** y crea el secreto `NTFY_TOPIC` con ese nombre. El servicio permite suscribirse sin cuenta. Los temas gratuitos son públicos para quien conozca su nombre y los mensajes se almacenan temporalmente para facilitar la recepción tras una desconexión. El aviso contiene solo datos públicos, incluida la ubicación del parque. [ntfy para Android](https://docs.ntfy.sh/subscribe/phone/) · [Privacidad](https://docs.ntfy.sh/privacy/) · [Temas públicos y límites](https://docs.ntfy.sh/publish/#public-topics)
3. **Prueba y activa.** En **Actions → Aurora Montréal → Run workflow**, ejecuta `dry-run` en la rama predeterminada. Después elige `test-push` y confirma que apareció una notificación en **cada** teléfono, idealmente con la pantalla bloqueada. Cuando las dos pruebas funcionen, crea la variable de repositorio `AURORA_ENABLED` con valor `true` en la pestaña **Variables** de la misma configuración. Para pausar, cámbiala a `false`.

```powershell
python -c "import secrets; print('aurora-' + secrets.token_hex(24))"
```

La programación consulta a las `:13` de cada hora y también a las `:43` entre las 16:00 y las 20:59. GitHub puede demorar u omitir ejecuciones. Con un máximo de 29 ejecuciones diarias y dos minutos por ejecución, se programan hasta 1.276 minutos en noviembre y 1.566 en diciembre, más las pruebas manuales. Son cifras de este piloto y la cuota privada se comparte con el resto de la cuenta. En un repositorio público, los ejecutores estándar hospedados por GitHub son gratuitos. Open-Meteo ofrece el acceso sin clave para uso no comercial y el flujo pide como máximo 58 pronósticos diarios. [Programación en GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) · [Facturación de Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions) · [Condiciones de Open-Meteo](https://open-meteo.com/en/pricing)

## Cómo se decide un aviso

| Aviso | Condición inicial |
| --- | --- |
| Preliminar | Kp previsto de al menos 6 en una franja de tarde o noche, con 48–72 h de antelación cuando NOAA publique datos para esa ventana. |
| Preparación | Revisión alrededor de 24 h, entre más de 12 y hasta 30 h, con comparación de ambos sectores. |
| Evaluación final | Entre 6 y 12 h. Puede llegar más tarde si el pronóstico aparece o cambia con menos antelación. |
| Urgente | Kp estimado de al menos 7 durante cinco minutos, con datos recientes y al menos 25 minutos de ventana meteorológica dentro de la próxima hora. Es una señal para revisar el óvalo si ya están cerca. |

La NOAA publica Kp planetario en bloques de tres horas y estimaciones de un minuto. El Kp sirve como filtro de actividad. Cada ventana usa horas locales, margen para la oscuridad y un filtro meteorológico. Para una ventana programada se necesitan dos horas consecutivas con un máximo de 30% de nubosidad total y 20% de nubes bajas, al menos 10 km de visibilidad, precipitación nula, temperatura de al menos −15 °C, ráfagas de hasta 40 km/h y código meteorológico de cielo despejado a cubierto. Son umbrales operativos conservadores y el mensaje muestra la nubosidad pronosticada, sin calcular una probabilidad de ver auroras. El óvalo NOAA es una comprobación manual para ventanas inminentes. [Pronóstico NOAA](https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json) · [Estimación NOAA](https://services.swpc.noaa.gov/json/planetary_k_index_1m.json) · [Óvalo NOAA](https://www.swpc.noaa.gov/products/aurora-30-minute-forecast) · [Datos meteorológicos de Open-Meteo, evaluados con filtros propios](https://open-meteo.com/en/docs)

Ambos sectores tienen horario publicado de 07:00 a 22:00. El piloto reserva 30 minutos para salir y solo presenta ventanas completas dentro de ese margen. La playa de Cap-Saint-Jacques queda excluida por el cierre de temporada. El STM publica la línea 68 y las paradas de referencia. Para considerar una salida, comprueben el mismo día el trayecto desde su punto de partida, la vuelta completa y las incidencias, los avisos del parque y un camino peatonal habilitado de hasta una hora desde la parada. Eviten arcenes, hielo y senderos aislados. El estado más favorable es **CONDICIONAL** porque faltan el itinerario y el acceso verificados para esa noche. **NO-GO** descarta la ventana evaluada. La tarifa de referencia es 14 CAD ida y vuelta para dos adultos con dos boletos de dos viajes, si todos los tramos son en zona A. [Anse-à-l’Orme](https://montreal.ca/en/places/grand-parc-de-louest-anse-lorme) · [Cap-Saint-Jacques](https://montreal.ca/en/places/grand-parc-de-louest-cap-saint-jacques) · [Cierre de la playa](https://montreal.ca/lieux/plages-du-cap-saint-jacques) · [Línea 68](https://www.stm.info/horaires-et-trajets/bus/68/ouest) · [Planificador STM](https://www.stm.info/en/schedules-and-routes/plan-a-route) · [Tarifa STM](https://www.stm.info/en/fares-pricing/2-trip)

## Historial y operación

- El flujo conserva `history/events.json` en la rama predeterminada. Cada noche local tiene una entrada por etapa, con actualizaciones limitadas cuando mejora o empeora la evaluación final. La hora de fin de cada aviso delimita su vigencia.
- El flujo guarda una reserva en Git antes de publicar y anota la confirmación después. Un registro `accepted` significa que ntfy aceptó el mensaje. Los registros `pending` o `unconfirmed` requieren revisar la ejecución y ambos teléfonos. El flujo omite reintentos automáticos para esos registros porque el mensaje podría haber llegado. Si compruebas que falló y la ventana sigue vigente, puedes quitar solo esa etapa del historial para permitir una nueva evaluación.
- Ante un fallo de datos, revisa el resultado de la ejecución en **Actions**. Si faltan datos meteorológicos para decidir, el programa señala la incertidumbre. El piloto empieza y termina con fechas locales en horario estándar. Antes de extenderlo fuera de este periodo, actualiza fechas, cron y manejo del cambio de hora.
- Los lugares están definidos en `aurora/sites.py` y la entrega se concentra en `publish` en `aurora/__main__.py`. Para incorporar destinos regionales, verifica primero acceso, zona horaria y últimas conexiones de ida y vuelta. Si más adelante se añade correo, registra su entrega por separado para poder comprobar cada canal.
