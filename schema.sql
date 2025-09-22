-- Zorg dat pgvector beschikbaar is
CREATE EXTENSION IF NOT EXISTS vector;

-- ======================
-- NOTES
-- ======================
CREATE TABLE notes (
    id uuid PRIMARY KEY,
    title text NOT NULL,
    content text NOT NULL,
    summary text NOT NULL,
    author text NOT NULL,
    status text DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Index voor veelgebruikte filters
CREATE INDEX notes_status_idx ON notes(status);
CREATE INDEX notes_created_at_idx ON notes(created_at);

-- ======================
-- EMBEDDINGS
-- ======================
CREATE TABLE embeddings (
    note_id uuid PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    model text NOT NULL,
    dim int NOT NULL,
    embedding vector(3072) NOT NULL,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Index voor snelle similarity search
CREATE INDEX embeddings_idx_cosine
ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ======================
-- NOTE RELATIONS
-- ======================
CREATE TABLE note_relations (
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

-- Indexen voor snellere filters en joins
CREATE INDEX note_relations_source_idx ON note_relations(source_note_id);
CREATE INDEX note_relations_target_idx ON note_relations(target_note_id);
CREATE INDEX note_relations_type_idx ON note_relations(relation_type);

-- ======================
-- ENTITIES
-- ======================
CREATE TABLE entities (
    id uuid PRIMARY KEY,
    entity_type text NOT NULL,       -- bv. app, proces, rol, locatie
    value text NOT NULL,             -- originele waarde
    canonical_value text,            -- genormaliseerde vorm
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Indexen voor entity lookups
CREATE INDEX entities_type_idx ON entities(entity_type);
CREATE INDEX entities_canonical_idx ON entities(canonical_value);

-- ======================
-- NOTE ENTITIES (koppel)
-- ======================
CREATE TABLE note_entities (
    note_id uuid NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role text,                       -- bv. onderwerp, actie
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    PRIMARY KEY (note_id, entity_id)
);

-- Index voor zoeken/filteren op role
CREATE INDEX note_entities_role_idx ON note_entities(role);

-- ======================
-- TAGS
-- ======================
CREATE TABLE tags (
    id uuid PRIMARY KEY,
    name text UNIQUE NOT NULL
);

CREATE TABLE note_tags (
    note_id uuid REFERENCES notes(id) ON DELETE CASCADE,
    tag_id uuid REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

-- Indexen voor tag lookups
CREATE INDEX tags_name_idx ON tags(name);
CREATE INDEX note_tags_note_idx ON note_tags(note_id);
CREATE INDEX note_tags_tag_idx ON note_tags(tag_id);
