# Cicero's Hoard

Un espacio de trabajo local que convierte un encargo y unos documentos en una presentación editable. Le das un
objetivo, un público y el material; propone un guion, escribe las diapositivas con notas del orador, te deja revisar
y aprobar cada diapositiva por separado, aplica un tema y exporta el resultado. Está pensado para que lo usen a la
vez una persona y un asistente: todo está disponible como API REST para la interfaz incluida y como herramientas MCP,
construidas con el mismo código, de modo que no pueden discrepar.

## Qué hace

- **Tus plantillas PPTX**: carga una presentación de referencia en Tema, o usa `template_inspect` y
  `deck_template` por MCP. El PPTX editable conserva tamaño, patrones, diseños, fondos, logotipos y
  tipografías. Una copia guardada permite reutilizarla aunque cambie el original. Notas y gráficos salen
  de la presentación nueva. Puedes asignar diapositivas modelo y formas concretas a cada diseño de Cicero.

- **Presentaciones**: título, encargo (brief), público, tono, idioma (español o inglés), número de diapositivas (de 3 a
  40) y tema. El estado se deduce, nunca se escribe a mano: `draft` (nada todavía), `outline` (hay guion), `review`
  (hay diapositivas y alguna sin aprobar), `ready` (todas aprobadas).
- **Fuentes**: pega texto o añade un archivo `.txt`, `.md`, `.pdf`, `.docx` o `.pptx` (solo texto; un PDF escaneado lo lee el OCR
  del servicio de documentos de la familia cuando esa aplicación está en marcha). Las fuentes se numeran y cada diapositiva puede citar en las que se apoya.
- **Guion**: lo genera el modelo local a partir del encargo y de fragmentos numerados de las fuentes, o se escribe a
  mano. Cada punto tiene título, propósito, unas ideas y una sugerencia de diseño opcional.
- **Diapositivas**: ocho diseños (`title`, `section`, `bullets`, `two_column`, `image_text`, `quote`, `chart`,
  `closing`) formados por bloques (viñetas, texto, imagen, cita, columnas, gráfico). Todas llevan notas del orador.
- **Revisión una a una**: aprobar o quitar la aprobación, regenerar con comentarios, editar a mano. Cada cambio crea
  una revisión; revertir restaura una revisión antigua como una nueva. Al volver a generar se conservan las
  aprobadas y se reescriben los borradores.
- **Sin cifras inventadas**: el modelo solo puede usar cifras que aparezcan en las fuentes. Un gráfico se conserva
  únicamente si todos sus valores están en las fuentes, y `deck_check` señala cada cifra de una diapositiva que
  ninguna fuente contiene. Los formatos numéricos se comparan entre notaciones (`1.234`, `1,234`, `1.234,5`, `1,5`).
- **Ajuste automático**: el texto se mide y la letra baja de tamaño hasta que cabe, igual en la vista previa, en el
  HTML y en el PPTX (los tres se dibujan desde la misma geometría). Si algo no cabe ni con la letra más pequeña, la
  revisión lo avisa en vez de recortarlo en silencio.
- **Temas**: siete temas (`claro`, `oscuro`, `editorial`, `carmesi`, `pizarra`, `tecnico`, `oceano`), todos con un
  contraste mínimo de 4,5:1 en texto, texto atenuado y acentos. Las tipografías son de las que trae Windows.
  Un sistema de diseño de la aplicación de sistemas de diseño de la familia puede convertirse en un tema propio
  (`theme_from_tokens`, o el selector "Tema desde un sistema de diseño" de la pantalla de tema): se trasladan sus
  colores, tipografías y radio de esquinas, los colores que no se leerían se acercan al blanco o al negro hasta llegar a
  4,5:1 (los cambios se listan) y una tipografía que no trae Windows se sustituye por la más parecida que sí. Las
  tarjetas de un tema con radio se dibujan con esquinas redondeadas en la vista previa, el HTML y el PPTX.
- **Exportaciones**:
  - PPTX con cuadros de texto reales, párrafos con viñeta, notas del orador y gráficos nativos (editables en el
    paquete ofimático), en 16:9.
  - PDF, una página por diapositiva, generado con un Chromium local.
  - HTML, un único archivo autocontenido (estilos, script e imágenes dentro) con navegación por flechas. Las notas
    del orador se dejan fuera a propósito, porque el archivo está pensado para compartirse.
  - Markdown, diapositivas separadas por `---`, notas como comentarios y gráficos como tablas.
- **Imágenes**: sube las tuyas o pide una por diapositiva al estudio de imágenes de la familia (Prospero's Hoard). El
  estudio es opcional.
- **Funciona sin modelo**: si no hay ningún modelo accesible, el guion y las diapositivas salen de las fuentes con
  reglas fijas y el resultado indica `"generator": "fallback"`. Regenerar una diapositiva con comentarios sí necesita
  un modelo, y lo dice en lugar de aparentar.

## Uso responsable

- **Cifras.** Una presentación generada es un borrador. La comprobación de cifras detecta las que no están en las
  fuentes; no puede saber si una fuente es correcta. Lee las notas y las cifras antes de presentar.
- **Las fuentes se quedan en tu equipo.** Los documentos se leen en este ordenador. Al modelo solo se le envían
  fragmentos numerados y cortos, a través de Hoard Link, hacia el backend que hayas configurado (uno local por
  defecto).
- **Archivos locales.** Añadir un archivo por ruta solo admite tipos de documento (`.txt`, `.md`, `.pdf`, `.docx`,
  `.pptx`) y se puede limitar a carpetas con `CICERO_FILE_ROOTS`.
- **Citas.** Un bloque de cita debe reproducir una cita que aparezca en una fuente. La revisión no verifica citas.
- **Borrados** (una presentación, una diapositiva, una fuente) exigen confirmación explícita, también por MCP.

## Instalación

Requisitos: Python 3.11 o superior (objetivo en Windows: 3.13); Node.js 22 o superior solo para recompilar el cliente.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium     # solo para exportar a PDF
python -m cicero_hoard            # http://127.0.0.1:5194
```

El cliente compilado está incluido en `cicero_hoard/static`, así que `npm` solo hace falta para cambiar la interfaz
(`npm install`, `npm run build`). Mientras se trabaja en la interfaz, `python scripts/dev.py` arranca la API y el
servidor de desarrollo de Vite a la vez, y `python scripts/launch.py` arranca la aplicación y la abre en el
navegador.

| variable | valor por defecto | significado |
| --- | --- | --- |
| `CICERO_PORT` / `PORT` | `5194` | puerto; con `PORT_STRICT=1` la aplicación falla en vez de pasar a otro puerto |
| `CICERO_DATA_DIR` | `./data` | base de datos, `assets/`, `exports/`, `mcp-token`, `url`, `backend.json` |
| `CICERO_ALLOWED_HOSTS` | solo local | nombres de host adicionales que acepta el servidor |
| `CICERO_FILE_ROOTS` | vacío | carpetas (separadas con el separador de rutas del sistema) de las que pueden venir archivos locales |
| `CICERO_IMAGE_STUDIO_URL` | se descubre | dirección del estudio de imágenes, para saltarse el descubrimiento |
| `CICERO_IMAGE_TIMEOUT` | `600` | segundos que se espera a un render del estudio de imágenes (10-86400) |
| `CICERO_PARALLEL_SLIDES` | `3` | diapositivas que el modelo escribe a la vez después de la primera (1-8); un servidor local con varias ranuras termina antes |
| `CICERO_SLIDE_EFFORT` | `low` | esfuerzo de razonamiento que se pide al modelo en cada diapositiva y reescritura (`off`, `low`, `medium`, `high`); el guion pide siempre `medium` |

El modelo sale de Hoard Link (`data/backend.json` o las variables de entorno de Hoard); el nombre del modelo también
se puede elegir en Ajustes.

## Código compartido de Hoard Link

La fontanería es la de las librerías comunes de Hoard Link (copia en `cicero_hoard/hoard_link/`): el lanzador (una instancia
por puerto, registros en `data/logs/`), el guardián de peticiones, el formato de errores, el `mcp-token` estable, la capa
SQLite, los ids ULID (los decks creados con versiones anteriores conservan sus ids de 12 caracteres), el catálogo del
agente con el límite de 20 KB, los lectores de Word y de texto con la protección contra zip-bombs, el troceador, el
lanzador de navegador para exportar a PDF y el puente MCP.

## MCP

`mcp_server.py` es un puente stdio. Nunca abre la base de datos: lee `data/mcp-token`, obtiene la lista de
herramientas de la aplicación en marcha y reenvía cada llamada. Si la aplicación no está en marcha, la arranca
(`CICERO_BRIDGE_AUTOSTART=0` lo desactiva). Regístralo en cualquier cliente MCP:

```json
{"mcpServers": {"cicero": {"command": "python", "args": ["/ruta/a/cicero/mcp_server.py"],
  "env": {"CICERO_URL": "http://127.0.0.1:5194", "CICERO_TOKEN_FILE": "/ruta/a/cicero/data/mcp-token"}}}}
```

`faustus-plugin.json` describe la misma configuración para el espacio de trabajo Faustus.

### Herramientas

| herramienta | qué hace |
| --- | --- |
| `cicero_status` | estado, recuentos, disponibilidad del modelo y del PDF |
| `deck_create`, `deck_list`, `deck_get`, `deck_update`, `deck_delete` | presentaciones; `deck_get` devuelve un resumen salvo con `detail=full`; borrar exige `confirm=true` |
| `source_add`, `source_list`, `source_get`, `source_remove` | fuentes desde texto pegado o un archivo local; lectura por tramos; quitar exige `confirm=true` |
| `outline_generate`, `outline_update` | generar el guion o sustituirlo a mano |
| `slides_generate` | escribir las diapositivas a partir del guion; las aprobadas se conservan |
| `slide_get`, `slide_update`, `slide_add`, `slide_delete`, `slides_reorder` | leer, editar, añadir, quitar (`confirm=true`) y reordenar diapositivas |
| `slide_regenerate` | reescribir una diapositiva según unos comentarios (necesita modelo) |
| `slide_approve` | aprobar o quitar la aprobación de una diapositiva |
| `slide_revert` | listar las revisiones de una diapositiva o restaurar una como revisión nueva |
| `deck_check` | revisión: desbordes, cifras que no están en las fuentes, notas ausentes, diapositivas sin aprobar |
| `deck_theme` | listar los temas (los de serie y los hechos desde sistemas de diseño) o aplicar uno |
| `asset_import` | copiar una figura local PNG/JPEG/WEBP; usar su ID en un bloque de imagen; repetir la importación reutiliza la imagen de esta presentación |
| `slides_add` | añadir lotes de borradores de forma atómica; repetir la misma clave y contenido devuelve los IDs originales |
| `slide_edit_text` | editar un título, subtítulo, nota o viñeta conservando los demás bloques |
| `slide_set_image` | añadir o reemplazar una figura importada o su pie; conserva los demás bloques y notas; los reintentos idénticos mantienen la revisión |
| `deck_rehearsal` | planificar turnos y estimar la duración desde las notas; no afirma haber medido un ensayo |
| `template_inspect`, `deck_template` | inspeccionar un PPTX local, adjuntarlo con asignaciones opcionales por diseño, consultar la plantilla o quitarla con `clear=true` |
| `theme_from_tokens` | crear un tema desde un sistema de diseño (`tokens_id`, `mode` claro u oscuro, `deck_id` opcional para aplicarlo); sin `tokens_id` lista los sistemas de diseño |
| `deck_export` | exportar a `pptx`, `pdf`, `html` o `md`; devuelve la ruta del archivo y la URL de descarga |
| `slide_image` | generar una imagen para una diapositiva con el estudio de imágenes |

Los resultados que se envían a un asistente se recortan a unos 20 KB con una pista para acotar la petición. Aprobar
una diapositiva es decisión de la persona: un asistente no debería aprobar por su cuenta.

## Familia

Cicero funciona solo. Las presentaciones se pueden direccionar como `hoard://cicero/deck/<id>`. Emite
`cicero.deck.created`, `cicero.deck.deleted`, `cicero.outline.generated`, `cicero.slides.generated` y
`cicero.deck.exported` en el bus del hub (solo identificadores y títulos cortos). Los temas hechos desde un sistema de diseño emiten
`cicero.theme.created` y quedan enlazados con él (`hoard://cicero/theme/<id>` derivado de
`hoard://vitruvius/tokens/<id>`); el sistema de diseño se lee a través del hub (`tokens_list` y `tokens_get` de la
aplicación de sistemas de diseño), así que el hub y esa aplicación deben estar en marcha, y pedir el mismo sistema en el
mismo estado devuelve el mismo tema. Las imágenes vienen de Prospero's
Hoard cuando está en marcha: el estudio se busca con `CICERO_IMAGE_STUDIO_URL`, con la lista de aplicaciones del hub o
con su puerto local por defecto (8815), y se usa a través de su API REST local, que no necesita token. Las imágenes de
las diapositivas van a un proyecto del estudio llamado "Cicero's Hoard slides" (se reutiliza o se crea la primera
vez); cada petición envía un render 16:9, espera a que termine y guarda la imagen resultante en la presentación. Solo
se contacta con direcciones de bucle local.

## Desarrollo

```bash
pip install -r requirements.txt
python -m pytest -q      # sin red: el modelo y el estudio de imágenes están simulados
```

Las pruebas de PDF solo se ejecutan si hay un Chromium disponible. La documentación de la API HTTP está en
`docs/API.md`.

## Una prueba real

En un PC con Windows y un modelo local de 27B servido con llama.cpp: un plan de ventas de siete diapositivas para una
tienda ficticia, a partir de un encargo y un informe pegado. El guion tardó 155 s; escritas una tras otra, cada
diapositiva tardaba unos 75 s, y por eso ahora se escriben de tres en tres. El modelo usó solo las cifras del informe:
un gráfico de barras con los cuatro trimestres, los datos de clientes en dos columnas y, tras la indicación «quita la
frase del margen bruto, no está en el informe; muestra el desglose de los 70.000 € como gráfico de barras», una
diapositiva con ese desglose exacto y sin la frase. La revisión no encontró cifras sin fuente. Se abrieron las
exportaciones PPTX y PDF: gráficos nativos, notas del orador y las fuentes del tema incrustadas en el PDF. El estudio
de imágenes dibujó una imagen 16:9 para una diapositiva en 79 s. Un asistente conectado por MCP listó las
presentaciones, pasó la revisión y exportó el PDF en cuatro rondas. Cuatro fallos encontrados en esa prueba están
corregidos y cubiertos por pruebas: fuentes del tema perdidas en el HTML, miles sin separar en los gráficos nativos, un
puente que daba por parada una aplicación en marcha cuando no podía leer su token y una llamada de imagen a una
herramienta que el estudio no tiene.

## Límites

- Con plantilla adjunta, la vista previa muestra el tema incorporado. Abre el PPTX exportado para revisar
  la plantilla aplicada. PDF/HTML con plantilla aún no están disponibles; Markdown exporta el contenido.
  No se copian animaciones ni transiciones del original. La selección automática de formas es un punto
  de partida; para referencias complejas, inspecciona sus IDs y asigna las formas explícitamente.

- Una imagen tarda lo que el estudio tarde en renderizarla; la petición espera hasta `CICERO_IMAGE_TIMEOUT` segundos.
  Si pasa ese tiempo, el render sigue en marcha en el estudio y no se vuelve a enviar. Solo se toma una imagen por
  petición, de un estudio de este mismo equipo; se rechazan las imágenes de más de 15 MB o que no sean PNG, JPEG ni
  WEBP.
- La exportación a PDF necesita Chromium (`python -m playwright install chromium`, o un Edge o Chrome del sistema). Sin
  él, exportar `pdf` falla con el código `pdf_unavailable` y los demás formatos siguen funcionando.
- Las tipografías son las del tema; un equipo que no las tenga sustituye otra y las líneas pueden cortarse de otra
  manera. El ajuste deja un pequeño margen de seguridad para ese caso.
- El ajuste del texto es una estimación a partir del ancho de los caracteres, no una medición con las métricas reales
  de la fuente.
- Gráficos: barras, líneas y circular; una o varias series (el circular usa la primera).
- Las notas del orador no se incluyen en la exportación a HTML.
- Los PDF escaneados solo se leen si el servicio de documentos de la familia (OCR) está en marcha; si no, se rechazan con un mensaje.

## Licencia

Consulta `LICENSE`.

## Lotes para presentaciones grandes

`slides_add(deck_id, batch_key, slides)` añade varias diapositivas en borrador, con notas, gráficos y fuentes, en una transacción. Repetir la misma clave y contenido tras una respuesta interrumpida devuelve los IDs originales. La misma clave con contenido distinto se rechaza. Conserva las diapositivas y aprobaciones existentes; no aprueba el lote. Si falla una diapositiva, no se guarda ninguna del lote.

Cuando una diapositiva cita fuentes concretas, `deck_check` comprueba sus cifras contra esas fuentes. Los números de ejemplo de otra fuente o del encargo no sirven como evidencia. Comprueba la presencia de cifras, no el significado de una afirmación; sigue siendo necesaria la revisión del contenido.

`slide_edit_text` cambia un título, subtítulo, nota o viñeta sin reconstruir los demás bloques. La edición de una viñeta usa índices de bloque y elemento desde cero; conserva gráficos y otras viñetas, y crea una revisión normal en borrador.

Para una figura existente, usa `asset_import` y después `slide_set_image(deck_id, slide_id, asset_id, caption?)`. Selecciona la primera imagen por defecto; `image_index` cuenta solo bloques de imagen y un índice igual al número de imágenes añade otra. Omitir el pie lo conserva; `null` explícito lo borra. Conserva los otros bloques, notas, título, fuentes y diseño. Un reintento idéntico no duplica imágenes ni revisiones. Los cambios crean revisiones en borrador y se deshacen con `slide_revert`. `expected_revision` opcional detecta una edición concurrente (409 `conflict`); vuelve a leer la diapositiva antes de reintentar.

### Plan de ensayo cronometrado

`deck_rehearsal(deck_id, duration_minutes, words_per_minute, pause_seconds, main_slides)` prepara un horario por diapositiva a partir de las notas. `main_slides` selecciona las primeras diapositivas de la exposición; las restantes quedan como apoyo. Los turnos suman exactamente el objetivo, y una estimación separada indica si el guion cabe al ritmo elegido, incluyendo pausas. Si faltan notas, la duración total estimada queda desconocida. No afirma haber medido un ensayo oral ni modifica notas, revisiones o aprobaciones.

### VectorCraft y DesignCraft locales

Configura `CICERO_VECTORCRAFT_CLI` y `CICERO_DESIGNCRAFT_CLI` con las rutas a los ejecutables portátiles instalados. Cicero inicia cada app como servidor MCP local sin interfaz y guarda sus datos de aplicación dentro de `data/craft-runs` de Cicero. Las pruebas actuales usan los paquetes portátiles verificados VectorCraft 0.3.1 y DesignCraft 0.2.1; las demás versiones compatibles se descubren en tiempo de ejecución. No requiere cuentas ni servicios remotos.

`craft_discover(app)` devuelve el catálogo MCP nativo completo y los esquemas de entrada. `craft_call(app, calls)` despacha las herramientas nativas con sus nombres y argumentos originales, en orden, y devuelve todo el contenido de texto o imagen. Así Cicero conserva la superficie MCP disponible de cada app.

Herramientas: `craft_discover`, `craft_call`, `vector_figure_create` y `deck_handout_designcraft`. El descubrimiento incluye herramientas, prompts, recursos y plantillas de recursos nativos cuando la app los ofrece. El despacho acepta `kind: "tool"`, `"prompt"` o `"resource"`; si el servidor no implementa un método MCP opcional, devuelve un catálogo vacío para ese método.

`vector_figure_create(deck_id, slide_id, title, shape, fill, stroke, replace_block_index?)` crea un documento VectorCraft editable, SVG y vista PNG, guarda una copia gestionada y la añade a la diapositiva como figura. Para corregir una figura existente, pasa su `block_index` devuelto como `replace_block_index`; se conservan los demás bloques, título y notas. El PPTX incluye la imagen SVG y una imagen PNG de compatibilidad. Los archivos `.vectorcraft`, `.svg` y `.png` quedan en los recursos de la presentación; no se modifica el original.

Como alternativa a las variables de entorno, guarda las rutas en el archivo local no versionado `data/craft-engines.json`: `{"vectorcraft":{"executable":"..."},"designcraft":{"executable":"..."}}`. Cada lote `craft_call` abre un proceso nativo nuevo. Agrupa los comandos dependientes en un solo lote y guarda el documento antes de terminar; la selección y el historial de deshacer no persisten entre lotes. Gutenberg ofrece sesiones editoriales persistentes para trabajos de publicación más largos.

El original vectorial se edita en VectorCraft. El PPTX contiene el SVG como imagen con alternativa PNG, no como geometría nativa de PowerPoint; la herramienta informa de esta diferencia. En el documento de apoyo las imágenes aportan sus pies y los gráficos sus valores como texto, en vez de imágenes incrustadas o gráficos nativos.

`deck_handout_designcraft(deck_id)` crea una página A4 editable de DesignCraft por diapositiva, con marcos separados para título y cuerpo, y renderiza una vista PNG por página. Transfiere texto y notas del orador de forma determinista; usa los pies de figura y valores de los gráficos. Informa de marcos de texto desbordados. El `.designcraft` y cada PNG se descargan desde la lista de exportaciones. No afirma exportar PDF ni igualar la maquetación de marca de la presentación original.
