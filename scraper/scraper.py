"""
Lógica de scraping.

Implementaciones:
    - scrape_api_source(): APIs REST VTEX IO Intelligent Search (Easy, El Amigo).
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
from urllib.parse import quote, urlparse

import httpx
from bs4 import BeautifulSoup, NavigableString

from config_loader import ApiSource, DynamicPageSource, SitemapPageSource, StaticPageSource

log = logging.getLogger("scraper")

# ============================================================================
# Formato de producto normalizado (contrato con n8n / Supabase)
# ============================================================================
#
# Campos comunes a todas las fuentes:
#   codigo_producto: str | None
#   descripcion:     str            # requerido
#   precio:          float          # requerido
#   disponibilidad:  str | None
#   url_producto:    str | None
#   url_imagen:      str | None
#   categoria:       str | None     # hoja de la jerarquía
#   empresa:         str
#   marca:           str | None
#   proveedor:       str
#   unidad_medida:   str | None
#   fuente:          str            # coincide con source.name
#
# Campos opcionales emitidos por el parser VTEX IO (Easy / El Amigo):
#   item_id              : str | None        item.itemId
#   nombre_completo      : str | None        item.nameComplete
#   precio_lista          : float | None     offer.ListPrice
#   precio_sin_impuestos : float | None      properties["price_wo_taxes"]
#   ean                  : str | None        item.ean
#   multiplicador_unidad : float | None      item.unitMultiplier
#   tipo_producto        : str | None        properties["Tipo de Producto"]
#   familia_producto     : str | None        categories[0] nivel 1
#   subtipo_producto     : str | None        categories[0] nivel 2
#   categoria_completa   : str | None        breadcrumb "A > B > C"


# ============================================================================
# Scraper de API REST (VTEX IO Intelligent Search)
# ============================================================================

async def scrape_api_source(source: ApiSource, limit: int | None = None) -> list[dict[str, Any]]:
    """Descarga y normaliza productos desde una API REST VTEX IO Intelligent Search."""
    if source.api_format == "vtex_io_categories":
        return await _scrape_vtex_io_by_categories(source, limit)
    return await _scrape_vtex_io(source, limit)


async def _scrape_vtex_io(source: ApiSource, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Pagina la API VTEX IO Intelligent Search.

    Respuesta: {"products": [...], "recordsFiltered": N, "pagination": {...}}
    Paginación: ?page=1&count=50, ?page=2&count=50, ... hasta lista vacía o < page_size.
    """
    page_size = source.page_size
    all_products: list[dict[str, Any]] = []
    page = 1

    parsed = urlparse(source.endpoint)
    store_base_url = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; bimeg-dbprecios/1.0)",
            "Accept": "application/json",
        },
    ) as client:
        while True:
            url = f"{source.endpoint}?page={page}&count={page_size}"
            log.info("[%s] Fetching page=%d count=%d", source.name, page, page_size)

            data = await _fetch_json(url, client)
            if not isinstance(data, dict):
                log.error("[%s] Respuesta inesperada en page=%d", source.name, page)
                break

            products = data.get("products", [])
            if not products:
                log.info("[%s] Página vacía en page=%d — fin", source.name, page)
                break

            for product in products:
                all_products.extend(_parse_vtex_io_product(product, source, store_base_url))

            log.info("[%s] Página %d: %d productos raw → %d acumulados",
                     source.name, page, len(products), len(all_products))

            if limit is not None and len(all_products) >= limit:
                all_products = all_products[:limit]
                log.info("[%s] Límite %d alcanzado", source.name, limit)
                break

            if len(products) < page_size:
                log.info("[%s] Última página (%d < %d) — fin", source.name, len(products), page_size)
                break

            page += 1
            await asyncio.sleep(0.1)

    log.info("[%s] Total productos: %d", source.name, len(all_products))
    return all_products


def _parse_vtex_io_product(
    product: dict[str, Any],
    source: ApiSource,
    store_base_url: str,
) -> list[dict[str, Any]]:
    """Normaliza un producto VTEX IO al formato estándar. Una fila por item/SKU."""
    brand = product.get("brand") or None
    if brand == "-":
        brand = None

    # Jerarquía de categorías — categories[0] es el path más específico
    # (ej: "/Plomería/Distribución de agua/Polipropileno/").
    categories = product.get("categories", [])
    familia, subtipo, categoria, categoria_completa = _parse_category_hierarchy(categories)

    # Specs custom del vendor (más rico que la jerarquía de navegación)
    tipo_producto = _get_property_value(product, "Tipo de Producto")
    precio_sin_impuestos = _safe_float(_get_property_value(product, "price_wo_taxes"))

    link = product.get("link", "")
    url_producto = f"{store_base_url}{link}" if link else None

    results = []
    for item in product.get("items", []):
        sellers = item.get("sellers", [])
        offer = sellers[0].get("commertialOffer", {}) if sellers else {}

        precio = offer.get("Price")
        if precio is None:
            continue  # sin precio → no vendible

        images = item.get("images", [])
        is_available = offer.get("IsAvailable") or (offer.get("AvailableQuantity") or 0) > 0
        precio_lista = offer.get("ListPrice") or offer.get("PriceWithoutDiscount")

        results.append({
            "codigo_producto":      item.get("itemId"),
            "descripcion":          product.get("productName", ""),
            "precio":               float(precio),
            "disponibilidad":       "Disponible" if is_available else "Sin stock",
            "url_producto":         url_producto,
            "url_imagen":           images[0]["imageUrl"] if images else None,
            "categoria":            categoria,
            "empresa":              source.empresa,
            "marca":                brand,
            "proveedor":            source.proveedor,
            "unidad_medida":        item.get("measurementUnit"),
            "fuente":               source.name,
            "item_id":              item.get("itemId"),
            "nombre_completo":      item.get("nameComplete"),
            "precio_lista":         float(precio_lista) if precio_lista is not None else None,
            "precio_sin_impuestos": precio_sin_impuestos,
            "ean":                  item.get("ean") or None,
            "multiplicador_unidad": item.get("unitMultiplier"),
            "tipo_producto":        tipo_producto,
            "familia_producto":     familia,
            "subtipo_producto":     subtipo,
            "categoria_completa":   categoria_completa,
        })

    return results


def _get_property_value(product: dict[str, Any], name: str) -> str | None:
    """Devuelve el primer valor de una spec custom en product.properties.

    VTEX expone specs como `[{"name": "...", "values": ["..."]}]`. Si la spec
    no existe o no tiene valores, devuelve None.
    """
    for prop in product.get("properties") or []:
        if prop.get("name") == name:
            values = prop.get("values") or []
            return values[0] if values else None
    return None


def _parse_category_hierarchy(
    categories: list[str],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Parsea el path más específico de VTEX categories en (familia, subtipo, hoja, breadcrumb).

    VTEX devuelve un array de paths ordenados de más específico a más genérico
    (ej: ["/Plomería/Distribución de agua/Polipropileno/", "/Plomería/Distribución de agua/", "/Plomería/"]).
    Usamos categories[0] porque contiene la jerarquía completa.

    Retorna (None, None, None, None) si no hay categorías.
    """
    if not categories:
        return None, None, None, None
    parts = [p for p in categories[0].split("/") if p]
    if not parts:
        return None, None, None, None
    familia = parts[0] if len(parts) >= 1 else None
    subtipo = parts[1] if len(parts) >= 2 else None
    hoja = parts[-1]
    breadcrumb = " > ".join(parts)
    return familia, subtipo, hoja, breadcrumb


def _safe_float(value: Any) -> float | None:
    """Convierte un valor (potencialmente str) a float. Devuelve None si no parsea."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def _scrape_vtex_io_by_categories(
    source: ApiSource, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Scrapea el catálogo VTEX IO completo iterando cada categoría hoja en paralelo.

    Estrategia: la búsqueda global de VTEX IO cap a 2500 resultados (página 50).
    Al filtrar por categoría la misma API devuelve resultados sin cap porque cada
    categoría hoja tiene < 2500 productos. Se procesan N categorías en paralelo
    y se deduplica por productId al final.
    """
    parsed = urlparse(source.endpoint)
    store_base_url = f"{parsed.scheme}://{parsed.netloc}"
    category_tree_url = f"{store_base_url}/api/catalog_system/pub/category/tree/10"
    concurrency = getattr(source, "concurrency", 3)

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; bimeg-dbprecios/1.0)",
            "Accept": "application/json",
        },
    ) as client:
        tree = await _fetch_json(category_tree_url, client)
        if not isinstance(tree, list):
            log.error("[%s] Category tree fetch failed", source.name)
            return []

        leaf_categories = _collect_leaf_categories(tree)
        total_cats = len(leaf_categories)

        # limit en modo categorías = cuántas categorías procesar (útil para tests rápidos)
        if limit is not None:
            leaf_categories = leaf_categories[:limit]
        log.info("[%s] %d/%d leaf categories — concurrency=%d",
                 source.name, len(leaf_categories), total_cats, concurrency)

        sem = asyncio.Semaphore(concurrency)
        tasks = [
            _fetch_category_raw(source, cat, client, sem)
            for cat in leaf_categories
        ]
        raw_lists = await asyncio.gather(*tasks)

    # Deduplicar por productId y parsear
    seen_product_ids: set[str] = set()
    all_products: list[dict[str, Any]] = []
    for raw_products in raw_lists:
        for product_id, product in raw_products:
            if product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            all_products.extend(_parse_vtex_io_product(product, source, store_base_url))

    log.info("[%s] Total productos únicos: %d", source.name, len(all_products))
    return all_products


async def _fetch_category_raw(
    source: ApiSource,
    cat: dict[str, Any],
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> list[tuple[str, dict[str, Any]]]:
    """Pagina una categoría y devuelve lista de (productId, product_dict) sin parsear."""
    cat_name = cat["name"]
    results: list[tuple[str, dict[str, Any]]] = []
    page = 1

    async with sem:
        while True:
            url = (
                f"{source.endpoint}"
                f"?query={quote(cat_name)}&map=c"
                f"&page={page}&count={source.page_size}"
            )
            data = await _fetch_json(url, client)
            if not isinstance(data, dict):
                break

            products = data.get("products", [])
            if not products:
                break

            for product in products:
                results.append((str(product.get("productId", "")), product))

            if len(products) < source.page_size:
                break
            page += 1
            await asyncio.sleep(0.05)

    log.debug("[%s] cat=%r → %d raw products", source.name, cat_name, len(results))
    return results


def _collect_leaf_categories(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Devuelve recursivamente sólo las categorías sin hijos (hojas del árbol)."""
    leaves: list[dict[str, Any]] = []
    for node in nodes:
        children = node.get("children") or []
        if not children:
            leaves.append(node)
        else:
            leaves.extend(_collect_leaf_categories(children))
    return leaves


async def _fetch_json(url: str, client: httpx.AsyncClient, max_retries: int = 5) -> Any:
    """GET url, devuelve JSON parseado o None en error permanente.

    Errores 4xx → falla inmediata (no reintentar, son errores permanentes).
    Errores 5xx y de red → reintentar con backoff exponencial.
    """
    for attempt in range(max_retries):
        try:
            resp = await client.get(url)
            if resp.status_code in (400, 404):
                return None  # fin de paginación o recurso inexistente — no reintentar
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            # 5xx u otros códigos inesperados
            if attempt == max_retries - 1:
                log.error("HTTP error fetching %s: %s", url, exc)
                return None
            await asyncio.sleep(2 ** attempt)
        except httpx.RequestError as exc:
            # Errores de red (DNS, timeout, conexión) — reintentar con más paciencia
            if attempt == max_retries - 1:
                log.error("Request error fetching %s: %s", url, exc)
                return None
            wait = min(2 ** attempt * 2, 30)  # 2s, 4s, 8s, 16s, 30s
            log.warning("Request error (attempt %d/%d) fetching %s — retrying in %ds: %s",
                        attempt + 1, max_retries, url, wait, exc)
            await asyncio.sleep(wait)
        except Exception as exc:
            log.error("Error inesperado en _fetch_json %s: %s", url, exc)
            return None
    return None


# ============================================================================
# Scraper de sitemap (guanzetti.com.ar / TiendaPower)
# ============================================================================

async def scrape_sitemap_source(source: SitemapPageSource, limit: int | None = None) -> list[dict[str, Any]]:
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
        if limit is not None:
            product_urls = product_urls[:limit]
            log.info("[%s] Limited to %d URLs", source.name, limit)

        tasks = [
            _scrape_product_with_semaphore(url, source, client, sem)
            for url in product_urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, Exception):
            log.error("Unexpected exception scraping a product: %s", r, exc_info=r)
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
    max_retries: int = 5,
) -> str | None:
    """GET url con reintentos exponenciales. Devuelve None en error permanente."""
    for attempt in range(max_retries):
        try:
            resp = await client.get(url)
            if resp.status_code in (400, 404):
                log.warning("%d — skipping: %s", resp.status_code, url)
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
            wait = min(2 ** attempt * 2, 30)
            log.warning("Request error (attempt %d/%d) fetching %s — retrying in %ds: %s",
                        attempt + 1, max_retries, url, wait, exc)
            await asyncio.sleep(wait)
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
