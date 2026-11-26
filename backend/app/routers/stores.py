import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app import models
from app.auth import (
    get_current_active_user,
    get_business_id,
    get_password_hash,
    has_permission,
    require_permission,
    verify_password,
)
from app.staff_access import assert_store_access, filter_stores_for_user
from app.store_context import get_owner_stores
from app.store_defaults import apply_store_type_changes, seed_store_type_defaults
from app.services.email_service import EmailService

router = APIRouter()


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    copy_settings_from_store_id: int | None = None
    store_types: list[str] = Field(default_factory=list)


class StoreOut(BaseModel):
    id: int
    name: str
    yandex_campaign_id: str | None = None
    yandex_business_id: str | None = None
    store_types: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class StoreTypesUpdate(BaseModel):
    store_types: list[str] = Field(default_factory=list)


class StoreAttentionRequest(BaseModel):
    seen_at: dict[str, str] = Field(default_factory=dict)


STORE_TYPE_CHOICES = ("digital",)


class StoreDeleteBody(BaseModel):
    otp: str = Field(min_length=6, max_length=6)


def _owner_admin_email(db: Session, owner_id: int) -> str:
    admin = (
        db.query(models.User)
        .filter(models.User.id == owner_id, models.User.is_admin.is_(True))
        .first()
    )
    if not admin or not admin.email:
        raise HTTPException(status_code=400, detail="Business admin email is not configured")
    return admin.email


def _purge_store_data(db: Session, store_id: int, business_id: int) -> None:
    db.query(models.StoreMarketplaceConnection).filter(
        models.StoreMarketplaceConnection.store_id == store_id
    ).delete(synchronize_session=False)
    db.query(models.AppSettings).filter(
        models.AppSettings.business_id == business_id,
        models.AppSettings.store_id == store_id,
    ).delete(synchronize_session=False)
    db.query(models.Product).filter(
        models.Product.business_id == business_id,
        models.Product.store_id == store_id,
    ).delete(synchronize_session=False)
    db.query(models.Order).filter(
        models.Order.business_id == business_id,
        models.Order.store_id == store_id,
    ).delete(synchronize_session=False)
    db.query(models.EmailTemplate).filter(
        models.EmailTemplate.business_id == business_id,
        models.EmailTemplate.store_id == store_id,
    ).delete(synchronize_session=False)
    db.query(models.Documentation).filter(
        models.Documentation.business_id == business_id,
        models.Documentation.store_id == store_id,
    ).delete(synchronize_session=False)
    db.query(models.MarketingEmailTemplate).filter(
        models.MarketingEmailTemplate.business_id == business_id,
        models.MarketingEmailTemplate.store_id == store_id,
    ).delete(synchronize_session=False)


@router.post("/attention")
def stores_attention(
    body: StoreAttentionRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from app.services.store_attention import attention_for_store

    owner_id = get_business_id(current_user)
    stores = filter_stores_for_user(current_user, get_owner_stores(db, owner_id))
    out: dict[str, dict] = {}
    for store in stores:
        out[str(store.id)] = attention_for_store(db, owner_id, store.id, body.seen_at or {})
    return {"stores": out}


@router.get("/", response_model=list[StoreOut])
def list_stores(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    owner_id = get_business_id(current_user)
    stores = get_owner_stores(db, owner_id)
    return filter_stores_for_user(current_user, stores)


@router.post("/", response_model=StoreOut)
def create_store(
    body: StoreCreate,
    current_user: models.User = Depends(require_permission("create_store")),
    db: Session = Depends(get_db),
):
    owner_id = get_business_id(current_user)
    name = body.name.strip()
    dup = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.owner_id == owner_id, models.MarketStore.name == name)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail="A store with this name already exists")

    types = [str(t).strip().lower() for t in (body.store_types or []) if str(t).strip()]
    store = models.MarketStore(
        owner_id=owner_id,
        name=name,
        yandex_campaign_id=None,
        yandex_business_id=None,
        store_types=types,
    )
    db.add(store)
    db.flush()

    src_settings = None
    if body.copy_settings_from_store_id:
        src_settings = (
            db.query(models.AppSettings)
            .filter(
                models.AppSettings.business_id == owner_id,
                models.AppSettings.store_id == body.copy_settings_from_store_id,
            )
            .first()
        )
    settings = models.AppSettings(
        business_id=owner_id,
        store_id=store.id,
        processing_time_min=20,
    )
    if src_settings:
        for field in (
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "smtp_password",
            "from_email",
            "auto_activation_enabled",
            "auto_append_clients",
        ):
            setattr(settings, field, getattr(src_settings, field, None))
    db.add(settings)
    if types:
        seed_store_type_defaults(db, owner_id, store.id, types)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        if "business_id" in msg or "app_settings" in msg or "ix_app_settings_business_id" in msg:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Database still limits one settings row per business. "
                    "Restart the backend to apply multi-store migrations, then try again."
                ),
            ) from e
        if "uq_market_store_owner_name" in msg or "market_stores" in msg.lower():
            raise HTTPException(status_code=400, detail="A store with this name already exists") from e
        raise HTTPException(status_code=400, detail="Could not create store. Check server logs.") from e
    db.refresh(store)
    return store


@router.patch("/{store_id}", response_model=StoreOut)
def update_store(
    store_id: int,
    body: StoreTypesUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update store metadata (e.g. product types for default templates)."""
    if not current_user.is_admin and not has_permission(current_user, "view_settings", store_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: view_settings")
    owner_id = get_business_id(current_user)
    store = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.id == store_id, models.MarketStore.owner_id == owner_id)
        .first()
    )
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    assert_store_access(current_user, store)

    kinds = {str(t).strip().lower() for t in (body.store_types or []) if str(t).strip()}
    for k in kinds:
        if k not in STORE_TYPE_CHOICES:
            raise HTTPException(status_code=400, detail=f"Unknown store type: {k}")
    prev = {str(t).strip().lower() for t in (store.store_types or []) if str(t).strip()}
    store.store_types = sorted(kinds)
    db.flush()
    try:
        apply_store_type_changes(db, owner_id, store.id, prev, kinds)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not update store type. Check server logs.") from e
    db.refresh(store)
    return store


@router.post("/{store_id}/delete-request")
def request_store_delete_otp(
    store_id: int,
    current_user: models.User = Depends(require_permission("delete_store")),
    db: Session = Depends(get_db),
):
    owner_id = get_business_id(current_user)
    store = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.id == store_id, models.MarketStore.owner_id == owner_id)
        .first()
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    assert_store_access(current_user, store)

    total = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.owner_id == owner_id)
        .count()
    )
    if total <= 1:
        raise HTTPException(status_code=400, detail="You cannot delete the only store")

    otp = f"{random.randint(0, 999999):06d}"
    store.delete_otp_hash = get_password_hash(otp)
    store.delete_otp_expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    to_email = _owner_admin_email(db, owner_id)
    try:
        email_service = EmailService(business_id=owner_id, db=db)
        email_service.send_email(
            to_email=to_email,
            subject=f"Confirm deletion of store “{store.name}”",
            body=(
                f"Your verification code to delete the store “{store.name}” is: {otp}\n\n"
                "This code expires in 15 minutes. If you did not request this, ignore this email."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not send verification code. Configure SMTP for a store in Settings. ({e})",
        ) from e

    return {
        "message": f"Verification code sent to {to_email}",
        "expires_in_minutes": 15,
    }


@router.delete("/{store_id}")
def delete_store(
    store_id: int,
    body: StoreDeleteBody,
    current_user: models.User = Depends(require_permission("delete_store")),
    db: Session = Depends(get_db),
):
    owner_id = get_business_id(current_user)
    store = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.id == store_id, models.MarketStore.owner_id == owner_id)
        .first()
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    assert_store_access(current_user, store)

    total = (
        db.query(models.MarketStore)
        .filter(models.MarketStore.owner_id == owner_id)
        .count()
    )
    if total <= 1:
        raise HTTPException(status_code=400, detail="You cannot delete the only store")

    if not store.delete_otp_hash or not store.delete_otp_expires:
        raise HTTPException(status_code=400, detail="Request a verification code first")
    if store.delete_otp_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired. Request a new one.")
    if not verify_password(body.otp, store.delete_otp_hash):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    _purge_store_data(db, store.id, owner_id)
    db.delete(store)
    db.commit()
    return {"success": True, "deleted_store_id": store_id}