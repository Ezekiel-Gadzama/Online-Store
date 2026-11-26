"""
Sync jobs - pull data from Yandex Market into the database.
Designed to run periodically via cron (e.g. every minute for orders).
"""
from sqlalchemy import or_
from app.database import SessionLocal
from app import models


def get_store_sync_targets():
    """Return (business_id, store_id) pairs that have Yandex API configured per store."""
    db = SessionLocal()
    try:
        rows = (
            db.query(models.AppSettings)
            .filter(
                models.AppSettings.store_id.isnot(None),
                or_(
                    models.AppSettings.yandex_api_token.isnot(None),
                    models.AppSettings.yandex_business_id.isnot(None),
                ),
            )
            .order_by(models.AppSettings.id.asc())
            .all()
        )
        return [(row.business_id, row.store_id) for row in rows]
    finally:
        db.close()


def get_business_ids_with_yandex_config():
    """Legacy: business_ids with any Yandex config (used if no store rows yet)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(models.AppSettings.business_id)
            .filter(
                or_(
                    models.AppSettings.yandex_api_token.isnot(None),
                    models.AppSettings.yandex_business_id.isnot(None),
                )
            )
            .distinct()
            .all()
        )
        return [r[0] for r in rows if r and r[0]]
    finally:
        db.close()


def run_order_sync():
    """Sync orders from Yandex for all configured stores."""
    from app.main import _sync_orders_sync

    targets = get_store_sync_targets()
    if not targets:
        business_ids = get_business_ids_with_yandex_config()
        if not business_ids:
            print("[Cron] No businesses with Yandex config - skipping order sync")
            return
        for business_id in business_ids:
            try:
                print(f"[Cron] Syncing orders for business_id={business_id}")
                _sync_orders_sync(business_id=business_id)
            except Exception as e:
                print(f"[Cron] Error syncing orders for business_id={business_id}: {e}")
                import traceback
                traceback.print_exc()
        return

    for business_id, store_id in targets:
        try:
            print(f"[Cron] Syncing orders for business_id={business_id} store_id={store_id}")
            _sync_orders_sync(business_id=business_id, store_id=store_id)
        except Exception as e:
            print(f"[Cron] Error syncing orders for business_id={business_id} store={store_id}: {e}")
            import traceback
            traceback.print_exc()


def run_product_sync():
    """Sync products from Yandex for all configured stores."""
    from app.main import _sync_products_sync

    targets = get_store_sync_targets()
    if not targets:
        business_ids = get_business_ids_with_yandex_config()
        if not business_ids:
            print("[Cron] No businesses with Yandex config - skipping product sync")
            return
        for business_id in business_ids:
            try:
                print(f"[Cron] Syncing products for business_id={business_id}")
                _sync_products_sync(business_id=business_id)
            except Exception as e:
                print(f"[Cron] Error syncing products for business_id={business_id}: {e}")
                import traceback
                traceback.print_exc()
        return

    seen_business: set[int] = set()
    for business_id, store_id in targets:
        if business_id in seen_business:
            continue
        seen_business.add(business_id)
        try:
            print(f"[Cron] Syncing products for business_id={business_id} store_id={store_id}")
            _sync_products_sync(business_id=business_id, store_id=store_id)
        except Exception as e:
            print(f"[Cron] Error syncing products for business_id={business_id}: {e}")
            import traceback
            traceback.print_exc()


def run_all_sync():
    """Run product sync then order sync for all businesses."""
    run_product_sync()
    run_order_sync()