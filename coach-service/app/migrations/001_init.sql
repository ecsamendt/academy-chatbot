-- Socio AI Coach: initial schema (Phase 0/1).
-- Vector size must match EMBEDDING_DIM (1536 for text-embedding-3-small).

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per searchable passage: a 30-90 s slice of a lesson transcript,
-- or a hand-written tool entry.
CREATE TABLE passages (
    id               BIGSERIAL PRIMARY KEY,
    source_type      TEXT NOT NULL CHECK (source_type IN ('lesson', 'tool', 'podcast')),
    source_id        TEXT NOT NULL,              -- WordPress lesson ID, or tool key
    course_id        TEXT,
    course_title     TEXT,
    module_title     TEXT,
    lesson_title     TEXT NOT NULL,
    lesson_url       TEXT NOT NULL,
    vimeo_id         TEXT,
    start_sec        INTEGER,
    end_sec          INTEGER,
    text             TEXT NOT NULL,
    topics           TEXT[] NOT NULL DEFAULT '{}',
    language         TEXT NOT NULL DEFAULT 'es',
    -- Access gating. A passage is visible to a member when is_public is true,
    -- or when the member holds one of allowed_memberships. Empty list + not
    -- public means staff only, so a missing rule never leaks locked content.
    is_public        BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_memberships INTEGER[] NOT NULL DEFAULT '{}',
    required_plan_label TEXT,                    -- shown in upgrade prompts
    embedding        vector(1536) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX passages_source_idx ON passages (source_type, source_id);
CREATE INDEX passages_embedding_idx ON passages USING hnsw (embedding vector_cosine_ops);

-- Per-lesson ingestion status, so re-indexing can skip unchanged lessons.
CREATE TABLE lessons (
    lesson_id        TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    url              TEXT NOT NULL,
    course_title     TEXT,
    vimeo_ids        TEXT[] NOT NULL DEFAULT '{}',
    wp_modified      TEXT,
    status           TEXT NOT NULL,               -- indexed | no_video | multiple_videos | error
    detail           TEXT,
    passage_count    INTEGER NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Simple durable job queue for the worker (transcription can take minutes).
CREATE TABLE jobs (
    id               BIGSERIAL PRIMARY KEY,
    kind             TEXT NOT NULL,
    payload          JSONB NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | failed
    attempts         INTEGER NOT NULL DEFAULT 0,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX jobs_queue_idx ON jobs (status, id);

-- One row per question (see spec: Insights and logging).
CREATE TABLE question_events (
    question_id      UUID PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    member_ref       TEXT NOT NULL,
    memberships      INTEGER[] NOT NULL DEFAULT '{}',
    question         TEXT NOT NULL,
    language         TEXT,
    topic            TEXT,
    intent           TEXT,
    time_sensitive   BOOLEAN,
    sensitive        BOOLEAN,
    layer            TEXT NOT NULL,   -- own_content | partial | general | web_search | locked_upsell | no_match
    top_score        REAL,
    cited_lessons    TEXT[] NOT NULL DEFAULT '{}',
    cited_tools      TEXT[] NOT NULL DEFAULT '{}',
    offers_shown     TEXT[] NOT NULL DEFAULT '{}',
    feedback         SMALLINT,        -- 1 thumbs up, -1 thumbs down
    tokens_in        INTEGER,
    tokens_out       INTEGER,
    cost_usd         NUMERIC(10, 5),
    latency_ms       INTEGER
);

CREATE INDEX question_events_created_idx ON question_events (created_at);

-- Lesson / tool / upgrade clicks from coach answers.
CREATE TABLE click_events (
    id               BIGSERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    question_id      UUID REFERENCES question_events (question_id),
    member_ref       TEXT NOT NULL,
    kind             TEXT NOT NULL,   -- lesson | tool | upgrade | offer
    target           TEXT NOT NULL
);
