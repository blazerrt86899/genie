-- ============================================================================
-- Genie — one-time database setup (CLAUDE.md §8)
--
-- Run once against the target Postgres's default database:
--   docker exec -i supabase_db_server psql -U postgres -d postgres < scripts/setup_supabase.sql
--   (or Supabase Cloud's `postgres` db)
--
-- Genie's tables live in the dedicated `genie` SCHEMA (Alembic + models target
-- it). This script creates the schema, the hybrid-search RPCs, and — once the
-- Phase 2 tables exist — their indexes / FTS triggers / RLS. Safe to re-run.
-- LangGraph checkpointer tables are NOT managed here (created by
-- `checkpointer.setup()` at FastAPI startup, also into the `genie` schema — §8.2).
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS genie;

-- ─── 1. Extensions ─────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- trigram / FTS support
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- uuid_generate_v4()

-- Everything below resolves into the genie schema.
SET search_path = genie, public, extensions;
-- Allow creating functions that reference tables which don't exist yet.
SET check_function_bodies = off;

-- ─── 2. Hybrid search — document_chunks (CLAUDE.md §8.3) ─────────────────────
CREATE OR REPLACE FUNCTION hybrid_search_documents(
  query_text      TEXT,
  query_embedding vector(1536),
  target_user_id  UUID,
  match_count     INT DEFAULT 10,
  fts_weight      FLOAT DEFAULT 1.0,
  semantic_weight FLOAT DEFAULT 1.0,
  rrf_k           INT DEFAULT 50
)
RETURNS TABLE (
  id          UUID,
  content     TEXT,
  metadata    JSONB,
  document_id UUID,
  score       FLOAT
)
LANGUAGE sql
STABLE
SET search_path = genie, public, extensions
AS $$
  WITH full_text AS (
    SELECT dc.id,
      ROW_NUMBER() OVER (
        ORDER BY ts_rank_cd(dc.fts_content, plainto_tsquery('english', query_text)) DESC
      ) AS rank_ix
    FROM document_chunks dc
    WHERE dc.user_id = target_user_id
      AND dc.fts_content @@ plainto_tsquery('english', query_text)
    LIMIT LEAST(match_count, 30) * 2
  ),
  semantic AS (
    SELECT dc.id,
      ROW_NUMBER() OVER (ORDER BY dc.embedding <=> query_embedding) AS rank_ix
    FROM document_chunks dc
    WHERE dc.user_id = target_user_id
    ORDER BY dc.embedding <=> query_embedding
    LIMIT LEAST(match_count, 30) * 2
  )
  SELECT dc.id, dc.content, dc.metadata, dc.document_id,
    (
      COALESCE(1.0 / (rrf_k + ft.rank_ix), 0.0) * fts_weight +
      COALESCE(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight
    ) AS score
  FROM document_chunks dc
  FULL OUTER JOIN full_text ft ON dc.id = ft.id
  FULL OUTER JOIN semantic s   ON dc.id = s.id
  WHERE dc.user_id = target_user_id
  ORDER BY score DESC
  LIMIT match_count;
$$;

-- ─── 3. Hybrid search — user_memory (CLAUDE.md §8.4) ────────────────────────
CREATE OR REPLACE FUNCTION hybrid_search_memories(
  query_text      TEXT,
  query_embedding vector(1536),
  target_user_id  UUID,
  match_count     INT DEFAULT 5,
  fts_weight      FLOAT DEFAULT 0.5,
  semantic_weight FLOAT DEFAULT 1.5,
  rrf_k           INT DEFAULT 50
)
RETURNS TABLE (
  id         UUID,
  content    TEXT,
  importance FLOAT,
  score      FLOAT
)
LANGUAGE sql
STABLE
SET search_path = genie, public, extensions
AS $$
  WITH full_text AS (
    SELECT id,
      ROW_NUMBER() OVER (
        ORDER BY ts_rank_cd(fts_content, plainto_tsquery('english', query_text)) DESC
      ) AS rank_ix
    FROM user_memory
    WHERE user_id = target_user_id
      AND fts_content @@ plainto_tsquery('english', query_text)
    LIMIT LEAST(match_count, 20) * 2
  ),
  semantic AS (
    SELECT id,
      ROW_NUMBER() OVER (ORDER BY embedding <=> query_embedding) AS rank_ix
    FROM user_memory
    WHERE user_id = target_user_id
    ORDER BY embedding <=> query_embedding
    LIMIT LEAST(match_count, 20) * 2
  )
  SELECT um.id, um.content, um.importance,
    (
      COALESCE(1.0 / (rrf_k + ft.rank_ix), 0.0) * fts_weight +
      COALESCE(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight
    ) AS score
  FROM user_memory um
  FULL OUTER JOIN full_text ft ON um.id = ft.id
  FULL OUTER JOIN semantic s   ON um.id = s.id
  WHERE um.user_id = target_user_id
  ORDER BY score DESC
  LIMIT match_count;
$$;

RESET check_function_bodies;

-- ─── 4. Indexes, FTS triggers, RLS — apply once Phase 2 tables exist ────────
CREATE OR REPLACE FUNCTION update_fts_content()
RETURNS TRIGGER AS $$
BEGIN
  NEW.fts_content := to_tsvector('english', COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Each statement is best-effort: a missing table OR a not-yet-created column
-- (fts_content / embedding land with the Phase 2 migration) just logs a NOTICE
-- and the script moves on. Re-run after the Phase 2 migration to apply them.
DO $$
DECLARE
  stmt TEXT;
  stmts TEXT[] := ARRAY[
    'CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)',
    'CREATE INDEX IF NOT EXISTS ix_document_chunks_fts ON document_chunks USING gin(fts_content)',
    'CREATE INDEX IF NOT EXISTS ix_document_chunks_doc_user ON document_chunks (document_id, user_id)',
    'DROP TRIGGER IF EXISTS update_document_chunks_fts ON document_chunks',
    'CREATE TRIGGER update_document_chunks_fts BEFORE INSERT OR UPDATE OF content ON document_chunks FOR EACH ROW EXECUTE FUNCTION update_fts_content()',
    'ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY',
    'CREATE INDEX IF NOT EXISTS ix_user_memory_embedding ON user_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)',
    'CREATE INDEX IF NOT EXISTS ix_user_memory_fts ON user_memory USING gin(fts_content)',
    'DROP TRIGGER IF EXISTS update_user_memory_fts ON user_memory',
    'CREATE TRIGGER update_user_memory_fts BEFORE INSERT OR UPDATE OF content ON user_memory FOR EACH ROW EXECUTE FUNCTION update_fts_content()',
    'ALTER TABLE user_memory ENABLE ROW LEVEL SECURITY',
    'CREATE INDEX IF NOT EXISTS ix_messages_conv_created ON messages (conversation_id, created_at)',
    'CREATE INDEX IF NOT EXISTS ix_tasks_user_status_created ON tasks (user_id, status, created_at)',
    'ALTER TABLE tasks ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE conversations ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE messages ENABLE ROW LEVEL SECURITY'
  ];
BEGIN
  FOREACH stmt IN ARRAY stmts LOOP
    BEGIN
      EXECUTE stmt;
    EXCEPTION WHEN undefined_table OR undefined_column THEN
      RAISE NOTICE 'skipped (not ready): %', stmt;
    END;
  END LOOP;
END $$;
