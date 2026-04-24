# bimeg-dbprecios

Agregador diario de precios de materiales de construcción desde APIs y páginas
web de proveedores argentinos. Normaliza todo a una tabla única en PostgreSQL
para usarse en presupuestos de obra.

**Stack**: n8n (orquestador) + microservicio Python/Playwright (scraping) +
PostgreSQL (local o Supabase cloud), todo en Docker Compose.

**Documento de diseño**: [`PLAN.md`](./PLAN.md).

---

## Características

- **100% portable**: `git clone`, completar `.env`, `docker-compose up` y listo.
- **Dos modos**: DB local en containers (dev) o Supabase cloud (prod). Se
  cambia con una sola variable de entorno.
- **Extensibilidad declarativa**: agregar una fuente nueva = editar
  `sources.yml`, sin tocar código.
- **Sin historial**: cada corrida reemplaza los datos de la fuente. Datos
  siempre frescos, sin datos huérfanos.

---

## Prerequisitos

- **Docker Desktop** (Windows/Mac) o **Docker Engine + docker-compose** (Linux)
- **Git**
- **openssl** (para generar la clave de encriptación de n8n)
  - Windows: incluido con Git for Windows
  - Mac/Linux: incluido por defecto

---

## Instalación — 10 pasos

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/bimeg-dbprecios.git
cd bimeg-dbprecios
```

### 2. Crear `.env` a partir de la plantilla

```bash
# Linux/Mac
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

### 3. Generar la clave de encriptación de n8n

Pegala en `.env` como `N8N_ENCRYPTION_KEY=...`

```bash
openssl rand -hex 32
```

**Crítico**: sin esto, n8n genera una clave distinta en cada arranque y los
datos persistidos quedan inutilizables al cambiar de máquina.

### 4. Elegir modo: LOCAL o PRODUCCIÓN

#### Modo LOCAL (recomendado para desarrollo)

Dejá los valores por defecto en `.env`:

```
SUPABASE_URL=http://postgrest:3000
SUPABASE_ANON_KEY=local-dev-no-auth
```

Saltá al paso 6.

#### Modo PRODUCCIÓN (Supabase cloud)

1. Crear cuenta gratuita en https://supabase.com
2. Crear un proyecto nuevo
3. Ir a **Settings → API** y copiar `Project URL` y `anon public key`
4. En `.env`, comentar las líneas de local y descomentar las de producción:
   ```
   SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
   SUPABASE_ANON_KEY=eyJhbGciOi...
   ```
5. Ir al **SQL Editor** de Supabase y ejecutar el contenido de
   [`db/schema.sql`](./db/schema.sql) (una sola vez)

### 5. Configurar contraseña de n8n

En `.env`:

```
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=una_password_fuerte
```

### 6. Editar `sources.yml` (opcional)

Por defecto todas las fuentes vienen con `enabled: false`. Habilitá o agregá
las que quieras usar. Ver [`sources.yml`](./sources.yml) para ejemplos.

### 7. Levantar los containers

```bash
# Modo LOCAL (levanta n8n + scraper + postgres + postgrest)
docker-compose --profile local up -d

# Modo PRODUCCIÓN (levanta solo n8n + scraper)
docker-compose up -d
```

La primera vez tarda varios minutos (baja imagen de Playwright + compila el
scraper). Las siguientes arrancan en segundos.

### 8. Verificar que los servicios estén sanos

```bash
docker-compose ps
```

Todos los servicios deben estar en estado `healthy` o `running`.

### 9. Importar el workflow de n8n

1. Abrir http://localhost:5678 en el navegador
2. Loguearse con `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD`
3. **Workflows → Import from File** →
   [`n8n/workflows/daily-price-sync.json`](./n8n/workflows/daily-price-sync.json)
4. El workflow aparece importado con el nombre `daily-price-sync`

### 10. Activar el workflow

En la vista del workflow, togglear el switch **Active** en la esquina superior
derecha.

A partir de ese momento se ejecuta todos los días a las 06:00 hora local
(configurable cambiando el cron trigger del primer nodo).

**Para testear manualmente**: botón `Execute Workflow` dentro de la UI.

---

## Verificación end-to-end

```bash
# 1. El scraper responde
docker-compose exec scraper-service \
    python -c "import httpx; print(httpx.get('http://localhost:8000/health').json())"

# 2. Las fuentes se parsean correctamente
docker-compose exec scraper-service \
    python -c "import httpx; print(httpx.get('http://localhost:8000/sources').json())"

# 3. (Modo local) La tabla existe y se puede consultar
docker-compose exec postgres \
    psql -U postgres -d postgres -c "SELECT COUNT(*) FROM productos;"

# 4. (Modo prod) Verificar en el dashboard de Supabase:
#    Table Editor → productos
```

---

## Auto-inicio al encender la computadora

Con `restart: always` en `docker-compose.yml`, los containers levantan solos
apenas Docker arranca. Lo que hay que asegurar es que **Docker arranque solo**.

### Windows

1. **Docker Desktop → Settings → General**
2. Activar **"Start Docker Desktop when you log in"**
3. (Opcional) Si querés asegurar que el compose se levante explícitamente al
   iniciar sesión, crear una tarea en el **Programador de Tareas**:
   - **Trigger**: At log on
   - **Action**: Start a program
   - **Program**: `docker-compose`
   - **Arguments**: `-f C:\ruta\a\bimeg-dbprecios\docker-compose.yml --profile local up -d`

### Linux

```bash
sudo systemctl enable docker
```

Los containers con `restart: always` levantan solos. Si querés más control,
crear un `systemd` service:

```ini
# /etc/systemd/system/bimeg-dbprecios.service
[Unit]
Description=bimeg-dbprecios
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/ruta/a/bimeg-dbprecios
ExecStart=/usr/bin/docker-compose --profile local up -d
ExecStop=/usr/bin/docker-compose down

[Install]
WantedBy=multi-user.target
```

Luego:
```bash
sudo systemctl enable bimeg-dbprecios
sudo systemctl start bimeg-dbprecios
```

### macOS

1. **Docker Desktop → Settings → General**
2. Activar **"Start Docker Desktop when you log in"**

---

## Agregar una fuente nueva

### Caso: API REST pública

1. Editar `sources.yml`, agregar bajo `apis:`:
   ```yaml
   - name: "mi-api"
     enabled: true
     endpoint: "https://api.proveedor.com/productos"
     auth_header: "Authorization"
     auth_value: "Bearer ${MI_API_KEY}"
     field_mappings:
       descripcion: "nombre"
       precio: "precio"
       # ...
     empresa: "Mi Empresa"
     proveedor: "Mi Proveedor"
   ```
2. Agregar en `.env`: `MI_API_KEY=...`
3. En `docker-compose.yml`, pasar `MI_API_KEY: ${MI_API_KEY}` al container n8n
   y/o scraper
4. Implementar la lógica en la rama "Fetch API source (TODO)" del workflow
5. Reiniciar:
   ```bash
   docker-compose restart scraper-service n8n
   ```

### Caso: Página estática o dinámica

1. Editar `sources.yml`, agregar bajo `static_pages:` o `dynamic_pages:`
2. Implementar la función en `scraper/scraper.py` (los TODOs están marcados)
3. Rebuild del container:
   ```bash
   docker-compose build scraper-service
   docker-compose up -d scraper-service
   ```

---

## Troubleshooting

### El workflow falla con `Bearer undefined`

Significa que `SUPABASE_ANON_KEY` no está llegando al container n8n. Verificá
que `.env` esté completo y **reiniciá** n8n:

```bash
docker-compose restart n8n
```

### El cron se ejecuta a una hora distinta de la esperada

El container usa UTC si `TZ` no está bien seteada. En `.env`:

```
TZ=America/Argentina/Buenos_Aires
GENERIC_TIMEZONE=America/Argentina/Buenos_Aires
```

Reiniciar n8n después de cambiar.

### "productos" no existe en Postgres local

Los scripts de `/docker-entrypoint-initdb.d/` sólo se ejecutan la **primera vez
que el container arranca**. Si cambiaste el schema, reseteá:

```bash
docker-compose down -v
rm -rf postgres_data
docker-compose --profile local up -d
```

### La imagen del scraper tarda mucho en compilar

Es normal la primera vez (~5 min): baja ~1.5 GB de Playwright con los browsers.
Después queda cacheada.

---

## Estructura del repo

```
bimeg-dbprecios/
├── docker-compose.yml            Orquestación de los 4 servicios
├── .env.example                  Plantilla de variables
├── sources.yml                   Declaración de fuentes (editable)
├── PLAN.md                       Documento de diseño detallado
├── CLAUDE.md                     Convenciones para Claude Code
├── README.md                     Este archivo
├── db/
│   ├── schema.sql                DDL canónico (Supabase + local)
│   └── init-local.sql            Roles/grants sólo para Postgres local
├── n8n/
│   └── workflows/
│       └── daily-price-sync.json Workflow exportado
└── scraper/
    ├── Dockerfile                Imagen del microservicio
    ├── requirements.txt
    ├── main.py                   API FastAPI
    ├── scraper.py                Lógica de Playwright (STUBS actualmente)
    └── config_loader.py          Parseo de sources.yml
```

---

## Licencia

TBD.
