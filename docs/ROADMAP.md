# Roadmap: de Asset Validator a suite para artistas de videojuegos

Documento para retomar el trabajo desde cualquier chat o dispositivo. Al empezar una sesión nueva, pide que se lea este fichero entero y el `README.md`. Al cerrar una tarea, actualiza la tabla **Estado** y marca sus casillas.

## Cómo retomar

1. Mira en **Estado** la fase en curso y su rama: `git switch <rama>`.
2. Tests: `.\tests\run.ps1` (PowerShell). Ejecuta cada `tests/check_*.py` dentro de Blender, sin interfaz, y deja la salida en `tests/_out/`. `.\tests\run.ps1 check_lods` ejecuta solo uno. Todos tienen que pasar antes de un commit.
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
  - QuadriFlow falla con geometría non-manifold y borra las piezas finas. `operations/topology.py` lo resuelve remallando pieza a pieza y reparando antes (`_repair_for_quadriflow`, `_patch_lost_surface`).

## Dónde está cada cosa

| Ruta | Qué hay |
|---|---|
| `blender_asset_validator/checks/` | Un fichero por área (geometry, integrity, topology, shading, materials, naming, transforms, roles) |
| `blender_asset_validator/operations/` | Lógica que modifica mallas: cleanup, topology (Clean/Retopo), lod, decimate, heatmap |
| `blender_asset_validator/operators/` | Botones (`bpy.types.Operator`) que llaman a operations y engine |
| `blender_asset_validator/core/` | `engine` (carga de config y validación), `roles`, `registry`, `result`, `state`, `steps`, `mesh_utils` |
| `blender_asset_validator/config/` | `default.json` ← `engines/<motor>.json` ← `presets/<preset>.json` ← `asset_validator.json` junto al .blend |
| `blender_asset_validator/report/` | Informe de consola, JSON y HTML |
| `blender_asset_validator/cli.py` | Validación por lotes sin interfaz (CI) |
| `tests/` | `check_*.py` (tests), `run.ps1` (runner), `bench.py` (velocidad) |

## Estado

| Fase | Rama | Estado |
|---|---|---|
| 0 Cimientos | `feature/phase-0-foundations` | hecha, revisada, testeada (234 tests) y commiteada. Falta: que el usuario pruebe el último zip en su escena y verificar en motor |
| 1 UVs y texel density | — | pendiente |
| 2 Hard surface | — | pendiente |
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
- **Siguiente paso**: la fase 1. Los puntos lentos que quedan (ver Línea base) solo valen la pena si un asset real lo pide.

## Fase 1: UVs y texel density

- [ ] Check de texel density por isla contra el objetivo del perfil (px/m, ±20 %). Herramienta para medirla, fijarla y copiarla entre objetos (`uv.average_islands_scale` y escalado hasta el objetivo).
- [ ] Check de estiramiento por isla (distorsión de área y ángulo).
- [ ] Separación entre islas en píxeles a la resolución objetivo (por ejemplo ≥8 px a 2K).
- [ ] Islas fuera de 0–1, salvo en materiales tiling o UDIM.
- [ ] Canal de lightmap UV1 sin solapes y dentro de 0–1. Opcional según el motor, porque Unreal y Unity pueden generarlo al importar. Para generarlo: `uv.lightmap_pack` o xatlas (MIT, como wheel).
- [ ] Heatmaps de texel density y de estiramiento.
- [ ] **Auto seams para hard surface**:
  1. Seams en las aristas sharp, en los bordes de material y en los bordes abiertos.
  2. Unwrap: MINIMUM_STRETCH si existe, si no CONFORMAL.
  3. Si una isla estira demasiado, se corta por el camino de mayor curvatura y se repite.
  4. Se prefieren aristas cóncavas u ocultas.
- [ ] Pesos de importancia en el unwrap: `use_weights` con el grupo `uv_importance`, que existe desde 4.3 (comprobarlo antes de usarlo).
- [ ] Enderezar islas de quads (Follow Active Quads).

## Fase 2: hard surface

- [ ] **Hard Surface Prep** en un clic, encadenando operadores nativos:
  1. Smooth by Angle.
  2. Marcar sharp por ángulo (`mesh.set_sharpness_by_angle`).
  3. Seams en las aristas sharp y en los bordes de material.
  4. Unwrap y pack (`uv.pack_islands` con `shape_method="CONCAVE"`).
  5. Texel density.
  6. Modificador Weighted Normal con Keep Sharp.
- [ ] Support loops: bevel en las aristas sharp con N segmentos y `harden_normals` para mid-poly, o crease para SubD.
- [ ] Check de mid-poly: si el perfil lo pide, tiene que haber Weighted Normal.
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

Lo que más tarda ahora:
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
