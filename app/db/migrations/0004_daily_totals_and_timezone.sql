-- Daily calorie & macro total tracking (specs/002-daily-total-tracking).
-- daily_totals gains macro columns to match what's already reported per
-- individual meal; users gains a mutable time zone used to determine each
-- user's local midnight (FR-003, FR-005, FR-010).

ALTER TABLE daily_totals
    ADD COLUMN carbs_g numeric NOT NULL DEFAULT 0,
    ADD COLUMN fat_g numeric NOT NULL DEFAULT 0;

ALTER TABLE users
    ADD COLUMN time_zone text NOT NULL DEFAULT 'UTC';
