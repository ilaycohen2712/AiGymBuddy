-- Vision model abstraction & comparison (specs/003-vision-model-comparison).
-- model_candidates mirrors app/services/vision_models.py's MODEL_REGISTRY
-- keys, so meals.model_id and model_results.model_id have real FK targets.

CREATE TABLE model_candidates (
    id text PRIMARY KEY,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO model_candidates (id, display_name) VALUES
    ('claude-sonnet-5', 'Claude Sonnet 5'),
    ('claude-opus-4-8', 'Claude Opus 4.8');

CREATE TABLE comparison_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed')),
    triggered_by text
);

CREATE TABLE model_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    comparison_run_id uuid NOT NULL REFERENCES comparison_runs(id),
    model_id text NOT NULL REFERENCES model_candidates(id),
    fixture_image text NOT NULL,
    status text NOT NULL CHECK (status IN ('ok', 'failed')),
    foods jsonb,
    total_calories numeric,
    protein_g numeric,
    carbs_g numeric,
    fat_g numeric,
    confidence numeric,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (comparison_run_id, model_id, fixture_image)
);

CREATE TABLE accuracy_scores (
    comparison_run_id uuid NOT NULL REFERENCES comparison_runs(id),
    model_id text NOT NULL REFERENCES model_candidates(id),
    metric text NOT NULL CHECK (metric IN ('calories', 'protein', 'carbs', 'fat')),
    mean_absolute_error_pct numeric NOT NULL,
    sample_count integer NOT NULL,
    PRIMARY KEY (comparison_run_id, model_id, metric)
);

ALTER TABLE meals ADD COLUMN model_id text REFERENCES model_candidates(id);
