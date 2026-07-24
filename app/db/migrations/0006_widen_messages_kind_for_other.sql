-- New inbound message kind for message types the bot has no dedicated
-- handler for (voice notes, stickers, documents, video, etc.) — specs/
-- 004-chat-responsiveness, User Story 2. One bucket for all of them rather
-- than one value per WhatsApp type, since the bot's behavior (a single
-- fixed acknowledgment) is identical regardless of which one it was and no
-- code path reads `kind` to distinguish between them (research.md #5).
ALTER TABLE messages DROP CONSTRAINT messages_kind_check;
ALTER TABLE messages ADD CONSTRAINT messages_kind_check
    CHECK (kind IN ('text', 'image', 'template', 'location', 'other'));
