from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    anthropic_api_key: str = ""
    database_url: str = ""
    live_vision_model_id: str = "claude-sonnet-5"
    # Fixed local hour (0-23) the end-of-day report/target-ask fires at for
    # every user — not user-configurable in the MVP (spec 001, Assumptions).
    eod_report_hour: int = 21
    # Shared secret the external scheduler (Railway/Render cron or similar)
    # must present to POST /internal/eod-trigger. Unset always rejects, same
    # defensive posture as whatsapp_app_secret.
    scheduler_secret: str = ""
    # Name of the Meta-approved WhatsApp template used to reach a user whose
    # 24h customer-service window has expired before a proactive push (see
    # app/whatsapp/templates.py). Empty until one is registered in Meta
    # Business Manager — an operational step outside this codebase.
    eod_template_name: str = ""


settings = Settings()
