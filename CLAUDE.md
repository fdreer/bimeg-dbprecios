# CLAUDE.md — bimeg-dbprecios

Convenciones y contexto del proyecto para Claude Code. Este archivo se lee
automáticamente al abrir el proyecto y no necesita ser referenciado.

---

## Qué es el proyecto

Agregador de precios de materiales de construcción. Consulta APIs públicas y
scrapea sitios web de proveedores en Argentina, normaliza los datos y los vuelca
en una tabla única (`productos`) en PostgreSQL. Se usa para presupuestar obras.

**Documento de diseño**: ver [`PLAN.md`](./PLAN.md).

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Orquestación | n8n (self-hosted, Docker) |
| Scraping | Microservicio Python + FastAPI + Playwright |
| Base de datos | PostgreSQL — local (Postgres + PostgREST) o Supabase cloud |
| Config declarativa | `sources.yml` |
| Deployment | Docker Compose |

---

## Dos modos de ejecución (importante)

El proyecto corre en dos modos según la DB:

```bash
# DEV (DB local en containers)
docker-compose --profile local up -d

# PROD (DB en Supabase cloud)
docker-compose up -d
```

La diferencia vive en **`.env`**: `SUPABASE_URL` apunta a `http://postgrest:3000`
(local) o a `https://xxxx.supabase.co` (prod). El resto es idéntico — el
workflow de n8n usa `{{ $env.SUPABASE_URL }}` y funciona igual en ambos.

---

## Convenciones de código

### Python (`scraper/`)
- **Python ≥ 3.11** (ver imagen base de Playwright).
- **Type hints en todo el código público** (`from __future__ import annotations`).
- **Pydantic v2** para validar `sources.yml`.
- **Docstrings en funciones públicas**, estilo Google o NumPy.
- **No hardcodear URLs ni secretos** — todo viene de `sources.yml` o env vars.

### YAML (`sources.yml`)
- Los valores `${VAR}` se resuelven contra env vars del container en runtime.
- `enabled: false` deshabilita una fuente sin borrarla — preferir eso a
  comentarla.
- El campo `name` es el identificador único usado como valor de `fuente` en la
  tabla y como clave para `DELETE FROM productos WHERE fuente = ...`.

### SQL (`db/`)
- **`schema.sql`** es canónico: se aplica tanto al Postgres local (vía
  `/docker-entrypoint-initdb.d/`) como al proyecto Supabase (copiando al SQL
  Editor).
- **`init-local.sql`** es SÓLO para el Postgres local — crea el rol `anon` que
  Supabase ya administra solo.
- Estrategia sin historial: `DELETE FROM productos WHERE fuente = X` seguido de
  `INSERT INTO productos (...)`.

### n8n (`n8n/workflows/`)
- **NO usar Credentials nativas de n8n** — usar siempre `{{ $env.VAR }}` en los
  nodos HTTP. Motivo: las Credentials no viajan en el JSON exportado y rompen
  portabilidad entre máquinas.
- El JSON exportado se guarda en `n8n/workflows/` y se commitea.
- Al editar el workflow: abrir n8n UI → cambiar → exportar → reemplazar el JSON
  del repo → commit.

---

## Comandos frecuentes

### Levantar / parar
```bash
docker-compose --profile local up -d   # dev
docker-compose up -d                   # prod
docker-compose down                    # parar
docker-compose down -v                 # parar y borrar volúmenes (destructivo)
```

### Logs
```bash
docker-compose logs -f                 # todos los servicios
docker-compose logs -f n8n             # solo n8n
docker-compose logs -f scraper-service # solo scraper
```

### Rebuild del scraper después de cambios en código
```bash
docker-compose build scraper-service
docker-compose up -d scraper-service
```

### Reset completo (destruye datos locales)
```bash
docker-compose down -v
rm -rf n8n_data postgres_data
docker-compose --profile local up -d
```

### Verificar scraper
```bash
# Dentro de la red Docker:
docker-compose exec scraper-service curl http://localhost:8000/health
docker-compose exec scraper-service curl http://localhost:8000/sources
```

### Verificar DB local
```bash
docker-compose exec postgres psql -U postgres -d postgres -c "SELECT COUNT(*) FROM productos;"
```

---

## MCPs configurados (para desarrollo con Claude Code)

Estos MCPs están registrados en `.claude.json` y NO viajan con el repo. Cada
desarrollador los configura en su máquina si quiere usarlos con Claude Code:

- **supabase** — operaciones sobre la DB cloud (schema, queries, logs)
- **n8n-mcp** — validación de nodos y workflows, docs de n8n
- **playwright** — automatización de browser para descubrir selectores CSS
- **context7** — docs actualizadas de FastAPI, Playwright, supabase-py

No forman parte de la infraestructura del proyecto.

---

## Estado actual de implementación

| Componente | Estado |
|------------|--------|
| Estructura del repo | ✅ |
| Schema SQL (productos) | ✅ aplicado en Supabase y local |
| Scraper: endpoints `/health`, `/sources` | ✅ funcionales |
| Scraper: `/scrape/static`, `/scrape/dynamic` | 🚧 stubs (devuelven `[]`) |
| Scraper: lógica real de Playwright + parsing | ❌ pendiente |
| `sources.yml` con ejemplos | ✅ (placeholders, todos `enabled: false`) |
| `sources.yml` con fuentes reales | ❌ pendiente |
| `docker-compose.yml` (prod + local) | ✅ |
| Workflow de n8n | ✅ skeleton válido |
| README multi-plataforma | ✅ |
| Tests | ❌ pendiente |

---

## Reglas de modificación

- **No tocar `scraper.py` en las funciones con TODO** salvo que el usuario
  explícitamente pida implementar scraping. Están stubbed a propósito hasta que
  se definan las fuentes reales.
- **Cualquier cambio en el schema de la tabla `productos` requiere**:
  1. Actualizar `db/schema.sql`.
  2. Aplicar sobre Supabase cloud manualmente (o vía MCP si corresponde).
  3. Para el Postgres local: `docker-compose down -v` y re-levantar, porque los
     scripts de `/docker-entrypoint-initdb.d/` sólo corren la primera vez.
- **Agregar una fuente nueva** = editar `sources.yml` + si es un `api`,
  implementar la rama correspondiente en el workflow de n8n. Si es `static` o
  `dynamic`, implementar la función correspondiente en `scraper.py`.
- **Credenciales**: ninguna password o key en el repo. Siempre vía `.env`.

---

## Nota de seguridad

La tabla `productos` actualmente tiene **RLS deshabilitado** en Supabase y se
accede con `anon_key`. Esto es aceptable mientras la DB sea de uso interno (el
anon key vive sólo en containers privados). Antes de exponerla al exterior,
habilitar RLS y aplicar policies restrictivas o migrar a `service_role` key.
