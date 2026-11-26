"""Create default MarketStore rows from legacy single-store app_settings."""
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import models


def run_legacy_data_backfill(db: Session) -> None:
    """No-op on empty DB; fixes legacy rows when upgrading an old database."""
    db.execute(text("""
        UPDATE products p
        SET store_id = sub.id
        FROM (
            SELECT DISTINCT ON (owner_id) id, owner_id
            FROM market_stores
            ORDER BY owner_id, id ASC
        ) sub
        WHERE p.store_id IS NULL AND p.business_id = sub.owner_id
    """))
    db.execute(text("""
        UPDATE email_templates t
        SET store_id = sub.id
        FROM (
            SELECT DISTINCT ON (owner_id) id, owner_id
            FROM market_stores
            ORDER BY owner_id, id ASC
        ) sub
        WHERE t.store_id IS NULL AND t.business_id = sub.owner_id
    """))
    db.execute(text("""
        UPDATE documentations d
        SET store_id = sub.id
        FROM (
            SELECT DISTINCT ON (owner_id) id, owner_id
            FROM market_stores
            ORDER BY owner_id, id ASC
        ) sub
        WHERE d.store_id IS NULL AND d.business_id = sub.owner_id
    """))
    db.execute(text("""
        UPDATE marketing_email_templates
        SET name = 'Default Digital Marketing Email'
        WHERE name = 'Default Marketing Template'
    """))
    db.execute(text("""
        UPDATE marketing_email_templates t
        SET store_id = sub.id
        FROM (
            SELECT DISTINCT ON (owner_id) id, owner_id
            FROM market_stores
            ORDER BY owner_id, id ASC
        ) sub
        WHERE t.store_id IS NULL AND t.business_id = sub.owner_id
    """))
    db.execute(text("""
        UPDATE market_stores ms
        SET store_types = '["digital"]'::jsonb
        WHERE (store_types IS NULL OR store_types::text = '[]')
          AND ms.id = (
            SELECT MIN(ms2.id) FROM market_stores ms2 WHERE ms2.owner_id = ms.owner_id
          )
    """))
    db.execute(text("""
        UPDATE market_stores SET store_types = '[]'::jsonb WHERE lower(name) = 'sdhdh'
    """))
    from app.store_defaults import (
        apply_store_type_changes,
        cleanup_legacy_store_defaults,
        clear_store_buyer_message_settings,
        remove_digital_store_defaults,
    )

    db.execute(text("""
        UPDATE app_settings
        SET processing_time_min = NULL,
            processing_time_max = NULL,
            maximum_wait_time_value = NULL,
            maximum_wait_time_unit = NULL,
            working_hours_text = NULL,
            company_email = NULL
        WHERE store_id IN (SELECT id FROM market_stores WHERE lower(name) = 'sdhdh')
    """))

    for store in db.query(models.MarketStore).order_by(models.MarketStore.id.asc()).all():
        kinds = {str(k).strip().lower() for k in (store.store_types or []) if str(k).strip()}
        if store.name and store.name.lower() == "sdhdh":
            clear_store_buyer_message_settings(db, store.id)
        if store.name and store.name.lower() == "sdhdh" and "digital" not in kinds:
            remove_digital_store_defaults(db, store.owner_id, store.id)
        if "digital" in kinds:
            cleanup_legacy_store_defaults(db, store.owner_id, store.id)
        if kinds:
            apply_store_type_changes(db, store.owner_id, store.id, set(), kinds)
    db.commit()


def ensure_default_stores(db: Session) -> None:
    legacy_rows = (
        db.query(models.AppSettings)
        .filter(models.AppSettings.store_id.is_(None))
        .order_by(models.AppSettings.id.asc())
        .all()
    )
    for row in legacy_rows:
        user = db.query(models.User).filter(models.User.id == row.business_id).first()
        store_name = (user.business_name if user and user.business_name else "Main store")
        campaign = (row.yandex_campaign_id or "").strip()
        business = (row.yandex_business_id or "").strip()
        if not campaign and not business:
            continue
        if not campaign:
            campaign = "unknown"
        if not business:
            business = "unknown"

        existing = (
            db.query(models.MarketStore)
            .filter(
                models.MarketStore.owner_id == row.business_id,
                models.MarketStore.yandex_campaign_id == campaign,
            )
            .first()
        )
        if existing:
            row.store_id = existing.id
            continue

        store = models.MarketStore(
            owner_id=row.business_id,
            name=store_name,
            yandex_campaign_id=campaign,
            yandex_business_id=business,
        )
        db.add(store)
        db.flush()
        row.store_id = store.id

    stores_by_owner: dict[int, models.MarketStore] = {}
    for store in db.query(models.MarketStore).order_by(models.MarketStore.id.asc()).all():
        if store.owner_id not in stores_by_owner:
            stores_by_owner[store.owner_id] = store

    if stores_by_owner:
        for order in db.query(models.Order).filter(models.Order.store_id.is_(None)).all():
            default = stores_by_owner.get(order.business_id)
            if default:
                order.store_id = default.id
        for product in db.query(models.Product).filter(models.Product.store_id.is_(None)).all():
            default = stores_by_owner.get(product.business_id)
            if default:
                product.store_id = default.id

    from app.marketplace_service import migrate_app_settings_to_connections

    migrate_app_settings_to_connections(db)
    for order in db.query(models.Order).filter(models.Order.marketplace.is_(None)).all():
        order.marketplace = "yandex"
    from app.staff_defaults import DEFAULT_OWNER_RESTRICTIONS, default_store_market_access

    for user in db.query(models.User).filter(models.User.is_admin.is_(True)).all():
        if not user.owner_restrictions:
            user.owner_restrictions = dict(DEFAULT_OWNER_RESTRICTIONS)
    for user in db.query(models.User).filter(models.User.is_admin.is_(False)).all():
        if not user.store_market_access:
            user.store_market_access = default_store_market_access(db, user.created_by_id or user.id)
    db.commit()