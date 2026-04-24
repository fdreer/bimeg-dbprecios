# Diseño: Scraper de Guanzetti S.A.

**Fecha:** 2026-04-24
**Estado:** Aprobado

---

## Contexto

Guanzetti S.A. (`guanzetti.com.ar`) es un proveedor de materiales de construcción en Argentina. Se quiere incorporar su catálogo completo al agregador de precios diario.

**Resultado de la investigación de API pública:**
La plataforma utilizada es TiendaPower (e-commerce argentino). TiendaPower tiene una API privada B2B (para que las tiendas sincronicen su stock), pero **no está disponible públicamente**. Se descartó el uso de API.

---

## Decisión de enfoque

**Opción elegida: Sitemap → páginas de detalle de producto (httpx + BeautifulSoup)**

Razones:
- El sitio es **server-side rendered**: los datos están en el HTML, sin necesidad de JS/Playwright.
- El `sitemap.xml` lista todas las URLs de producto de forma única → **deduplicación automática** sin lógica extra.
- Las páginas de detalle tienen todos los campos requeridos.
- `robots.txt` sin restricciones para crawlers.

Alternativas descartadas:
- *Scraping por categoría*: más rápido pero los listados omiten código de producto y marca.
- *Scraping dinámico con Playwright*: innecesario, el HTML ya viene renderizado del servidor.

---

## Campos a extraer

| Campo DB | Fuente en HTML | Notas |
|----------|---------------|-------|
| `descripcion` | `<h1>` text | Nombre completo del producto |
| `precio` | `<h2>` text | Formato `$209.034,00` → strip `$`, quitar `.` miles, reemplazar `,` por `.` → float |
| `disponibilidad` | `<strong>DISPONIBILIDAD:</strong>` → siguiente `<strong>` hermano | Valor ej: `"Stock disponible"` |
| `codigo_producto` | `<strong>CÓDIGO:</strong>` → nodo de texto siguiente (`.next_sibling`) | Valor ej: `"99074"` |
| `url_imagen` | `<img src>` con dominio `images.guanzetti.com.ar` | Primera imagen del producto |
| `url_producto` | URL extraída del sitemap directamente | Completa, no relativa |
| `empresa` | Estático: `"Guanzetti S.A."` | |
| `proveedor` | Estático: `"Guanzetti"` | |
| `fuente` | Estático: `"guanzetti"` | Clave para DELETE/INSERT en n8n |
| `categoria` | `null` | No requerida por el usuario |
| `marca` | `null` | No requerida; puede agregarse después |
| `unidad_medida` | `null` | No disponible fácilmente en el sitio |

---

## Cambio al schema de la tabla `productos`

Se agrega la columna `disponibilidad` que no existe actualmente:

```sql
ALTER TABLE productos ADD COLUMN disponibilidad VARCHAR(100);
```

**Restricción:** Este cambio se aplica **solo al Postgres local** durante desarrollo. No se toca la DB de producción (Supabase) en esta iteración.

El archivo `db/schema.sql` se actualiza con la nueva columna para que quede documentado.

---

## Nuevo tipo de fuente: `sitemap_pages`

El modelo de fuentes existente (`static_pages`, `dynamic_pages`) asume una `base_url` con paginación por categoría. Guanzetti sigue un flujo distinto (sitemap → páginas de detalle), por lo que se agrega un tercer tipo de fuente.

### Entrada en `sources.yml`

```yaml
sitemap_pages:
  - name: "guanzetti"
    enabled: true
    sitemap_url: "https://www.guanzetti.com.ar/sitemap.xml"
    empresa: "Guanzetti S.A."
    proveedor: "Guanzetti"
    concurrency: 5
    delay_seconds: 0.5
```

### Modelo Pydantic (`SitemapPageSource`)

```python
class SitemapPageSource(BaseModel):
    type: Literal["sitemap"] = "sitemap"
    name: str
    enabled: bool
    sitemap_url: str
    empresa: str
    proveedor: str
    concurrency: int = 5
    delay_seconds: float = 0.5
```

---

## Flujo de scraping

```
1. GET sitemap_url
      ↓
2. Parsear XML → filtrar URLs que contienen /product/
      ↓
3. Para cada URL (con asyncio.Semaphore(concurrency)):
      a. GET url_producto (httpx async, timeout 15s, 3 reintentos)
      b. Parsear HTML con BeautifulSoup
      c. Extraer campos según selectores
      d. Normalizar precio (strip "$", "." miles, "," decimal → float)
      e. Esperar delay_seconds
      ↓
4. Devolver lista de productos normalizados
```

### Lógica de reintentos

- **HTTP 5xx / timeout**: reintentar hasta 3 veces con backoff exponencial (1s, 2s, 4s)
- **HTTP 404**: loguear y skip (producto eliminado del sitio)
- **Error de parsing**: loguear con URL y skip (no interrumpir el lote)

---

## Archivos a crear / modificar

| Archivo | Tipo | Descripción del cambio |
|---------|------|----------------------|
| `db/schema.sql` | Modificar | Agregar columna `disponibilidad VARCHAR(100)` |
| `sources.yml` | Modificar | Agregar sección `sitemap_pages` con entrada `guanzetti` |
| `scraper/config_loader.py` | Modificar | Agregar modelo `SitemapPageSource`; actualizar `SourcesConfig` y `enabled_sources()` |
| `scraper/scraper.py` | Modificar | Agregar función `scrape_sitemap_source()` |
| `scraper/main.py` | Modificar | Agregar endpoint `POST /scrape/sitemap` |
| `n8n/workflows/daily-price-sync.json` | Modificar | Agregar rama `sitemap` en el nodo Switch |

---

## Estimación de rendimiento

- Productos en sitemap: ~1000
- Concurrencia: 5 workers simultáneos
- Delay entre requests: 0.5s
- Tiempo de red estimado por request: 0.5-1s
- **Estimado total: 3-6 minutos**

Aceptable para un job diario. Si en el futuro el catálogo crece significativamente, se puede aumentar `concurrency` en `sources.yml` sin cambiar código.

---

## Qué NO se hace en esta iteración

- No se aplican cambios en la DB de producción (Supabase).
- No se implementan otros proveedores.
- No se extrae `marca` ni `categoria` de Guanzetti.
- No se implementa cache del sitemap (se descarga fresco en cada ejecución).
