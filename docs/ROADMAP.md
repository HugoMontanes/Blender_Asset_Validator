# Roadmap: de Asset Validator a suite para artistas de videojuegos

Documento para retomar el trabajo desde cualquier chat o dispositivo. Al empezar una sesión nueva, pide que se lea este fichero entero y el `README.md`. Al cerrar una tarea, actualiza la tabla **Estado** y marca sus casillas.

## Cómo retomar

1. Mira en **Estado** la fase en curso y su rama: `git switch <rama>`. Nada está fusionado en `main` (que no tiene ni la fase 0): cada rama sale de la anterior, `feature/phase-0-foundations` → `bugfix/hard-surface-normals-and-lods` → `feature/phase-1-uvs` → `feature/phase-2-hard-surface`. La siguiente fase sale de la última.
2. Tests: `.\tests\run.ps1` (PowerShell; encuentra Blender en PATH, en la Store o en `Program Files\Blender Foundation`). Ejecuta cada `tests/check_*.py` dentro de Blender, sin interfaz, y deja la salida en `tests/_out/`. `.\tests\run.ps1 check_lods` ejecuta solo uno. Todos tienen que pasar antes de un commit.
3. Velocidad: `tests/bench.py` mide cada check con mallas de 16k, 260k y 1M de triángulos. `run.ps1` no lo ejecuta; el comando está en su cabecera. Se compara con la **Línea base**.
4. Lee **Convenciones** antes de tocar código.

## Decisiones tomadas (2026-10-27)

- **Motor de destino**: se elige en el addon (Unreal, Unity, Godot o Custom). Si algo no da para los tres, la prioridad es Unity y Unreal.
- **Tipos de asset**: la meta es cubrirlos todos. Van primero hard surface/props y entornos/modulares; personajes/skinned y orgánico/foliage después.
- **Distribución**: de momento es un addon interno; más adelante, comercial (Superhive). Por eso, las dependencias tienen que ser MIT o BSD, y los binarios externos (V-HACD, QuadWild…) siempre opcionales.
- **Blender mínimo**: 4.2 LTS, con el formato de extensión (`blender_manifest.toml`). Lo que solo existe desde 4.3 (unwrap Minimum Stretch) se comprueba antes de usarlo y tiene alternativa (CONFORMAL).
- Desarrollo y tests en Blender 5.2.3 (Microsoft Store). Unreal y Unity no están instalados, así que lo que dependa de ellos va a **Pendiente de verificar en motor**.

## Convenciones

- Una rama por tarea (`feature/…`, `bugfix/…`). Al empezar, preguntar si hay ticket `GEN-`; la fase 0 no lo tiene.
- Commit y push solo cuando lo pida el usuario. Antes del commit: `/ponytail-review` y `/code-review`.
- Los mensajes de commit terminan con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Nunca se commitean `.vscode/settings.json`, el cambio local de `.gitignore` ni `blender_asset_validator.zip`.
- Estilo ponytail: el mínimo código que funciona, sin abstracciones especulativas, y una prueba ejecutable por cada lógica no trivial. Los atajos con un límite conocido llevan un comentario `# ponytail: <límite>, <cómo ampliarlo>`.
- Comentarios: una línea, salvo los que explican un porqué que no es obvio (2–3 líneas). Sin cabeceras decorativas ni código comentado.
- Reglas aprendidas, no romperlas:
  - **Un fix vuelve a buscar lo que corrige en el momento de aplicarse.** Fix All aplica todos los fixes y solo revalida al final, así que los índices guardados al validar ya no sirven después de un fix anterior. Ver `triangulate_warped`.
  - Un check es una función `@register_check` dentro de `checks/`. Devuelve `CheckResult`, con `fix` (aplica la corrección) y `select` (abre Edit Mode con lo problemático seleccionado) opcionales. Los pasos del modo guiado agrupan checks por nombre de función (`core/steps.py`).
  - En Edit Mode `mesh.polygons` está desactualizado y `bmesh.to_mesh` falla, por eso los operadores que modifican mallas heredan `ObjectModeOnly`.
  - Con el Blender de la Microsoft Store hay que lanzar con `Start-Process -Wait`, porque el launcher devuelve el control antes de que Blender termine.
  - **Después de `mode_set` hay que volver a pedir `mesh.uv_layers[i]`** (y cualquier dato de la malla): la referencia de antes apunta a datos viejos, sin dar error. Ver `set_texel_density`.
  - Nada que reempaquete o desenvuelva UVs va en un **Fix**: Fix All lo aplicaría a assets ya texturizados y rompería sus texturas. Esas operaciones son herramientas aparte.
  - QuadriFlow falla con geometría non-manifold y borra las piezas finas. `operations/topology.py` lo resuelve remallando pieza a pieza y reparando antes (`_repair_for_quadriflow`, `_patch_lost_surface`).

## Dónde está cada cosa

| Ruta | Qué hay |
|---|---|
| `blender_asset_validator/checks/` | Un fichero por área (geometry, integrity, topology, shading, uvs, materials, naming, transforms) |
| `blender_asset_validator/operations/` | Lógica que modifica mallas: cleanup, topology (Clean/Retopo), lod, decimate, heatmap, uvs (islas, métricas y herramientas UV) |
| `blender_asset_validator/operators/` | Botones (`bpy.types.Operator`) que llaman a operations y engine |
| `blender_asset_validator/core/` | `engine` (carga de config y validación), `roles`, `registry`, `result`, `state`, `steps`, `mesh_utils` |
| `blender_asset_validator/config/` | `default.json` ← `engines/<motor>.json` ← `presets/<preset>.json` ← `asset_validator.json` junto al .blend |
| `blender_asset_validator/report/` | Informe de consola, JSON y HTML |
| `blender_asset_validator/cli.py` | Validación por lotes sin interfaz (CI) |
| `tests/` | `check_*.py` (tests), `run.ps1` (runner), `bench.py` (velocidad) |

## Estado

| Fase | Rama | Estado |
|---|---|---|
| 0 Cimientos | `feature/phase-0-foundations` | hecha, revisada, testeada (234 tests) y commiteada. Falta: que el usuario pruebe el último zip en su escena y verificar en motor. Arreglos de las pruebas con el Makarov en `bugfix/hard-surface-normals-and-lods` (252 tests) |
| 1 UVs y texel density | `feature/phase-1-uvs` (desde `bugfix/hard-surface-normals-and-lods`, sin ticket) | hecha, revisada (`/ponytail-review`, `/code-review`), testeada (319 tests) y commiteada. Falta: probarla con interfaz en tu escena y revisar el panel (ver "Siguiente paso" en la fase 1) |
| 2 Hard surface | `feature/phase-2-hard-surface` (desde `feature/phase-1-uvs`, sin ticket) | primera parte hecha (Hard Surface Prep, Bevel, check de mid-poly), revisada (`/ponytail-review`, `/code-review`), testeada (334 tests) y probada con interfaz y con escenas reales. Sin commitear. Falta: que el usuario la pruebe y decida qué hacer con Auto Unwrap/Prep en escaneos grandes. Quedan el bake helper, el crease para SubD y las trim sheets |
| 3 Entornos, colisiones, texturas | — | pendiente |
| 4 Topología y LOD avanzados | — | pendiente |
| 5 Personajes y orgánico | — | pendiente |
| 6 Comercial | — | pendiente |

## Fase 0: cimientos

Todo lo demás depende de esto: el motor fija las reglas y los roles dicen qué es cada objeto.

- [x] **B1 Selector de motor y config por proyecto.** Desplegable *Engine* (Custom, Unreal, Unity, Godot) junto a *Preset*. La config se combina en este orden: `default` ← `engines/<motor>.json` ← `presets/<preset>.json` ← `asset_validator.json` junto al .blend. El motor fija el formato de export, cómo se exportan los LODs y qué nombres se reconocen como colisión o socket. Código: `core/engine.py` (`ENGINE_ITEMS`, `load_config`) y `config/engines/`.
- [x] **B2 Roles de objeto**: asset, LOD, colisión y socket (`core/roles.py`).
  - Se deducen del nombre con las expresiones regulares del motor (`roles.collision`, con el grupo `(?P<owner>…)`, y `roles.socket`) y de la marca que llevan los LODs generados.
  - Cada check declara a qué roles se aplica con `@register_check(roles=…)`; por defecto, asset y LOD. Las colisiones solo pasan `check_transforms` y `check_collisions` (colisión que apunta a un mesh que no existe).
  - Un `UCX_` sin material ya no bloquea el export.
- [x] **Export por motor** (`operators/export.py`, `_engine_layout`):
  - **Unity**: un FBX por asset con `Name_LOD0…n` (el base se renombra a `_LOD0` durante el export).
  - **Unreal**: un Empty `LodGroup` (`fbx_type`) sobre `Name_LOD0…n`, `UCX_Name_LOD0_NN` (renombrado durante el export) y `SOCKET_`. La estructura del FBX está comprobada con `parse_fbx` en `tests/check_engines.py`.
  - **Godot**: un .glb con `-colonly`, sin LODs.
  - Nombres, padres y transforms se restauran después del export. El operador se llama ahora `asset_validator.export` (antes `export_fbx`).
- [x] **B3 Velocidad**: numpy en `shading_stats`, en el solape de UVs (rejilla con cada par probado una sola vez, en la celda donde empiezan a solaparse sus cajas, y SAT vectorizado) y en `quad_warps`. Da los mismos resultados que la versión anterior en 16 mallas y 300 sopas de triángulos aleatorias. Números en **Línea base**.
- [x] **B4 Informe JSON/HTML y CLI** (`cli.py`, `report/generator.py`): `blender -b --factory-startup --python blender_asset_validator/cli.py -- [--engine unreal] [--preset mobile] [--report out.json|out.html] a.blend b.blend …`.
  - Sin `--engine`, usa el motor guardado en cada .blend.
  - Código de salida 1 si hay errores, comprobado con el Blender de la Store.
- [x] **B5 Excepciones y aprobaciones por objeto** (`core/waivers.py`, `core/steps.py`).
  - La casilla junto a un aviso pide un motivo y lo guarda en el objeto, en `asset_validator_waivers`. La clave es un hash del mensaje con los números y el nombre del objeto en blanco, así que la aceptación sobrevive a que cambie el recuento.
  - Los errores no se pueden aceptar.
  - Las aprobaciones se guardan en `obj["asset_validator_approved"]`. No se invalidan si se edita la malla a mano después de aprobar (el export revalida igualmente).
- [x] **B6 Heatmaps** (`operations/heatmap.py`, `operators/heatmap.py`):
  - Un atributo de color temporal `AV_heat` que se ve en Solid > Attribute. El export lo borra.
  - Métricas: Quad Warp y Triangle Quality. Se añaden en `METRICS` como una función que devuelve un valor 0..1 por cara (NaN = no aplica).
- [x] **B7 Extensión 4.2**: `blender_manifest.toml` (id `blender_asset_validator`), validado e instalado con `extensions.package_install_files` en un perfil de usuario aislado (`BLENDER_USER_RESOURCES`). Se quitaron `bl_info` y las ramas para Blender anterior a 4.1.

### Notas de la fase 0, útiles para retomar

- **Los exportadores ignoran los objetos ocultos de la selección**: el FBX usa `context.selected_objects` y el glTF `select_get()`. Las colisiones y la colección `LODs` suelen estar ocultas y se perdían. Ahora se exporta desde una colección temporal con el parámetro `collection=` de los exportadores (existe desde 4.2), sin tocar la selección.
- `Region.active_panel_category` es de solo lectura. Para capturar el panel en una prueba con interfaz, se registra el panel con `bl_category = "Item"` y `preferences.view.show_splash = False`.
- `tests/run.ps1 check_x` no funcionaba: el primer argumento posicional iba a parar a `-Blender`. Se arregló con `[CmdletBinding(PositionalBinding = $false)]`.
- **Probar siempre con la escena real del usuario**, no solo con mallas sintéticas: `C:\Users\hugom\Documents\Assets\BlenderSuitTest_01.blend`, en este equipo. Ábrela en segundo plano y nunca la guardes. Es un coche de unos 190k triángulos por malla, con **11.579 piezas sueltas**.
  - Desde la fase 1 (2026-10-28, en otro equipo): `Addon_Test.blend` en la raíz del repo (sin commitear; preset Cinematic guardado; el usuario la va cambiando: el 2026-10-29 tenía 5 mallas del Audi R8, 410k caras, con LODs del capó). Lo usa `tests/check_scene.py`, que la abre sin guardarla y sale con SKIP si no está. Suele estar abierta en el Blender del usuario: nunca se guarda. En `test_assets/` hay más: Audi R8 (FBX), una roca escaneada (FBX) y un T-Rex (OBJ).
- **Retopologize "colgado" en el coche** (2026-10-27): no era un bucle, eran 145 ejecuciones de QuadriFlow seguidas, más una copia del bmesh entero por cada pieza, sin ninguna señal. Más de un minuto con Blender congelado, multiplicado por cada coche seleccionado. Arreglo:
  - `retopologize_steps` es un generador.
  - El operador es modal: avanza una pieza por tick, muestra el progreso en la barra de estado y se cancela con Esc.
  - Resultado con la interfaz: 57 s y como mucho 7,7 s congelado (antes, todo el tiempo). Sin interfaz: de 62 s a 39 s.
- **Retopologize colgado de nuevo** (2026-10-27, después del commit `1631bee`). El usuario hizo Merge by Distance a 0,0001 en el coche, lo que fusiona capas del cristal, y Blender se quedó sin responder. Con `py-spy dump --pid` se vio que estaba en una sola llamada a QuadriFlow, la pieza 3 de 119, desde hacía más de 10 minutos.
  - Causa: `_shape_mesh`, que había metido por velocidad, cambiaba el orden de los vértices de la entrada. Con "preserve sharp" y "preserve boundary", QuadriFlow no termina nunca con ese orden; con el orden original de la malla tarda 2 s. Aun en el orden original, otras dos piezas de esa malla tampoco terminan.
  - Arreglo: QuadriFlow corre en un Blender en segundo plano (`operations/remesh_worker.py`, `_Remesher` en `topology.py`). La pieza va en el orden de la malla y se envía en un `.npz`. Si pasa de `_time_limit` (15 s, más 1 s por cada 300 quads y por cada 20k triángulos de entrada, y 10 s más si el worker acaba de arrancar), se mata el proceso y la pieza conserva sus caras. Esc lo para en cualquier momento. Si el worker muere 3 veces seguidas, el error lo dice, en vez de contarlo como fallos de QuadriFlow.
  - Con la interfaz y los pasos del usuario: unos 110 s, 2 piezas cortadas por tiempo y como mucho 6,7 s congelado (al reconstruir UVs y normales). Mientras corre se puede mover la vista (sin Ctrl ni Alt: Alt+rueda cambia de frame).
  - Lo que queda: el panel de redo (cambiar el ratio después) ejecuta `execute`, que bloquea la interfaz durante todo el proceso, aunque ya no puede colgarse para siempre. Y si se mata el Blender del artista en mitad de una pieza colgada, el worker sobrevive (`ponytail:` en `_Remesher._kill`).
  - Fix All decima el coche de 191k a 50k triángulos: es el fix del check de polycount, que decima al presupuesto (`max_triangles`). Es lo previsto, pero sorprende; quizá debería pedir confirmación.
- **Fix All rompía el coche** (2026-10-27). El arreglo de caras degeneradas hacía merge by distance (0,1 mm) en **toda** la malla y fusionaba piezas separadas muy juntas (las capas del cristal): para quitar 30 caras borraba 615 y dejaba 840 aristas con 3 o más caras y unas 20k caras invertidas. Ahora solo toca las caras que reporta el check, cada una soldada consigo misma. Tiene un test de regresión en `check_regressions.py` con dos capas a 0,05 mm.
  - Regla: **un fix toca solo lo que su check reporta, nunca la malla entera.**
- Medido en la escena del coche (3 mallas seleccionadas, sin interfaz):

  | Operación | Tiempo | Nota |
  |---|---|---|
  | Validar | 8 s | |
  | Fix All | 25 s | |
  | Generate LODs | 30 s | 21 s son `bake_mesh` del decimate |
  | Clean Topology | 31 s | |
  | Heatmap | 0,4 s | |

  Fix All, LODs y Clean Topology bloquean la interfaz sin dar ninguna señal. Si molesta, el mismo patrón modal que Retopologize, o al menos `wm.progress_update` por objeto.
- Pendiente menor: `triangulate_warped` puede generar una cara degenerada nueva (30 → 31 en `.001`), y entonces Fix All necesita una segunda pasada.
- **Revisión antes del commit** (2026-10-27, `/ponytail-review` y `/code-review`). Arreglado, cada punto con su test:
  - Colisión de un mesh cuyo nombre acaba en `_NN` (`UCX_Pipe_90`): el índice es opcional, así que gana el mesh con el nombre completo (`collision_owner`).
  - El .blend guarda el número del item de un enum, no su nombre. Era la posición en la lista, y añadir un perfil desplazaba a los demás. Ahora es un crc32 del nombre (`_profiles`). Un perfil que falta se lee como `""` y cae a Custom o Default. Por eso, los .blend guardados antes con un preset elegido vuelven a Default.
  - El export Unity/Unreal renombra también los LODs a `Name_LOD1…n`; antes conservaban el nombre con el que se generaron.
  - Una regex de roles inválida o sin `(?P<owner>…)` en `asset_validator.json` sale como error de config en el panel, no como traceback. Un `lod.export_target` desconocido también da error.
  - Aceptar un aviso relee el objeto: el redo tras un undo veía la caché y retiraba la aceptación. Además, ya no revalida el paso entero.
  - Un UV NaN volvía O(T²) el solape de UVs: 7 s con 80k triángulos, unos 20 min con 1M.
  - Una excepción dentro del modal de Retopologize dejaba vivo el timer.
  - Los LODs heredaban las aprobaciones del asset por `obj.copy()`.
  - El heatmap Triangle Quality usa el `min_triangle_quality` del check: la mitad de la rampa es el límite, como en Quad Warp.
  - Descartados tras medirlos: `foreach_get` con int64 no es más lento que con int32 (0,14 s frente a 0,17 s en 2M loops), y `load_config` en cada redibujado del panel cuesta 0,15 ms.
- **Pruebas con el Makarov** (2026-10-28): `C:\Users\hugom\Documents\Assets\makarov-pm\source\Makarov.blend`, una pistola casi final: 8 piezas emparentadas a `Makarov_base` (escala 0,034 y rotación de un import FBX), 13,7k triángulos en total, todo triángulos, normales custom y texturas horneadas empaquetadas. Se prueba con una copia en el scratchpad. Todo tarda menos de 1 s, salvo Retopologize (28 s) y el export glTF (12 s). Hallazgos:
  - **`transfer_normals` estropea las aristas duras**: con `POLYINTERP_NEAREST`, copiar las normales a una malla *idéntica* deja el 5 % de las esquinas a más de 45° (cogen la normal de la cara vecina). Con `NEAREST_POLYNOR` el error es 0, y en Clean Topology el p95 baja de 49° a 7°. Afecta a `fix_normals`, Clean Topology, LODs y Retopologize: el arreglo es una línea en la función compartida.
  - **Los LODs generados bloquean el export** a Unreal/Unity (`Makarov_mag_LOD3`: 2 caras al revés) y traen vértices/aristas sueltos y non-manifold que el original no tiene.
  - **Falsos positivos de "closed part facing inward"** en LODs pequeños: la bala LOD2 (88 caras) sale entera "hacia dentro", pero su volumen con signo es positivo, como el original. `recalc_face_normals` falla en cascos de pocas caras; el volumen con signo es fiable. Sí hay una pieza invertida de verdad (`Makarov_base_LOD3`, volumen negativo).
  - **Transforms**: 15 errores bloquean el export del arma tal como está. El de la raíz (escala 0,034) es correcto; los de los hijos son pivotes de piezas móviles (corredera, martillo, gatillo, cargador), y aplicarlos los pierde. Además, `individual_files` parte el arma en 8 ficheros sin jerarquía.
  - **Godot**: cada .glb incrusta las texturas 4K: 8 ficheros, 245 MB (38 MB solo la bala).
  - **Clean Topology y Retopologize en un asset ya horneado**: Clean Topology conserva forma y UVs (la textura se lee igual), pero quadea una malla que el baker trianguló, y salen 40-54 quads alabeados por pieza. Retopologize duplica las costuras UV. Son herramientas de antes del bake. El aviso de slivers (1.012, el 7 % de los triángulos) recomienda justo esas dos herramientas.
  - Lo que va bien: Fix All no toca nada del arma (no hay nada arreglable) y el FBX y el glTF vuelven idénticos al reimportarlos (geometría, normales custom y UVs). El CLI devuelve 1 y escribe el HTML.
  - Menores: en el Floor (54 aristas con 3+ caras), Fix All pasa de 8 a 12 caras al revés. Los nombres de mesh `.001` no tienen fix. El heatmap Quad Warp sale todo gris en mallas trianguladas.
- **Arreglado en `bugfix/hard-surface-normals-and-lods`** (2026-10-28, rama desde la fase 0, sin ticket). Cada punto tiene un test en `check_regressions.py`, y se ha comprobado que falla con el código anterior.
  - `transfer_normals` muestrea en una copia con cada cara separada y encogida un 1 % hacia su centro (`POLYINTERP_NEAREST`). Así una esquina en una arista dura lee su propia cara. Se probó `NEAREST_POLYNOR`: arregla la copia idéntica, pero escalona las normales de los LODs, porque no interpola. Medido en el Makarov: Clean Topology pasa de p95 49° a 3°, y la corredera LOD1, del 36 % al 8 % de esquinas desviadas más de 10°. El coste a 1M triángulos pasa de 5,3 s a 6,5 s: `normals_split_custom_set` con `.tolist()` es 6 veces más rápido que con un array numpy.
  - `fix_normals` ya no transfiere. Guarda las normales antes de dar la vuelta a las caras y las vuelve a escribir: al girar unas caras se rehacen los abanicos de suavizado y se estropean las normales guardadas de las vecinas. Las de una cara girada se orientan hacia su cara.
  - `wrong_way_faces`: en cada pieza, las caras malas son las de la minoría (antes, en una pieza abierta, marcaba las 13 de la mayoría en vez de las 3 sueltas). Una pieza cerrada mira hacia dentro si su volumen con signo es negativo, y eso es un aviso aparte. La primera versión decidía también las caras malas por el volumen: en una habitación con una cara suelta, marcaba las otras 95, y el Fix automático de los LODs la habría girado hacia fuera sin avisar. Coste: `check_normals` pasa de 4,0 s a 4,8 s con 1M triángulos.
  - LODs: después del colapso se borran los vértices y aristas sueltos y se giran las caras al revés. Las aristas duras ya no se protegen ni se usan como borde en el decimado: con las aristas duras que la transferencia nueva marca en el LOD1 (169 en el cargador), el colapso del LOD2 hacía 20 aristas con 3+ caras. En un asset de juego están casi siempre sobre costuras UV, que siguen protegidas. El Makarov ya exporta con LODs a Unreal y Unity, y el FBX vuelve idéntico al reimportarlo (32 mallas). Coste a 1M triángulos: la limpieza añade unos 4 s a un Generate LODs de 34-37 s, casi todo en `wrong_way_faces`; saltarse la escritura cuando no hay nada que girar no ahorraba nada medible.
  - Las normales custom se borran antes del decimado con `mesh.customdata_custom_splitnormals_clear`, no quitando el atributo `custom_normal`, que solo existe en las versiones recientes (en 4.2 no se ha podido probar).
  - Aviso en `check_transforms` cuando el export pierde el vínculo con el padre: con `individual_files`, cuando el padre no se exporta, o cuando un LOD Group de Unreal ocupa su sitio. No sale en LODs ni colisiones. El export no cambia.
  - `tests/bench.py` llevaba roto desde que se añadieron los roles: llamaba a `check_collisions` con objetos que no son colisión.
  - Queda: LOD3 sigue degradando normales y texturas (es lo esperable al 10 %), y `Makarov_base_LOD3` tiene una pieza plegada de verdad (volumen negativo), que sale como aviso "inward". Los .glb con texturas duplicadas siguen igual. Aceptado en la revisión: el LOD1 tampoco protege las aristas duras que no están sobre una costura UV (`check_shading` ya las avisa), y en una pieza cerrada plana (una tarjeta de doble cara soldada) el aviso "inward" sale al azar, porque su volumen es ~0 (`ponytail:` en `wrong_way_faces`).
- **Siguiente paso** (hecho): la fase 1. Los puntos lentos que quedan (ver Línea base) solo valen la pena si un asset real lo pide.

## Fase 1: UVs y texel density

Código: `operations/uvs.py` (islas, métricas, herramientas), `checks/uvs.py` (`check_uvs`, movido desde `geometry.py`; `check_uv_layout`; `check_lightmap_uv`), `operators/uvs.py`, sección `uv` de `config/default.json`. Tests: `tests/check_uvs.py`.

- [x] Check de texel density por isla contra el objetivo del perfil (`uv.texel_density` px/m a `uv.texture_size`, ±`texel_tolerance`). La línea INFO de cada objeto da su densidad (mediana ponderada por área 3D): eso es "medirla". **Set Texel Density** la fija: escala cada isla en numpy alrededor de su centro y empaqueta sin reescalar (`pack_islands(scale=False)`); si no cabe en 0–1, lo dice. *Copy from Active* la copia entre objetos. No se usa `uv.average_islands_scale`: da lo mismo con un paso menos.
- [x] Check de estiramiento por isla: área (cuánto se aparta la escala UV de cada cara de la de su isla, `max_area_stretch`) y ángulo (error medio de los ángulos de las esquinas, `max_angle_stretch` en grados).
- [x] Separación entre islas en píxeles (`min_island_gap_px` a `texture_size`). Se mide en la rejilla de píxeles de la textura: los bordes de cada isla se dibujan en píxeles, se engordan medio margen, y las islas que comparten un píxel están demasiado cerca. Cuenta islas, no pares.
- [x] Islas fuera de 0–1, salvo en materiales tiling (regex `uv.tiling_materials` sobre el nombre) o UDIM (imagen `TILED`: la isla solo tiene que caber en una baldosa).
- [x] Canal de lightmap UV1 sin solapes y dentro de 0–1. Si falta, solo es error con `uv.require_lightmap`. El Fix lo rehace con `uv.lightmap_pack` y no toca UV0. xatlas no hizo falta.
- [x] Heatmaps *Texel Density* (lejos del objetivo, por exceso o por defecto; sin objetivo, de la mediana del objeto) y *UV Stretch*.
- [x] **Auto seams para hard surface** (**Auto Unwrap**):
  1. Seams en las aristas marcadas sharp (si no hay ninguna, en las que doblan más de `topology.feature_angle`), en los bordes de material y en los bordes abiertos.
  2. Unwrap: MINIMUM_STRETCH si existe, si no CONFORMAL.
  3. Si una isla estira demasiado, se corta por el camino de aristas más dobladas (desde la más doblada, en las dos direcciones, hasta llegar a un seam o un borde) y se repite, hasta 4 rondas.
  4. Las aristas cóncavas puntúan 1,5 veces más. Las "ocultas" no se tienen en cuenta.
- [x] Pesos de importancia en el unwrap: `use_weights` con el grupo `uv_importance`, si el operador tiene ese parámetro (4.3+) y el objeto tiene el grupo.
- [x] Enderezar islas de quads: opción *Straighten Quad Islands* de Auto Unwrap (Follow Active Quads en las islas hechas solo de quads).

### Notas de la fase 1, útiles para retomar

- **Las escenas de prueba del roadmap no están en este equipo** (`C:\Users\hugom\Documents\Assets\...`). Se probó con lo que hay en `test_assets/` (sin commitear): el Audi R8 (FBX, 144 mallas, 178k caras), la roca (FBX, escaneo de 35k caras), el T-Rex (OBJ, 250k caras) y `Addon_Test.blend` (abierto en segundo plano, nunca guardado).
- **UV0 es `uv_layers[0]`**, no la capa activa: es la que muestrea el material en el motor. `check_uvs` usaba la activa; con una sola capa da lo mismo.
- **Islas**: caras unidas por una arista con las mismas UVs en sus dos extremos, como las ve Pack Islands. Coinciden exactamente con `bpy_extras.mesh_utils.mesh_linked_uv_islands` (test). Union-find en numpy (`_components`).
- **Ninguno de los checks de layout tiene Fix**: Set Texel Density y Auto Unwrap reescriben UV0, y Fix All los aplicaría a assets ya horneados (el Makarov).
- **El check de huecos se rehízo dos veces con los assets reales**:
  1. Por pares de aristas (rejilla y distancia entre segmentos) se colgaba con el Audi: una malla con todas sus UVs en un parche de 15×20 px (paleta de colores) daba 43 millones de pares.
  2. En píxeles seguía atascado con la fibra de carbono, que tiene UVs de −154 a 217 (22 millones de píxeles de borde por malla). Ahora hay un presupuesto de 5 M de filas: si se pasa, solo se recortan las aristas más largas. Además, se saltan las islas que están fuera de 0–1, que ya tienen su propio aviso.
- **Islas de color sólido** (la isla entera cabe en un texel; mapeo de paleta): no tienen textura que medir, así que quedan fuera de densidad, estiramiento y huecos. Se cuentan en la línea INFO y no cuentan para la mediana.
- Resultados con los assets reales (densidad objetivo 512 px/m por defecto): casi todo sale con aviso de densidad, porque ninguno está hecho a 512. Es lo esperado: el perfil del proyecto fija su objetivo, y `texel_density: 0` lo desactiva. Tiempos de `check_uv_layout`: Audi 11 s (144 mallas), T-Rex 3,2 s, roca 0,6 s, `Addon_Test` 1,9 s.
- **Minimum Stretch (SLIM) de Blender 5.2 colapsa islas** de mallas reales: con los seams por ángulo, el 72 % de los triángulos de la roca salía con área UV 0, y el T-Rex quedaba en una tira de 0,005 de ancho. Angle Based y Conformal no lo hacen. `_unwrap` detecta las islas con más del 5 % de su área colapsada, las rehace con Conformal y las deja en Conformal en las rondas siguientes; si no, SLIM las volvía a colapsar cada ronda, con minutos por ronda. Angle Based arregla lo mismo, pero tardaba minutos en las islas grandes y cerradas del esqueleto.
- Auto Unwrap, medido: lexan de `Addon_Test.blend` 11,6 s (178k caras), T-Rex 34 s (250k caras; antes de los arreglos, 256 s), roca 11 s, neumático del Audi 3 s. En orgánico (roca, T-Rex) salen miles de islas por los seams por ángulo: es una herramienta de hard surface, y lo orgánico es la fase 5. Sobre mallas reales siguen saliendo solapes tras el empaquetado. No se investigó más a fondo: la sospecha son triángulos casi degenerados de Conformal (unos 860 en la roca).
- **Set Texel Density centra cada isla en (0,5; 0,5) antes de escalarla**. Islas con UVs en torno a 500 (basura o tiling) perdían hasta un 10 % de área por la precisión float32, y Pack Islands (closest UDIM) empaqueta en la baldosa donde están las islas. Hay test.
- El margen de empaquetado es `ADD`, que es exacto con `scale=False` (Set Texel Density). Con `scale=True` (Auto Unwrap), el margen encoge con el layout, así que en layouts densos queda por debajo del configurado: en el lexan, el 65 % de las islas quedaron demasiado cerca, y `check_uv_layout` lo avisa. `FRACTION` sería exacto, pero `pack_islands` se quedó más de 20 s girando con un cubo. Pendiente: probar a empaquetar dos veces (escalar primero y después empaquetar sin escalar con el margen).
- **Siguiente paso**:
  1. Probar la fase 1 con interfaz en tu escena: el paso "Shading & UVs", las dos herramientas, los heatmaps y la línea INFO de densidad.
  2. ~~Decidir si la densidad objetivo por defecto (512 px/m) se queda o pasa a 0.~~ Decidido el 2026-10-29: se queda en 512. Es el estándar indie/PC; el aviso se acepta, o el perfil del proyecto fija otro objetivo. Además, así Hard Surface Prep tiene una densidad que aplicar.
  3. ~~Medir con `tests/bench.py`.~~ Hecho el 2026-10-29: ver **Línea base**. En `Addon_Test.blend` (410k caras), `check_uv_layout` es lo más lento de la validación: 15,5 s de 21 s.
  4. ~~La fase 2 (hard surface).~~ Empezada: Hard Surface Prep encadena Auto Unwrap y Set Texel Density.
- ~~Pendiente menor: el panel no se ha revisado con interfaz.~~ Revisado el 2026-10-29 con capturas (ver las notas de la fase 2).

## Fase 2: hard surface

### Primera parte: criterios (2026-10-29, antes del código)

Alcance: Hard Surface Prep, support loops con bevel y check de mid-poly. Quedan para después el bake helper, el crease para SubD (hace el `_high`, así que va con el bake helper) y las trim sheets. Cada criterio es un test en `tests/check_hard_surface.py`.

**Hard Surface Prep** (`asset_validator.hard_surface_prep`). Trabaja sobre las mallas seleccionadas: lo de la malla, una vez por malla compartida; los modificadores, en cada objeto.

- FR-1: sombreado smooth y sharp en las aristas que doblan más de *Sharp Angle* (por defecto, `topology.feature_angle`). Las sharp que ya estaban se conservan (`object.shade_smooth_by_angle` con `keep_sharp_edges`).
- FR-2: Auto Unwrap. Seams en las sharp, en los bordes de material y en los bordes abiertos, cortes por estiramiento y pack.
- FR-3: si `uv.texel_density` > 0, Set Texel Density con ese valor. Con 0 se queda el pack de Auto Unwrap.
- FR-4: un modificador Weighted Normal (Face Area, Keep Sharp, fijado al final con `use_pin_to_last`), si el objeto no tiene ya uno activo.
- FR-5: opción *Bevel Sharp Edges* (support loops para mid-poly). Las sharp pasan a bevel weight 1 y dejan de ser sharp. Se añade un Bevel limitado por weight, con *Segments* (2) y un ancho del 0,5 % de la dimensión mayor del objeto, delante del Weighted Normal. Medido antes en 5.2 con un cubo: si las aristas siguen sharp, el Bevel copia la marca a los bordes del bisel (24 aristas duras); sin Weighted Normal, las caras grandes se curvan 29°; con los dos, 0,6°.
- FR-6: una línea por objeto con las sharp, las islas, la densidad y los modificadores añadidos.
- FR-7: **check de mid-poly** (`check_weighted_normal`, solo assets: los LODs llevan las normales horneadas, sin modificadores). Con `hard_surface.require_weighted_normal: true`, un asset sin Weighted Normal activo en el viewport es un error, con un Fix que añade uno y no toca nada más. Con `false` (por defecto) no dice nada.
- FR-8: el check va en el paso "Shading & UVs". Hard Surface Prep va en las herramientas de ese paso y en el modo normal.
- NFR-1: Prep tarda lo que Auto Unwrap más Set Texel Density. En la malla más grande de la escena real del usuario, menos de 60 s.

| AC | Requisito | Dado / cuando / entonces |
|---|---|---|
| 1 | FR-1, 2 | Un cilindro de 32 lados sin marcas, con `texel_density` 0: tras Prep tiene 64 sharp (los bordes de las tapas), 3 islas y ningún aviso de `check_uv_layout` ni de `check_uvs` |
| 2 | FR-1 | Una arista del tubo marcada sharp a mano sigue sharp y es seam |
| 3 | FR-3 | Con objetivo 512: cada isla a 512 ±1 % y todas dentro de 0–1 |
| 4 | FR-4 | Hay un Weighted Normal con Keep Sharp, y repetir Prep no añade otro |
| 5 | FR-4 | `check_shading` no avisa de aristas duras fuera de seams |
| 6 | FR-5 | En un cubo con Bevel: la pila es Bevel → Weighted Normal, el mesh evaluado no tiene sharp, y las esquinas de las caras grandes se apartan menos de 2° de su normal |
| 7 | FR-7 | Con el perfil que lo pide: error sin Weighted Normal; Fix lo añade y el error desaparece. Un LOD no da error. Sin el perfil, ningún resultado |
| 8 | FR-8 | El check está en un paso (`check_steps`) y el operador se registra y se ejecuta desde `bpy.ops` |
| 9 | NFR-1 | `check_scene.py`: Prep en la malla más grande de la escena real, en menos de 60 s |

Casos límite: una malla sin caras se salta, sin error. Duplicados enlazados: la malla se prepara una vez, y cada objeto recibe sus modificadores. Un Weighted Normal desactivado no cuenta para el check. Si la densidad no cabe en 0–1, la línea lo dice (es el mensaje de Set Texel Density).

Fuera de alcance: `harden_normals` en el Bevel (el Weighted Normal ya aplana las caras grandes, y como va detrás, lo sobrescribiría), un modo modal con progreso (Prep bloquea lo mismo que Auto Unwrap) y ajustar un Bevel que ya exista (si hay uno activo limitado por weight, no se añade otro; tras la revisión).

### Notas de la primera parte, útiles para retomar

Código: `operations/hard_surface.py`, `operators/hard_surface.py`, `check_weighted_normal` en `checks/shading.py` y la sección `hard_surface` de `config/default.json`. Tests: `tests/check_hard_surface.py`, 25 tests. Los cinco puntos delicados se comprobaron mutando el código: el test falla sin `keep_sharp_edges`, sin borrar las sharp al pasarlas a bevel weight, sin `use_pin_to_last`, sin `roles=("asset",)` y sin mirar `show_viewport`. El de `use_pin_to_last` no fallaba al principio, porque el operador añade el Bevel antes que el Weighted Normal. Hubo que añadir el caso real: un objeto que ya tiene Weighted Normal (por el Fix o por un Prep anterior) y al que después se le pone Bevel.

- **API de 5.2, comprobada**: `object.shade_smooth_by_angle(angle, keep_sharp_edges)` conserva las sharp marcadas y las normales custom, y no añade modificadores. Necesita `temp_override` con el objeto como seleccionado y activo. No existen `Mesh.set_sharp_from_angle` ni `ObjectModifiers.move`; para el orden se usa `use_pin_to_last` en el Weighted Normal. En 4.2 no se ha podido probar (`use_pin_to_last` debería existir desde 4.2).
- **Escenas reales en este equipo** (`$env:AV_SCENE`, ver Tests en el README):
  - `C:\Users\hugom\Documents\Assets\makarov-pm\source\Makarov.blend`: Prep con Bevel en 1,4 s en el cargador (4,5k caras): 1.030 sharp, 374 islas, 512 px/m dentro de 0–1. Bevel + Weighted Normal se evalúan en 0,05 s (de 4,5k a 8k caras). Quedan solapes de UV tras el empaquetado y 19 islas estiradas: es lo que la fase 1 ya anotó de Auto Unwrap en mallas reales.
  - `C:\Users\hugom\Documents\Assets\BlenderSuitTest_01.blend` ya no es solo el coche: el 2026-10-29 tenía 20 mallas y 2,6M de caras (copias de la carrocería del Audi, sus Retopo y LODs, el Gipsy Danger y `geo_dead_LOD2`, el escaneo del coche destrozado). La validación completa tarda 105 s, lineal con el tamaño. `check_scene.py` escala ahora el límite: 30 s por cada 400k caras.
  - **Carrocería del Audi** (`aud_r8_08_lod0_body_black_glass_`, 190k caras, 11.579 piezas): Prep en 16,8 s, sin área colapsada. Cumple NFR-1. Que 512 px/m no quepan en una textura de 2048 es lo esperable en un coche entero.
  - **El escaneo** (`geo_dead_LOD2`, 564k caras) es la malla más grande de la escena, así que es la que coge `check_scene.py`: Prep (y Auto Unwrap, que es lo mismo) tarda de 385 a 557 s, con Blender bloqueado y sin poder cancelar. Marca 286k sharp y deja 77k islas, con un 8-16 % del área colapsada. Medido por fases: el 88 % es `bpy.ops.uv.unwrap` nativo (4 llamadas de unos 2 min), luego `uv_stats` (56 s en 9 llamadas) y `face_islands` (47 s en 10). En nuestro código no hay nada que acelerar; solo se podría cancelar entre llamadas o sacar el unwrap a un proceso aparte, como QuadriFlow. Es un escaneo orgánico, fuera del alcance de hard surface (fase 5), pero es fácil lanzarlo sin querer seleccionando todo. **Sin decidir**: proteger o hacer modal Auto Unwrap/Prep, o solo documentarlo. Por eso NFR-1 falla en `check_scene.py` con esta escena.
- **Interfaz** (capturas con Blender abierto y el panel en la pestaña Item): Prep va en su propia fila, en el modo normal y en el paso 4. En el N-panel no caben tres botones con texto en una fila, así que `_STEP_TOOLS` es ahora una lista de filas. Desde la interfaz (invoke, que toma el ángulo de `topology.feature_angle`) con Bevel, la pila queda Bevel → Weighted Normal. La descripción del paso 4 ya salía cortada antes de este cambio.
- `check_scene.py`: Set Texel Density usa ahora la densidad mediana de la propia malla. Con 64 px/m fijos, todas las islas del Makarov quedaban por debajo de 4×4 px y no había nada que medir.
- **`/code-review`** (2026-10-29): 15 hallazgos. Arreglados, cada uno con su test (los seis se comprobaron mutando el código):
  - Un Weighted Normal añadido a mano sin fijar quedaba delante del Bevel. Ahora Prep fija al final todos los Weighted Normal.
  - Las sharp pasaban a bevel weight aunque no se añadiera ningún Bevel que las biselara (había otro Bevel, por ángulo o desactivado). Ahora solo se omite el Bevel si ya hay uno activo limitado por weight.
  - Prep, Auto Unwrap y Set Texel Density reescribían las UVs de los LODs y de las colisiones seleccionadas. Ahora solo tocan assets (`asset_meshes` en `operators/uvs.py`).
  - Un modificador *Smooth by Angle* (de Shade Auto Smooth, fijado al final) volvía a marcar sharp los bordes del bisel: 48 aristas duras en un cubo, medido. Prep lo quita, porque las sharp marcadas hacen su trabajo.
  - `invoke` pisaba el ángulo pasado con `INVOKE_DEFAULT`. **Sin interfaz, `INVOKE_DEFAULT` no llama a `invoke`**: ejecuta `execute`. Por eso el test headless no podía detectarlo, y se comprobó con Blender abierto (con el arreglo, 16 y 24 sharp; mutado, 24 y 24).
  - Si ninguna arista llegaba al ángulo de Prep, Auto Unwrap ponía los seams con `topology.feature_angle`. Ahora usa el mismo ángulo que Prep.
  - El test de "nada seleccionado" daba por bueno cualquier `RuntimeError`, también un crash; ahora mira el mensaje.
  - Descartados, con la razón:
    - "el FBX aplica los modificadores según render": `export_fbx_bin.py` de 5.2 usa `context.evaluated_depsgraph_get()`, el del viewport, y su `use_mesh_modifiers_render` está desactivado desde 2.8.
    - Asserts que revientan antes de imprimir FAIL: el runner ya marca el fichero como "did not finish".
    - Las UVs del bisel evaluado: medidas, sin solapes y dentro de 0–1. El chaflán sale comprimido un 30-37 % de área; queda documentado en el README.
    - El doble empaquetado (Auto Unwrap y luego Set Texel Density): medido en la carrocería del Audi, `_pack` son 3,3 s en 2 llamadas de un Prep de 16,8 s. Ahorraría ~10 % a cambio de una opción más en `auto_unwrap`.
    - `.vscode/settings.json` y el zip: las convenciones ya los dejan fuera del commit.
    - El test lee las sharp con su propia función, a propósito, para no depender de la que prueba.
  - Pendiente de decisión: el escaneo de 564k caras (ver arriba).

### Plan completo

- [x] **Hard Surface Prep** en un clic, encadenando operadores nativos:
  1. Smooth by Angle.
  2. Marcar sharp por ángulo (con `object.shade_smooth_by_angle`, que hace 1 y 2 a la vez; `mesh.set_sharpness_by_angle` es de Edit Mode).
  3. Seams en las aristas sharp y en los bordes de material.
  4. Unwrap y pack (`uv.pack_islands` con `shape_method="CONCAVE"`).
  5. Texel density.
  6. Modificador Weighted Normal con Keep Sharp.
- [ ] Support loops: [x] bevel en las aristas sharp con N segmentos para mid-poly (sin `harden_normals`: el Weighted Normal lo cubre); [ ] crease para SubD, que va con el bake helper.
- [x] Check de mid-poly: si el perfil lo pide, tiene que haber Weighted Normal.
- [ ] **Bake helper**:
  - Empareja `_high` y `_low` por nombre y crea el cage solo (copia inflada) o calcula la distancia de rayo a partir del tamaño.
  - Hornea con `object.bake` (`use_selected_to_active`, `cage_extrusion`, `normal_g`): `NEG_Y` en Unreal (DirectX), `POS_Y` en Unity y Godot (OpenGL).
  - Exporta pares con nombres compatibles con Substance Painter y Marmoset.
- [ ] Trim sheets: mapear caras a las franjas de una hoja.

## Fase 3: entornos, colisiones y texturas

- [ ] Modulares: medidas múltiplo del grid y bordes abiertos sobre el grid. Herramienta de pivote (base centrada o esquina).
- [ ] Aviso de tamaño absurdo (bounding box de menos de 1 cm o más de 1 km), que delata unidades o escala mal.
- [ ] Generar colisiones:
  - UCX con casco convexo nativo (`bmesh.ops.convex_hull`).
  - Cajas, cápsulas y esferas ajustadas (UBX, UCP, USP).
  - Descomposición convexa con CoACD (MIT) o V-HACD (BSD) como binario o wheel opcional.
- [ ] Check de UCX convexo: Unreal rehace el casco convexo de cada UCX, así que uno cóncavo colisiona mal.
- [ ] Texturas:
  - Potencia de 2 y resolución máxima según la plataforma.
  - Non-Color en normal, ORM y roughness.
  - Nombres `T_*_N/_D/_ORM`.
- [ ] Materiales: número de materiales (cada uno es un draw call) contra un presupuesto, y slots sin caras.
- [ ] Prefijos de nombre según el motor (`SM_`, `SK_`, `T_`, `M_`, `MI_`).
- [ ] Botón para activar el Mesh Analysis nativo (grosor, intersecciones, distorsión) en vez de reimplementarlo.

## Fase 4: topología y LOD avanzados

- [ ] **LOD quitando loops enteros** en mallas de quads: se quitan los loops que menos cambian la silueta, medido contra el original, hasta llegar al objetivo. Mantiene quads, UVs y seams. Reutiliza `_edge_loop` y `_straight_through` de `operations/topology.py`, cambiando "solo zonas planas" por "por debajo de un error".
- [ ] Error de cada LOD respecto al original (distancia de Hausdorff con BVH), con heatmap y screen size sugerido (el nivel desde el que el error es menor de 1 px).
- [ ] T-junctions (vértice apoyado en una arista que no es suya), caras duplicadas o coplanares (z-fighting), autointersecciones, piezas sueltas diminutas.
- [ ] Micro-triángulos: la GPU sombrea en bloques de 2×2 píxeles. Más de 65.535 vértices GPU por malla en móvil.
- [ ] Set Flow: ajustar loops a la curvatura, como hace EdgeFlow. EdgeFlow es GPL, así que se reimplementa en vez de copiarlo.
- [ ] Remeshers externos opcionales: Instant Meshes (BSD) y QuadWild Bi-MDF (revisar la licencia).

## Fase 5: personajes y orgánico

- [ ] Influencias por vértice (4 u 8), pesos normalizados, grupos de vértices sin usar.
- [ ] LODs que mantengan el Armature: ahora se hornean estáticos (ver el `ponytail:` en `operations/lod.py`).
- [ ] Flujo de escultura a retopo con los remeshers de la fase 4.

## Fase 6: comercial

- [ ] Pulir la UI, escribir la documentación y revisar las licencias de las dependencias.
- [ ] Pasar los heatmaps a un overlay GPU (`draw_handler_add`) que no toque la malla.
- [ ] Publicar en Superhive y/o extensions.blender.org.

## Lo que no se hace

- Ni empaquetador de UVs ni remesher propios: el pack nativo (CONCAVE, con rotación) y QuadriFlow bastan; lo externo va como opcional.
- No reimplementar Mesh Analysis.

## Pendiente de verificar en motor

En la máquina de desarrollo no hay Unreal ni Unity. Se ha comprobado la estructura del FBX/GLB exportado, pero no cómo lo importa cada motor.

- [ ] **Unreal**: con "Import Mesh LODs", ¿el Empty `LodGroup` se importa como un único Static Mesh con LOD0…n? ¿Se reconocen `UCX_<nombre>_LOD0_NN` y `SOCKET_`? La regla de que el UCX se llame como el LOD0 sale del código del importador y de ejemplos de la comunidad.
- [ ] **Unreal**: ejes y escala (`axis_forward`/`axis_up` de `default.json`) y la advertencia de smoothing groups (el perfil usa `mesh_smooth_type: FACE`).
- [ ] **Unity**: ¿un FBX con `_LOD0…n` crea el LOD Group? ¿La receta del perfil (`-Z`/`Y`, `FBX_SCALE_ALL`, `bake_space_transform`) importa con rotación 0 y escala 1?
- [ ] **Godot**: ¿el .glb importa `-colonly` como StaticBody3D y genera los LODs solo?

## Línea base de rendimiento

Medido en Blender 5.2.3 con una UV sphere con UVs y sombreado smooth, antes de la fase 0:

| Triángulos | Total | check_uvs | check_shading | check_normals | check_quad_planarity |
|---|---|---|---|---|---|
| 16k | 0,5 s | 0,26 s | 0,20 s | 0,03 s | 0,03 s |
| 261k | ~10,7 s | 5,3 s | 3,8 s | 0,9 s | 0,46 s |
| 1M | 18 s sin UVs (~40 s con UVs, extrapolado) | — | 11,2 s | 3,0 s | 2,3 s |

Como cada Fix revalida, en modo guiado un asset de 1M de triángulos llegaba a más de 30 s por clic.

Después de la fase 0 (numpy en UVs, shading y planaridad), medido con `tests/bench.py`:

| Triángulos | Total | check_uvs | check_shading | check_normals | check_quad_planarity |
|---|---|---|---|---|---|
| 16k | 0,22 s | 0,06 s | 0,10 s | 0,04 s | 0,01 s |
| 261k | 3,1 s | 1,1 s | 0,66 s | 0,84 s | 0,11 s |
| 1M | 13,6 s | 5,4 s | 2,9 s | 3,3 s | 0,48 s |

Con el volumen con signo en `check_normals` (2026-10-28), medido el mismo día con el código anterior y con el nuevo:

| Triángulos | Total | check_uvs | check_shading | check_normals (antes → ahora) | check_quad_planarity |
|---|---|---|---|---|---|
| 16k | 0,30 s | 0,06 s | 0,13 s | 0,04 → 0,08 s | 0,01 s |
| 261k | 3,9 s | 1,4 s | 0,66 s | 0,88 → 1,38 s | 0,11 s |
| 1M | 16,8 s | 6,5 s | 3,2 s | 3,97 → 4,84 s | 0,52 s |

Con los checks de UV de la fase 1 y `check_weighted_normal` de la fase 2 (2026-10-29, `tests/bench.py`):

| Triángulos | Total | check_uvs | check_uv_layout | check_shading | check_normals | check_quad_planarity |
|---|---|---|---|---|---|---|
| 16k | 0,40 s | 0,04 s | 0,21 s | 0,08 s | 0,04 s | 0,01 s |
| 261k | 4,2 s | 0,89 s | 1,29 s | 0,57 s | 1,06 s | 0,08 s |
| 1M | 16,4 s | 3,93 s | 5,46 s | 2,20 s | 3,23 s | 0,37 s |

`check_lightmap_uv` y `check_weighted_normal` salen a 0,00 s: la esfera no tiene UV1, y el perfil por defecto no pide Weighted Normal. `check_uv_layout` es ahora el check más lento: un tercio del total.

Lo que más tarda ahora:
- `check_uv_layout`: `uv_stats` y `face_islands`, que en el escaneo de 564k caras tardaban unos 5-6 s por llamada.
- `check_normals`: `loose_parts` es un recorrido en Python. Se aceleraría con una union-find en numpy.
- `check_shading`: el `np.unique` por filas. Se aceleraría con una vista `void`.
- `check_uvs` en mallas enormes.

## Investigación: datos clave y fuentes

- **Unity** solo crea el LOD Group con `Nombre_LOD0`, `_LOD1`… juntos en el mismo FBX ([manual](https://docs.unity3d.com/6/Documentation/Manual/importing-lod-meshes.html)).
- **Godot 4** genera los LODs al importar ([mesh LOD](https://docs.godotengine.org/en/4.5/tutorials/3d/mesh_lod.html)). Sufijos `-col`, `-convcol`, `-colonly`, `-convcolonly`, `-occ`, `-navmesh`, `-rigid`, `-noimp`… Valen `-`, `$` o `_`, y no distinguen mayúsculas ([import hints](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/node_type_customization.html)).
- **Unreal**: colisiones `UCX_`, `UBX_`, `USP_`, `UCP_` + nombre del mesh + `_NN`. Con varios meshes con colisión propia en un solo FBX, solo se importa la colisión del primero, así que va un FBX por asset ([FBX Static Mesh](https://docs.unrealengine.com/4.27/WorkingWithContent/Importing/FBX/StaticMeshes)). LOD Group desde Blender: un Empty con la propiedad `fbx_type = "LodGroup"` ([Better FBX FAQ](https://superhivemarket.com/products/better-fbx-importer--exporter/faq)). Comprobado en `export_fbx_bin.py` de Blender 5.2: la propiedad `fbx_type` decide el tipo de nodo que se escribe.
- **Blender 5.2**, comprobado con `get_rna_type()`:
  - `uv.unwrap` ofrece los métodos ANGLE_BASED, CONFORMAL y MINIMUM_STRETCH, con `iterations` y `use_weights`/`weight_group` (por defecto `uv_importance`).
  - `uv.pack_islands` admite `shape_method` CONCAVE, CONVEX o AABB.
  - `object.bake` admite `use_selected_to_active`, `cage_extrusion` y `normal_g`.
  - Existen el modificador `WEIGHTED_NORMAL`, `wm.collection_export_all` (Collection Exporters, desde 4.2) y `export_scene.gltf`.
  - Lleva numpy 2.3.4.
- **Baking en hard surface**: seam de UV = hard edge; triangular antes de hornear y exportar; mismas normales en el bake que en el motor ([80.lv](https://80.lv/articles/best-practices-for-hard-surface-normal-map-baking), [Polycount](https://polycount.com/discussion/comment/2805354)).
- **Micro-triángulos**: la GPU sombrea en bloques de 2×2 píxeles, así que los triángulos de pocos píxeles desperdician trabajo ([Self Shadow](https://blog.selfshadow.com/publications/overdraw-in-overdrive/)).
- **Remeshers**:
  - QuadriFlow tiene inestabilidades que vienen del propio algoritmo ([devtalk](https://devtalk.blender.org/t/quadriflow-integration/23156)).
  - QuadWild con Bi-MDF es más rápido y alinea los quads con las aristas marcadas ([Bi-MDF](https://cgg.unibe.ch/publication/011282/)).
  - EdgeFlow: [GitHub](https://github.com/BenjaminSauder/EdgeFlow).
- **Colisiones**: CoACD respeta mejor los huecos y las concavidades que V-HACD, a cambio de ser más lento ([comparativa](https://simready.artlabs.ai/compare/v-hacd-vs-coacd-vs-manual-hulls)).
- **UVs**: SLIM / Minimum Stretch ([80.lv](https://80.lv/articles/blender-received-new-uv-unwrapping-algorithm/)); xatlas en Python ([PyPI](https://pypi.org/project/xatlas)); presets de texel density habituales: 512 px/m para indie/PC y 1024 px/m para AAA ([Texelmaster](https://superhivemarket.com/products/texelmaster-texel-density-manager)).
- **Mesh Analysis** de Blender: grosor, intersecciones, distorsión, aristas afiladas y voladizos, solo en Edit Mode ([manual](https://docs.blender.org/manual/en/4.2/modeling/meshes/mesh_analysis.html)).
- **Extensiones** de Blender: [manual](https://docs.blender.org/manual/en/dev/advanced/extensions/getting_started.html).
