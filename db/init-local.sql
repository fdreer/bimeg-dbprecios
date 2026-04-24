-- ============================================================================
-- bimeg-dbprecios — inicialización LOCAL ÚNICAMENTE
-- ============================================================================
-- Este archivo se ejecuta automáticamente por el container postgres la primera
-- vez que arranca (vía /docker-entrypoint-initdb.d/).
--
-- Su único propósito es crear el rol `anon` que PostgREST usa para servir
-- requests sin autenticación. En Supabase cloud este rol ya existe y está
-- administrado por la plataforma — NO correr este script allá.
--
-- Orden de ejecución (alfabético dentro de initdb.d):
--     00-schema.sql      ← tabla productos + índices (mismo que producción)
--     01-init-local.sql  ← este archivo, crea rol y grants
-- ============================================================================

-- Rol anónimo usado por PostgREST -------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
END$$;

-- Permisos sobre schema public ----------------------------------------------
GRANT USAGE ON SCHEMA public TO anon;

-- Permisos sobre la tabla productos (ya existe gracias a 00-schema.sql) -----
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE productos TO anon;

-- Para cualquier tabla que se agregue en el futuro, heredar los mismos grants
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon;
