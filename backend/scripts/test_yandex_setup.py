"""Verify Yandex API wiring for the VPS (run in backend container)."""
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
from app.services.yandex_api import YandexMarketAPI


def main():
    db: Session = SessionLocal()
    try:
        settings = (
            db.query(models.AppSettings)
            .filter(models.AppSettings.yandex_api_token.isnot(None))
            .first()
        )
        if not settings:
            print("FAIL: no app_settings with yandex_api_token — sign up and run vps_bootstrap.py")
            sys.exit(1)

        api = YandexMarketAPI(business_id=settings.business_id, db=db)
        print("OK: YandexMarketAPI initialized")
        print(f"  business_id (Yandex): {api.business_id}")
        print(f"  campaign_id: {api.campaign_id}")

        token_info = api.verify_api_access()
        print("Token check:", token_info.get("status"), token_info.get("errors"))

        campaigns = api.list_campaigns()
        print(f"Campaigns: {len(campaigns)}")
        for c in campaigns[:5]:
            print(f"  - id={c.get('id')} domain={c.get('domain')}")

        if campaigns and not api.campaign_id:
            print("WARN: campaign_id not set in settings but campaigns exist — set in Settings UI")

        if token_info.get("status") == "ERROR":
            errs = token_info.get("errors") or []
            if any(e.get("code") == "API_DISABLED" for e in errs):
                print(
                    "Yandex returned API_DISABLED: enable API / active partner in "
                    "Yandex Market partner cabinet for business", api.business_id
                )
                sys.exit(2)

        if api.campaign_id:
            orders = api.get_orders()
            print(f"Orders sample fetch: {len(orders)} order(s)")
            products = api.get_products()
            print(f"Products sample fetch: {len(products)} product(s)")
        else:
            print("SKIP product/order sync: no campaign_id (set when Yandex returns campaigns)")

        print("DONE")
        sys.exit(0)
    finally:
        db.close()


if __name__ == "__main__":
    main()