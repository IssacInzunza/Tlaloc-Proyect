# Notificaciones de lluvia

Tláloc utiliza Web Push y un service worker para recibir avisos después de cerrar
la pestaña. El servidor local de Tláloc y la computadora deben seguir encendidos;
el navegador y el sistema operativo deben permitir recibir push en segundo plano.
Cerrar por completo el navegador, suspender el equipo, bloquear notificaciones o
perder conexión puede impedir o retrasar la entrega. La aceptación del mensaje
por el proveedor push no demuestra que el sistema haya mostrado el aviso.

La activación requiere pulsar el botón de notificaciones y aceptar el permiso del
navegador. El usuario puede enviar una prueba identificada como tal y desactivar
su suscripción. No se activa mediante una petición de permiso al cargar la página.
La ubicación guardada para navegación permanece en LocalStorage; activar avisos
añade una copia de la ubicación vigilada en este mismo equipo para que el servidor
pueda comprobar lluvia mientras la página está cerrada.

## Datos y privacidad

Las claves VAPID, suscripciones y vigilancia se guardan en
`.cache/notifications/` (o en `TLALOC_CACHE/notifications/`), ignorado por Git.
El archivo de vigilancia contiene coordenadas y claves: no debe compartirse.
Se escribe de forma atómica; en sistemas POSIX se crea con permiso `0600`, y
en Windows se aplican los permisos de la carpeta local del usuario.
La clave pública VAPID se entrega al navegador; la privada nunca se expone por API.
Un identificador aleatorio de 32 bytes permite consultar, cambiar y eliminar la
vigilancia y se conserva en el navegador. No se imprime en logs.

Los mensajes están cifrados mediante Web Push y pasan por el servicio push del
navegador (Google, Mozilla, Microsoft o Apple). El proveedor recibe el destino y
metadatos de entrega; el contenido no incluye dirección ni coordenadas vigiladas.
El texto solo identifica una estimación de radar o una previsión experimental.
No se utiliza una cuenta ni un servicio de pago.

## Reglas científicas y frecuencia

El trabajador consulta cada 120 segundos, sin usar replay ni reflectividad
compuesta para inferir lluvia. Requiere observación de los últimos diez minutos,
objetivo válido, al menos 60 % de área válida y calidad de radar buena. Datos
faltantes, futuros, obsoletos o de calidad insuficiente no generan aviso.
La lluvia actual usa exclusivamente `target_rate`, estimación real del producto de
precipitación, comparada con el umbral del usuario. Se avisa una vez al comenzar
el episodio y se rearma solo cuando una observación válida vuelve a estar seca.
Ausencia de datos nunca equivale a seco.

Las llegadas preventivas/inminentes requieren confianza media/alta, intervalo
finito, ordenado y dentro del horizonte de 60 minutos, y timestamp igual al análisis.
Se respetan los niveles seleccionados para pronósticos; un eco informativo no
genera un aviso de lluvia. El comienzo observado es independiente de los niveles
de pronóstico. Se conserva deduplicación por observación/celda/nivel y un intervalo
mínimo de 30 minutos por nivel para evitar repetición tras reasignar identificadores
de seguimiento. Una escalada preventiva a inminente puede generar un aviso nuevo.
Cambiar ubicación o umbral reinicia la deduplicación de esa vigilancia.

El TTL de entrega es 120 segundos para evitar mostrar alertas antiguas mucho
después de que el equipo recupere conexión. Estas reglas no son probabilidades
calibradas ni sustituyen avisos meteorológicos oficiales.

## API e integración

`NotificationService(cache: Path, analyze_callback)` ofrece `.router`, `.start()`
y `.stop()`. El callback síncrono recibe `Location` y devuelve `coverage`,
`predictions`, `observation_time` ISO con zona y `target_rate` nullable.
El ciclo de vida de FastAPI arranca y detiene el trabajador. Hay como máximo ocho
suscripciones, persistidas entre reinicios, y un solo hilo de comprobación.

- `GET /api/notifications/config`: clave pública y disponibilidad.
- `POST /api/notifications/subscribe`: suscripción Push API, ubicación, idioma y
  niveles; devuelve identificador secreto y estado.
- `POST /api/notifications/{id}/update`: ubicación viva, idioma y niveles.
- `GET /api/notifications/{id}/status`: enabled, last_checked, last_sent, last_error.
- `DELETE /api/notifications/{id}`: borra la vigilancia local.
- `POST /api/notifications/{id}/test`: prueba explícita; máximo una cada 30 segundos.

Las mutaciones exigen Origin idéntico al backend de loopback. El cliente utiliza
el mismo origen (también mediante el proxy de desarrollo). Solo se admiten
endpoints HTTPS443 de proveedores push conocidos, claves ECDH válidas y auth de
16 bytes. La entrega rechaza redirecciones y tiene timeout de 15 segundos.
Los errores exponen códigos estables y nunca detalles del endpoint o claves.
404/410 del proveedor desactivan la suscripción; 429 y otros fallos aplican
reintentos con espera creciente y acotada. La prueba aceptada confirma transporte,
no visualización por el sistema operativo.

La implementación sigue la API oficial de
[pywebpush](https://github.com/web-push-libs/pywebpush) con `aes128gcm`, VAPID,
timeout, sesión sin redirecciones y TTL breve. Requiere `pywebpush` y `cryptography`.

## Verificación

`backend/tests/test_notifications.py` utiliza únicamente transporte falso y
análisis sintéticos: nunca envía notificaciones reales. Verifica contrato API,
persistencia, inicio de lluvia, deduplicación, timestamps, calidad, intervalos,
endpoints, origen, expiración de suscripción y backoff. La prueba de navegador con
pestaña cerrada debe distinguir ejecución del service worker, aceptación push y
presentación efectiva en el escritorio; esta última depende del navegador y SO.
