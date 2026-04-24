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

-- Índices para consultas típicas ---------------------------------------------
CREATE INDEX IF NOT EXISTS idx_productos_fuente    ON productos(fuente);
CREATE INDEX IF NOT EXISTS idx_productos_empresa   ON productos(empresa);
CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria);
