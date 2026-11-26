"""Apply KateSkate Yandex ids from environment to all admin app_settings rows."""
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal
from app import models
from app.vps_env import apply_env_settings_for_business

db = SessionLocal()
try:
    for u in db.query(models.User).filter(models.User.is_admin == True).all():
        apply_env_settings_for_business(db, u.id)
        print(f"Updated settings for admin {u.id} {u.email}")
finally:
    db.close()