# Tláloc Project

[English](../README.md) · Versión 1.0.0 · MIT

Tláloc Project es una aplicación meteorológica experimental de código abierto que utiliza radares NOAA para detectar precipitaciones, analizar su desplazamiento y estimar su posible llegada a una ubicación específica.

Se ejecuta en tu computadora. Puedes elegir un punto, vigilar un círculo geográfico de 50 km, modificarlo entre 10 y 100 km y consultar observaciones reales MRMS. Las estimaciones se basan en ecos observados y su movimiento; no predicen tormentas que todavía no existen ni sustituyen avisos oficiales.

## Funciones

- Mapa interactivo, búsqueda de calles y lugares con sugerencias, coordenadas, marcador arrastrable, selección por clic y GPS opcional.
- Interfaz en español e inglés con idioma, ubicación y configuración guardados.
- Precipitación NOAA auténtica, animación, hora de observación, cobertura y calidad RQI cuando está disponible.
- Segmentación, seguimiento, vectores y estimaciones mediante la extensión espacial de cada región.
- Avisos informativos, preventivos e inminentes cuando hay evidencia suficiente, historial SQLite local y sonido opcional.
- Replay de períodos históricos de 2–60 minutos, ejemplo real incluido, métricas experimentales, comparación de ejecuciones y exportación JSON.

## Ejecución en Windows 11

Requiere Python 3.12 o posterior, Node.js 20.19 o posterior y npm. En PowerShell, desde la raíz:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
```

Abre [Tláloc local](http://127.0.0.1:8000). Detén el servidor con Ctrl+C. En este espacio de trabajo Codex, el entorno y la compilación ya están instalados: basta ejecutar el último comando. El Python empaquetado aquí no incluye pip; para actualizar sus dependencias usa `python -m pip --python .venv/Scripts/python.exe install -r backend/requirements.txt` con el Python del sistema.

## Ejecución en Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
bash scripts/run.sh
```

Estas instrucciones se incluyen para Linux; esta sesión verificó Windows. Algunas distribuciones necesitan instalar el paquete de soporte venv. No se requiere cuenta, clave API, GPU ni servicio de pago.

## Uso

Elige una ciudad o coordenadas, o mueve el marcador. El círculo indica dónde se buscan ecos; no representa una zona pronosticada de lluvia. Revisa cobertura, antigüedad y calidad antes de interpretar los avisos. El gris significa ausencia de datos; no significa tiempo seco.

En Replay histórico, pulsa Cargar ejemplo real para reproducir once observaciones NOAA del 17 de octubre de 2026, 08:00–08:20 UTC, alrededor de 27°N, 82.5°O. El archivo recortado funciona sin descargar radar adicional; el mapa base sigue necesitando red. Ese episodio no contiene una llegada verificable al objetivo, por lo que sus errores de llegada quedan desconocidos. Puedes seleccionar otro período UTC disponible y ejecutar el análisis. Las predicciones de cada instante utilizan exclusivamente datos anteriores; las observaciones futuras sirven para validarlas.

El selector permite ver **reflectividad compuesta en dBZ** o **lluvia estimada en mm/h**. La reflectividad muestra ecos, incluso en altura; no confirma lluvia en superficie. Cada capa conserva su hora, fuente y leyenda. El recorte cubre el círculo más un margen de 20 km, no todo el mapa visible. Las alertas de llegada siguen basándose en lluvia estimada y movimiento fiable. La confianza y los intervalos son heurísticos, no probabilidades calibradas; los intervalos numéricos se limitan a llegadas de hasta 30 minutos.

NOAA no ofrece cobertura radar mundial. MRMS tiene productos para varios dominios; solo la ingestión real CONUS se verificó en esta sesión. Las fronteras no se usan para bloquear ubicaciones, pero los píxeles y la calidad determinan si pueden analizarse. El relieve, la altura del haz, la evolución de tormentas y la latencia limitan las estimaciones. Sigue las alertas oficiales.

## Pruebas

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.cache/pytest-local
.venv/Scripts/python.exe -m ruff check backend scripts
cd frontend
npm test
npm run build
```

La integración NOAA requiere habilitar `TLALOC_NETWORK_TESTS=1`. El sandbox de Windows puede bloquear el socket interno de asyncio y requerir ejecución de pruebas fuera del sandbox. Consulta [pruebas y métricas](testing.md), [limitaciones](limitations.md) y [estado real del proyecto](../PROGRESS.md).

## Privacidad, fuentes y documentación

No hay telemetría ni cuentas. La última ubicación **en vivo** se guarda únicamente en LocalStorage del navegador; el replay es temporal y no la reemplaza. Al volver al modo en vivo o recargar se restaura. Usa siempre el mismo navegador y dirección, porque `localhost` y `127.0.0.1` tienen almacenamiento separado; una ventana privada puede borrar los datos al cerrar.

El backend de esta computadora recibe el punto para recortar datos localmente; observaciones, historial SQLite y métricas quedan en `.cache/`. Ese historial local contiene coordenadas. El GPS se solicita solo al pulsar su botón. Photon está activado para buscar y autocompletar calles: recibe el texto y el centro aproximado del mapa, conforme a tu autorización. Las consultas solo se guardan brevemente en RAM, no en archivos. La cobertura depende de las direcciones presentes en OpenStreetMap; no se inventan domicilios ausentes.

Datos: NOAA MRMS, procesados por Tláloc sin implicar respaldo de NOAA. Mapas y direcciones: OpenStreetMap; sugerencias mediante Photon con límites de uso razonable. Cada servicio conserva sus términos. Código bajo licencia [MIT](../LICENSE).

Documentación técnica en inglés: [fuentes verificadas](data-sources.md), [arquitectura](architecture.md), [procesamiento](radar-processing.md), [seguimiento](tracking-algorithm.md), [nowcasting](nowcasting.md). API local: [OpenAPI](http://127.0.0.1:8000/docs).

### Notificaciones fuera de la página

En Edge o Chrome completo, abre Ajustes, pulsa Activar notificaciones de lluvia y acepta el permiso. Mantén encendidos el equipo y el servidor de Tláloc. El navegador integrado WebView2 no admite push. Usa Enviar notificación de prueba para comprobar la entrega en tu sistema. La vigilancia y suscripción se guardan en este equipo; los mensajes cifrados pasan por el servicio push sin coordenadas. [Funcionamiento y límites](notifications.md).
