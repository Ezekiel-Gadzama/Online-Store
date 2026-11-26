from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_active_user, get_business_id, has_permission, require_admin
from app.database import get_db
from app.marketplace_service import MARKETPLACE_CHOICES, sync_yandex_app_settings
from app.store_context import get_current_store

router = APIRouter()


class MarketplaceConnectionOut(BaseModel):
    id: int
    store_id: int
    marketplace: str
    label: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool

    class Config:
        from_attributes = True


class MarketplaceConnectionCreate(BaseModel):
    marketplace: str
    label: Optional[str] = None
    credentials: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class MarketplaceConnectionUpdate(BaseModel):
    label: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


def _require_settings_access(user: models.User) -> None:
    if user.is_admin or has_permission(user, "view_settings"):
        return
    raise HTTPException(status_code=403, detail="Permission required: view_settings")


def _normalize_marketplace(value: str) -> str:
    key = (value or "").strip().lower()
    if key not in MARKETPLACE_CHOICES:
        raise HTTPException(status_code=400, detail=f"Unknown marketplace: {value}")
    return key


@router.get("/", response_model=List[MarketplaceConnectionOut])
def list_connections(
    current_user: models.User = Depends(get_current_active_user),
    store: models.MarketStore = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    _require_settings_access(current_user)
    owner_id = get_business_id(current_user)
    if store.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Store not found")
    return (
        db.query(models.StoreMarketplaceConnection)
        .filter(models.StoreMarketplaceConnection.store_id == store.id)
        .order_by(models.StoreMarketplaceConnection.id.asc())
        .all()
    )


@router.post("/", response_model=MarketplaceConnectionOut)
def create_connection(
    body: MarketplaceConnectionCreate,
    current_user: models.User = Depends(require_admin()),
    store: models.MarketStore = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    marketplace = _normalize_marketplace(body.marketplace)
    row = models.StoreMarketplaceConnection(
        store_id=store.id,
        marketplace=marketplace,
        label=body.label,
        credentials=body.credentials or {},
        is_enabled=body.is_enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if marketplace == "yandex":
        sync_yandex_app_settings(db, store.id)
        db.commit()
    return row


@router.put("/{connection_id}", response_model=MarketplaceConnectionOut)
def update_connection(
    connection_id: int,
    body: MarketplaceConnectionUpdate,
    current_user: models.User = Depends(require_admin()),
    store: models.MarketStore = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.id == connection_id,
            models.StoreMarketplaceConnection.store_id == store.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")
    if body.label is not None:
        row.label = body.label
    if body.credentials is not None:
        row.credentials = body.credentials
    if body.is_enabled is not None:
        row.is_enabled = body.is_enabled
    db.commit()
    db.refresh(row)
    if row.marketplace == "yandex":
        sync_yandex_app_settings(db, store.id)
        db.commit()
    return row


@router.delete("/{connection_id}")
def delete_connection(
    connection_id: int,
    current_user: models.User = Depends(require_admin()),
    store: models.MarketStore = Depends(get_current_store),
    db: Session = Depends(get_db),
):
    row = (
        db.query(models.StoreMarketplaceConnection)
        .filter(
            models.StoreMarketplaceConnection.id == connection_id,
            models.StoreMarketplaceConnection.store_id == store.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Connection not found")
    marketplace = row.marketplace
    db.delete(row)
    db.commit()
    if marketplace == "yandex":
        sync_yandex_app_settings(db, store.id)
        db.commit()
    return {"ok": True}