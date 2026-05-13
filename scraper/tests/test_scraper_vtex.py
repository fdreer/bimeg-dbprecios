"""Tests para el parser VTEX IO (Easy, El Amigo)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import ApiSource
from scraper import (
    _get_property_value,
    _parse_category_hierarchy,
    _parse_vtex_io_product,
    _safe_float,
)


def _make_source() -> ApiSource:
    return ApiSource(
        name="easy",
        enabled=True,
        endpoint="https://www.easy.com.ar/api/io/_v/api/intelligent-search/product_search",
        api_format="vtex_io_categories",
        empresa="Easy S.A.",
        proveedor="Easy",
    )


# Fixture inspirado en la respuesta real de Easy para productId=1221709
def _make_buje_product() -> dict:
    return {
        "productId": "1221709",
        "productName": 'Buje Reducción 1 1/4 X 3/4" Polipropileno Amanco',
        "brand": "Amanco",
        "link": "/buje-reduccion-1-14-x-34-polipropileno-amanco/p",
        "categories": [
            "/Plomería/Distribución de agua/Polipropileno/",
            "/Plomería/Distribución de agua/",
            "/Plomería/",
        ],
        "properties": [
            {"name": "Marca", "values": ["Amanco"]},
            {"name": "Tipo de Producto", "values": ["Bujes de Acople"]},
            {"name": "Material", "values": ["Polipropileno"]},
            {"name": "price_wo_taxes", "values": ["49.59"]},
        ],
        "items": [
            {
                "itemId": "1221709",
                "nameComplete": 'Buje Reducción 1 1/4 X 3/4" Polipropileno Amanco Buje Ppl 1 1/4" X 3/4" Amanco',
                "ean": "7798116066241",
                "measurementUnit": "un",
                "unitMultiplier": 1,
                "images": [{"imageUrl": "https://cdn.easy.com.ar/buje.jpg"}],
                "sellers": [
                    {
                        "commertialOffer": {
                            "Price": 60,
                            "ListPrice": 60,
                            "PriceWithoutDiscount": 60,
                            "Tax": 0,
                            "taxPercentage": 0,
                            "IsAvailable": True,
                            "AvailableQuantity": 10000,
                        }
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# _get_property_value
# ---------------------------------------------------------------------------

class TestGetPropertyValue:
    def test_returns_first_value(self):
        product = {"properties": [{"name": "Foo", "values": ["bar", "baz"]}]}
        assert _get_property_value(product, "Foo") == "bar"

    def test_returns_none_if_missing(self):
        product = {"properties": [{"name": "Foo", "values": ["bar"]}]}
        assert _get_property_value(product, "Otra") is None

    def test_returns_none_if_properties_absent(self):
        assert _get_property_value({}, "Foo") is None

    def test_returns_none_if_properties_is_none(self):
        assert _get_property_value({"properties": None}, "Foo") is None

    def test_returns_none_if_values_empty(self):
        product = {"properties": [{"name": "Foo", "values": []}]}
        assert _get_property_value(product, "Foo") is None


# ---------------------------------------------------------------------------
# _parse_category_hierarchy
# ---------------------------------------------------------------------------

class TestParseCategoryHierarchy:
    def test_three_levels(self):
        result = _parse_category_hierarchy(
            ["/Plomería/Distribución de agua/Polipropileno/"]
        )
        assert result == (
            "Plomería",
            "Distribución de agua",
            "Polipropileno",
            "Plomería > Distribución de agua > Polipropileno",
        )

    def test_uses_first_path_not_shorter_paths(self):
        # VTEX devuelve paths ordenados de más específico a más genérico
        result = _parse_category_hierarchy(
            [
                "/Plomería/Distribución de agua/Polipropileno/",
                "/Plomería/Distribución de agua/",
                "/Plomería/",
            ]
        )
        assert result[2] == "Polipropileno"  # hoja del path más específico

    def test_single_level(self):
        familia, subtipo, hoja, breadcrumb = _parse_category_hierarchy(["/Solo/"])
        assert familia == "Solo"
        assert subtipo is None
        assert hoja == "Solo"
        assert breadcrumb == "Solo"

    def test_four_levels_preserved_in_breadcrumb(self):
        familia, subtipo, hoja, breadcrumb = _parse_category_hierarchy(
            ["/A/B/C/D/"]
        )
        assert familia == "A"
        assert subtipo == "B"
        assert hoja == "D"  # siempre el último
        assert breadcrumb == "A > B > C > D"  # no perdemos C

    def test_empty_list(self):
        assert _parse_category_hierarchy([]) == (None, None, None, None)

    def test_empty_path_string(self):
        assert _parse_category_hierarchy([""]) == (None, None, None, None)


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_parses_string_number(self):
        assert _safe_float("49.59") == pytest.approx(49.59)

    def test_parses_int(self):
        assert _safe_float(60) == 60.0

    def test_returns_none_on_invalid_string(self):
        assert _safe_float("no-numero") is None

    def test_returns_none_on_none(self):
        assert _safe_float(None) is None

    def test_returns_none_on_empty_string(self):
        assert _safe_float("") is None


# ---------------------------------------------------------------------------
# _parse_vtex_io_product — integración
# ---------------------------------------------------------------------------

class TestParseVtexProduct:
    def test_buje_real_response(self):
        source = _make_source()
        result = _parse_vtex_io_product(
            _make_buje_product(), source, "https://www.easy.com.ar"
        )
        assert len(result) == 1
        row = result[0]
        # Campos base
        assert row["codigo_producto"] == "1221709"
        assert row["descripcion"].startswith("Buje Reducción")
        assert row["precio"] == 60.0
        assert row["disponibilidad"] == "Disponible"
        assert row["categoria"] == "Polipropileno"
        assert row["marca"] == "Amanco"
        assert row["empresa"] == "Easy S.A."
        assert row["proveedor"] == "Easy"
        assert row["fuente"] == "easy"
        assert row["unidad_medida"] == "un"
        assert row["url_producto"].endswith("/buje-reduccion-1-14-x-34-polipropileno-amanco/p")
        # Campos VTEX nuevos
        assert row["item_id"] == "1221709"
        assert row["nombre_completo"].endswith('1 1/4" X 3/4" Amanco')
        assert row["precio_lista"] == 60.0
        assert row["precio_sin_impuestos"] == pytest.approx(49.59)
        assert row["ean"] == "7798116066241"
        assert row["multiplicador_unidad"] == 1
        assert row["tipo_producto"] == "Bujes de Acople"
        assert row["familia_producto"] == "Plomería"
        assert row["subtipo_producto"] == "Distribución de agua"
        assert row["categoria_completa"] == "Plomería > Distribución de agua > Polipropileno"

    def test_missing_price_wo_taxes_yields_null(self):
        product = _make_buje_product()
        product["properties"] = [p for p in product["properties"] if p["name"] != "price_wo_taxes"]
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result[0]["precio_sin_impuestos"] is None

    def test_invalid_price_wo_taxes_yields_null(self):
        product = _make_buje_product()
        for p in product["properties"]:
            if p["name"] == "price_wo_taxes":
                p["values"] = ["no-es-un-numero"]
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result[0]["precio_sin_impuestos"] is None

    def test_missing_tipo_de_producto_yields_null(self):
        product = _make_buje_product()
        product["properties"] = [p for p in product["properties"] if p["name"] != "Tipo de Producto"]
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result[0]["tipo_producto"] is None

    def test_no_categories_yields_null_hierarchy(self):
        product = _make_buje_product()
        product["categories"] = []
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        row = result[0]
        assert row["categoria"] is None
        assert row["familia_producto"] is None
        assert row["subtipo_producto"] is None
        assert row["categoria_completa"] is None

    def test_skips_item_without_price(self):
        product = _make_buje_product()
        product["items"][0]["sellers"][0]["commertialOffer"]["Price"] = None
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result == []

    def test_listprice_fallback_to_pricewithoutdiscount(self):
        product = _make_buje_product()
        offer = product["items"][0]["sellers"][0]["commertialOffer"]
        offer["ListPrice"] = None
        offer["PriceWithoutDiscount"] = 75
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result[0]["precio_lista"] == 75.0

    def test_empty_ean_normalized_to_none(self):
        product = _make_buje_product()
        product["items"][0]["ean"] = ""
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result[0]["ean"] is None

    def test_unavailable_when_quantity_zero(self):
        product = _make_buje_product()
        offer = product["items"][0]["sellers"][0]["commertialOffer"]
        offer["IsAvailable"] = False
        offer["AvailableQuantity"] = 0
        result = _parse_vtex_io_product(product, _make_source(), "https://www.easy.com.ar")
        assert result[0]["disponibilidad"] == "Sin stock"
