import sys
from pathlib import Path

sys.path.insert(0, "/app" if Path("/app/app").exists() else str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app import models

db = SessionLocal()
n = (
    db.query(models.Product)
    .filter(models.Product.selling_price == 5)
    .update({models.Product.selling_price: 10}, synchronize_session=False)
)
db.commit()
print("local selling_price 5 -> 10:", n)