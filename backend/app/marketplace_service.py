"""Per-store marketplace API credentials (multi-marketplace per store)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app import models

MARKETPLACE_CHOICES = frozenset(
    {"yandex", "ozon", "wildberries", "aliexpress", "other"}
)


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def sync_yandex_app_settings(db: Session, store_id: int) -> None:
    """Copy primary Yandex connection credentials into app_settings for legacy sync paths."""
    settings = (
        db.query(models.AppSettings)
        .filter(models.AppSettings.store_id == store_id)
        .first()
    )
    if not settings:
        return
    conn = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.store_id == store_id,
            models.StoreMarketplaceConnection.marketplace == "yandex",
            models.StoreMarketplaceConnection.is_enabled.is_(True),
        )
        .order_by(models.StoreMarketplaceConnection.id.asc())
        .first()
    )
    store = db.query(models.MarketStore).filter(models.MarketStore.id == store_id).first()
    if not conn:
        return
    creds = conn.credentials or {}
    token = _s(creds.get("api_token"))
    business_id = _s(creds.get("business_id"))
    campaign_id = _s(creds.get("campaign_id"))
    api_url = _s(creds.get("api_url"))
    if token:
        settings.yandex_api_token = token
    if business_id:
        settings.yandex_business_id = business_id
    if campaign_id:
        settings.yandex_campaign_id = campaign_id
    if api_url:
        settings.yandex_api_url = api_url
    if store:
        if campaign_id:
            store.yandex_campaign_id = campaign_id
        if business_id:
            store.yandex_business_id = business_id


def overlay_yandex_on_settings(
    settings: Optional[models.AppSettings], db: Session, store_id: Optional[int]
) -> Optional[models.AppSettings]:
    if not settings or not store_id:
        return settings
    conn = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.store_id == store_id,
            models.StoreMarketplaceConnection.marketplace == "yandex",
            models.StoreMarketplaceConnection.is_enabled.is_(True),
        )
        .order_by(models.StoreMarketplaceConnection.id.asc())
        .first()
    )
    if not conn:
        return settings
    creds = conn.credentials or {}
    token = _s(creds.get("api_token"))
    if token:
        settings.yandex_api_token = token
    business_id = _s(creds.get("business_id"))
    if business_id:
        settings.yandex_business_id = business_id
    campaign_id = _s(creds.get("campaign_id"))
    if campaign_id:
        settings.yandex_campaign_id = campaign_id
    api_url = _s(creds.get("api_url"))
    if api_url:
        settings.yandex_api_url = api_url
    return settings


def primary_yandex_connection_id(db: Session, store_id: int) -> Optional[int]:
    row = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.store_id == store_id,
            models.StoreMarketplaceConnection.marketplace == "yandex",
            models.StoreMarketplaceConnection.is_enabled.is_(True),
        )
        .order_by(models.StoreMarketplaceConnection.id.asc())
        .first()
    )
    return row.id if row else None


def sync_all_store_connections(business_id: int, store_id: int, db: Session, force: bool = False) -> dict:
    """Sync every enabled marketplace connection configured for a store (Yandex implemented)."""
    from app.main import _sync_orders_sync, _sync_products_sync

    conns = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.store_id == store_id,
            models.StoreMarketplaceConnection.is_enabled.is_(True),
        )
        .order_by(models.StoreMarketplaceConnection.id.asc())
        .all()
    )
    errors: list[str] = []
    if not conns:
        return {"connections": 0, "errors": ["No marketplace APIs configured for this store"]}

    products_done = False
    for conn in conns:
        mp = (conn.marketplace or "").lower()
        try:
            if mp == "yandex":
                if not products_done:
                    _sync_products_sync(business_id=business_id, store_id=store_id)
                    products_done = True
                _sync_orders_sync(business_id=business_id, store_id=store_id)
            else:
                errors.append(f"{mp}: sync not implemented yet")
        except Exception as e:
            errors.append(f"{mp}: {e}")
    return {"connections": len(conns), "errors": errors}


def migrate_app_settings_to_connections(db: Session) -> None:
    rows = db.query(models.AppSettings).filter(models.AppSettings.store_id.isnot(None)).all()
    for row in rows:
        has_yandex = bool(_s(row.yandex_api_token))
        if not has_yandex:
            continue
        exists = (
            db.query(models.StoreMarketplaceConnection)
            .filter(
                models.StoreMarketplaceConnection.store_id == row.store_id,
                models.StoreMarketplaceConnection.marketplace == "yandex",
            )
            .first()
        )
        if exists:
            continue
        creds: Dict[str, Any] = {
            "api_token": row.yandex_api_token,
            "business_id": row.yandex_business_id,
            "campaign_id": row.yandex_campaign_id,
            "api_url": row.yandex_api_url,
        }
        db.add(
            models.StoreMarketplaceConnection(
                store_id=row.store_id,
                marketplace="yandex",
                label="Yandex Market",
                credentials=creds,
                is_enabled=True,
            )
        )
    db.commit()