from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas
from app.auth import get_current_active_user, has_permission, get_business_id
from app.store_context import get_current_store

router = APIRouter()

_SETTINGS_DEFAULTS = {
    "processing_time_min": 20,
    "yandex_api_url": "https://api.partner.market.yandex.ru",
    "auto_activation_enabled": False,
    "auto_append_clients": False,
}


def _apply_settings_defaults(settings: models.AppSettings) -> bool:
    changed = False
    for field, value in _SETTINGS_DEFAULTS.items():
        if getattr(settings, field, None) is None:
            setattr(settings, field, value)
            changed = True
    return changed


def get_or_create_settings(
    business_id: int, db: Session, store: models.MarketStore
) -> models.AppSettings:
    """Get or create the settings record for a store."""
    settings = (
        db.query(models.AppSettings)
        .filter(
            models.AppSettings.business_id == business_id,
            models.AppSettings.store_id == store.id,
        )
        .first()
    )
    if not settings:
        settings = models.AppSettings(
            business_id=business_id,
            store_id=store.id,
            yandex_campaign_id=store.yandex_campaign_id,
            yandex_business_id=store.yandex_business_id,
            processing_time_min=_SETTINGS_DEFAULTS["processing_time_min"],
            yandex_api_url=_SETTINGS_DEFAULTS["yandex_api_url"],
            auto_activation_enabled=_SETTINGS_DEFAULTS["auto_activation_enabled"],
            auto_append_clients=_SETTINGS_DEFAULTS["auto_append_clients"],
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings
    if _apply_settings_defaults(settings):
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/", response_model=schemas.AppSettings)
def get_settings(
    current_user: models.User = Depends(get_current_active_user),
    store: models.MarketStore = Depends(get_current_store),
    db: Session = Depends(get_db)
):
    """Get application settings. Requires view_settings permission."""
    # Check permission
    if not current_user.is_admin and not has_permission(current_user, "view_settings"):
        raise HTTPException(
            status_code=403,
            detail="Permission required: view_settings"
        )
    business_id = get_business_id(current_user)
    return get_or_create_settings(business_id, db, store)


@router.put("/", response_model=schemas.AppSettings)
def update_settings(
    settings_update: schemas.AppSettingsUpdate,
    current_user: models.User = Depends(get_current_active_user),
    store: models.MarketStore = Depends(get_current_store),
    db: Session = Depends(get_db)
):
    """Update application settings. Requires view_settings permission."""
    # Check permission
    if not current_user.is_admin and not has_permission(current_user, "view_settings"):
        raise HTTPException(
            status_code=403,
            detail="Permission required: view_settings"
        )
    business_id = get_business_id(current_user)
    settings = get_or_create_settings(business_id, db, store)
    
    update_data = settings_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    
    db.commit()
    db.refresh(settings)
    return settings
