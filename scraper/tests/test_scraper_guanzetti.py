"""Tests para las funciones de scraping de Guanzetti."""
from __future__ import annotations

import sys
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
        assert result["marca"] is None
        assert result["categoria"] is None
        assert result["unidad_medida"] is None

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

# ---------------------------------------------------------------------------
# scrape_sitemap_source (orchestrator)
# ---------------------------------------------------------------------------

class TestScrapeSitemapSource:
    async def test_returns_products_scraped_from_sitemap(self):
        from unittest.mock import AsyncMock, patch
        import scraper

        xml_text = _load_xml()
        html_text = _load_html()
        source = SitemapPageSource(
            name="guanzetti",
            enabled=True,
            sitemap_url="https://www.guanzetti.com.ar/sitemap.xml",
            empresa="Guanzetti S.A.",
            proveedor="Guanzetti",
            delay_seconds=0.0,
        )

        def fake_fetch(url, client, max_retries=3):
            return xml_text if url == source.sitemap_url else html_text

        with patch.object(scraper, "_fetch_text", new=AsyncMock(side_effect=fake_fetch)):
            products = await scraper.scrape_sitemap_source(source)

        assert len(products) == 2
        assert all(p["fuente"] == "guanzetti" for p in products)
        assert all(p["empresa"] == "Guanzetti S.A." for p in products)

    async def test_returns_empty_list_when_sitemap_unreachable(self):
        from unittest.mock import AsyncMock, patch
        import scraper

        source = SitemapPageSource(
            name="guanzetti",
            enabled=True,
            sitemap_url="https://www.guanzetti.com.ar/sitemap.xml",
            empresa="Guanzetti S.A.",
            proveedor="Guanzetti",
            delay_seconds=0.0,
        )

        with patch.object(scraper, "_fetch_text", new=AsyncMock(return_value=None)):
            products = await scraper.scrape_sitemap_source(source)

        assert products == []


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
