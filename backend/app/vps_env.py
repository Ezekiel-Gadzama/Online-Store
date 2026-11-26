"""Apply VPS / docker .env Yandex and SMTP values to app_settings."""
import os

from sqlalchemy.orm import Session

from app import models


def _env(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def apply_env_settings_for_business(db: Session, business_id: int) -> None:
    token = _env("YANDEX_MARKET_API_TOKEN")
    yandex_business = _env("YANDEX_MARKET_BUSINESS_ID") or "217104046"
    campaign = _env("YANDEX_MARKET_CAMPAIGN_ID")

    if token and not campaign:
        try:
            from app.yandex_campaigns import fetch_campaigns_list

            camps = fetch_campaigns_list(
                token,
                business_id=yandex_business or None,
            )
            if camps:
                campaign = str(camps[0].get("id", ""))
        except Exception:
            pass

    settings_row = (
        db.query(models.AppSettings)
        .filter(models.AppSettings.business_id == business_id)
        .first()
    )
    if not settings_row:
        settings_row = models.AppSettings(business_id=business_id)
        db.add(settings_row)

    if token:
        settings_row.yandex_api_token = token
    settings_row.yandex_business_id = yandex_business
    if campaign:
        settings_row.yandex_campaign_id = campaign
    settings_row.yandex_api_url = "https://api.partner.market.yandex.ru"

    smtp_user = _env("SMTP_USER")
    smtp_password = _env("SMTP_PASSWORD")
    if smtp_user and smtp_password:
        settings_row.smtp_host = _env("SMTP_HOST") or "smtp.gmail.com"
        settings_row.smtp_port = int(_env("SMTP_PORT") or "587")
        settings_row.smtp_user = smtp_user
        settings_row.smtp_password = smtp_password
        settings_row.smtp_from_email = _env("SMTP_FROM_EMAIL") or smtp_user

    db.commit()