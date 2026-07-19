-- Baseline schema per .claude/skills/db-schema/SKILL.md, scoped to what
-- photo calorie tracking (User Story 1) needs. photo_media_ids is baked in
-- here directly since this is the first migration in a greenfield repo.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    wa_phone text UNIQUE NOT NULL,
    name text,
    language text,
    goal text,
    experience text,
    days_per_week integer,
    equipment text,
    height_cm numeric,
    weight_kg numeric,
    birth_year integer,
    sex text,
    activity_factor numeric,
    allergies text[] NOT NULL DEFAULT '{}',
    dietary_flags text[] NOT NULL DEFAULT '{}',
    push_morning_time time,
    subscription_status text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    logged_at timestamptz NOT NULL DEFAULT now(),
    photo_media_id text NOT NULL,
    photo_media_ids text[] NOT NULL DEFAULT '{}',
    foods jsonb NOT NULL DEFAULT '[]',
    total_calories numeric NOT NULL DEFAULT 0,
    confidence numeric
);

CREATE INDEX meals_user_id_logged_at_idx ON meals (user_id, logged_at DESC);

CREATE TABLE daily_totals (
    user_id uuid NOT NULL REFERENCES users(id),
    date date NOT NULL,
    calories_consumed numeric NOT NULL DEFAULT 0,
    calorie_target integer,
    protein_g numeric NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    direction text NOT NULL CHECK (direction IN ('in', 'out')),
    wa_message_id text UNIQUE,
    body text,
    kind text NOT NULL CHECK (kind IN ('text', 'image', 'template')),
    created_at timestamptz NOT NULL DEFAULT now()
);
