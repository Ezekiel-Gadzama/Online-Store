"""Owner vs business-admin roles and owner-only restriction locks."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app import models

PERMISSION_KEYS = (
    "view_staff",
    "view_settings",
    "client_right",
    "view_marketing_emails",
    "dashboard_right",
    "view_product_prices",
    "create_store",
    "delete_store",
)

ALL_PERMISSIONS_TRUE: Dict[str, bool] = {k: True for k in PERMISSION_KEYS}
ALL_PERMISSIONS_TRUE["view_product_prices"] = True


def is_owner(user: models.User) -> bool:
    return bool(user.is_admin)


def is_business_admin(user: models.User) -> bool:
    return bool(getattr(user, "is_business_admin", False))


def restrictions_dict(user: models.User) -> Dict[str, Any]:
    raw = getattr(user, "owner_restrictions", None)
    return raw if isinstance(raw, dict) else {}


def permission_owner_locked(user: models.User, key: str) -> bool:
    locks = restrictions_dict(user).get("permissions")
    if not isinstance(locks, dict):
        return False
    return bool(locks.get(key))


def section_owner_locked(user: models.User, section: str) -> bool:
    return bool(restrictions_dict(user).get(section))


def business_admin_covers_store(user: models.User, store_id: Optional[int]) -> bool:
    if not is_business_admin(user):
        return False
    if getattr(user, "business_admin_all_stores", True):
        return True
    if store_id is None:
        return True
    access = user.store_market_access if isinstance(user.store_market_access, dict) else {}
    if access.get("all_stores"):
        return True
    stores = access.get("stores")
    if not isinstance(stores, dict):
        return False
    return str(store_id) in stores


def can_view_staff_page(user: models.User, store_id: Optional[int] = None) -> bool:
    if is_owner(user):
        return True
    from app.staff_permissions import effective_permissions_dict

    return bool(effective_permissions_dict(user, store_id).get("view_staff"))


def can_manage_staff_rights(actor: models.User, store_id: Optional[int] = None) -> bool:
    if is_owner(actor):
        return True
    if is_business_admin(actor) and business_admin_covers_store(actor, store_id):
        return not permission_owner_locked(actor, "view_staff")
    return False


def assert_can_change_permissions(actor: models.User, target: models.User, store_id: Optional[int] = None) -> None:
    if is_owner(actor):
        return
    if not can_manage_staff_rights(actor, store_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or a business admin may change staff permissions",
        )
    if actor.id == target.id and not is_business_admin(actor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot change your own permissions",
        )


def assert_no_locked_permission_grants(target: models.User, perm: Dict[str, Any]) -> None:
    for key in PERMISSION_KEYS:
        if permission_owner_locked(target, key) and perm.get(key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{key}' is owner-locked for this staff member",
            )


def apply_permission_locks(target: models.User, perm: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(perm)
    for key in PERMISSION_KEYS:
        if permission_owner_locked(target, key):
            out[key] = False
    return out


def actor_store_market_ceiling(actor: models.User) -> Dict[str, Any]:
    """Stores/markets the actor may assign to other staff (owner = all)."""
    if is_owner(actor):
        return {"all_stores": True, "stores": {}}
    if is_business_admin(actor) and getattr(actor, "business_admin_all_stores", True):
        access = actor.store_market_access if isinstance(actor.store_market_access, dict) else {}
        if access.get("all_stores"):
            return {"all_stores": True, "stores": {}}
    access = actor.store_market_access if isinstance(actor.store_market_access, dict) else {}
    return {
        "all_stores": bool(access.get("all_stores")),
        "stores": dict(access.get("stores") or {}) if isinstance(access.get("stores"), dict) else {},
    }


def assert_store_market_access_grant(actor: models.User, proposed: Dict[str, Any]) -> None:
    """Non-owners may only grant store+marketplace pairs they already have."""
    if is_owner(actor):
        return
    ceiling = actor_store_market_ceiling(actor)
    if ceiling.get("all_stores"):
        return
    if proposed.get("all_stores"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot grant all stores and all marketplaces",
        )
    proposed_stores = proposed.get("stores")
    if not isinstance(proposed_stores, dict):
        return
    ceiling_stores = ceiling.get("stores") or {}
    for store_key, markets in proposed_stores.items():
        if store_key not in ceiling_stores:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You cannot assign access for store {store_key}",
            )
        allowed = ceiling_stores.get(store_key)
        if not isinstance(allowed, list):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You have no marketplace access to assign for store {store_key}",
            )
        allowed_set = {str(m).strip().lower() for m in allowed if str(m).strip()}
        if not isinstance(markets, list):
            continue
        for m in markets:
            slug = str(m).strip().lower()
            if slug and slug not in allowed_set:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You cannot grant marketplace '{slug}' for store {store_key}",
                )


def assert_actor_can_grant_permissions(
    actor: models.User, perm: Dict[str, Any], store_id: Optional[int] = None
) -> None:
    if is_owner(actor):
        return
    from app.staff_permissions import effective_permissions_dict

    actor_perms = effective_permissions_dict(actor, store_id)
    for key in PERMISSION_KEYS:
        if not perm.get(key):
            continue
        if permission_owner_locked(actor, key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You cannot grant '{key}' (owner-restricted for your account)",
            )
        if not actor_perms.get(key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You cannot grant '{key}' without having it yourself",
            )


def normalize_owner_restrictions(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base: Dict[str, Any] = {"permissions": {}, "store_market_access": False, "password_change": False}
    if not isinstance(raw, dict):
        return base
    perms_in = raw.get("permissions")
    if isinstance(perms_in, dict):
        base["permissions"] = {k: bool(perms_in.get(k)) for k in PERMISSION_KEYS if perms_in.get(k)}
    if raw.get("store_market_access"):
        base["store_market_access"] = True
    if raw.get("password_change"):
        base["password_change"] = True
    return base