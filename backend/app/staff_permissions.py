"""Per-store staff permission overrides (global permissions + store_permissions JSONB)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app import models
from app.staff_roles import (
    ALL_PERMISSIONS_TRUE,
    PERMISSION_KEYS,
    business_admin_covers_store,
    is_business_admin,
    is_owner,
    permission_owner_locked,
)


def effective_permissions_dict(user: models.User, store_id: Optional[int] = None) -> Dict[str, Any]:
    if is_owner(user):
        return dict(ALL_PERMISSIONS_TRUE)

    if is_business_admin(user) and business_admin_covers_store(user, store_id):
        perms = dict(ALL_PERMISSIONS_TRUE)
        for key in PERMISSION_KEYS:
            if permission_owner_locked(user, key):
                perms[key] = False
        if store_id is not None:
            by_store = user.store_permissions if isinstance(user.store_permissions, dict) else {}
            override = by_store.get(str(store_id))
            if isinstance(override, dict) and override:
                for key in PERMISSION_KEYS:
                    if key in override:
                        if permission_owner_locked(user, key):
                            perms[key] = False
                        else:
                            perms[key] = bool(override[key])
        return perms

    base: Dict[str, Any] = dict(user.permissions or {})
    if store_id is None:
        for key in PERMISSION_KEYS:
            if permission_owner_locked(user, key):
                base[key] = False
        return base
    by_store = user.store_permissions if isinstance(user.store_permissions, dict) else {}
    override = by_store.get(str(store_id))
    merged = {**base, **(override if isinstance(override, dict) else {})}
    for key in PERMISSION_KEYS:
        if permission_owner_locked(user, key):
            merged[key] = False
    return merged