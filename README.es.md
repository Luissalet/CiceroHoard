# Cicero's Hoard

Un espacio de trabajo local que convierte un encargo y unos documentos en una presentación editable. Le das un
objetivo, un público y el material; propone un guion, escribe las diapositivas con notas del orador, te deja revisar
y aprobar cada diapositiva por separado, aplica un tema y exporta el resultado. Está pensado para que lo usen a la
vez una persona y un asistente: todo está disponible como API REST para la interfaz incluida y como herramientas MCP,
construidas con el mismo código, de modo que no pueden discrepar.

## Qué hace

- **Presentaciones**: título, encargo (brief), público, tono, idioma (español o inglés), número de diapositivas (de 3 a
  40) y tema. El estado se deduce, nunca se escribe a mano: `draft` (nada todavía), `outline` (hay guion), `review`
  (hay diapositivas y alguna sin aprobar), `ready` (todas aprobadas).
- **Fuentes**: pega texto o añade un archivo `.txt`, `.md`, `.pdf`, `.docx` o `.pptx` (solo texto; los PDF escaneados
  necesitan OCR aparte). Las fuentes se numeran y cada diapositiva puede citar en las que se apoya.
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
| `deck_theme` | listar los temas o aplicar uno |
| `deck_export` | exportar a `pptx`, `pdf`, `html` o `md`; devuelve la ruta del archivo y la URL de descarga |
| `slide_image` | generar una imagen para una diapositiva con el estudio de imágenes |

Los resultados que se envían a un asistente se recortan a unos 20 KB con una pista para acotar la petición. Aprobar
una diapositiva es decisión de la persona: un asistente no debería aprobar por su cuenta.

## Familia

Cicero funciona solo. Las presentaciones se pueden direccionar como `hoard://cicero/deck/<id>`. Emite
`cicero.deck.created`, `cicero.deck.deleted`, `cicero.outline.generated`, `cicero.slides.generated` y
`cicero.deck.exported` en el bus del hub (solo identificadores y títulos cortos). Las imágenes vienen de Prospero's
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
- Los PDF escaneados no tienen texto y se rechazan con un mensaje.

## Licencia

Consulta `LICENSE`.
