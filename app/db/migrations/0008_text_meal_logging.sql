-- Text-based meal logging (specs/005-text-meal-logging). A meal can now
-- originate from a typed food description instead of only a photo, so
-- photo_media_id can no longer be NOT NULL. text_entries parallels
-- photo_media_ids: each text-originated contribution's raw body, in the
-- order it was added, so a meal's total contribution count is
-- len(photo_media_ids) + len(text_entries) regardless of origin mix.

ALTER TABLE meals ALTER COLUMN photo_media_id DROP NOT NULL;
ALTER TABLE meals ADD COLUMN text_entries text[] NOT NULL DEFAULT '{}';

-- reviewer-flagged: application code guarantees every meal has at least one
-- contribution (a photo or a typed description), but nothing enforced that
-- at the DB level — a future caller bug could silently insert a
-- contribution-less row into this health-data table. Defense-in-depth.
ALTER TABLE meals ADD CONSTRAINT meals_has_a_contribution
    CHECK (photo_media_id IS NOT NULL OR array_length(text_entries, 1) > 0);

-- A text-originated pending clarifying question has no photo to re-download
-- when completing the analysis — the original text itself must be stored
-- instead, so media_id becomes nullable and a parallel text_body column
-- holds it when media_type = 'text'.
ALTER TABLE pending_clarifications ALTER COLUMN media_id DROP NOT NULL;
ALTER TABLE pending_clarifications ADD COLUMN text_body text;
