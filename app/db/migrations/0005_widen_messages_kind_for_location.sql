-- New inbound message type for daily total tracking (WhatsApp location
-- share, User Story 4, specs/002-daily-total-tracking) — widen the existing
-- kind check rather than leave it rejecting a real, expected value.
--
-- Split into its own migration (rather than bundled with
-- 0004_daily_totals_and_timezone.sql) because that filename was already
-- applied elsewhere without this change — the migration runner skips a
-- filename it's already recorded, regardless of content, so amending 0004
-- after the fact would never actually run against a database that's already
-- past it.
ALTER TABLE messages DROP CONSTRAINT messages_kind_check;
ALTER TABLE messages ADD CONSTRAINT messages_kind_check
    CHECK (kind IN ('text', 'image', 'template', 'location'));
