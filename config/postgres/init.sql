-- =============================================================================
-- Maestro Healthcare Platform - PostgreSQL Initialization
-- Creates databases for CIB Seven, HAPI FHIR, and Keycloak
-- =============================================================================

-- HAPI FHIR database (idempotent - safe to run multiple times)
SELECT 'CREATE DATABASE hapi_fhir' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'hapi_fhir')\gexec

-- Keycloak database (idempotent - safe to run multiple times)
SELECT 'CREATE DATABASE keycloak' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec

-- Grant least-privilege access to maestro user
-- Note: GRANT statements are idempotent in PostgreSQL
\c hapi_fhir
GRANT CONNECT ON DATABASE hapi_fhir TO maestro;
GRANT CREATE ON SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO maestro;

\c keycloak
GRANT CONNECT ON DATABASE keycloak TO maestro;
GRANT CREATE ON SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO maestro;

-- CIB Seven extensions
\c cibseven

-- pgaudit extension is not available in postgres:alpine image
-- If audit logging is required, either:
-- 1. Use postgres:16 (non-alpine) image with pgaudit package installed
-- 2. Use PostgreSQL's built-in logging (log_statement = 'all')
-- 3. Use application-level audit logging
-- CREATE EXTENSION IF NOT EXISTS pgaudit;

-- UUID extension for FHIR resource identifiers
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
