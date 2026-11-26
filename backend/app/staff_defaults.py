"""Default permissions and owner locks for new accounts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app import models

DEFAULT_STAFF_PERMISSIONS: Dict[str, bool] = {
    "view_staff": True,
    "view_settings": True,
    "client_right": True,
    "view_marketing_emails": True,
    "dashboard_right": True,
    "view_product_prices": True,
    "create_store": False,
    "delete_store": False,
}

DEFAULT_OWNER_RESTRICTIONS: Dict[str, Any] = {
    "permissions": {
        "create_store": True,
        "delete_store": True,
    },
    "store_market_access": False,
    "password_change": False,
}


def default_store_market_access(db: Session, owner_id: int) -> Dict[str, Any]:
    """First store, Yandex only — matches standard staff onboarding."""
    store = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.owner_id == owner_id)
        .order_by(models.MarketStore.id.asc())
        .first()
    )
    if not store:
        return {"all_stores": False, "stores": {}}
    return {"all_stores": False, "stores": {str(store.id): ["yandex"]}}


def new_staff_fields(
    db: Session,
    owner_id: int,
    *,
    is_business_admin: Optional[bool] = None,
    business_admin_all_stores: Optional[bool] = None,
) -> Dict[str, Any]:
    return {
        "permissions": dict(DEFAULT_STAFF_PERMISSIONS),
        "is_business_admin": True if is_business_admin is None else is_business_admin,
        "business_admin_all_stores": False if business_admin_all_stores is None else business_admin_all_stores,
        "store_market_access": default_store_market_access(db, owner_id),
        "owner_restrictions": {},
    }