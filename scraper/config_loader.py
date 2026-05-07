"""
Carga y parseo de sources.yml.

Responsabilidades:
    - Leer el archivo YAML montado en el container (por defecto en /app/sources.yml).
    - Expandir referencias a variables de entorno ``${VAR}`` en los valores.
    - Filtrar fuentes con ``enabled: false``.
    - Exponer la configuración como estructuras Python tipadas via Pydantic.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

# ----------------------------------------------------------------------------
# Ubicación por defecto del archivo de configuración.
# El docker-compose monta sources.yml en esta ruta como read-only.
# ----------------------------------------------------------------------------
DEFAULT_SOURCES_PATH = Path(
    os.environ.get("SOURCES_PATH", "/app/sources.yml")
)

# ----------------------------------------------------------------------------
# Regex para detectar referencias a env vars tipo ${NOMBRE_VAR}
# ----------------------------------------------------------------------------
_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


# ============================================================================
# Modelos de configuración
# ============================================================================

class ApiSource(BaseModel):
    """Fuente basada en una API REST pública."""

    type: Literal["api"] = "api"
    name: str
    enabled: bool = True
    endpoint: str
    api_format: Literal["vtex_io", "vtex_io_categories"] = "vtex_io"
    page_size: int = 50
    concurrency: int = 3
    auth_header: str | None = None
    auth_value: str | None = None
    field_mappings: dict[str, str] = Field(default_factory=dict)
    empresa: str = ""
    proveedor: str = ""


class PageSelectors(BaseModel):
    """Selectores CSS para extraer campos de una página web."""

    descripcion: str | None = None
    precio: str | None = None
    codigo_producto: str | None = None
    url_imagen: str | None = None
    categoria: str | None = None
    marca: str | None = None


class StaticPageSource(BaseModel):
    """Fuente basada en una página HTML estática (sin JavaScript)."""

    type: Literal["static"] = "static"
    name: str
    enabled: bool = True
    base_url: str
    selectores: PageSelectors
    empresa: str = ""
    proveedor: str = ""
    marca: str = ""


class DynamicPageSource(BaseModel):
    """Fuente basada en una página con contenido renderizado por JavaScript."""

    type: Literal["dynamic"] = "dynamic"
    name: str
    enabled: bool = True
    base_url: str
    selectores: PageSelectors
    empresa: str = ""
    proveedor: str = ""
    marca: str = ""


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


Source = ApiSource | StaticPageSource | DynamicPageSource | SitemapPageSource


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


# ============================================================================
# Expansión de variables de entorno
# ============================================================================

def _expand_env(value: Any) -> Any:
    """
    Reemplaza recursivamente los patrones ``${VAR}`` por el valor de la env var.

    Si la variable no está definida, se deja el placeholder tal cual (para que
    el error sea visible en lugar de silencioso).
    """
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value,
        )
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


# ============================================================================
# API pública
# ============================================================================

def load_sources(path: Path | None = None) -> SourcesConfig:
    """
    Carga y parsea sources.yml, expandiendo env vars en los valores.

    Args:
        path: Ruta opcional al archivo. Si no se pasa, usa SOURCES_PATH env var
              o ``/app/sources.yml`` por defecto.

    Returns:
        SourcesConfig tipado listo para usar.

    Raises:
        FileNotFoundError: si el archivo no existe.
        yaml.YAMLError: si el archivo no es YAML válido.
        pydantic.ValidationError: si la estructura no coincide con el schema.
    """
    path = path or DEFAULT_SOURCES_PATH
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    expanded = _expand_env(raw)
    return SourcesConfig.model_validate(expanded)


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
