-- Tracks a user's single outstanding clarifying question (per calorie_vision.md
-- rule 6) so a subsequent text reply can resume and complete that photo's
-- analysis instead of the question being a dead end.

CREATE TABLE pending_clarifications (
    user_id uuid PRIMARY KEY REFERENCES users(id),
    media_id text NOT NULL,
    media_type text NOT NULL DEFAULT 'image/jpeg',
    question text NOT NULL,
    asked_at timestamptz NOT NULL DEFAULT now()
);
