"""Yandex Market store (campaign) selection for multi-store accounts."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.auth import get_business_id, get_current_active_user
from app.database import get_db
from app.staff_access import assert_store_access, filter_stores_for_user


def parse_store_header(x_store_id: Optional[str] = Header(None, alias="X-Store-Id")) -> Optional[int]:
    if not x_store_id or not str(x_store_id).strip():
        return None
    try:
        return int(x_store_id)
    except ValueError:
        return None


def get_owner_stores(db: Session, owner_id: int):
    return (
        db.query(models.MarketStore)
        .filter(models.MarketStore.owner_id == owner_id)
        .order_by(models.MarketStore.id.asc())
        .all()
    )


def get_app_settings_for_store(
    db: Session, owner_id: int, store_id: Optional[int]
) -> Optional[models.AppSettings]:
    if store_id:
        return (
            db.query(models.AppSettings)
            .filter(
                models.AppSettings.business_id == owner_id,
                models.AppSettings.store_id == store_id,
            )
            .first()
        )
    row = (
        db.query(models.AppSettings)
        .filter(models.AppSettings.business_id == owner_id)
        .order_by(models.AppSettings.id.asc())
        .first()
    )
    return row


def get_current_store(
    store_id: Optional[int] = Depends(parse_store_header),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> models.MarketStore:
    owner_id = get_business_id(current_user)
    stores = filter_stores_for_user(current_user, get_owner_stores(db, owner_id))
    if not stores:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No stores configured. Create a store first.",
        )
    if store_id is None:
        return stores[0]
    store = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.id == store_id, models.MarketStore.owner_id == owner_id)
        .first()
    )
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    assert_store_access(current_user, store)
    return store