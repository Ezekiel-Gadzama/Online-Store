from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_active_user
from app.database import get_db
from app.staff_access import assert_store_access, marketplace_filters_for_request
from app.store_context import get_current_store


@dataclass
class StoreDataScope:
    store: models.MarketStore
    selected_marketplaces: Optional[Set[str]]
    marketplaces: Optional[Set[str]]


def _prefs_for_store(user: models.User, store_id: int) -> dict:
    prefs = user.store_ui_preferences if isinstance(user.store_ui_preferences, dict) else {}
    block = prefs.get(str(store_id))
    return block if isinstance(block, dict) else {}


def _enabled_market_slugs(db: Session, store_id: int) -> Set[str]:
    rows = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.store_id == store_id,
            models.StoreMarketplaceConnection.is_enabled.is_(True),
        )
        .all()
    )
    return {str(r.marketplace).strip().lower() for r in rows if r.marketplace}


def parse_marketplaces_header(
    x_marketplaces: Optional[str] = Header(None, alias="X-Marketplaces"),
    x_data_view: Optional[str] = Header(None, alias="X-Data-View"),
    x_marketplace: Optional[str] = Header(None, alias="X-Marketplace"),
) -> Optional[Set[str]]:
    if x_marketplaces and str(x_marketplaces).strip():
        parts = {p.strip().lower() for p in str(x_marketplaces).split(",") if p.strip()}
        return parts if parts else None
    if (x_data_view or "").strip().lower() == "separate" and x_marketplace and str(x_marketplace).strip():
        return {str(x_marketplace).strip().lower()}
    return None


def get_store_data_scope(
    store: models.MarketStore = Depends(get_current_store),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    header_markets: Optional[Set[str]] = Depends(parse_marketplaces_header),
) -> StoreDataScope:
    assert_store_access(current_user, store)
    prefs = _prefs_for_store(current_user, store.id)
    pref_list = prefs.get("selected_marketplaces")
    if isinstance(pref_list, list) and pref_list:
        selected = {str(m).strip().lower() for m in pref_list if str(m).strip()}
    elif header_markets:
        selected = header_markets
    else:
        selected = _enabled_market_slugs(db, store.id)
    markets = marketplace_filters_for_request(current_user, store.id, selected)
    return StoreDataScope(
        store=store,
        selected_marketplaces=selected,
        marketplaces=markets,
    )


def apply_order_marketplace_filter(query, scope: StoreDataScope):
    if scope.marketplaces is None:
        return query
    if not scope.marketplaces:
        return query.filter(models.Order.id == -1)
    return query.filter(models.Order.marketplace.in_(list(scope.marketplaces)))


def products_for_store(query, business_id: int, store_id: int):
    return query.filter(
        models.Product.business_id == business_id,
        models.Product.store_id == store_id,
    )


def email_templates_for_store(query, business_id: int, store_id: int):
    return query.filter(
        models.EmailTemplate.business_id == business_id,
        models.EmailTemplate.store_id == store_id,
    )


def documentations_for_store(query, business_id: int, store_id: int):
    return query.filter(
        models.Documentation.business_id == business_id,
        models.Documentation.store_id == store_id,
    )