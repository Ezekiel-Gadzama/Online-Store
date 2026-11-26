"""One-off: ensure an ezekiel* admin exists and apply .env Yandex settings (VPS smoke test)."""
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal
from app import models
from app.auth import get_password_hash
from app.vps_env import apply_env_settings_for_business

db = SessionLocal()
try:
    u = (
        db.query(models.User)
        .filter(models.User.email.ilike("%ezekiel%"))
        .filter(models.User.is_admin == True)
        .first()
    )
    if not u:
        u = models.User(
            email="ezekiel.setup@local",
            hashed_password=get_password_hash("setup-temp-change-me"),
            is_admin=True,
            is_active=True,
            permissions={
                "view_staff": True,
                "view_settings": True,
                "client_right": True,
                "view_marketing_emails": True,
                "dashboard_right": True,
                "view_product_prices": True,
            },
        )
        db.add(u)
        db.commit()
        db.refresh(u)
    apply_env_settings_for_business(db, u.id)
    print(f"Ready: admin id={u.id} email={u.email}")
finally:
    db.close()