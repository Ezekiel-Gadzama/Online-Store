"""Order accept/assign helpers."""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app import models
from app.staff_access import allowed_marketplaces_for_store, allowed_store_ids, staff_has_all_stores


def _market_slug(value: Optional[str]) -> str:
    return (value or "yandex").strip().lower()


def eligible_assignees(
    db: Session,
    business_id: int,
    store_id: int,
    marketplace: Optional[str],
) -> List[models.User]:
    market = _market_slug(marketplace)
    admin = db.query(models.User).filter(models.User.id == business_id, models.User.is_admin.is_(True)).first()
    staff = (
        db.query(models.User)
        .filter(models.User.is_admin.is_(False), models.User.created_by_id == business_id, models.User.is_active.is_(True))
        .all()
    )
    out: List[models.User] = []
    if admin:
        out.append(admin)
    for user in staff:
        if staff_has_all_stores(user):
            markets = allowed_marketplaces_for_store(user, store_id)
            if markets is None or market in markets:
                out.append(user)
            continue
        allowed_stores = allowed_store_ids(user)
        if allowed_stores is not None and store_id not in allowed_stores:
            continue
        markets = allowed_marketplaces_for_store(user, store_id)
        if markets is None or market in markets:
            out.append(user)
    seen: Set[int] = set()
    unique: List[models.User] = []
    for u in out:
        if u.id in seen:
            continue
        seen.add(u.id)
        unique.append(u)
    return unique


def get_assignment(
    db: Session, store_id: int, yandex_order_id: str
) -> Optional[models.OrderAssignment]:
    return (
        db.query(models.OrderAssignment)
        .filter(
            models.OrderAssignment.store_id == store_id,
            models.OrderAssignment.yandex_order_id == str(yandex_order_id),
        )
        .first()
    )


def assignments_for_orders(db: Session, store_id: int, yandex_order_ids: List[str]) -> Dict[str, models.OrderAssignment]:
    if not yandex_order_ids:
        return {}
    rows = (
        db.query(models.OrderAssignment)
        .filter(
            models.OrderAssignment.store_id == store_id,
            models.OrderAssignment.yandex_order_id.in_(yandex_order_ids),
        )
        .all()
    )
    return {r.yandex_order_id: r for r in rows}