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
- Este documento es el tracker de las skills de Matt Pocock (opción «Other»): no se crean `.scratch/`, `GLOSSARY.md` ni `docs/adr/` sin pedirlo.
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
| `blender_asset_validator/operations/` | Lógica que modifica mallas: cleanup, topology (Clean/Retopo), lod, decimate, heatmap, uvs (islas, métricas y herramientas UV), hard_surface, bake (distancias medidas y normal map) |
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
| 2 Hard surface | `feature/phase-2-hard-surface` (desde `feature/phase-1-uvs`, sin ticket) | primera parte (Hard Surface Prep, Bevel, check de mid-poly) commiteada en `f82c897`. Segunda parte, el bake helper (rol `high`, Bake Normals, Export Bake Pairs), y `--jobs` en el CLI: testeados (368 tests; `check_scene` falla con la escena actual, ver notas) y commiteados el 2026-10-29 sin revisar, a petición del usuario. El 2026-11-03 se revisaron (10 hallazgos, 7 arreglados) y se arregló el solape de UVs con islas lejanas: 379 tests, revisado y commiteado el 2026-11-04 (`7c31cc2`). El mismo día: Auto Unwrap y Prep modales con Esc, y los tres bugs conocidos de Prep arreglados (385 tests), revisados y commiteados (`ffbf5d9`). Después, en `feature/showroom` (desde esa rama, sin ticket): pruebas con BlenderSuitTest_01, el arreglo del crash por mallas corruptas, los LODs sin caras duplicadas y el showroom (ver "Pruebas con BlenderSuitTest_01 y showroom"): 395 tests, revisado y commiteado en esa rama. En el repo solo va el script del showroom: el `.blend` y la normal map se regeneran. Lo siguiente está en "Siguiente paso" de la segunda parte. Quedan el crease para SubD y las trim sheets |
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
- [x] **B4 Informe JSON/HTML y CLI** (`cli.py`, `report/generator.py`): `blender -b --factory-startup --python blender_asset_validator/cli.py -- [--engine unreal] [--preset mobile] [--report out.json|out.html] [--jobs N] a.blend b.blend …`.
  - Sin `--engine`, usa el motor guardado en cada .blend.
  - Código de salida 1 si hay errores, comprobado con el Blender de la Store.
  - `--jobs` (2026-10-29, a petición del usuario): cada fichero se valida en su propio Blender en segundo plano (`bpy.app.binary_path`, el propio `cli.py` con ese fichero solo y `--jobs 1`). Por defecto usa la mitad de los núcleos lógicos. Los threads de `ThreadPoolExecutor` solo esperan a los procesos, sin tocar `bpy`. Un Blender que muere sin escribir su informe (un .blend corrupto) da un error en ese fichero; `--python-exit-code 2` distingue un fallo de Python del exit 1 de "hay errores". Si el binario no se puede lanzar, valida uno detrás de otro. Medido con 8 .blend de una esfera de 260k triángulos cada uno, en 16 núcleos lógicos: de 30,3 s con `--jobs 1` a 10,1 s con `--jobs 8`, con informes idénticos. Lo que no baja es el arranque de cada Blender (unos segundos), así que la ganancia se acerca a N cuanto más pesa cada fichero.
  - Revisión (2026-11-03): con un Blender por fichero, 16 props pequeños tardaban 10,1 s con `--jobs 8` y 6,1 s con `--jobs 1`, porque cada arranque cuesta 3,1 s. Ahora hay un Blender por job y los ficheros se reparten entre ellos (`files[i::jobs]`): los mismos 16 tardan unos 6-7 s, lo mismo que en secuencial. En props pequeños no se gana nada, pero ya no se pierde. Si un hijo muere sin escribir el informe, sus ficheros se repiten de uno en uno, y el corrupto sigue fallando solo. Probado con el Blender de la Store, que lanza los hijos sin problema. Ese launcher no reenvía el stdout del proceso, así que el test captura la consola desde `cli.main`.
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

- **API de 5.2, comprobada**: `object.shade_smooth_by_angle(angle, keep_sharp_edges)` conserva las sharp marcadas y las normales custom, y no añade modificadores. Con normales custom, mide el ángulo entre ellas y no entre las caras, así que Prep ya no lo usa (ver "Bugs conocidos de Prep"). Necesita `temp_override` con el objeto como seleccionado y activo. No existen `Mesh.set_sharp_from_angle` ni `ObjectModifiers.move`; para el orden se usa `use_pin_to_last` en el Weighted Normal. En 4.2 no se ha podido probar (`use_pin_to_last` debería existir desde 4.2).
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

### Segunda parte: bake helper, criterios (2026-10-29, antes del código)

Alcance: emparejar low y high, hornear la normal map en Blender y exportar los pares para Substance Painter y Marmoset. Quedan para después el crease para SubD (crear el `_high`) y las trim sheets. Cada criterio es un test en `tests/check_bake.py`.

- FR-1: **emparejado por nombre**, con la regla de "Match by Mesh Name" de Substance Painter, que distingue mayúsculas ([Adobe](https://experienceleague.adobe.com/en/docs/substance-3d/bakers/features/matching-by-name)). El low es un asset `Name` o `Name_low`. Sus high son `Name_high`, `Name_high_<lo que sea>` y `Name_high.NNN` (lo que da duplicar en Blender). Los sufijos están en `bake.low_suffix` y `bake.high_suffix`.
- FR-2: **rol `high`**. Un high no pasa ningún check y no se exporta al motor. Prep, Auto Unwrap, Set Texel Density y Generate LODs se lo saltan. Retopologize y Clean Topology no, porque retopologizar un high es justo cómo se hace un low. La única excepción es `check_bake_pairs` (paso 1): un high sin low da un aviso que dice que no se va a exportar. Es una errata, o un asset que por casualidad acaba en `_high` (`Tower_high`) y que, si no, desaparecería del export sin decir nada. Añadido al revisar el código, antes de los tests finales.
- FR-3: **distancias medidas, no adivinadas**. Con un BVH del low evaluado, se mide la distancia con signo de los vértices del high evaluado a la superficie del low (hasta 100k vértices; si hay más, una muestra). La extrusión del cage es lo que más sale el high por fuera, y la distancia de rayo, la extrusión más lo que más se mete por dentro. Las dos llevan un 10 % de margen más 1 mm por metro de diagonal del low. Si la mitad de los vértices del high quedan a más del 10 % de la diagonal, el par no está superpuesto y no se hornea (añadido tras la prueba con la escena real, ver notas).
- FR-4: **Bake Normals** (`asset_validator.bake_normals`). Normal map en espacio tangente sobre UV0 (`uv_layer`, no la capa activa), con Cycles a 16 muestras. El canal verde sale de `bake.normal_g` (`NEG_Y` en Unreal y `POS_Y` en el resto), el margen es la mitad de `uv.min_island_gap_px` (el relleno de las islas se junta en el centro del hueco) y el tamaño, `uv.texture_size`. La imagen se llama `Name_N`, es Non-Color y se guarda como PNG en `bake.path`. Volver a hornear reutiliza la imagen. Los materiales, el motor de render y las muestras quedan como estaban.
- FR-5: **Triangulate** (con `keep_custom_normals`) antes del bake y del export de pares, si el low no tiene uno activo. Así el bake, Painter y el motor ven los mismos triángulos: si cada uno triangula los quads no planos a su manera, el espacio tangente cambia.
- FR-6: **Export Bake Pairs** (`asset_validator.export_bake_pairs`). Escribe `<Name>_low.fbx` con los assets seleccionados, renombrados `X_low`, y `<Name>_high.fbx` con sus high. En los nombres, `.` pasa a `_`, porque Painter solo empareja si tras el sufijo viene `_`. Usa los ejes y la escala del perfil, y después restaura los nombres.
- FR-7: los dos botones van en el paso "Shading & UVs" y en el modo normal.
- NFR-1: medir las distancias con un high de 1M de vértices cuesta menos de 1 s.

| AC | Requisito | Dado / cuando / entonces |
|---|---|---|
| 1 | FR-1 | `Box` se empareja con `Box_high`, `Box_high_bolts` y `Box_high.001`, pero no con `Box_highlight` ni con `Box_HIGH`. `Crate_low` se empareja con `Crate_high` |
| 2 | FR-2 | Un high con ngons y sin material no da ningún resultado al validar. Export escribe el asset sin el high. Prep y Generate LODs no lo tocan |
| 3 | FR-3 | Un high biselado y subdividido, 3 cm más arriba que el low: la extrusión cubre los 3 cm sin pasar de 5, y el rayo llega a la parte de abajo, que queda por dentro |
| 4 | FR-4 | Un low cubo plano con un high cubo plano 2 cm por fuera: la normal map es plana (0,5; 0,5; 1) en cada píxel de isla. Con el high biselado, los píxeles del borde se inclinan, y el verde de Unreal es 1 − el de Unity. El PNG está en disco con el tamaño del perfil. Los materiales no tienen nodos de más, y el motor y las muestras vuelven a ser los de antes |
| 5 | FR-5 | Tras hornear, la pila acaba en Triangulate → Weighted Normal, y hornear otra vez no añade otro Triangulate |
| 6 | FR-6 | Dos FBX. Al reimportarlos, los nombres son `Box_low`, `Box_high`, `Box_high_bolts` y `Box_high_001`, y los de la escena siguen como estaban |
| 7 | FR-7 | Los operadores se registran y se ejecutan desde `bpy.ops` |
| 8 | NFR-1 | `ray_distances` con un high de 1M de vértices tarda menos de 1 s |

Casos límite: un asset sin high se salta y la línea lo dice. Si al low le faltan UVs o tiene un slot sin material, la línea lo dice y no se hornea nada. Sin nada seleccionado, se cancela. Con el .blend sin guardar y `bake.path` relativo, se cancela (como el export).

Fuera de alcance: AO, curvatura e ID (Painter y Marmoset los hornean con los pares exportados), conectar la normal map al material, un cage editable (`cage_extrusion` infla el low por dentro de Blender, sin crear ningún objeto) y una textura por material (es una imagen por low, para todos sus materiales).

### Notas de la segunda parte, útiles para retomar

Código: `operations/bake.py` (`ray_distances`, `bake_normals`, `add_triangulate`), `operators/bake.py` (Bake Normals), `ASSET_VALIDATOR_OT_export_bake_pairs` y `_renamed` en `operators/export.py`, `high_owner`/`bake_base`/`highs_of` en `core/roles.py`, `check_bake_pairs` en `checks/naming.py` y la sección `bake` de `config/default.json` (y `normal_g` en `engines/unreal.json`). Tests: `tests/check_bake.py`, 32 tests (39 tras la revisión del 2026-11-03). Se comprobó mutando el código que fallan sin `uv_layer` (con la capa de lightmap activa, se horneaba en UV1) y sin el cambio de `.` a `_` en los nombres.

- **API de 5.2, comprobada antes del código**:
  - `object.bake` funciona sin interfaz, con `temp_override` (`selected_objects` y `active_object`), aunque el high esté oculto con `hide_set`.
  - `uv_layer` elige la capa de UV en la que se hornea.
  - `cage_extrusion` no deja costuras en las aristas duras: un cubo plano horneado desde un cubo plano 2 cm más grande sale plano en cada píxel.
  - Un Triangulate añadido con `modifiers.new` queda delante de un Weighted Normal fijado con `use_pin_to_last`.
  - Con un low smooth y un high plano, la normal map sale con degradados, y es correcto: compensa el sombreado suave del low.
- **Escena real** (`Addon_Test.blend`, el capó del Audi, 106k caras, con sus LOD1 de 64k y LOD3 de 18k como lows; sin guardar):
  - El primer intento horneó basura con un cage de 8,3 m en un coche de 5,45 m. La medición era correcta: el usuario tiene los LODs en fila, a −2,8, −5,3 y −7,7 m en X, así que el high no estaba encima de ningún low (mediana de 0,8 a 1,5 m). De ahí la comprobación de FR-3: ahora el par se rechaza con la distancia y el porcentaje.
  - Con el LOD encima del original: cage de 5 cm (LOD1) y 11 cm (LOD3), y rayo de 10 y 23 cm. Cada bake tarda unos 5 s a 2048 px. `ray_distances` tarda 0,14 s con 154k vértices de high.
  - La normal map llena la textura, pero mezclada, porque las UVs del coche son de tiling y se solapan (`check_uvs` ya lo avisa). Con este asset no se puede juzgar la calidad del bake. Falta probarlo con un par high/low de verdad, hecho para hornear.
- **`check_scene.py` falla con la escena actual, y no por el bake helper**. El 2026-10-29 a las 21:14 el usuario metió en `Addon_Test.blend` la Rank-3 Police Unit (`test_assets/rank-3-police-unit`): 53 mallas y 3,4M de caras. La malla más grande es `suit_zipper` (1,46M de caras, de 34k a 92k islas UV). Fallan:
  - Auto Unwrap (172 s), Prep (232 s) y las islas colapsadas (6,4 %): es lo ya anotado del escaneo de 564k caras, sin decidir.
  - Set Texel Density: 2110 px/m no caben en 4096.
  - La validación completa tardó 1.790 s en `check_scene`, pero repetida sola, con todas las mallas en una llamada, tarda **309 s** (289 s sumando los checks uno a uno). Aquella vuelta compitió por la CPU, seguramente con el Blender del usuario, que estaba abierto con la escena. Aun así, 309 s se pasan del límite lineal de 258 s, y es el primer asset real que pide acelerar la validación (ver **Línea base**).
  - Medido check a check y malla a malla, la suma es de unos 292 s. El 80 % se va en los checks de UV: `check_uvs` tarda 138 s, de los que **131 s son una sola malla** (`suit_zipper_suit_zipper_Cube.001`, 1,46M de caras y 34k islas; en `tests/bench.py`, 1M de triángulos tardan 5,4 s), y `check_uv_layout` tarda 114 s (48 s en esa misma malla). Les siguen `check_normals` (16 s) y `check_shading` (14 s), y el resto suma menos de 11 s. El siguiente paso es perfilar el solape de UVs (`check_uvs`) en esa malla: algo crece más que lineal con las islas o con el tamaño de su rejilla.
  - Sospecha, sin perfilar: `_any_triangles_overlap` (`operations/uvs.py`) da una pasada sobre todo el array por cada vuelta del bucle `for gap`, y da tantas vueltas como triángulos tenga la celda más llena. La rejilla cubre los límites de todas las UVs, y esa malla tiene 619 islas fuera de 0–1, así que casi todos los triángulos caerían en pocas celdas: el coste sería (triángulos de la celda más llena × total). Si es eso, la rejilla debería ajustarse a donde están los triángulos (percentiles o una rejilla por isla), no a los extremos.
  - `--jobs` en el CLI no lo arregla: esa malla está en un solo fichero.
- **Solape de UVs con islas lejanas, arreglado** (2026-11-03, en un equipo sin `Addon_Test.blend`, así que se reprodujo la sospecha con una malla sintética). Una rejilla de 180k triángulos limpia en 0–1 tarda 0,64 s. Con solo 10 de sus quads movidos a u, v = 200, pasó de 4 min y hubo que matarlo. La sospecha era correcta: la rejilla se extiende hasta la isla lejana y casi todo cae en una celda, que se prueba por pares.
  - Arreglo en `_any_triangles_overlap`. Si la celda más llena pasa de `_CROWDED` (64; una rejilla uniforme no llega a 32), se dan `_CROWDED_ROUNDS` (8) vueltas por si hay un solape a mano y luego se parte el conjunto por la mitad de su lado más largo, cada mitad con su rejilla. Un triángulo que cruza la mitad va a las dos. No se parte si más de un cuarto cruzan (triángulos grandes), y entonces sigue la rejilla. Además, el bucle de huecos ya no recorre el array entero en cada vuelta, solo las entradas que siguen en la misma celda.
  - Se probaron otros dos criterios, y empeoraban algo medible. Partir por pares por triángulo (> 16) partía también la esfera del bench, que es uniforme: 114 cortes, y de 5,0 a 9,2 s. Partir de entrada, sin las 8 vueltas, hacía el doble de lentas las carrocerías del Audi, que tienen solapes de tiling (0,6 → 1,2 s). Esperar 64 vueltas antes de partir dejaba el caso de 980k con islas lejanas en 10,9 s, frente a 6,1 s con 8.
  - Resultado (mismo equipo): rejilla de 980k con 10 o 1.000 quads lejos, de colgarse a 6,1 s; limpia, 4,1 s, igual que antes; esfera de 1M, igual (4,8 s). En `BlenderSuitTest_01.blend` (25 mallas, 2,6M caras), los veredictos son idénticos malla a malla, y el total pasa de 28,7 a 28,2 s. En el Makarov, idénticos también.
  - Tests en `check_regressions.py`: la rejilla de 12,8k triángulos con 10 quads lejos (unos 8 s sin cortes, 0,09 s con ellos), y 27 sopas de triángulos comparadas con la respuesta por fuerza bruta (todos los pares), forzando los cortes. Los dos fallan con su mutación (sin cortes; cortes que pierden los triángulos que cruzan). Fuera de los tests, 360 sopas con 56k cortes dieron la misma respuesta que la fuerza bruta.
  - **Falta medirlo en `suit_zipper`**, en el equipo que tiene `Addon_Test.blend`: los 131 s de `check_uvs` deberían bajar a unos pocos segundos. `check_uv_layout` (48 s en esa malla) no se ha tocado.

- **Revisión** (2026-11-03, `/ponytail-review` y `/code-review` de `f82c897..fe81718`). Cada hallazgo se comprobó en Blender antes de tocar nada. Los arreglados tienen su test, y se comprobó con 10 mutaciones que cada test falla si se quita su arreglo:
  - **Los ajustes del panel Bake de la escena se colaban** en `object.bake`. Lo que no se le pasa, lo coge de `scene.render.bake`. Medido: con `normal_r = NEG_X` en la escena, el mapa salía distinto (0,88), y con un cage activado, el bake fallaba. Ahora se pasan `use_cage=False`, `normal_r`, `normal_b` y `margin_type` (`ADJACENT_FACES`, el de fábrica).
  - **Un `RuntimeError` del bake cortaba el bucle** de Bake Normals con un traceback. Pasa, por ejemplo, con un low que tiene desactivado el render. Ahora sale como `ValueError` en la línea de ese low, los demás siguen, y se quita el Triangulate que se acababa de añadir: un operador cancelado no deja paso de undo. La dependencia circular que proponía la revisión (la normal map conectada al material) no falla en 5.2.
  - `check_bake_pairs` buscaba el low con otra regla que `highs_of`: con `Pair_low_high`, daba por bueno `Pair_low`, pero el bake no los emparejaba. Además, avisa cuando un high tiene dos lows (`Twin` y `Twin_low`), y Bake Normals solo hornea uno de los dos: antes, el segundo pisaba `Twin_N.png` y decía que había horneado los dos. Export Bake Pairs ya fallaba con un mensaje claro ("that name is taken").
  - Con el Triangulate del bake, `check_shading` perdía el botón *Select* de las aristas duras fuera de costura: la malla evaluada tiene más aristas. Como Triangulate no cambia los vértices, ahora las aristas se emparejan por sus dos vértices (`_original_edges`). Lo otro que decía la revisión, que el Triangulate crea diagonales duras nuevas, se midió y no pasa (`keep_custom_normals`).
  - `--jobs`: un Blender por job, no por fichero (ver B4).
  - Muestreo de 100k vértices en `ray_distances`: una punta de pocos vértices en un high de millones puede quedarse fuera, y el cage saldría corto. Se queda así por NFR-1, con un `ponytail:`.
  - Descartados, porque es lo que pedían los criterios: `Fence_high_02` junto a `Fence` es un high, porque así empareja Painter (FR-1), y Clean Topology/Retopologize trabajan con highs (FR-2). Del `/ponytail-review` no se aplicó nada: juntar `_world_bvh` y `_world_vertices` obligaba a triangular cada high (más lento en highs de millones de caras), la guarda de "guarda el .blend" compartida ocupaba más líneas que las tres copias, y las filas del panel se repiten desde antes de este cambio (tocarlas pide revisar la interfaz).

### Auto Unwrap y Prep modales (2026-11-04)

- `auto_unwrap_steps` y `prep_mesh_steps` son generadores: ceden el control antes de cada paso caro (marcar seams, cada ronda de `uv.unwrap`, enderezar, pack, texel density). `auto_unwrap()` y `prep_mesh()` los recorren enteros con `finish`.
- El bucle modal de Retopologize pasó a un mixin, `Steps` (`operators/__init__.py`), que usan los tres operadores: `invoke` es modal con estado en la barra y Esc, y `execute` (scripts, panel de redo) lo hace todo seguido. `Steps._each` recorre los objetos y junta las líneas.
- **Esc no deja mallas a medias**. `restorable` copia la malla antes de empezar (`mesh.copy()` comparte los datos hasta que se escriben: 0,00 s con 564k caras). Si se para a mitad, con Esc o con una excepción, vuelve a poner la copia con `user_remap`, así que los duplicados enlazados siguen compartiéndola, y le devuelve el nombre. Test en `check_hard_surface.py` (cerrar los pasos a mitad de Prep). Falla si se quita la restauración.
- Probado con interfaz (`--enable-event-simulate`, con Esc simulado) en `BlenderSuitTest_01.blend`, sin guardarla. Auto Unwrap en la carrocería del Audi (190k caras) se para y la malla vuelve idéntica (nombre, UV0, seams, sharp, usuarios). Prep llega al final en modal con el ángulo de `invoke` (30°), y Retopologize sigue funcionando con el mixin. El escaneo `geo_dead_LOD2` es un LOD por el nombre, así que las herramientas UV se lo saltan.
- Esc se lee entre pasos. Una sola llamada a `uv.unwrap` del escaneo de 564k caras sigue bloqueando unos 2 minutos.
- **`uv.pack_islands` con CONCAVE tarda segundos en mallas pequeñas**: 2,8 s en un cilindro de 8 lados, con o sin interfaz (CONVEX, 5,9 s; AABB, 0,00 s). Se midió AABB en el Makarov y en la carrocería del Audi tras un Auto Unwrap: es instantáneo, pero llena mucho peor (Makarov_base, de 0,65 a 0,37 del espacio UV; Floor, de 0,20 a 0,13), y CONCAVE cuesta de 0,1 a 3 s por llamada. Se queda CONCAVE. Con `temp_override(window=None)`, `pack_islands` se bloquea en 5.2.

### Bugs conocidos de Prep (2026-11-04)

Medidos en el Makarov (todas las piezas traen normales custom del FBX), en memoria y sin guardar. Los tres se confirmaron. Los scripts de medida no se guardaron: el ancho real del bisel es el área de sus caras (con `bevel.material` en un slot nuevo) entre la longitud biselada, y los cruces son pares de triángulos de la malla evaluada que se solapan sin compartir vértice (`BVHTree.overlap`).

- **`shade_smooth_by_angle` mide las normales custom, no la geometría.** A 30° marcaba 108 sharp en el silenciador, frente a 400 sin normales custom, y 25 frente a 307 en el martillo. Además marcaba aristas planas: 279 de las 940 sharp de la base tenían menos de 1°. Eso era también el segundo bug (se biselaban aristas sharp en zonas planas). Ahora Prep marca con `_bent_edges` (numpy, el ángulo entre las dos caras de cada arista; una arista con 3 o más caras es sharp, como en Blender) y `Mesh.shade_smooth()`. Sin normales custom, da exactamente lo mismo que el operador en las 11 mallas de la escena, a 30° y a 60°. Las sharp planas biseladas bajan de 279 a 1 en la base y de 222 a 0 en el cargador. Las normales custom se conservan, como antes.
- **El *Clamp Overlap* del Bevel es global**: recorta toda la malla al ancho que cabe en su arista más corta. El bisel del cargador se quedaba en el 0 % del ancho pedido, el de la corredera en el 12 % y el de Floor en el 7 %. Sin el clamp, el bisel sale entero, pero se cruza consigo mismo: de 268 cruces a 6.944 en el cargador. Ahora el clamp va por arista. Su bevel weight (que escala el ancho) es como mucho `_EDGE_CLAMP` (0,25) por la arista más corta de sus dos vértices, contando la propia, entre el ancho, y el clamp global va desactivado. Con 0,25 quedan los mismos cruces que con el clamp global (cargador 448 frente a 589, corredera 365 frente a 385, base 524 frente a 576), con biseles de 2 a 40 veces más anchos. Con 0,5 los cruces se doblaban. Con los weights y el clamp global activado, el cargador volvía al 4 %, así que el clamp global tiene que ir apagado. Una versión que excluía la propia arista daba lo mismo con más código.
- Tests en `check_hard_surface.py`: un cubo triangulado con normales custom suaves (12 sharp, ninguna diagonal plana), un cubo grande con otro de 1 cm en la misma malla (el bisel del grande no encoge y el del pequeño no se sale de su caja) y el clamp global apagado. Este último comprueba el ajuste, no el efecto: no se encontró ninguna geometría sintética en la que el clamp global recorte con los weights puestos (se probaron triángulos agudos, caras con poke y un cubo triangulado con ruido). Cada test falla al quitar su arreglo.
- Queda: el ancho por defecto (0,5 % de la dimensión mayor) y el clamp por arista se calculan una vez. Si se ensancha el Bevel después, los biseles de las aristas cortas crecen en proporción y pueden cruzarse. Floor (no es hard surface) sigue con biseles del 10 %, porque sus triángulos son diminutos.

### Pruebas con BlenderSuitTest_01 y showroom (2026-11-04, rama `feature/showroom`)

Cada herramienta, con variaciones, sobre copias de cinco modelos de `C:\Users\hugom\Documents\Assets\BlenderSuitTest_01.blend`, nunca guardada: la carrocería del Audi (190k caras), el Gipsy Danger (16,6k caras, 924 piezas), `LP_stiffener.001` (7,7k), `LP_stiffener.002` (178) y el escaneo `geo_dead_LOD2` (564k). Las variantes: Fix All, Clean Topology, Retopologize con dos ratios, Generate LODs, Auto Unwrap con y sin enderezar, Set Texel Density 256/1024, Prep, Prep + Bevel 2, Prep 60° + Bevel 3, Prep 15° y Bake Normals (el high es el original y el low el Retopologize más bajo, preparado). Cada variante se valida por separado, sin `check_location`. Hay renders con interfaz de cada una: sólido con malla, primer plano, checker sobre UV0, heatmaps y layout de UV0. Informe con las láminas (privado): https://claude.ai/artifact/WP3tTJDpno2HW9JGnsdCfx. Los scripts (`process.py`, `render.py`, `make_sheets.py`, `make_report.py`) quedaron en el scratchpad de la sesión, no en el repo.

- **Arreglado: validar `LP_stiffener.001` cerraba Blender** (access violation en `bmesh.from_mesh`, y también en Clean Topology). El informe de `Mesh.validate(verbose=True)`, capturado redirigiendo el descriptor 1 a un fichero con `os.dup2`, decía: "Selection element (1, 228688) has invalid index". Es el historial de selección de Edit Mode guardado en la malla, que apunta fuera de una malla de 7.729 caras. Desde Python no se ve, porque atributos, offsets y geometría coinciden con la copia validada. El crash no es determinista: a veces aparece a la primera lectura y a veces tras varias.
  - `run_validation` pasa primero `validate()` por una copia de cada malla (`_invalid_mesh`). Si encuentra algo que reparar, la malla sale como ERROR `mesh_data`, con un Fix que valida el original, y los demás checks se la saltan hasta que se repare. Coste: 0,47 s para las 25 mallas de la escena (2,6M caras).
  - Las herramientas (Prep, Auto Unwrap, Set Texel Density, Clean Topology, Retopologize, Generate LODs y el Select de los resultados) reparan antes de leer, con `repair_invalid` en `core/mesh_utils.py`, y lo avisan con `report`.
  - Tests en `check_validation.py`: una malla con caras duplicadas hace de corrupta, porque la API no puede escribir un historial de selección roto. Y un espía comprueba que las seis herramientas reparan, porque bmesh ya descarta las caras duplicadas por sí solo y la malla no lo distingue. Cada test falla al quitar su arreglo.
- **Arreglado: Generate LODs dejaba caras duplicadas** (1.182 en los LODs del Gipsy y 29 en los del Audi; también estaba en el `_LOD3` de la escena). Ahora `validate()` va tras el colapso. Test en `check_lods.py` con un origen que ya trae duplicados (falla sin el arreglo).
- **Arreglado: Retopologize decía "QuadriFlow failed on a clean manifold mesh"** cuando todas las piezas tienen menos de 200 caras y QuadriFlow ni se ejecuta. Test en `check_topology.py`.
- **Revisión** (`/ponytail-review` sin recortes, `/code-review` con 10 hallazgos, 8 arreglados):
  - Show reparaba la selección antes de seleccionar el objeto del resultado, así que no reparaba ese objeto.
  - Fix All necesitaba un segundo clic tras reparar una malla. Ahora da una segunda pasada solo a los fixes de los objetos reparados.
  - Una malla instanciada se validaba una vez por objeto en lugar de una vez por malla.
  - Retopologize sin caras decía "All 0 loose parts".
  - El espía del test no se restauraba.
  - El test de LODs dejaba copias huérfanas.
  - Dos fallos del showroom: el umbral de Clean Topology no podía fallar, y la etiqueta decía 164k triángulos cuando son 82k.
  - Cada test nuevo falla sin su arreglo.
  - **No arreglados, a propósito:**
    - Mientras una malla espera su reparación, sus vecinos pueden recibir avisos falsos. Por ejemplo, un hijo avisa de que su padre "no se exporta con él". Desaparecen al reparar.
    - El error `mesh_data` sale en todos los pasos guiados, aunque el paso no lo incluya. Es a propósito: si un paso se aprueba sobre un objeto que nadie ha comprobado, la aprobación no vale nada.
- **Abiertos, sin decidir** (detalle e imágenes en el informe):
  1. Retopologize apenas reduce los modelos de muchas piezas: conserva las de menos de 200 caras, y el ratio se aplica al resto. Gipsy: 16.663 → 16.374 (ratio 0,5) y 16.307 (0,25). Audi: 0,5 da el 69 %. Escaneo: 0,1 da el 99,8 %.
     - **Decidido (2026-11-04): avisar, no reducir las piezas pequeñas**, porque saldrían en triángulos, no en quads. Si se conservó alguna pieza y el resultado queda por encima de 1,5 veces el ratio pedido, la nota lo dice: Gipsy al 25 %, "only down to 98% of the triangles, not the 25% asked". Test en `check_topology.py`: una esfera con 60 cubos pequeños avisa, una esfera sola no; falla sin el arreglo.
  2. ~~Retopologize deja caras degeneradas (ERROR `geometry_cleanup`, bloquea el export) en el Gipsy al 25 % y en el stiffener.~~ **Arreglado** (sin commitear):
     - Una prueba por etapas encontró de dónde salen: 7 de la salida de QuadriFlow y 1 del remuestreo en el stiffener, y 2 caras en el umbral al ensamblar el Gipsy.
     - Ahora `fix_degenerate_faces` pasa por el resultado antes de transferir las normales. Usa la distancia de fusión en unidades locales del objeto, las costuras se marcan después de la reparación y la nota del operador cuenta las caras quitadas. Stiffener al 50 % y al 25 % y Gipsy al 25 %: 0 caras degeneradas (se quitaron 8, 7 y 2).
     - En la revisión quedó aceptado, sin arreglar, que el umbral de área sea el de por defecto: `retopologize` no recibe la configuración. Si se sube `degenerate_face_area_epsilon`, el check puede seguir marcando caras.
     - El test aplasta una cara de la salida real de QuadriFlow y falla sin el arreglo.
     - Sigue abierto: Retopologize arruga una pieza de detalle del stiffener. Es calidad de QuadriFlow, no un error del check.
  3. El bake del Audi sale a parches, con zonas invertidas en la normal map. Probablemente es la geometría interior del coche; falta un par high/low hecho para hornear.
  4. ~~Los LODs del Gipsy conservan 4 caras al revés (ERROR `normals`).~~ **Arreglado** (sin commitear). El fallo no estaba en los LODs, sino en `wrong_way_faces`, así que afectaba a cualquier asset:
     - Las 4 o 5 caras son triángulos colgados de una arista de 3 caras, con sus otras dos aristas en el borde.
     - `recalc_face_normals` los voltea tanto si están de un lado como del otro. Por eso salían como erróneos en ambas orientaciones, y Fix los volteaba en cada pasada sin dejarlos nunca bien.
     - Con un cubo y una solapa no se reproduce; con una pieza real de 5 caras extraída del LOD, sí.
     - Ahora la clasificación se repite sobre una copia con esas caras volteadas, hasta que las caras que voltea Fix sean exactamente las probadas. Las que siguen saliendo erróneas no tienen un lado bueno: su arista de 3 caras pasa al WARNING de aristas "que no se pueden orientar" del mismo `check_normals`, así que se siguen viendo aunque `check_manifold` esté desactivado.
     - Es lo mismo que el 1→3 de Fix All en el escaneo, cuya única cara "al revés" era una de estas solapas.
     - Coste: de 4 a 8 s en el escaneo de 564k caras, solo cuando hay caras al revés; sin ellas no cambia (1,07 s frente a 1,08 s en una esfera de 130k). Marcado con `ponytail:`.
     - Test en `check_regressions.py` con esa pieza, en las dos orientaciones; falla sin el arreglo.
  5. El LOD3 arruga las formas cilíndricas: un barril de 48 lados (unos 800 triángulos) en el showroom. No hay mínimo de triángulos por nivel. Encaja con "LOD quitando loops" de la fase 4.
     - **Decidido (2026-11-04): avisar de la desviación.** El arreglo de fondo sigue siendo el de la fase 4. Generate LODs mide cuánto se aleja cada LOD del original: el percentil 99 de las distancias en los dos sentidos, en espacio de mundo (cuenta la escala del objeto) y en % de la diagonal. Por encima de `lod.max_deviation` (1 % por defecto), la línea del LOD lo dice, el LOD se marca con `asset_validator_lod_stray` y el operador da un WARNING con sus nombres.
     - Calibración del umbral: los LODs que se ven bien (estatua, stiffener, Audi, LOD1 del Gipsy) quedan en ≤ 0,45 %. Arrugados o rotos: el LOD3 del barril, 1,3 %; el LOD2 y el LOD3 del Gipsy, 1,2 % y 4,4 %; los cilindros de 16 y 32 lados, de 1,4 % a 27 %; un cubo que el LOD1 dejaba en 6 caras, 31 %.
     - Coste, dentro del ruido: Audi 11-12 s con y sin la medición; Gipsy +0,1 a 0,2 s sobre 1,5 s. Se muestrean como máximo 20k vértices por malla.
     - Límites que quedan: con el percentil 99, un detalle que pierda menos del 1 % de los vértices (los retrovisores de un coche) no cuenta; y la diagonal deja mucho margen a una pieza larga y fina.
     - Tests en `check_lods.py`: una malla contra sí misma da 0, y un cilindro de 16 lados avisa mientras una esfera densa no; fallan sin el arreglo.
  6. ~~Auto Unwrap con *Straighten Quad Islands* tarda 78,5 s frente a 2,9 s en el Gipsy.~~ **Arreglado:** cada isla deseleccionaba la malla entera y llamaba dos veces a `update_edit_mesh`, que es O(n) por isla. Ahora se selecciona una isla cada vez sin tocar el resto, y se saltan las de una sola cara (4.974 de las 5.609 del Gipsy), que son su propia referencia.
     - Gipsy: 85 s → 4,4 s. Stiffener: 2,45 s → 0,85 s. UV idénticas a las de antes en los dos.
     - Test de tiempo en `check_uvs.py` (1.600 islas junto a una pieza de 20k caras): 0,4 s con el arreglo, 5,6 s sin él.
  7. Menores:
     - ~~Prep + Bevel pasa el presupuesto de triángulos sin avisar.~~ **Arreglado:** la nota de Prep lo dice cuando es el Bevel el que lo cruza (de cuántos a cuántos), y no cuando la malla ya venía pasada, porque ahí menos segmentos no lo arreglan.
     - ~~Copias de LODs.~~ **Arreglado, y era peor de lo que parecía:** regenerar los LODs borraba también las copias que hubiera hecho el usuario. Ahora el origen guarda un puntero a cada LOD que generó (`asset_validator_lod_object_<n>`); al copiar, Blender no lo reasigna a la copia. `roles.is_lod` lo comprueba, y lo usan el rol, `lods_of`, el export, el Fix de polycount y Clean Topology. Una copia pasa a ser un asset normal. Un LOD renombrado sigue siendo LOD, como ya esperaba el test del export. Los LODs de antes de este cambio, sin puntero, siguen contando como LODs.
     - ~~Fix All en el escaneo deja 3 caras al revés donde había 1~~ (arreglado con el 4; queda comprobar el Floor del Makarov, que puede ser lo mismo).
- **Showroom** (`demo/build_showroom.py`, ver README): genera `demo/Showroom.blend` por código, en unos 20 s. Tiene 17 estaciones de checks (incluida la nueva `mesh_data`) y 6 de herramientas, y se comprueba sola al final. Escribe junto al .blend un `asset_validator.json` que desactiva `check_location`. En el escaneo se ve que, en `-b`, `matrix_world` no sigue a `location` hasta un `view_layer.update()`; la cámara se apunta después de llamarlo.

### Siguiente paso (para retomar, 2026-11-03)

1. ~~`/ponytail-review` y `/code-review` del bake helper y de `--jobs`.~~ Hecho el 2026-11-03 (ver arriba). Lo arreglado en esa revisión y el solape de UVs se revisaron el 2026-11-04 sin hallazgos nuevos (el reparto de `--jobs` con más jobs que ficheros, `check_bake_pairs` frente a `highs_of` con `low_suffix` vacío, la recursión de `_halves`), y se commitearon.
2. ~~Arreglar `check_uvs` en `suit_zipper`.~~ Arreglado el 2026-11-03 con una reproducción sintética (ver "Solape de UVs con islas lejanas"). Falta, en el equipo con `Addon_Test.blend`: medir `check_uvs` en `suit_zipper_suit_zipper_Cube.001` (eran 131 s), volver a medir la validación completa de la escena (309 s, con el Blender del usuario cerrado) y actualizar la **Línea base**. Si sigue pasando del límite lineal, lo siguiente es `check_uv_layout` (48 s en esa malla).
3. ~~Decidir qué hacer con Auto Unwrap/Prep en mallas enormes.~~ Decidido el 2026-11-04: modal con Esc (ver "Auto Unwrap y Prep modales"). `check_scene.py` sigue fallando NFR-1 con mallas enormes, porque el modal no las acelera. Queda decidir si `check_scene` debe probar las herramientas en la malla más grande o en una de tamaño "de juego".
4. Que el usuario pruebe Bake Normals y Export Bake Pairs con interfaz (zip reconstruido el 2026-11-03), con un par high/low de verdad y UV0 sin solapes.
5. ~~Problemas conocidos de Hard Surface Prep, citados en el mensaje del commit `f82c897`.~~ Comprobados y arreglados el 2026-11-04 (ver "Bugs conocidos de Prep").
6. El resto de la fase 2: el crease para SubD (crear el `_high` desde el low) y las trim sheets.

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
- [x] **Bake helper** (segunda parte, arriba):
  - Empareja `_high` y `_low` por nombre y mide el cage (`cage_extrusion`) y la distancia de rayo a partir de las mallas.
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
- [ ] **Substance Painter y Marmoset** (tampoco están instalados): ¿"Match by Mesh Name" empareja los `X_low`/`X_high` de Export Bake Pairs por el nombre del objeto del FBX? La regla de los sufijos sale de la documentación de Adobe, y la de Marmoset, de herramientas de terceros que dicen seguirla. ¿Las normal maps de Bake Normals se ven sin costuras en Unreal (`NEG_Y`) y en Unity (`POS_Y`) con el FBX triangulado?

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

Con los cortes en el solape de UVs (2026-11-03, `tests/bench.py`, en el equipo de `C:\Users\hugom\Documents\Assets`, que va más lento que el de la tabla anterior), una vuelta con HEAD y otra con el cambio, seguidas:

| Triángulos | Total (HEAD → ahora) | check_uvs | check_uv_layout | check_shading | check_normals |
|---|---|---|---|---|---|
| 16k | 0,48 → 0,51 s | 0,05 → 0,06 s | 0,26 → 0,27 s | 0,09 → 0,09 s | 0,05 → 0,06 s |
| 261k | 4,5 → 4,9 s | 1,01 → 1,07 s | 1,50 → 1,54 s | 0,62 → 0,59 s | 0,95 → 1,29 s |
| 1M | 18,8 → 19,1 s | 4,73 → 5,32 s | 6,16 → 6,60 s | 2,53 → 2,55 s | 3,64 → 2,86 s |

El ruido entre vueltas en este equipo llega al 25 %: `check_normals`, que no cambió, va de 3,64 a 2,86 s. `uv_overlap` sola, medida aparte en la esfera de 1M, da lo mismo con las dos versiones (4,8-5,0 s).

Lo que más tarda ahora:
- `check_uv_layout`: `uv_stats` y `face_islands`, que en el escaneo de 564k caras tardaban unos 5-6 s por llamada.
- `check_normals`: `loose_parts` es un recorrido en Python. Se aceleraría con una union-find en numpy.
- `check_shading`: el `np.unique` por filas. Se aceleraría con una vista `void`.
- ~~`check_uvs` en mallas enormes.~~ Arreglado el caso de las islas lejanas (2026-11-03); falta medirlo en `suit_zipper`.

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
