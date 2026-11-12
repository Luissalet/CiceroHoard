<img src="app-icon.png" width="96" alt="">

# Cicero's Hoard

Espacio de trabajo local que convierte un encargo y unos documentos fuente en una presentación editable, para una persona y un asistente que trabajan juntos. [English](README.md)

## Qué es

Le das a Cicero un objetivo, un público y el material. Propone un esquema, escribe las diapositivas con notas del orador, te deja revisar y aprobar cada una, aplica un tema y exporta el resultado. Todo está disponible como API REST para la interfaz incluida y como herramientas MCP construidas con el mismo código, de modo que no pueden discrepar.

Las fuentes se leen en tu ordenador; al modelo solo van extractos cortos y numerados, a través de Hoard Link, al backend que hayas configurado (uno local por defecto). Sin modelo accesible, el esquema y las diapositivas se construyen desde las fuentes con reglas fijas y el resultado indica `"generator": "fallback"`.

## Qué hace

### Presentaciones, fuentes y diapositivas
- Presentaciones con título, encargo, público, tono, idioma (español o inglés), de 3 a 40 diapositivas y un tema. El estado se deriva: borrador, esquema, revisión o listo (todas las diapositivas aprobadas).
- Fuentes: texto pegado o archivos `.txt`, `.md`, `.pdf`, `.docx` y `.pptx`; los PDF escaneados los lee el servicio de documentos de la familia cuando está en marcha. Las fuentes se numeran y las diapositivas las citan.
- Esquema generado a partir del encargo y de extractos de las fuentes, o escrito a mano.
- Quince diseños (con evidencia, comparación y composición libre) construidos con bloques de texto, imagen, gráfico, diagrama, métrica, tabla y línea de tiempo; cada diapositiva tiene notas del orador.
- Revisión por diapositiva: aprobar, regenerar con comentarios, editar a mano. Cada cambio es una revisión; revertir restaura una revisión antigua como una nueva. Regenerar conserva las aprobadas y reescribe los borradores.
- Duplicar una diapositiva, editar un título, nota o viñeta sin reconstruir el resto, añadir borradores en lotes idempotentes y cambiar una figura existente.
- Importar un `.pptx` a una presentación editable (texto, tablas, gráficos con datos, imágenes, notas) con un diseño y tema de Cicero.
- Títulos que afirman la conclusión: los títulos de etiqueta se señalan y se propone una conclusión a partir del contenido de la propia diapositiva, aplicable por diapositiva o a toda la presentación y reversible hasta las etiquetas.

### Comprobaciones y confianza
- Sin cifras inventadas: el modelo solo puede usar cifras de las fuentes, un gráfico se conserva solo si todos sus valores aparecen en ellas, y `deck_check` lista cada cifra que ninguna fuente contiene (comparando notaciones como `1.234` y `1,5`).
- Ajuste automático del texto en vista previa, HTML y PPTX desde una sola geometría; el texto que no cabe se avisa en vez de recortarse.
- Revisión visual: renderiza cada diapositiva en el navegador y mide objetos fuera de la diapositiva, texto desbordado, solapes, contraste, imágenes que no cargan y títulos ausentes, con un arreglo automático del tamaño mínimo de letra.
- Revisión de diseño con Vitruvius's Hoard: puntúa el aspecto generado de 0 a 100 y sitúa cada hallazgo en su diapositiva.
- Comprobación de fuentes por diapositiva y un banco de pruebas que compara flujos completos de PPTX con un rasterizador común y una rúbrica fija.

### Temas y plantillas
- Siete temas incluidos con contraste de al menos 4,5:1, temas propios desde un sistema de diseño o desde un preajuste de Vitruvius (claro u oscuro, con una sugerencia de «elegir tres para este encargo») y borrado de temas guardados.
- Tus plantillas PPTX: se conservan patrones, diseños, fondos, logotipos y fuentes, con vínculos entre diseños y diapositivas de origen para plantillas poco habituales.
- Numeración y barra de progreso (arriba o abajo), con un apéndice excluido del total.

### Visuales, movimiento y medios
- Visuales tipados: 14 tipos de gráfico, diagramas, métricas y tablas con esquemas versionados; sustituir un bloque conservando los demás; comparar tres composiciones.
- Pasos por clic, animaciones y transiciones nativas de PPTX, rutas interactivas entre diapositivas, bloques de audio y vídeo e importación sin conexión de modelos de escena 3D.
- Integración local con VectorCraft y DesignCraft para figuras vectoriales editables y hojas A4, y figuras de código editable desde Vitruvius.
- Imágenes: sube las tuyas o pide una por diapositiva a Prospero's Hoard.

### Datos y presentación en directo
- Importa CSV, TSV y XLSX como conjuntos inmutables, fíltralos, agrúpalos y ordénalos de forma reproducible, asócialos a gráficos y tablas y enlázalos a fuentes locales o URL que se refrescan como instantáneas.
- Presentación en directo con URL separadas para presentador y público, pasos, pantalla en negro, cronómetro, encuestas al público y presencia de edición compartida; la vista del público nunca muestra las notas del orador.
- Planificación de ensayos con tiempo a partir de las notas del orador y ensayos medidos desde la consola del presentador, comparados con el plan.

### Exportaciones
- PPTX con cuadros de texto reales, notas del orador y gráficos nativos editables (16:9 o el tamaño de la plantilla).
- PDF, una página por diapositiva, renderizado por un Chromium local.
- Un único HTML autónomo con navegación por teclado (sin notas del orador).
- Markdown, con las diapositivas separadas por `---`.

## Uso responsable

- **Cifras.** Una presentación generada es un borrador. La comprobación de números encuentra cifras que no están en las fuentes; no puede saber si una fuente es correcta. Lee las notas y las cifras antes de presentar.
- **Las fuentes se quedan en local.** Los documentos se leen en este ordenador. Al modelo solo se envían extractos cortos y numerados, a través de Hoard Link.
- **Archivos locales.** Añadir un archivo por ruta solo acepta tipos de documento (`.txt`, `.md`, `.pdf`, `.docx`, `.pptx`) y se puede limitar a carpetas con `CICERO_FILE_ROOTS`.
- **Citas.** Un bloque de cita debe reproducir una cita que aparezca en una fuente. La comprobación no verifica citas.
- **Borrados** (una presentación, una diapositiva, una fuente) requieren confirmación explícita, también por MCP.

## Cómo ejecutarlo

Requiere Python 3.11+ y Node.js 22+ solo para recompilar el cliente.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium     # solo para exportar a PDF
python -m cicero_hoard            # http://127.0.0.1:5194
```

El cliente compilado está en `cicero_hoard/static`; `npm install` y `npm run build` solo hacen falta para cambiar la interfaz. `python scripts/dev.py` arranca la API y Vite juntos; `python scripts/launch.py` arranca la app y abre el navegador.

| Variable | Por defecto | Significado |
| --- | --- | --- |
| `CICERO_PORT` / `PORT` | `5194` | Puerto; con `PORT_STRICT=1` la app falla en vez de moverse |
| `CICERO_DATA_DIR` | `./data` | Base de datos, `assets/`, `exports/`, `mcp-token`, `url`, `backend.json` |
| `CICERO_ALLOWED_HOSTS` | solo local | Nombres de host extra que acepta el servidor |
| `CICERO_FILE_ROOTS` | vacío | Carpetas de las que pueden venir las fuentes de archivos locales |
| `CICERO_IMAGE_STUDIO_URL` | descubierta | Dirección del estudio de imágenes |
| `CICERO_IMAGE_TIMEOUT` | `600` | Segundos de espera por cada render de imagen |
| `CICERO_PARALLEL_SLIDES` | `3` | Diapositivas escritas a la vez tras la primera (1-8) |
| `CICERO_SLIDE_EFFORT` | `low` | Esfuerzo de razonamiento por diapositiva y reescritura (`off`, `low`, `medium`, `high`) |
| `CICERO_VECTORCRAFT_CLI`, `CICERO_DESIGNCRAFT_CLI` | sin definir | Rutas de las apps opcionales de vectores y hojas |

El modelo viene de Hoard Link (`data/backend.json` o las variables de entorno de Hoard) y también se puede elegir en Ajustes.

Límites: la exportación a PDF necesita Chromium (o un Edge o Chrome del sistema); sin él, exportar `pdf` falla con `pdf_unavailable` y los demás formatos siguen funcionando. La vista previa y el HTML con plantilla necesitan un motor local de diapositivas de oficina en Windows, o informan del mismo código. Las fuentes tipográficas son las del tema; una máquina que no las tenga sustituye otra. El ajuste del texto es una estimación por anchos de carácter. Los PDF escaneados sin OCR se rechazan. Las notas del orador nunca van en el HTML exportado.

## Conexión con Faustus y el Hoard Hub

- `faustus-plugin.json` describe el plugin. `mcp_server.py` es el puente stdio común de Hoard Link: lee `data/mcp-token`, pide la lista de herramientas a la app en marcha, reenvía cada llamada y arranca la app si no está en marcha (`CICERO_BRIDGE_AUTOSTART=0` lo desactiva). Regístralo con `CICERO_URL` (por defecto `http://127.0.0.1:5194`) y `CICERO_TOKEN_FILE`.
- Escrituras de agente con responsabilidad: toda herramienta que no sea de lectura exige un `reason` de 3 a 300 caracteres, cada escritura queda en el diario `data/agent_journal.jsonl`, una sesión de agente entera se puede previsualizar y deshacer, y se pueden emitir tokens con perfiles `read_only`, `drafts` o `all`.
- Las presentaciones se direccionan como `hoard://cicero/deck/<id>`. Los eventos de presentación, esquema, diapositivas, exportación y creación de temas van al bus del hub. Los temas de un sistema de diseño quedan enlazados a él. Las imágenes vienen de Prospero's Hoard cuando está en marcha; solo se contactan direcciones de bucle local.
- El botón de Faustus monta el panel de asistente común; Cicero aporta su identidad de espacio de datos y la presentación, diapositiva y estado de edición sin guardar actuales.
- La app lleva skills para agentes conectados (`presentation-from-brief`, `diagram-authoring`, `image-composition`, `deep-research`); el punto de entrada portable es `agent-skill/SKILL.md`.

<details>
<summary>Herramientas MCP por grupos</summary>

- Estado y presentaciones: `cicero_status`, `deck_list`, `deck_create`, `deck_get`, `deck_update`, `deck_delete`, `deck_import_pptx`.
- Fuentes y esquema: `source_add`, `source_list`, `source_get`, `source_remove`, `outline_generate`, `outline_update`.
- Diapositivas: `slides_generate`, `slide_get`, `slide_add`, `slides_add`, `slide_update`, `slide_edit_text`, `slide_set_image`, `slide_image`, `slide_regenerate`, `slide_approve`, `slide_revert`, `slide_delete`, `slides_reorder`, `asset_import`, `figure_get`.
- Revisión y diseño: `deck_check`, `deck_visual_review`, `deck_design`, `deck_design_audit`, `deck_visual_lab`, `deck_benchmark`, `titles_overview`, `titles_propose`, `titles_apply`, `titles_restore`, `titles_mode`.
- Temas y plantillas: `deck_theme`, `theme_from_tokens`, `deck_theme_from_preset`, `theme_delete`, `template_inspect`, `deck_template`, `deck_chrome`.
- Visuales: `visual_catalog`, `slide_visual_update`, `slide_variants`, `deck_scene`, `deck_present`.
- Movimiento, navegación y medios: `deck_animations`, `deck_transitions`, `deck_navigation`, `deck_media_control`, `media_import`, `media_get`, `scene_model_import`.
- Datos: `dataset_import`, `dataset_get`, `dataset_transform`, `dataset_visual`, `dataset_link`, `dataset_links`, `dataset_link_control`, `dataset_bind`, `dataset_connect`.
- Directo y colaboración: `deck_live_start`, `deck_live_state`, `deck_live_control`, `deck_poll`, `slide_collaborate`.
- Ensayo y exportación: `deck_rehearsal`, `deck_rehearsal_runs`, `deck_export`, `deck_handout_designcraft`.
- Apps Craft: `craft_discover`, `craft_call`, `vector_figure_create`.

</details>

## Estructura del proyecto

| Ruta | Contenido |
| --- | --- |
| `cicero_hoard/` | Paquete Python: API, generación, comprobaciones, exportaciones, sesiones en directo, Hoard Link incluido |
| `client/` | Interfaz React/Vite (compilada en `cicero_hoard/static`) |
| `mcp_server.py` | Puente MCP por stdio |
| `faustus-plugin.json` | Manifiesto del plugin de Faustus |
| `agent-skill/` | Skill portable para agentes |
| `docs/` | Referencias de API y funciones ([API](docs/API.md), [visuales para agentes](docs/AGENT_VISUALS.md), [datos y presentación](docs/DATA_PRESENTATION.md), [medios en directo](docs/LIVE_MEDIA.md), [navegación interactiva](docs/INTERACTIVE_NAVIGATION.md), [autoría avanzada](docs/ADVANCED_AUTHORING.md)) |
| `scripts/` | `dev.py`, `launch.py`, galería visual |
| `tests/` | Pruebas |

## Desarrollo

```bash
pip install -r requirements.txt
python -m pytest -q      # sin red: el modelo y el estudio de imágenes están simulados
```

Las pruebas de PDF solo se ejecutan si hay un Chromium disponible. Licencia: véase `LICENSE`.
