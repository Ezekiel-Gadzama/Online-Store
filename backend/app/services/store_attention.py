"""Per-store attention signals for the store switcher and notifications."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app import models
from app.marketplace_service import overlay_yandex_on_settings
from app.services.config_validator import get_business_settings


def _parse_seen(iso: Optional[str]) -> Optional[datetime]:
    if not iso or not str(iso).strip():
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def store_missing_marketplace_api(db: Session, business_id: int, store_id: int) -> bool:
    conns = (
        db.query(models.StoreMarketplaceConnection)
        .filter(models.StoreMarketplaceConnection.store_id == store_id)
        .all()
    )
    for conn in conns:
        creds = conn.credentials or {}
        if (creds.get("api_token") or "").strip():
            return False
    settings = get_business_settings(business_id, db, store_id)
    if settings:
        overlay_yandex_on_settings(settings, db, store_id)
        if (settings.yandex_api_token or "").strip():
            return False
    return True


def pending_orders_count(
    db: Session, business_id: int, store_id: int, since: Optional[datetime]
) -> int:
    q = db.query(models.Order).filter(
        models.Order.business_id == business_id,
        models.Order.store_id == store_id,
        models.Order.status.in_([models.OrderStatus.PENDING, models.OrderStatus.PROCESSING]),
    )
    if since:
        q = q.filter(models.Order.updated_at > since)
    return q.count()


def chats_waiting_count(business_id: int, db: Session, store_id: int) -> int:
    if store_missing_marketplace_api(db, business_id, store_id):
        return 0
    try:
        from app.services.yandex_api import YandexMarketAPI

        api = YandexMarketAPI(business_id=business_id, db=db, store_id=store_id)
        result = api.get_chats(limit=20)
        chats = result.get("chats") or []
        return sum(1 for c in chats if str(c.get("status", "")).upper() == "WAITING_FOR_PARTNER")
    except Exception:
        return 0


def attention_for_store(
    db: Session,
    business_id: int,
    store_id: int,
    seen_at_map: Dict[str, Any],
) -> dict:
    missing_api = store_missing_marketplace_api(db, business_id, store_id)
    since = _parse_seen(seen_at_map.get(str(store_id)))
    pending = pending_orders_count(db, business_id, store_id, since)
    chats = chats_waiting_count(business_id, db, store_id)
    has_attention = missing_api or pending > 0 or chats > 0
    return {
        "has_attention": has_attention,
        "missing_api": missing_api,
        "pending_orders": pending,
        "chats_waiting": chats,
    }