from __future__ import annotations

import datetime as dt
import hmac
import logging
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/internal/eod-trigger")
async def trigger_eod(x_scheduler_secret: str | None = Header(default=None)) -> dict:
    """Hit periodically (every 5-15 min, research.md #9) by an external
    scheduled job (e.g. a Railway/Render cron) — there's no in-process
    scheduler here since an ephemeral deploy can't reliably keep one running
    across restarts. Protected by a shared secret header, same defensive
    posture as the WhatsApp webhook's own signature check: an unset secret
    always rejects rather than accepting an unauthenticated trigger that
    could mass-send proactive messages to every user."""
    configured = settings.scheduler_secret
    if (
        not configured
        or not x_scheduler_secret
        or not hmac.compare_digest(x_scheduler_secret, configured)
    ):
        raise HTTPException(status_code=403, detail="Invalid scheduler secret")
    handled = await run_eod_trigger()
    return {"handled": handled}


async def run_eod_trigger(now: dt.datetime | None = None) -> int:
    """For each user whose local time is currently within the fixed
    end-of-day report hour (settings.eod_report_hour, spec Assumptions: one
    fixed local time for all users in the MVP) and hasn't already been
    handled today: sends either the daily-target ask (FR-007, if no target
    is on file yet) or the end-of-day report (FR-006).

    Idempotent per user per day via pending_daily_target_asks.asked_at and
    the daily_reports unique constraint, so re-invocation within the same
    hour — this runs several times an hour by design, per the polling
    interval above — is always safe and never double-sends.

    Every per-user step, including the time zone conversion and the actual
    send, runs inside that user's own try/except (reviewer-flagged bug found
    live: an earlier version left the time zone conversion and the send call
    outside the try block, so one user's bad time zone or a non-131047 send
    error would abort the whole run and skip every remaining user). Each
    user's "handled" state is only persisted *after* their message is
    actually sent — never before — so a delivery failure is retried on the
    next scheduler tick instead of being silently, permanently lost.

    Returns the number of users actually messaged, for the caller/logs."""
    from app.db import queries
    from app.db.pool import get_pool
    from app.services import daily_target, eod_report
    from app.whatsapp import templates

    now = now or dt.datetime.now(dt.UTC)
    pool = await get_pool()
    users = await queries.get_users_for_eod_check(pool)

    handled = 0
    for user in users:
        try:
            user_id = str(user["id"])
            wa_phone = user["wa_phone"]
            time_zone = user["time_zone"]
            local_now = now.astimezone(ZoneInfo(time_zone))
            if local_now.hour != settings.eod_report_hour:
                continue
            today = local_now.date()

            if user["daily_calorie_target"] is None:
                if await _already_asked_today(pool, queries, user_id, today, time_zone):
                    continue
                reply = await daily_target.build_target_ask()
                await templates.send_proactive_message(wa_phone, reply)
                await daily_target.mark_target_ask_sent(user_id, wa_phone)
            else:
                draft = await eod_report.build_report(user_id, wa_phone, today)
                if draft is None:  # already recorded by a near-simultaneous run
                    continue
                await templates.send_proactive_message(wa_phone, draft.message)
                await eod_report.record_report_sent(user_id, today, draft)

            handled += 1
        except Exception:
            logger.exception("Failed end-of-day handling for user_id=%s", user.get("id"))
            continue

    return handled


async def _already_asked_today(pool, queries, user_id: str, today: dt.date, time_zone: str) -> bool:
    asked_at = await queries.get_pending_daily_target_ask(pool, user_id)
    if asked_at is None:
        return False
    return asked_at.astimezone(ZoneInfo(time_zone)).date() == today
