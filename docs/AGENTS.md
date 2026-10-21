# AGENTS.md — Biosphere Worlds (Issac Edition)

Mod de worldgen para Minecraft 1.21.1, NeoForge, Java 21. Fork de NeoBiosphere
(GPL-3.0). mod_id: biosphereworlds. Paquete: mx.issacinzunza.biosphereworlds.
Genera el Overworld como biosferas de vidrio flotantes rodeadas de vacío.

## Reglas
- No hagas commit ni push. No cambies mod_version. No toques biospheres.json
  salvo que la tarea lo pida expresamente.
- No leas build/, .gradle/ ni .idea/ (salvo la caché de fuentes de Minecraft
  cuando la tarea lo pida). Ediciones puntuales, sin reescribir archivos enteros.
- No modifiques ni borres nada fuera de la carpeta del proyecto.
- No inventes nombres de clases, métodos ni APIs de Minecraft/NeoForge. Si no
  estás seguro, dilo. Cita archivo, clase y línea; para código de Minecraft,
  cita la fuente de la caché de Gradle o di que no la tienes.
- Prioriza la solución MÁS SIMPLE que funcione. No añadas clases u opciones
  nuevas salvo que sean imprescindibles; si el alcance crece, avísame antes.
- Dos fases. FASE 1: solo lectura (diseño o diagnóstico, riesgos y pruebas
  que solo se pueden hacer en el juego) y ESPERA MI OK. FASE 2: implementa.
- Respuestas breves.

## Comandos (PowerShell)
- Compilar y probar: .\gradlew build
- Cliente de desarrollo: .\gradlew runClient --no-configuration-cache
- No uses gradlew clean salvo que te lo pida (rompe runClient en el IDE).

## Cuando añades una opción de configuración
SphereConfig, claves de idioma en en_us, es_es y es_mx, tablas de README.md y
docs/es/ARQUITECTURA.md. Valida min <= max donde aplique.

## Lecciones del proyecto
- Toda función del mod solo actúa en mundos con el preajuste Biospheres.
  Comprueba esa condición ANTES de cualquier cálculo o caché. Un mundo vanilla
  debe quedar idéntico.
- Con una opción apagada, el resultado debe ser un no-op EXACTO, probado bit a
  bit contra una copia literal de la lógica anterior.
- JUnit no puede arrancar NeoForge: extrae la lógica a clases puras y pruébala.
  El cableado con el motor se verifica a mano en el juego.
- Un DensityFunction envolvente debe recorrer a su hijo en mapAll.
- Heightmap: todo bloque que escriba un carver dentro de esferas o satélites
  debe ser ignorado por MixinHeightmap (afecta a calles de aldea y vegetación).
- La geometría vive en SphereLayout. sphereAtCell(int,int) recibe índices de
  celda; sphereContaining(double,double) recibe coordenadas de bloque. No
  dupliques geometría ni uses sobrecargas int/double con significados distintos.
- Generación multihilo (C2ME): nada de estado mutable compartido; los
  catálogos se publican como instantáneas inmutables.
- Los hashes de colocación son separados de los existentes. No toques el hash
  del radio ni el caso borde de Math.abs(Integer.MIN_VALUE).

## Arquitectura (resumen)
- SphereLayout: celda, hash, centro, radio, centro vertical propio (centerY),
  satélites por celda (SatellitePlacement, SatelliteLayers, MineralCatalog).
- SphereCarver y SphereBridgeCarver escriben cascarón, puentes y satélites.
- BiosphereBiomeSource: wrapper que devuelve the_void fuera de las esferas.
- MultipleSpheresDistanceFunction y SphereEdgeOceanFunction (terreno y océano).
- Mixins: heightmap, aquifer, estructuras, biome source, applyCarvers.
- SatelliteMineralCatalog: instantánea volátil reconstruida en TagsUpdatedEvent.
- Opciones: bedrock_mode, close_open_top, edge_ocean_*, satellites_*.

## Mensajes de commit
Si existe .github/instructions/commit-message.instructions.md, sigue sus reglas
cuando te pida redactar un commit.