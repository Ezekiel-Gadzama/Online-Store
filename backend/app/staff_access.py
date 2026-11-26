"""Staff access to stores and marketplace APIs within a business."""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import models


def _access_row(user: models.User) -> Dict:
    data = user.store_market_access
    if isinstance(data, dict):
        return data
    return {}


def staff_has_all_stores(user: models.User) -> bool:
    if user.is_admin:
        return True
    return bool(_access_row(user).get("all_stores"))


def allowed_store_ids(user: models.User) -> Optional[Set[int]]:
    """None = all stores in business. Empty set = no stores."""
    if user.is_admin or staff_has_all_stores(user):
        return None
    raw = _access_row(user).get("stores") or {}
    out: Set[int] = set()
    for key in raw:
        try:
            out.add(int(key))
        except (TypeError, ValueError):
            continue
    return out


def allowed_marketplaces_for_store(user: models.User, store_id: int) -> Optional[Set[str]]:
    """None = all marketplaces in that store (admin / all_stores)."""
    if user.is_admin or staff_has_all_stores(user):
        return None
    raw = _access_row(user).get("stores") or {}
    key = str(store_id)
    if key not in raw:
        return set()
    markets = raw.get(key)
    if not isinstance(markets, list):
        return set()
    return {str(m).strip().lower() for m in markets if str(m).strip()}


def assert_store_access(user: models.User, store: models.MarketStore) -> None:
    if user.is_admin:
        return
    if staff_has_all_stores(user):
        return
    allowed = allowed_store_ids(user)
    if allowed is None:
        return
    if store.id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this store")


def filter_stores_for_user(user: models.User, stores: List[models.MarketStore]) -> List[models.MarketStore]:
    allowed = allowed_store_ids(user)
    if allowed is None:
        return stores
    return [s for s in stores if s.id in allowed]


def marketplace_filters_for_request(
    user: models.User,
    store_id: int,
    selected_marketplaces: Optional[Set[str]],
) -> Optional[Set[str]]:
    """
    Return marketplace slugs to include in queries.
    Empty set = no data visible.
    """
    allowed = allowed_marketplaces_for_store(user, store_id)
    sel = selected_marketplaces or set()
    if allowed is not None:
        sel = sel & allowed
    return sel