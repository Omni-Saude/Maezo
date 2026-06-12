-- =============================================================================
-- MAEZO Healthcare Platform — PostgreSQL Initialization
-- Executado automaticamente quando o container postgres sobe pela primeira vez
--
-- Bancos criados:
--   cibseven  — CIB Seven BPM Engine (processo e histórico)
--   hapi_fhir — HAPI FHIR R4 (recursos clínicos)
--   maestro   — Dados de negócio (contratos, idempotência, dead-letter)
--
-- Nota: Keycloak removido (ADR-020 — Basic Auth sem Keycloak)
-- =============================================================================

-- ─── Criar bancos (o banco 'cibseven' já é criado pelo POSTGRES_DB) ──────────
SELECT 'CREATE DATABASE hapi_fhir'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'hapi_fhir')\gexec

SELECT 'CREATE DATABASE maestro'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'maestro')\gexec

-- ─── hapi_fhir ────────────────────────────────────────────────────────────────
\c hapi_fhir
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT CONNECT ON DATABASE hapi_fhir TO maestro;
GRANT CREATE ON SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO maestro;

-- ─── maestro (dados de negócio) ───────────────────────────────────────────────
\c maestro
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT CONNECT ON DATABASE maestro TO maestro;
GRANT CREATE ON SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO maestro;

-- Tabela de idempotência para webhooks (ADR-014)
CREATE TABLE IF NOT EXISTS webhook_idempotency (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    system VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL DEFAULT 'received'
);
CREATE INDEX IF NOT EXISTS idx_webhook_idempotency_key ON webhook_idempotency(idempotency_key);

-- Tabela dead-letter para mensagens Kafka não processáveis
CREATE TABLE IF NOT EXISTS kafka_dead_letter (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic VARCHAR(255) NOT NULL,
    partition_num INTEGER,
    offset_num BIGINT,
    tenant_id VARCHAR(100),
    payload JSONB NOT NULL,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_retry_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_dead_letter_topic ON kafka_dead_letter(topic);
CREATE INDEX IF NOT EXISTS idx_dead_letter_tenant ON kafka_dead_letter(tenant_id);

-- ─── cibseven (POSTGRES_DB padrão — configurações) ───────────────────────────
\c cibseven
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
GRANT CREATE ON SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maestro;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO maestro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO maestro;
-- O schema do CIB Seven (tabelas ACT_*) é criado automaticamente pelo engine na primeira inicialização
