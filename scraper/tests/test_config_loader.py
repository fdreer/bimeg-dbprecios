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


class TestLoadSourcesWithSitemap:
    def test_yaml_round_trip(self, tmp_path):
        yml = tmp_path / "sources.yml"
        yml.write_text(
            "sitemap_pages:\n"
            "  - name: guanzetti\n"
            "    enabled: true\n"
            "    sitemap_url: https://www.guanzetti.com.ar/sitemap.xml\n"
            "    empresa: Guanzetti S.A.\n"
            "    proveedor: Guanzetti\n",
            encoding="utf-8",
        )
        config = load_sources(path=yml)
        assert len(config.sitemap_pages) == 1
        src = config.sitemap_pages[0]
        assert src.name == "guanzetti"
        assert src.type == "sitemap"
        assert src.sitemap_url == "https://www.guanzetti.com.ar/sitemap.xml"
        assert src.concurrency == 5
        assert src.delay_seconds == 0.5
