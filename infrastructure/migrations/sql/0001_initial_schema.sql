-- Ensure pgvector is available
CREATE EXTENSION IF NOT EXISTS vector;

-- ======================
-- NOTES
-- ======================
CREATE TABLE IF NOT EXISTS notes (
    id uuid PRIMARY KEY,
    title text NOT NULL,
    content text NOT NULL,
    summary text NOT NULL,
    author text NOT NULL,
    status text DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notes_status_idx ON notes(status);
CREATE INDEX IF NOT EXISTS notes_created_at_idx ON notes(created_at);

-- ======================
-- EMBEDDINGS
-- ======================
CREATE TABLE IF NOT EXISTS embeddings (
    note_id uuid PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    model text NOT NULL,
    dim int NOT NULL,
    embedding vector(3072) NOT NULL,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Specialized vector indexes (ivfflat/hnsw) cap at 2000 dimensions on older
-- pgvector releases; with 3072-dim embeddings this would fail, so we skip it.
DROP INDEX IF EXISTS embeddings_idx_cosine;

-- ======================
-- NOTE RELATIONS
-- ======================
CREATE TABLE IF NOT EXISTS note_relations (
    id uuid PRIMARY KEY,
    source_note_id uuid NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    target_note_id uuid NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    relation_type text NOT NULL CHECK (relation_type IN ('supports','contradicts','supersedes','related','duplicate')),
    confidence numeric(3,2),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (source_note_id, target_note_id),
    CONSTRAINT no_self_relation CHECK (source_note_id <> target_note_id)
);

CREATE INDEX IF NOT EXISTS note_relations_source_idx ON note_relations(source_note_id);
CREATE INDEX IF NOT EXISTS note_relations_target_idx ON note_relations(target_note_id);
CREATE INDEX IF NOT EXISTS note_relations_type_idx ON note_relations(relation_type);

-- ======================
-- ENTITIES
-- ======================
CREATE TABLE IF NOT EXISTS entities (
    id uuid PRIMARY KEY,
    entity_type text NOT NULL,
    value text NOT NULL,
    canonical_value text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS entities_type_idx ON entities(entity_type);
CREATE INDEX IF NOT EXISTS entities_canonical_idx ON entities(canonical_value);

-- ======================
-- NOTE ENTITIES
-- ======================
CREATE TABLE IF NOT EXISTS note_entities (
    note_id uuid NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    PRIMARY KEY (note_id, entity_id)
);

CREATE INDEX IF NOT EXISTS note_entities_role_idx ON note_entities(role);

-- ======================
-- TAGS
-- ======================
CREATE TABLE IF NOT EXISTS tags (
    id uuid PRIMARY KEY,
    name text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id uuid REFERENCES notes(id) ON DELETE CASCADE,
    tag_id uuid REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE INDEX IF NOT EXISTS tags_name_idx ON tags(name);
CREATE INDEX IF NOT EXISTS note_tags_note_idx ON note_tags(note_id);
CREATE INDEX IF NOT EXISTS note_tags_tag_idx ON note_tags(tag_id);
