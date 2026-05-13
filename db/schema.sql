-- ============================================================================
-- bimeg-dbprecios — Schema de base de datos
-- ============================================================================
-- Ejecutar UNA SOLA VEZ sobre el proyecto de Supabase.
--
-- Uso:
--   1) Abrir el dashboard del proyecto en https://supabase.com/dashboard
--   2) Ir a SQL Editor → New query
--   3) Pegar este archivo y ejecutar.
--
-- Estrategia de actualización (sin historial):
--   Cada corrida del workflow para una fuente determinada:
--     DELETE FROM productos WHERE fuente = 'nombre-fuente';
--     INSERT INTO productos (...) VALUES ...
--   Esto garantiza datos frescos y elimina productos discontinuados.
-- ============================================================================

-- Tabla única de productos ----------------------------------------------------
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

COMMENT ON TABLE  productos                 IS 'Productos de materiales de construcción agregados desde múltiples fuentes (APIs + scraping).';
COMMENT ON COLUMN productos.codigo_producto IS 'SKU o código interno del proveedor, si existe.';
COMMENT ON COLUMN productos.disponibilidad  IS 'Estado de stock del proveedor (ej: "Stock disponible", "Sin stock").';
COMMENT ON COLUMN productos.fuente          IS 'Identificador de la fuente que originó el registro (coincide con name en sources.yml).';
COMMENT ON COLUMN productos.actualizado_en  IS 'Timestamp de la última inserción para este registro.';

-- Columnas para fuentes VTEX (Easy y similares) ------------------------------
ALTER TABLE productos ADD COLUMN IF NOT EXISTS item_id              VARCHAR(50);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS nombre_completo      TEXT;
ALTER TABLE productos ADD COLUMN IF NOT EXISTS precio_lista         NUMERIC(12, 2);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS precio_sin_impuestos NUMERIC(12, 2);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS ean                  VARCHAR(50);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS multiplicador_unidad NUMERIC(10, 3);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS tipo_producto        VARCHAR(200);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS familia_producto     VARCHAR(200);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS subtipo_producto     VARCHAR(200);
ALTER TABLE productos ADD COLUMN IF NOT EXISTS categoria_completa   TEXT;

COMMENT ON COLUMN productos.item_id              IS 'ID de SKU/variante en VTEX (itemId).';
COMMENT ON COLUMN productos.nombre_completo      IS 'Nombre completo del SKU incluyendo variante (nameComplete en VTEX).';
COMMENT ON COLUMN productos.precio_lista         IS 'Precio de lista antes de descuentos (ListPrice en VTEX).';
COMMENT ON COLUMN productos.precio_sin_impuestos IS 'Precio neto sin impuestos (spec "price_wo_taxes" en properties VTEX).';
COMMENT ON COLUMN productos.ean                  IS 'Código de barras EAN/GTIN del SKU.';
COMMENT ON COLUMN productos.multiplicador_unidad IS 'Multiplicador de unidad de venta (unitMultiplier en VTEX). Ej: 1.5 para caja de 1.5 m².';
COMMENT ON COLUMN productos.tipo_producto        IS 'Clasificación granular del proveedor — spec "Tipo de Producto" en properties VTEX (ej: "Bujes de Acople", "Cemento Portland").';
COMMENT ON COLUMN productos.familia_producto     IS 'Nivel raíz de la jerarquía de categorías (ej: "Plomería", "Pinturas").';
COMMENT ON COLUMN productos.subtipo_producto     IS 'Nivel intermedio de la jerarquía de categorías (ej: "Distribución de agua").';
COMMENT ON COLUMN productos.categoria_completa   IS 'Breadcrumb completo de categorías separado por " > " (ej: "Plomería > Distribución de agua > Polipropileno").';

-- Índices para consultas típicas ---------------------------------------------
CREATE INDEX IF NOT EXISTS idx_productos_fuente           ON productos(fuente);
CREATE INDEX IF NOT EXISTS idx_productos_empresa          ON productos(empresa);
CREATE INDEX IF NOT EXISTS idx_productos_categoria        ON productos(categoria);
CREATE INDEX IF NOT EXISTS idx_productos_tipo_producto    ON productos(tipo_producto);
CREATE INDEX IF NOT EXISTS idx_productos_familia_producto ON productos(familia_producto);
