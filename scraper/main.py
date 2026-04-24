"""
API HTTP del microservicio scraper.

Endpoints:
    GET  /health              Health check.
    GET  /sources             Devuelve sources.yml parseado como JSON.
    POST /scrape/static       Scrapea una página estática (stub).
    POST /scrape/dynamic      Scrapea una página dinámica (stub).
    POST /scrape/sitemap      Scrapea fuentes tipo sitemap (httpx + BeautifulSoup).

Todos los endpoints son consumidos exclusivamente por n8n dentro de la red
Docker privada. El servicio no está expuesto al host.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import scraper
from config_loader import (
    ApiSource,
    DynamicPageSource,
    SitemapPageSource,
    SourcesConfig,
    StaticPageSource,
    find_source,
    load_sources,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scraper-service")

app = FastAPI(
    title="bimeg-dbprecios scraper service",
    description="Extrae precios de materiales desde páginas web y APIs.",
    version="0.1.0",
)


# ============================================================================
# Caché de configuración en memoria
# ============================================================================
# sources.yml se lee al arrancar y se expone via /sources.
# Si se edita el archivo en runtime, reiniciar el container (o llamar a
# POST /sources/reload, TODO) para recargar.
# ============================================================================

_config: SourcesConfig | None = None


def get_config() -> SourcesConfig:
    """Devuelve la config cargada, la carga si es la primera llamada."""
    global _config
    if _config is None:
        _config = load_sources()
        log.info(
            "Loaded sources.yml: %d APIs, %d static pages, %d dynamic pages",
            len(_config.apis),
            len(_config.static_pages),
            len(_config.dynamic_pages),
        )
    return _config


@app.on_event("startup")
def _startup() -> None:
    """Carga sources.yml al arrancar el servicio."""
    get_config()


# ============================================================================
# Modelos de request / response
# ============================================================================

class ScrapeRequest(BaseModel):
    source_name: str


class SourceDescriptor(BaseModel):
    """Versión simplificada de una fuente para el endpoint /sources."""

    type: str
    name: str
    enabled: bool
    empresa: str
    proveedor: str


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
def health() -> dict[str, str]:
    """Health check simple. Usado por Docker healthcheck y por n8n."""
    return {"status": "ok"}


@app.get("/sources", response_model=list[SourceDescriptor])
def list_sources() -> list[SourceDescriptor]:
    """
    Devuelve todas las fuentes habilitadas como una lista plana.

    El workflow de n8n itera este array con un nodo Split-in-Batches y ejecuta
    la rama correspondiente según ``type``.
    """
    config = get_config()
    return [
        SourceDescriptor(
            type=src.type,
            name=src.name,
            enabled=src.enabled,
            empresa=src.empresa,
            proveedor=src.proveedor,
        )
        for src in config.enabled_sources()
    ]


@app.post("/scrape/static")
def scrape_static(req: ScrapeRequest) -> list[dict[str, Any]]:
    """Ejecuta el scraper estático para la fuente indicada."""
    config = get_config()
    source = find_source(config, req.source_name)

    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{req.source_name}' not found")
    if not isinstance(source, StaticPageSource):
        raise HTTPException(
            status_code=400,
            detail=f"Source '{req.source_name}' is not a static page (type={source.type})",
        )

    log.info("Scraping static page: %s", source.name)
    return scraper.scrape_static_page(source)


@app.post("/scrape/dynamic")
async def scrape_dynamic(req: ScrapeRequest) -> list[dict[str, Any]]:
    """Ejecuta el scraper dinámico (Playwright) para la fuente indicada."""
    config = get_config()
    source = find_source(config, req.source_name)

    if source is None:
        raise HTTPException(status_code=404, detail=f"Source '{req.source_name}' not found")
    if not isinstance(source, DynamicPageSource):
        raise HTTPException(
            status_code=400,
            detail=f"Source '{req.source_name}' is not a dynamic page (type={source.type})",
        )

    log.info("Scraping dynamic page: %s", source.name)
    return await scraper.scrape_dynamic_page(source)


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


# ============================================================================
# Nota: las fuentes de tipo "api" NO se consumen desde este servicio.
# n8n las consulta directamente con su nodo HTTP Request nativo, que es más
# flexible y permite manejar auth, paginación y transformaciones sin código.
# ============================================================================
