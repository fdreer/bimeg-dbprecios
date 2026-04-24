# Guanzetti Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar scraping del catálogo completo de guanzetti.com.ar usando el sitemap XML como índice de URLs únicas y BeautifulSoup para parsear las páginas de detalle de cada producto.

**Architecture:** El scraper descarga `sitemap.xml`, filtra URLs de tipo `/product/`, y scrapea cada página de detalle de forma asincrónica con concurrencia controlada. No requiere Playwright — el sitio es server-side rendered. La deduplicación es automática: el sitemap lista cada producto una sola vez.

**Tech Stack:** Python 3.11, httpx (async), BeautifulSoup4, lxml, pytest, pytest-asyncio. n8n para orquestación.

---

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---------|--------|-----------------|
| `db/schema.sql` | Modificar | Agregar columna `disponibilidad` |
| `scraper/requirements.txt` | Modificar | Agregar pytest y pytest-asyncio |
| `scraper/tests/__init__.py` | Crear | Paquete de tests |
| `scraper/tests/fixtures/product_page.html` | Crear | HTML de producto real para tests |
| `scraper/tests/fixtures/sitemap.xml` | Crear | XML de sitemap para tests |
| `scraper/tests/test_config_loader.py` | Crear | Tests del modelo SitemapPageSource |
| `scraper/tests/test_scraper_guanzetti.py` | Crear | Tests de parsing y extracción |
| `scraper/config_loader.py` | Modificar | Agregar `SitemapPageSource`; actualizar `SourcesConfig`, `enabled_sources()`, `find_source()` |
| `scraper/scraper.py` | Modificar | Agregar `scrape_sitemap_source()` y funciones auxiliares |
| `scraper/main.py` | Modificar | Agregar endpoint `POST /scrape/sitemap` |
| `sources.yml` | Modificar | Agregar sección `sitemap_pages` con entrada `guanzetti` |
| `n8n/workflows/daily-price-sync.json` | Modificar | Agregar rama `sitemap` al Switch; nodo POST /scrape/sitemap; Merge 4 inputs |

---

## Task 1: Agregar columna `disponibilidad` al schema SQL

**Files:**
- Modify: `db/schema.sql`

- [ ] **Step 1: Agregar columna en schema.sql**

Abrir `db/schema.sql` y reemplazar el bloque de `CREATE TABLE IF NOT EXISTS productos` con esta versión (agrega `disponibilidad` antes de `fuente`):

```sql
CREATE TABLE IF NOT EXISTS productos (
  id              UUID           DEFAULT gen_random_uuid() PRIMARY KEY,
  codigo_producto VARCHAR(255),
  descripcion     TEXT           NOT NULL,
  precio          NUMERIC(12, 2) NOT NULL,
  url_producto    TEXT,
  url_imagen      TEXT,
  disponibilidad  VARCHAR(100),
  categoria       VARCHAR(255),
  empresa         VARCHAR(255),
  marca           VARCHAR(255),
  proveedor       VARCHAR(255),
  unidad_medida   VARCHAR(50),
  fuente          VARCHAR(100),
  actualizado_en  TIMESTAMPTZ    DEFAULT NOW()
);
```

También agregar el comment debajo de los existentes:

```sql
COMMENT ON COLUMN productos.disponibilidad IS 'Estado de stock del proveedor (ej: "Stock disponible", "Sin stock").';
```

- [ ] **Step 2: Aplicar a la DB local (NO producción)**

```bash
docker-compose --profile local up -d
docker-compose exec postgres psql -U postgres -d postgres -c \
  "ALTER TABLE productos ADD COLUMN IF NOT EXISTS disponibilidad VARCHAR(100);"
```

Salida esperada: `ALTER TABLE`

- [ ] **Step 3: Verificar la columna**

```bash
docker-compose exec postgres psql -U postgres -d postgres -c \
  "\d productos"
```

Verificar que aparece la columna `disponibilidad character varying(100)`.

- [ ] **Step 4: Commit**

```bash
git add db/schema.sql
git commit -m "feat: add disponibilidad column to productos schema"
```

---

## Task 2: Configurar infraestructura de tests

**Files:**
- Modify: `scraper/requirements.txt`
- Create: `scraper/tests/__init__.py`
- Create: `scraper/tests/fixtures/product_page.html`
- Create: `scraper/tests/fixtures/sitemap.xml`

- [ ] **Step 1: Agregar dependencias de test a requirements.txt**

Agregar al final de `scraper/requirements.txt`:

```
pytest==8.3.5
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Crear paquete de tests**

Crear `scraper/tests/__init__.py` (vacío):

```python
```

- [ ] **Step 3: Crear fixture de HTML de producto**

Crear `scraper/tests/fixtures/product_page.html`:

```html
<!DOCTYPE html>
<html>
<head><title>Juego Bidet Fv Alerce 295/D7 Cr</title></head>
<body>
  <h1>Juego Bidet Fv Alerce 295/D7 Cr</h1>
  <h2>$209,034.00</h2>
  <div class="product-details">
    <p><strong>CÓDIGO:</strong> 99074</p>
    <p><strong>DISPONIBILIDAD:</strong> <strong>Stock disponible</strong></p>
    <p><strong>STOCK DISPONIBLE:</strong> 1</p>
  </div>
  <div class="product-images">
    <a href="#">
      <img src="https://images.guanzetti.com.ar/products/5af3525b16a571525895771.jpg"
           alt="Juego Bidet Fv Alerce 295/D7 Cr">
    </a>
  </div>
</body>
</html>
```

- [ ] **Step 4: Crear fixture de sitemap XML**

Crear `scraper/tests/fixtures/sitemap.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.guanzetti.com.ar/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://www.guanzetti.com.ar/category/materiales-gruesos-corralon</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://www.guanzetti.com.ar/product/ladrillo-hueco-del-12-x-unidad</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://www.guanzetti.com.ar/product/cemento-loma-negra-40kg</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
```

- [ ] **Step 5: Commit**

```bash
git add scraper/requirements.txt scraper/tests/
git commit -m "test: add pytest infrastructure and HTML/XML fixtures"
```

---

## Task 3: Agregar `SitemapPageSource` a `config_loader.py`

**Files:**
- Create: `scraper/tests/test_config_loader.py`
- Modify: `scraper/config_loader.py`

- [ ] **Step 1: Escribir los tests que deben fallar**

Crear `scraper/tests/test_config_loader.py`:

```python
"""Tests para SitemapPageSource y su integración en SourcesConfig."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import SitemapPageSource, SourcesConfig, find_source, load_sources


def _make_sitemap_source(**kwargs) -> SitemapPageSource:
    defaults = {
        "name": "guanzetti",
        "enabled": True,
        "sitemap_url": "https://www.guanzetti.com.ar/sitemap.xml",
        "empresa": "Guanzetti S.A.",
        "proveedor": "Guanzetti",
    }
    return SitemapPageSource(**{**defaults, **kwargs})


class TestSitemapPageSource:
    def test_type_is_sitemap(self):
        src = _make_sitemap_source()
        assert src.type == "sitemap"

    def test_defaults(self):
        src = _make_sitemap_source()
        assert src.concurrency == 5
        assert src.delay_seconds == 0.5
        assert src.enabled is True

    def test_disabled_source(self):
        src = _make_sitemap_source(enabled=False)
        assert src.enabled is False


class TestSourcesConfigWithSitemap:
    def test_sitemap_pages_field_exists(self):
        config = SourcesConfig()
        assert hasattr(config, "sitemap_pages")
        assert config.sitemap_pages == []

    def test_enabled_sources_includes_sitemap(self):
        src = _make_sitemap_source()
        config = SourcesConfig(sitemap_pages=[src])
        enabled = config.enabled_sources()
        assert any(s.name == "guanzetti" for s in enabled)

    def test_disabled_sitemap_excluded(self):
        src = _make_sitemap_source(enabled=False)
        config = SourcesConfig(sitemap_pages=[src])
        enabled = config.enabled_sources()
        assert not any(s.name == "guanzetti" for s in enabled)

    def test_find_source_finds_sitemap(self):
        src = _make_sitemap_source()
        config = SourcesConfig(sitemap_pages=[src])
        found = find_source(config, "guanzetti")
        assert found is not None
        assert found.type == "sitemap"

    def test_find_source_returns_none_when_missing(self):
        config = SourcesConfig()
        assert find_source(config, "nonexistent") is None
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
cd scraper
python -m pytest tests/test_config_loader.py -v
```

Salida esperada: `ImportError: cannot import name 'SitemapPageSource' from 'config_loader'`

- [ ] **Step 3: Implementar `SitemapPageSource` en `config_loader.py`**

Abrir `scraper/config_loader.py`.

**3a.** Agregar el nuevo modelo después de la clase `DynamicPageSource` (línea ~87):

```python
class SitemapPageSource(BaseModel):
    """Fuente basada en sitemap XML — scrapea páginas de detalle de producto."""

    type: Literal["sitemap"] = "sitemap"
    name: str
    enabled: bool = True
    sitemap_url: str
    empresa: str = ""
    proveedor: str = ""
    concurrency: int = 5
    delay_seconds: float = 0.5
```

**3b.** Reemplazar la línea del type alias `Source`:

```python
Source = ApiSource | StaticPageSource | DynamicPageSource | SitemapPageSource
```

**3c.** Reemplazar la clase `SourcesConfig` completa:

```python
class SourcesConfig(BaseModel):
    """Configuración completa parseada de sources.yml."""

    apis: list[ApiSource] = Field(default_factory=list)
    static_pages: list[StaticPageSource] = Field(default_factory=list)
    dynamic_pages: list[DynamicPageSource] = Field(default_factory=list)
    sitemap_pages: list[SitemapPageSource] = Field(default_factory=list)

    def enabled_sources(self) -> list[Source]:
        """Devuelve todas las fuentes habilitadas, marcadas con su tipo."""
        result: list[Source] = []
        result.extend(s for s in self.apis if s.enabled)
        result.extend(s for s in self.static_pages if s.enabled)
        result.extend(s for s in self.dynamic_pages if s.enabled)
        result.extend(s for s in self.sitemap_pages if s.enabled)
        return result
```

**3d.** Reemplazar la función `find_source`:

```python
def find_source(config: SourcesConfig, name: str) -> Source | None:
    """Busca una fuente por su ``name`` en cualquiera de las categorías."""
    for source in (
        *config.apis,
        *config.static_pages,
        *config.dynamic_pages,
        *config.sitemap_pages,
    ):
        if source.name == name:
            return source
    return None
```

- [ ] **Step 4: Verificar que los tests pasan**

```bash
cd scraper
python -m pytest tests/test_config_loader.py -v
```

Salida esperada: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/config_loader.py scraper/tests/test_config_loader.py
git commit -m "feat: add SitemapPageSource model to config_loader"
```

---

## Task 4: Implementar `scrape_sitemap_source()` en `scraper.py`

**Files:**
- Create: `scraper/tests/test_scraper_guanzetti.py`
- Modify: `scraper/scraper.py`

- [ ] **Step 1: Escribir tests que deben fallar**

Crear `scraper/tests/test_scraper_guanzetti.py`:

```python
"""Tests para las funciones de scraping de Guanzetti."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import SitemapPageSource

FIXTURES = Path(__file__).parent / "fixtures"


def _load_html() -> str:
    return (FIXTURES / "product_page.html").read_text(encoding="utf-8")


def _load_xml() -> str:
    return (FIXTURES / "sitemap.xml").read_text(encoding="utf-8")


def _make_source() -> SitemapPageSource:
    return SitemapPageSource(
        name="guanzetti",
        enabled=True,
        sitemap_url="https://www.guanzetti.com.ar/sitemap.xml",
        empresa="Guanzetti S.A.",
        proveedor="Guanzetti",
    )


# ---------------------------------------------------------------------------
# _parse_precio
# ---------------------------------------------------------------------------

class TestParsePrecio:
    def test_us_format_with_thousands(self):
        from scraper import _parse_precio
        assert _parse_precio("$209,034.00") == pytest.approx(209034.00)

    def test_us_format_simple(self):
        from scraper import _parse_precio
        assert _parse_precio("$714.87") == pytest.approx(714.87)

    def test_argentine_format(self):
        from scraper import _parse_precio
        assert _parse_precio("$209.034,00") == pytest.approx(209034.00)

    def test_returns_none_on_invalid(self):
        from scraper import _parse_precio
        assert _parse_precio("sin precio") is None

    def test_strips_spaces(self):
        from scraper import _parse_precio
        assert _parse_precio("  $1,500.00  ") == pytest.approx(1500.00)


# ---------------------------------------------------------------------------
# _extract_label_text
# ---------------------------------------------------------------------------

class TestExtractLabelText:
    def test_extracts_codigo(self):
        from scraper import _extract_label_text
        soup = BeautifulSoup(_load_html(), "lxml")
        result = _extract_label_text(soup, "CÓDIGO")
        assert result == "99074"

    def test_returns_none_when_label_missing(self):
        from scraper import _extract_label_text
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        assert _extract_label_text(soup, "CÓDIGO") is None


# ---------------------------------------------------------------------------
# _extract_label_strong
# ---------------------------------------------------------------------------

class TestExtractLabelStrong:
    def test_extracts_disponibilidad(self):
        from scraper import _extract_label_strong
        soup = BeautifulSoup(_load_html(), "lxml")
        result = _extract_label_strong(soup, "DISPONIBILIDAD")
        assert result == "Stock disponible"

    def test_returns_none_when_label_missing(self):
        from scraper import _extract_label_strong
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        assert _extract_label_strong(soup, "DISPONIBILIDAD") is None


# ---------------------------------------------------------------------------
# _parse_product_page
# ---------------------------------------------------------------------------

class TestParseProductPage:
    def test_full_product_parse(self):
        from scraper import _parse_product_page
        source = _make_source()
        url = "https://www.guanzetti.com.ar/product/juego-bidet-fv-alerce-295-d7-cr"
        result = _parse_product_page(_load_html(), url, source)

        assert result is not None
        assert result["descripcion"] == "Juego Bidet Fv Alerce 295/D7 Cr"
        assert result["precio"] == pytest.approx(209034.00)
        assert result["codigo_producto"] == "99074"
        assert result["disponibilidad"] == "Stock disponible"
        assert "images.guanzetti.com.ar" in result["url_imagen"]
        assert result["url_producto"] == url
        assert result["empresa"] == "Guanzetti S.A."
        assert result["proveedor"] == "Guanzetti"
        assert result["fuente"] == "guanzetti"

    def test_returns_none_when_no_description(self):
        from scraper import _parse_product_page
        source = _make_source()
        html = "<html><body><h2>$100.00</h2></body></html>"
        result = _parse_product_page(html, "https://example.com/product/x", source)
        assert result is None

    def test_returns_none_when_no_price(self):
        from scraper import _parse_product_page
        source = _make_source()
        html = "<html><body><h1>Producto</h1></body></html>"
        result = _parse_product_page(html, "https://example.com/product/x", source)
        assert result is None


# ---------------------------------------------------------------------------
# _filter_product_urls (parsing del sitemap)
# ---------------------------------------------------------------------------

class TestFilterProductUrls:
    def test_filters_only_product_urls(self):
        from scraper import _filter_product_urls
        xml_text = _load_xml()
        urls = _filter_product_urls(xml_text)
        assert len(urls) == 2
        assert all("/product/" in u for u in urls)

    def test_full_urls_returned(self):
        from scraper import _filter_product_urls
        urls = _filter_product_urls(_load_xml())
        assert "https://www.guanzetti.com.ar/product/ladrillo-hueco-del-12-x-unidad" in urls
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
cd scraper
python -m pytest tests/test_scraper_guanzetti.py -v
```

Salida esperada: `ImportError: cannot import name '_parse_precio' from 'scraper'`

- [ ] **Step 3: Implementar las funciones en `scraper.py`**

Reemplazar el contenido completo de `scraper/scraper.py` con:

```python
"""
Lógica de scraping.

Implementaciones:
    - scrape_sitemap_source(): sitemap XML → páginas de detalle (httpx async + BeautifulSoup).
      Usado para guanzetti.com.ar (TiendaPower, server-side rendered).

Stubs pendientes de implementar:
    - scrape_static_page(): httpx + BeautifulSoup para páginas con paginación por categoría.
    - scrape_dynamic_page(): Playwright para páginas con JS.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from bs4 import BeautifulSoup, NavigableString

from config_loader import DynamicPageSource, SitemapPageSource, StaticPageSource

log = logging.getLogger("scraper")

# ============================================================================
# Formato de producto normalizado (contrato con n8n / Supabase)
# ============================================================================
#
# {
#     "codigo_producto": str | None,
#     "descripcion":     str,          # requerido
#     "precio":          float,        # requerido
#     "disponibilidad":  str | None,
#     "url_producto":    str | None,
#     "url_imagen":      str | None,
#     "categoria":       str | None,
#     "empresa":         str,
#     "marca":           str | None,
#     "proveedor":       str,
#     "unidad_medida":   str | None,
#     "fuente":          str,          # coincide con source.name
# }


# ============================================================================
# Scraper de sitemap (guanzetti.com.ar / TiendaPower)
# ============================================================================

async def scrape_sitemap_source(source: SitemapPageSource) -> list[dict[str, Any]]:
    """
    Scrapea un catálogo completo usando el sitemap XML como índice.

    Flujo:
        1. GET sitemap_url → extraer URLs de /product/*.
        2. Para cada URL (con Semaphore para concurrencia limitada):
           GET página → parsear HTML → normalizar datos.
        3. Devolver lista de productos normalizados.
    """
    sem = asyncio.Semaphore(source.concurrency)

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "bimeg-dbprecios/1.0 (price aggregator)"},
    ) as client:
        sitemap_xml = await _fetch_text(source.sitemap_url, client)
        if sitemap_xml is None:
            log.error("Could not fetch sitemap: %s", source.sitemap_url)
            return []

        product_urls = _filter_product_urls(sitemap_xml)
        log.info("[%s] Found %d product URLs in sitemap", source.name, len(product_urls))

        tasks = [
            _scrape_product_with_semaphore(url, source, client, sem)
            for url in product_urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    productos = [r for r in results if isinstance(r, dict)]
    skipped = len(product_urls) - len(productos)
    log.info(
        "[%s] Scraped %d products (%d skipped/errors)",
        source.name, len(productos), skipped,
    )
    return productos


async def _scrape_product_with_semaphore(
    url: str,
    source: SitemapPageSource,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> dict[str, Any] | None:
    async with sem:
        html = await _fetch_text(url, client)
        await asyncio.sleep(source.delay_seconds)
        if html is None:
            return None
        return _parse_product_page(html, url, source)


async def _fetch_text(
    url: str,
    client: httpx.AsyncClient,
    max_retries: int = 3,
) -> str | None:
    """GET url con reintentos exponenciales. Devuelve None en error permanente."""
    for attempt in range(max_retries):
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                log.warning("404 — skipping: %s", url)
                return None
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as exc:
            if attempt == max_retries - 1:
                log.error("HTTP error fetching %s: %s", url, exc)
                return None
            await asyncio.sleep(2 ** attempt)
        except httpx.RequestError as exc:
            if attempt == max_retries - 1:
                log.error("Request error fetching %s: %s", url, exc)
                return None
            await asyncio.sleep(2 ** attempt)
    return None


# ============================================================================
# Funciones de parsing (públicas para testabilidad)
# ============================================================================

def _filter_product_urls(sitemap_xml: str) -> list[str]:
    """Parsea el XML del sitemap y devuelve solo las URLs de producto."""
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    try:
        root = ET.fromstring(sitemap_xml)
    except ET.ParseError as exc:
        log.error("Failed to parse sitemap XML: %s", exc)
        return []
    return [
        loc.text
        for loc in root.findall(".//sm:loc", ns)
        if loc.text and "/product/" in loc.text
    ]


def _parse_product_page(
    html: str,
    url: str,
    source: SitemapPageSource,
) -> dict[str, Any] | None:
    """Extrae datos de producto de una página de detalle de guanzetti.com.ar."""
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.find("h1")
    descripcion = h1.get_text(strip=True) if h1 else None
    if not descripcion:
        log.warning("No description at %s — skipping", url)
        return None

    h2 = soup.find("h2")
    precio = _parse_precio(h2.get_text(strip=True)) if h2 else None
    if precio is None:
        log.warning("No price at %s — skipping", url)
        return None

    img = soup.find("img", src=lambda s: s and "images.guanzetti.com.ar" in s)

    return {
        "codigo_producto": _extract_label_text(soup, "CÓDIGO"),
        "descripcion": descripcion,
        "precio": precio,
        "disponibilidad": _extract_label_strong(soup, "DISPONIBILIDAD"),
        "url_producto": url,
        "url_imagen": img["src"] if img else None,
        "categoria": None,
        "empresa": source.empresa,
        "marca": None,
        "proveedor": source.proveedor,
        "unidad_medida": None,
        "fuente": source.name,
    }


def _parse_precio(text: str) -> float | None:
    """
    Convierte texto de precio a float.

    Maneja formato US ($1,234.56) y argentino ($1.234,56).
    El separador decimal es el que aparece más a la derecha.
    """
    cleaned = text.strip().lstrip("$").strip()
    dot_pos = cleaned.rfind(".")
    comma_pos = cleaned.rfind(",")

    if dot_pos == -1 and comma_pos == -1:
        pass  # sin separadores: "209034"
    elif dot_pos > comma_pos:
        cleaned = cleaned.replace(",", "")          # US: quitar miles
    else:
        cleaned = cleaned.replace(".", "").replace(",", ".")  # ARG: quitar miles, decimal
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_label_text(soup: BeautifulSoup, label: str) -> str | None:
    """Busca <strong>LABEL:</strong> y devuelve el nodo de texto siguiente."""
    for tag in soup.find_all("strong"):
        if label in tag.get_text():
            sibling = tag.next_sibling
            if sibling and isinstance(sibling, NavigableString):
                value = str(sibling).strip()
                return value if value else None
    return None


def _extract_label_strong(soup: BeautifulSoup, label: str) -> str | None:
    """Busca <strong>LABEL:</strong> y devuelve el texto del siguiente <strong>."""
    for tag in soup.find_all("strong"):
        if label in tag.get_text():
            for sibling in tag.next_siblings:
                if hasattr(sibling, "name") and sibling.name == "strong":
                    return sibling.get_text(strip=True)
    return None


# ============================================================================
# Stubs (pendientes de implementar)
# ============================================================================

def _empty_product_stub(source_name: str) -> list[dict[str, Any]]:
    _ = source_name
    return []


def scrape_static_page(source: StaticPageSource) -> list[dict[str, Any]]:
    """
    Scrapea una página HTML estática.

    TODO: implementar
        1. httpx.get(source.base_url) con timeout y reintentos.
        2. BeautifulSoup(response.text, 'lxml').
        3. Iterar contenedores de productos y aplicar source.selectores.
        4. Manejo de paginación (si aplica, según config de la fuente).
        5. Normalizar al formato de producto.
    """
    return _empty_product_stub(source.name)


async def scrape_dynamic_page(source: DynamicPageSource) -> list[dict[str, Any]]:
    """
    Scrapea una página con contenido renderizado por JavaScript.

    TODO: implementar
        1. async with async_playwright() as p:
               browser = await p.chromium.launch(headless=True)
        2. page.goto(source.base_url, wait_until='networkidle').
        3. Iterar productos y aplicar source.selectores.
        4. Manejo de paginación.
    """
    return _empty_product_stub(source.name)
```

- [ ] **Step 4: Verificar que los tests pasan**

```bash
cd scraper
python -m pytest tests/test_scraper_guanzetti.py -v
```

Salida esperada: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper.py scraper/tests/test_scraper_guanzetti.py
git commit -m "feat: implement scrape_sitemap_source for guanzetti.com.ar"
```

---

## Task 5: Agregar endpoint `POST /scrape/sitemap` a `main.py`

**Files:**
- Modify: `scraper/main.py`

- [ ] **Step 1: Actualizar el import de `config_loader` en `main.py`**

En `scraper/main.py`, reemplazar la línea de import:

```python
from config_loader import (
    ApiSource,
    DynamicPageSource,
    SourcesConfig,
    StaticPageSource,
    find_source,
    load_sources,
)
```

Por:

```python
from config_loader import (
    ApiSource,
    DynamicPageSource,
    SitemapPageSource,
    SourcesConfig,
    StaticPageSource,
    find_source,
    load_sources,
)
```

- [ ] **Step 2: Agregar el endpoint al final de `main.py` (antes del comentario final)**

Agregar inmediatamente después del endpoint `scrape_dynamic`, antes del bloque de comentarios finales:

```python
@app.post("/scrape/sitemap")
async def scrape_sitemap(req: ScrapeRequest) -> list[dict[str, Any]]:
    """Ejecuta el scraper de sitemap (httpx + BeautifulSoup) para la fuente indicada."""
    config = get_config()
    source = find_source(config, req.source_name)

    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{req.source_name}' not found")
    if not isinstance(source, SitemapPageSource):
        raise HTTPException(
            status_code=400,
            detail=f"Source '{req.source_name}' is not a sitemap source (type={source.type})",
        )

    log.info("Scraping sitemap source: %s", source.name)
    return await scraper.scrape_sitemap_source(source)
```

- [ ] **Step 3: Verificar que el servidor arranca y el endpoint existe**

```bash
cd scraper
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/openapi.json | python -c "import sys,json; routes=[r for r in json.load(sys.stdin)['paths'].keys()]; print(routes)"
kill %1
```

Verificar que `/scrape/sitemap` aparece en la lista de rutas.

- [ ] **Step 4: Commit**

```bash
git add scraper/main.py
git commit -m "feat: add POST /scrape/sitemap endpoint"
```

---

## Task 6: Agregar guanzetti a `sources.yml`

**Files:**
- Modify: `sources.yml`

- [ ] **Step 1: Agregar sección `sitemap_pages` al final de `sources.yml`**

Agregar al final del archivo:

```yaml

# ============================================================================
# Páginas indexadas por sitemap XML
# ----------------------------------------------------------------------------
# El scraper descarga el sitemap, filtra URLs /product/ y scrapea cada página
# de detalle. Sin Playwright — el sitio es server-side rendered.
# Deduplicación automática: el sitemap lista cada producto una sola vez.
# ============================================================================
sitemap_pages:
  - name: "guanzetti"
    enabled: true
    sitemap_url: "https://www.guanzetti.com.ar/sitemap.xml"
    empresa: "Guanzetti S.A."
    proveedor: "Guanzetti"
    concurrency: 5
    delay_seconds: 0.5
```

- [ ] **Step 2: Verificar que el YAML es válido**

```bash
python -c "import yaml; yaml.safe_load(open('sources.yml')); print('OK')"
```

Salida esperada: `OK`

- [ ] **Step 3: Commit**

```bash
git add sources.yml
git commit -m "feat: add guanzetti source to sources.yml"
```

---

## Task 7: Actualizar el workflow de n8n

**Files:**
- Modify: `n8n/workflows/daily-price-sync.json`

El workflow necesita: (a) nueva condición en el nodo Switch para `type == "sitemap"`, (b) nuevo nodo HTTP que llame a `/scrape/sitemap`, (c) actualizar el nodo Merge de 3 a 4 inputs, y (d) nuevas conexiones.

- [ ] **Step 1: Agregar condición `sitemap` al nodo Switch**

En `n8n/workflows/daily-price-sync.json`, en el nodo `"Switch on type"` (id `a1b2c3d4-0004-...`), dentro de `parameters.rules.values`, agregar este objeto después de la condición `dynamic`:

```json
{
  "conditions": {
    "options": {
      "caseSensitive": true,
      "leftValue": "",
      "typeValidation": "strict"
    },
    "conditions": [
      {
        "id": "cond-sitemap",
        "leftValue": "={{ $json.type }}",
        "rightValue": "sitemap",
        "operator": {
          "type": "string",
          "operation": "equals"
        }
      }
    ],
    "combinator": "and"
  },
  "renameOutput": true,
  "outputKey": "sitemap"
}
```

- [ ] **Step 2: Agregar el nodo `POST /scrape/sitemap`**

En la lista `nodes`, agregar este objeto después del nodo `POST /scrape/dynamic`:

```json
{
  "parameters": {
    "method": "POST",
    "url": "={{ $env.SCRAPER_URL }}/scrape/sitemap",
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={\n  \"source_name\": \"{{ $json.name }}\"\n}",
    "options": {}
  },
  "id": "a1b2c3d4-000d-4000-8000-00000000000d",
  "name": "POST /scrape/sitemap",
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "position": [1160, 780]
}
```

- [ ] **Step 3: Actualizar el nodo Merge de 3 a 4 inputs**

En el nodo `"Merge branches"` (id `a1b2c3d4-0008-...`), cambiar:

```json
"numberInputs": 3
```

Por:

```json
"numberInputs": 4
```

- [ ] **Step 4: Agregar las nuevas conexiones**

En la sección `connections`, hacer dos cambios:

**4a.** En `"Switch on type"`, agregar el cuarto output a `"main"` (índice 3):

```json
"Switch on type": {
  "main": [
    [{"node": "Fetch API source (TODO)", "type": "main", "index": 0}],
    [{"node": "POST /scrape/static",     "type": "main", "index": 0}],
    [{"node": "POST /scrape/dynamic",    "type": "main", "index": 0}],
    [{"node": "POST /scrape/sitemap",    "type": "main", "index": 0}]
  ]
}
```

**4b.** Agregar la conexión del nuevo nodo al Merge (input 3):

```json
"POST /scrape/sitemap": {
  "main": [
    [
      {
        "node": "Merge branches",
        "type": "main",
        "index": 3
      }
    ]
  ]
}
```

- [ ] **Step 5: Validar JSON**

```bash
python -c "import json; json.load(open('n8n/workflows/daily-price-sync.json')); print('JSON válido')"
```

Salida esperada: `JSON válido`

- [ ] **Step 6: Commit**

```bash
git add n8n/workflows/daily-price-sync.json
git commit -m "feat: add sitemap branch to n8n workflow for guanzetti"
```

---

## Task 8: Rebuild y smoke test end-to-end

- [ ] **Step 1: Rebuild del container scraper**

```bash
docker-compose build scraper-service
docker-compose --profile local up -d
```

- [ ] **Step 2: Verificar que los tests pasan dentro del container**

```bash
docker-compose exec scraper-service python -m pytest /app/tests/ -v
```

Salida esperada: todos los tests en verde.

- [ ] **Step 3: Verificar `/sources` incluye guanzetti**

```bash
docker-compose exec scraper-service curl -s http://localhost:8000/sources | python -m json.tool
```

Verificar que aparece `{"type": "sitemap", "name": "guanzetti", "enabled": true, ...}`.

- [ ] **Step 4: Smoke test del scraper (primeras 5 URLs)**

Para no scrapear el catálogo completo, verificar manualmente con un producto real:

```bash
docker-compose exec scraper-service python -c "
import asyncio, httpx, json
from scraper import _filter_product_urls, _parse_product_page
from config_loader import SitemapPageSource

async def test():
    src = SitemapPageSource(
        name='guanzetti', enabled=True,
        sitemap_url='https://www.guanzetti.com.ar/sitemap.xml',
        empresa='Guanzetti S.A.', proveedor='Guanzetti',
    )
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        xml = (await client.get(src.sitemap_url)).text
        urls = _filter_product_urls(xml)
        print(f'Total product URLs: {len(urls)}')
        html = (await client.get(urls[0])).text
        prod = _parse_product_page(html, urls[0], src)
        print(json.dumps(prod, ensure_ascii=False, indent=2))

asyncio.run(test())
"
```

Verificar que aparece un producto con `descripcion`, `precio`, `codigo_producto`, `disponibilidad` y `url_imagen` correctos.

- [ ] **Step 5: Importar el workflow actualizado en n8n UI**

1. Abrir `http://localhost:5678`
2. Ir a Workflows → importar `n8n/workflows/daily-price-sync.json`
3. Verificar que el nodo Switch ahora tiene 4 salidas (api, static, dynamic, sitemap)
4. Verificar que existe el nodo `POST /scrape/sitemap`

- [ ] **Step 6: Ejecutar manualmente el workflow solo para guanzetti (opcional)**

En la UI de n8n, ejecutar el workflow manualmente. Verificar en los logs del container scraper que aparecen mensajes como:

```
INFO scraper: [guanzetti] Found 1000+ product URLs in sitemap
INFO scraper: [guanzetti] Scraped 998 products (3 skipped/errors)
```

Verificar en el Postgres local:

```bash
docker-compose exec postgres psql -U postgres -d postgres -c \
  "SELECT COUNT(*), MIN(precio), MAX(precio) FROM productos WHERE fuente = 'guanzetti';"
```

- [ ] **Step 7: Commit final**

```bash
git add .
git commit -m "chore: verify guanzetti scraper end-to-end in local environment"
```
