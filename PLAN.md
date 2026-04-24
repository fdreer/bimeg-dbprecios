# Plan: bimeg-dbprecios — Agregador de Precios de Materiales de Construcción

## Contexto

El objetivo es construir un sistema que consulte APIs públicas y scrapee páginas web de proveedores de materiales de construcción de forma diaria, volcando toda la información normalizada en una base de datos propia en la nube. Los precios se usarán para presupuestar obras.

**Stack elegido:** n8n (orquestador) + microservicio Python/Playwright (scraping dinámico) + Supabase (base de datos PostgreSQL gratuita en la nube), todo empaquetado en Docker Compose.

**Requisito central:** el proyecto debe poder subirse a GitHub y clonarse en cualquier dispositivo (Windows/Linux/Mac) y funcionar con configuraciones mínimas (completar `.env`, importar workflow de n8n, ejecutar `docker-compose up`).

---

## Decisiones de diseño

Estas son las decisiones acordadas que condicionan la implementación:

1. **Autenticación de n8n → Supabase vía `$env`**: los nodos HTTP de n8n referencian `{{ $env.SUPABASE_URL }}` y `{{ $env.SUPABASE_ANON_KEY }}` directamente. **No se usan Credentials nativas de n8n** porque esas no viajan en el JSON exportado y obligan a recrearlas manualmente en cada máquina. Con `$env`, el workflow es 100% portable.

2. **`N8N_ENCRYPTION_KEY` fija y committeable como placeholder**: se genera una vez y se guarda en `.env` (no committeado). Sin esto, n8n genera una distinta en cada instalación y rompe la portabilidad de datos persistidos.

3. **Timezone explícito**: el container de n8n corre con `TZ=America/Argentina/Buenos_Aires` (configurable vía `.env`) para que los cron triggers ejecuten a la hora local esperada en cualquier máquina.

4. **Auto-inicio multi-plataforma**: el README documenta cómo configurar auto-start en Windows, Linux y Mac por separado.

---

## Estructura del Repositorio

```
bimeg-dbprecios/
├── docker-compose.yml
├── .env.example            ← plantilla con todas las variables necesarias
├── .env                    ← gitignored, cada usuario configura el suyo
├── .gitignore
├── README.md               ← instrucciones de instalación paso a paso por SO
├── PLAN.md                 ← este documento
├── CLAUDE.md               ← convenciones del proyecto para Claude Code
├── sources.yml             ← configuración de fuentes (APIs + páginas)
├── n8n/
│   └── workflows/
│       └── daily-price-sync.json   ← workflow exportado de n8n, listo para importar
├── scraper/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py             ← API FastAPI (endpoints HTTP)
│   ├── scraper.py          ← lógica de Playwright para páginas dinámicas
│   └── config_loader.py    ← parsea sources.yml
└── db/
    └── schema.sql          ← definición de tablas en Supabase (ejecutar una vez)
```

---

## Componente 1: Configuración de Fuentes (`sources.yml`)

Archivo YAML editable por el usuario donde se declaran todas las fuentes de datos. Es la pieza central de extensibilidad del sistema.

### Estructura lógica:

```yaml
apis:
  - name: "Nombre de la API"
    enabled: true
    endpoint: "https://..."
    auth_header: "Authorization"        # opcional
    auth_value: "${NOMBRE_API_KEY}"     # referencia a variable de .env
    field_mappings:                     # mapeo de campos de la respuesta al schema de la DB
      descripcion: "campo_origen"
      precio: "campo_precio"
      categoria: "campo_categoria"
      codigo_producto: "campo_id"
      marca: "campo_marca"
      unidad_medida: "campo_unidad"
    empresa: "Nombre empresa"
    proveedor: "Nombre proveedor"

static_pages:                          # HTML estático, sin JS
  - name: "Nombre Tienda"
    enabled: true
    base_url: "https://..."
    selectores:
      descripcion: ".css-selector"
      precio: ".css-selector"
      codigo_producto: ".css-selector"
      url_imagen: ".css-selector"
      categoria: ".css-selector"
    empresa: "Nombre empresa"
    proveedor: "Nombre proveedor"
    marca: ""

dynamic_pages:                         # páginas con JS (Easy, Sodimac, etc.)
  - name: "Nombre Tienda"
    enabled: true
    base_url: "https://..."
    selectores:
      descripcion: "[data-attr]"
      precio: "[data-attr]"
      # etc.
    empresa: "Nombre empresa"
    proveedor: "Nombre proveedor"
```

### Variables de entorno en sources.yml:
Los valores `${VAR}` en sources.yml son reemplazados en runtime por `config_loader.py` usando los valores del entorno del contenedor (que vienen del `.env`).

---

## Componente 2: Microservicio Scraper (Python + FastAPI + Playwright)

### Responsabilidades:
- Exponer endpoints HTTP que n8n consume
- Ejecutar scraping de páginas **dinámicas** (JS) con Playwright
- Opcionalmente también scrapear páginas **estáticas** (aunque n8n puede hacerlo directamente)
- Parsear y servir la configuración de `sources.yml`

### Endpoints:

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Health check del servicio |
| GET | `/sources` | Devuelve el sources.yml parseado como JSON |
| POST | `/scrape/dynamic` | Recibe `{source_name}`, ejecuta Playwright y devuelve array de productos |
| POST | `/scrape/static` | Recibe `{source_name}`, hace HTTP request + parsing HTML y devuelve productos |

### Formato de respuesta de `/scrape/*`:
```json
[
  {
    "codigo_producto": "...",
    "descripcion": "...",
    "precio": 1234.56,
    "url_producto": "...",
    "url_imagen": "...",
    "categoria": "...",
    "empresa": "...",
    "marca": "...",
    "proveedor": "...",
    "unidad_medida": "...",
    "fuente": "nombre-fuente"
  }
]
```

Los datos ya vienen **normalizados** al schema de la DB — la lógica de mapeo ocurre dentro del scraper.

### Lógica de paginación:
El scraper maneja la paginación internamente por cada fuente (según configuración en sources.yml). N8n hace una sola llamada por fuente y recibe todos los productos.

---

## Componente 3: Base de Datos en Supabase

### Por qué Supabase:
- PostgreSQL gestionado, free tier con 500MB y 2 proyectos
- Interfaz web para gestionar datos
- API REST automática (PostgREST) para consultar la DB desde n8n via HTTP
- Sin costo de mantenimiento

### Schema de la tabla `productos`:

```sql
CREATE TABLE productos (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  codigo_producto VARCHAR(255),
  descripcion TEXT NOT NULL,
  precio NUMERIC(12, 2) NOT NULL,
  url_producto TEXT,
  url_imagen TEXT,
  categoria VARCHAR(255),
  empresa VARCHAR(255),
  marca VARCHAR(255),
  proveedor VARCHAR(255),
  unidad_medida VARCHAR(50),
  fuente VARCHAR(100),
  actualizado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_productos_fuente ON productos(fuente);
CREATE INDEX idx_productos_empresa ON productos(empresa);
CREATE INDEX idx_productos_categoria ON productos(categoria);
```

### Estrategia de actualización (sin historial):
Cada vez que el workflow corre para una fuente determinada:
1. `DELETE FROM productos WHERE fuente = 'nombre-fuente'`
2. `INSERT INTO productos (...) VALUES ...` (batch insert)

Esto elimina productos que el proveedor ya no tiene y garantiza datos frescos. Más simple que upsert y no deja datos huérfanos.

---

## Componente 4: Workflow de n8n

### Trigger:
- Cron diario configurable (ej: 06:00 AM hora local, gracias a `TZ` del container)

### Flujo lógico del workflow:

```
[Cron Trigger]
       ↓
[HTTP GET /sources]  ← llama al scraper service para obtener fuentes activas
       ↓
[Split in Batches]   ← itera sobre cada fuente habilitada
       ↓
[Switch por tipo]
   ├── tipo: api      → [HTTP Request a la API] → [transform/normalize] 
   ├── tipo: static   → [POST /scrape/static al scraper service]
   └── tipo: dynamic  → [POST /scrape/dynamic al scraper service]
       ↓
[HTTP DELETE a Supabase]  ← borra registros de esa fuente
       ↓
[HTTP POST a Supabase]    ← inserta nuevos productos en batch
       ↓
[Notificación opcional]   ← log de éxito/error (email o webhook)
```

### Autenticación: expresiones `$env` (no Credentials)

**Decisión clave para portabilidad**: cada nodo HTTP que habla con Supabase usa expresiones de n8n que leen variables de entorno del container, en lugar de Credentials nativas.

Ejemplo de configuración de un nodo HTTP Request en n8n:

| Campo | Valor |
|-------|-------|
| URL | `={{ $env.SUPABASE_URL }}/rest/v1/productos` |
| Header `apikey` | `={{ $env.SUPABASE_ANON_KEY }}` |
| Header `Authorization` | `=Bearer {{ $env.SUPABASE_ANON_KEY }}` |
| Header `Content-Type` | `application/json` |
| Header `Prefer` (para POST) | `return=representation` |

El prefijo `=` en cada valor activa el modo expresión de n8n. Los `{{ $env.VAR }}` se resuelven en cada ejecución contra el entorno del container n8n, que hereda las variables del `.env` vía docker-compose.

**Ventaja**: el workflow JSON exportado **funciona tal cual en cualquier máquina** — solo hay que tener el `.env` completo antes de levantar los containers.

### URL del scraper service:
Dentro de la red Docker, n8n accede al scraper por el hostname del servicio: `http://scraper-service:8000`. Este valor también se puede parametrizar vía `$env.SCRAPER_URL` si se prefiere.

### Workflow exportado como JSON:
El archivo `n8n/workflows/daily-price-sync.json` se exporta desde n8n y se commitea al repositorio. Cualquier usuario nuevo solo necesita importarlo desde la UI de n8n — las referencias `$env` se resuelven automáticamente contra su `.env`.

---

## Componente 5: Docker Compose

### Servicios:

**n8n:**
- Imagen oficial de n8n (`n8nio/n8n:latest`)
- Puerto 5678 expuesto localmente
- Volúmenes: datos de n8n persistidos localmente en `./n8n_data`
- Variables de entorno críticas:
  - `N8N_BASIC_AUTH_ACTIVE=true`
  - `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` (desde `.env`)
  - `N8N_ENCRYPTION_KEY` (desde `.env`, obligatoria para portabilidad)
  - `TZ` y `GENERIC_TIMEZONE` (desde `.env`, para cron en hora local)
  - `SUPABASE_URL` / `SUPABASE_ANON_KEY` (desde `.env`, consumidas vía `$env` en workflows)
  - `SCRAPER_URL=http://scraper-service:8000` (URL interna)
  - APIs externas adicionales según `sources.yml`
- `restart: always`

**scraper-service:**
- Imagen custom construida desde `scraper/Dockerfile`
- Puerto 8000 expuesto solo dentro de la red Docker (n8n lo accede internamente)
- Volumen: `sources.yml` montado como read-only
- Variables de entorno: todas las API keys de proveedores que use el scraper
- `restart: always`

### Red interna:
Ambos servicios comparten una red Docker privada. El scraper no está expuesto al exterior — solo n8n puede llamarlo.

---

## Componente 6: Portabilidad y configuración inicial

### `.env.example` (committed):
```
# ==========================================
# Supabase
# ==========================================
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=

# ==========================================
# n8n — UI y autenticación básica
# ==========================================
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=

# ==========================================
# n8n — clave de encriptación interna
# Generar una sola vez con: openssl rand -hex 32
# CRÍTICO: sin esto, n8n genera una distinta cada vez y rompe portabilidad
# ==========================================
N8N_ENCRYPTION_KEY=

# ==========================================
# Timezone (afecta a los cron triggers)
# Lista: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
# ==========================================
TZ=America/Argentina/Buenos_Aires
GENERIC_TIMEZONE=America/Argentina/Buenos_Aires

# ==========================================
# APIs de fuentes (agregar según sources.yml)
# ==========================================
NOMBRE_API_KEY=
```

### `.gitignore`:
```
.env
n8n_data/
__pycache__/
*.pyc
.pytest_cache/
```

### Pasos de instalación para un nuevo usuario (README):
1. Clonar el repositorio
2. Copiar `.env.example` a `.env`
3. Generar `N8N_ENCRYPTION_KEY` con `openssl rand -hex 32` y pegarla en `.env`
4. Crear cuenta gratuita en Supabase, crear proyecto, completar `SUPABASE_URL` y `SUPABASE_ANON_KEY` en `.env`
5. Ejecutar `db/schema.sql` en el SQL Editor de Supabase
6. Editar `sources.yml` con las fuentes deseadas
7. Completar cualquier API key extra en `.env`
8. Ejecutar `docker-compose up -d`
9. Abrir n8n en `http://localhost:5678`, loguearse con basic auth
10. Importar `n8n/workflows/daily-price-sync.json` desde la UI
11. Activar el workflow

---

## Componente 7: Auto-inicio al encender la PC (multi-plataforma)

Con `restart: always` en los servicios, los containers se levantan automáticamente cuando Docker arranca. Lo que cambia entre sistemas operativos es cómo configurar que **Docker mismo** arranque al inicio.

### Windows
1. **Docker Desktop**: Settings → General → activar "Start Docker Desktop when you log in"
2. **(Opcional) Task Scheduler**: para ejecutar `docker-compose up -d` explícitamente al iniciar sesión si Docker Desktop no arranca los compose solo. Crear tarea con trigger "At log on" y acción ejecutando:
   ```
   docker-compose -f C:\ruta\a\bimeg-dbprecios\docker-compose.yml up -d
   ```

### Linux
1. **Docker systemd**: `sudo systemctl enable docker` — Docker arranca solo en cada boot
2. Los containers con `restart: always` se levantan automáticamente
3. **(Opcional) systemd service custom** si se quiere mayor control:
   ```ini
   # /etc/systemd/system/bimeg-dbprecios.service
   [Unit]
   Description=bimeg-dbprecios
   After=docker.service
   Requires=docker.service

   [Service]
   WorkingDirectory=/ruta/a/bimeg-dbprecios
   ExecStart=/usr/bin/docker-compose up
   ExecStop=/usr/bin/docker-compose down
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   Luego `sudo systemctl enable bimeg-dbprecios`.

### macOS
1. **Docker Desktop**: Settings → General → activar "Start Docker Desktop when you log in"
2. Los containers con `restart: always` se levantan automáticamente cuando Docker arranca

---

## Extensibilidad: Agregar nuevas fuentes

El usuario solo necesita editar `sources.yml` y agregar una nueva entrada bajo `apis`, `static_pages` o `dynamic_pages`. El workflow de n8n detecta las fuentes habilitadas dinámicamente al leer `/sources` en cada ejecución — no hay que modificar el workflow.

---

## Orden de implementación

1. Estructura base del repositorio (carpetas, `.gitignore`, `.env.example` con todas las vars)
2. Schema SQL de Supabase (`db/schema.sql`) + ejecutarlo en el proyecto existente
3. Microservicio scraper (Dockerfile, FastAPI, config_loader, scraper con Playwright)
4. `docker-compose.yml` con ambos servicios (incluyendo `TZ`, `N8N_ENCRYPTION_KEY`, pass-through de `SUPABASE_*`)
5. Workflow de n8n (crear en UI, configurar nodos con `{{ $env.VAR }}`, probar, exportar como JSON)
6. `sources.yml` con ejemplos de cada tipo (api, static, dynamic)
7. `CLAUDE.md` del proyecto (convenciones, comandos frecuentes)
8. `README.md` con instrucciones completas multi-plataforma

---

## Verificación

### Local (primera máquina):
- `docker-compose up -d` levanta ambos servicios sin errores
- `GET localhost:8000/health` responde 200
- `GET localhost:8000/sources` devuelve las fuentes del sources.yml
- Activar el workflow manualmente en n8n y verificar que:
  - Se conecta al scraper service
  - Las expresiones `{{ $env.SUPABASE_* }}` se resuelven correctamente
  - Datos llegan normalizados
  - Se borran y reinsertan en Supabase correctamente
- Verificar en el dashboard de Supabase que la tabla `productos` tiene datos
- Reiniciar el equipo y confirmar que Docker y los containers se levantan solos

### Portabilidad (segunda máquina — test real del requisito):
- Clonar el repo
- Seguir los 11 pasos del README desde cero
- Confirmar que con solo completar `.env` e importar el workflow JSON, el sistema funciona igual
- Verificar que el cron ejecuta a la hora local correcta (no UTC)
