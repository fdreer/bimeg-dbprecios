# Design: Excel Report Generation & Email Delivery

**Fecha:** 2026-05-13  
**Estado:** Aprobado  
**Alcance:** Extensión del workflow `daily-price-sync` para generar un Excel con todos los productos y enviarlo por email al terminar el sync diario, con opción de ejecución manual.

---

## Contexto

El sistema agrega precios de materiales de construcción diariamente en una tabla `productos` (PostgreSQL local o Supabase cloud). Los usuarios necesitan recibir esos precios en formato Excel por email para usarlos en presupuestos de obras, sin tener que acceder a la base de datos directamente.

La app puede ser usada por distintas personas/instalaciones, por lo que los destinatarios del mail deben ser configurables por instalación.

---

## Decisiones de diseño

1. **Generación de Excel en n8n** usando el nodo nativo `Spreadsheet File` — sin cambios al scraper Python.
2. **Envío via Gmail OAuth2** — el usuario conecta su cuenta Google desde n8n UI (Client ID/Secret ingresados manualmente en Credentials, no en `.env`). Experiencia: popup de Google, sin contraseñas expuestas.
3. **Destinatarios configurables via `.env`** — `REPORT_EMAIL_TO` como lista separada por coma, inyectada al container n8n y referenciada con `{{ $env.REPORT_EMAIL_TO }}` en el nodo Gmail.
4. **Dos modos de disparo** — automático al terminar el sync diario + Manual Trigger para reenviar el reporte sin re-scrapear.
5. **Configurado primero para DB local** — el GET de productos apunta a `{{ $env.SUPABASE_URL }}/productos` (PostgREST local), compatible con el modo `--profile local`.
6. **Portabilidad**: el workflow JSON referencia la credencial Gmail por tipo. En una instalación nueva el usuario debe crear la credencial Gmail OAuth2 en n8n UI antes de activar el workflow.

---

## Variables de entorno

### Nuevas en `.env` / `.env.example`

```env
# ==========================================================================
# Email — reporte de precios
# Remitente: la cuenta Gmail conectada con OAuth2 en n8n Credentials.
# Destinatarios: separados por coma, sin espacios.
# ==========================================================================
REPORT_EMAIL_FROM=reportes@gmail.com
REPORT_EMAIL_TO=franco@bimeg.com,otro@bimeg.com
```

### En `docker-compose.yml` (sección `n8n > environment`)

```yaml
REPORT_EMAIL_FROM: ${REPORT_EMAIL_FROM}
REPORT_EMAIL_TO: ${REPORT_EMAIL_TO}
```

### Lo que NO va en `.env`

- `GMAIL_OAUTH_CLIENT_ID` y `GMAIL_OAUTH_CLIENT_SECRET` — se ingresan directamente en n8n UI → Credentials → Gmail OAuth2. Quedan encriptados en `n8n_data`.

---

## Arquitectura del workflow

### Flujo completo

```
[Schedule Trigger 06:00]  ──┐
                             ├──→ [sync diario existente (sin cambios)]
[Manual Trigger]            ──┘              ↓
                                    [All sources processed]
                                             ↓
                                  [GET /productos (PostgREST)]
                                  URL: {{ $env.SUPABASE_URL }}/productos
                                  Header apikey: {{ $env.SUPABASE_ANON_KEY }}
                                  Orden: fuente ASC, descripcion ASC
                                             ↓
                                    [Spreadsheet File]
                                    Operación: toFile
                                    Formato: xlsx
                                    Nombre: precios-{{ $now.format('yyyy-MM-dd') }}.xlsx
                                    Columnas incluidas (en orden):
                                      fuente, proveedor, empresa,
                                      descripcion, marca, categoria,
                                      precio, unidad_medida,
                                      disponibilidad, actualizado_en
                                             ↓
                                      [Send Gmail]
                                      Credential: Gmail OAuth2
                                      From: {{ $env.REPORT_EMAIL_FROM }}
                                      To: {{ $env.REPORT_EMAIL_TO }}
                                      Subject: Precios BIMEG — {{ $now.format('dd/MM/yyyy') }}
                                      Body: "Adjunto el reporte de precios del día."
                                      Attachment: binario del nodo anterior
```

### Manual Trigger — comportamiento

El Manual Trigger **no ejecuta el sync** — entra directamente al nodo `GET /productos`. Esto permite reenviar el reporte del día sin volver a scrapear todas las fuentes.

### Nodos existentes sin cambios

Toda la lógica previa al nodo `All sources processed` queda intacta.

---

## Nodo: GET /productos

| Campo | Valor |
|-------|-------|
| Método | GET |
| URL | `={{ $env.SUPABASE_URL }}/productos?order=fuente.asc,descripcion.asc` |
| Header `apikey` | `={{ $env.SUPABASE_ANON_KEY }}` |
| Header `Authorization` | `=Bearer {{ $env.SUPABASE_ANON_KEY }}` |

PostgREST devuelve por defecto hasta 1000 filas. Si la tabla supera ese límite, agregar header `Range: 0-9999` o usar paginación.

---

## Nodo: Spreadsheet File

| Campo | Valor |
|-------|-------|
| Operation | Write to file |
| File Format | XLSX |
| File Name | `=precios-{{ $now.format('yyyy-MM-dd') }}.xlsx` |
| Input Data Field | output del GET anterior |

---

## Nodo: Send Gmail

| Campo | Valor |
|-------|-------|
| Credential | Gmail OAuth2 (configurada en n8n UI) |
| Resource | Message |
| Operation | Send |
| To | `={{ $env.REPORT_EMAIL_TO }}` |
| From | `={{ $env.REPORT_EMAIL_FROM }}` |
| Subject | `=Precios BIMEG — {{ $now.format('dd/MM/yyyy') }}` |
| Email Type | Text |
| Message | `Adjunto el reporte de precios del día.` |
| Attachments | `data` (campo binario de salida del nodo Spreadsheet File) |

---

## Setup inicial por instalación

### Prerequisito (una sola vez — ya hecho por el mantenedor del proyecto)
- Proyecto Google Cloud `bimeg-496214` con Gmail API habilitada y OAuth2 Client ID creado.
- Redirect URI configurada: `http://localhost:5678/rest/oauth2-credential/callback`

### Por cada instalación nueva
1. Completar `.env` con `REPORT_EMAIL_FROM` y `REPORT_EMAIL_TO`.
2. Reiniciar n8n: `docker-compose up -d n8n` para que tome las nuevas vars.
3. En n8n UI → **Credentials** → **Add credential** → **Gmail OAuth2 API**.
4. Ingresar Client ID y Client Secret (provistos por el mantenedor del proyecto).
5. Click **"Sign in with Google"** → autenticar con la cuenta Gmail remitente.
6. Guardar la credencial.
7. Abrir el workflow → nodo **Send Gmail** → seleccionar la credencial recién creada.
8. Activar el workflow.

---

## Manejo de errores

- Si `GET /productos` devuelve array vacío (DB local sin datos), el Spreadsheet File genera un Excel vacío. El mail se envía igual con el archivo adjunto vacío — aceptable para esta etapa.
- Si el nodo Gmail falla (credencial vencida, sin conexión), n8n registra el error en el historial de ejecuciones. No afecta el sync ya completado.
- No se implementa retry automático en esta iteración.

---

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `.env.example` | Agregar `REPORT_EMAIL_FROM`, `REPORT_EMAIL_TO` |
| `docker-compose.yml` | Inyectar las dos vars nuevas al servicio `n8n` |
| `n8n/workflows/daily-price-sync.json` | Agregar Manual Trigger + 3 nodos nuevos (GET productos, Spreadsheet File, Send Gmail) |

Sin cambios en: `scraper/`, `db/`, `sources.yml`, `CLAUDE.md`.

---

## Fuera de alcance (esta iteración)

- Múltiples hojas en el Excel por fuente/proveedor.
- Reporte de cambios de precio (requiere historial).
- Retry automático de email.
- Soporte para Outlook / otros proveedores de email.
- Configuración en Supabase cloud (se hace después de validar en local).
