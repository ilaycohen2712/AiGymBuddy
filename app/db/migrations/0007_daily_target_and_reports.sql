-- Daily calorie target collection + end-of-day report (specs/001-photo-
-- calorie-tracking, User Story 3).

ALTER TABLE users
    ADD COLUMN daily_calorie_target integer;

-- Tracks that a user has been asked for their daily calorie target today, so
-- the very next text reply is treated as an attempted answer (same pattern
-- as pending_clarifications) and so the scheduler doesn't re-send the ask
-- more than once within the same day while waiting for a reply.
CREATE TABLE pending_daily_target_asks (
    user_id uuid PRIMARY KEY REFERENCES users(id),
    asked_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE daily_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    date date NOT NULL,
    calories_total numeric NOT NULL,
    protein_g numeric NOT NULL,
    carbs_g numeric NOT NULL,
    fat_g numeric NOT NULL,
    feedback_text text NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, date)
);
