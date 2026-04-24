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
