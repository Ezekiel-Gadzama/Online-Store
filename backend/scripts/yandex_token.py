"""Yandex API token and ids from env or app DB."""
from __future__ import annotations

import os
from typing import Optional, Tuple


def load_yandex_token() -> str:
    tok = os.environ.get("YANDEX_API_TOKEN", "").strip()
    if tok:
        return tok
    try:
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        try:
            row = (
                db.query(models.AppSettings)
                .filter(models.AppSettings.yandex_api_token.isnot(None))
                .order_by(models.AppSettings.id.asc())
                .first()
            )
            if row and row.yandex_api_token:
                return str(row.yandex_api_token)
        finally:
            db.close()
    except Exception as exc:
        print("Yandex token from DB failed:", exc)
    return ""


def load_store_yandex(
    store_id: int,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """token, business_id, campaign_id, store_name."""
    try:
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        try:
            store = db.query(models.MarketStore).filter(models.MarketStore.id == store_id).first()
            if not store:
                return None, None, None, None
            settings = (
                db.query(models.AppSettings)
                .filter(models.AppSettings.store_id == store_id)
                .first()
            )
            token = (settings.yandex_api_token if settings else None) or load_yandex_token()
            business = (store.yandex_business_id or "").strip() or None
            campaign = (store.yandex_campaign_id or "").strip() or None
            if settings and not business:
                business = (settings.yandex_business_id or "").strip() or None
            if settings and not campaign:
                campaign = (settings.yandex_campaign_id or "").strip() or None
            tok = str(token) if token else None
            return tok, business, campaign, store.name
        finally:
            db.close()
    except Exception as exc:
        print("Store Yandex settings from DB failed:", exc)
    return None, None, None, None