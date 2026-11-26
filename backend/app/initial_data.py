"""
Script to create initial data (default email template and app settings)
Run this after database is created
"""
from app.database import SessionLocal
from app import models


def create_default_settings():
    """Create default app settings for each admin if they don't exist"""
    db = SessionLocal()
    try:
        # Get all admin users
        admins = db.query(models.User).filter(models.User.is_admin == True).all()
        
        if not admins:
            print("No admin users found. Skipping default settings creation.")
            return
        
        # Create default settings for each admin's business
        for admin in admins:
            existing = db.query(models.AppSettings).filter(
                models.AppSettings.business_id == admin.id
            ).first()
            
            if existing:
                continue
            
            default_settings = models.AppSettings(
                business_id=admin.id,
                processing_time_min=20,
                processing_time_max=30,
                maximum_wait_time_value=6,
                maximum_wait_time_unit="hours",
                working_hours_text="Мы работаем ежедневно с 10:00 до 23:00 по московскому времени.",
            )
            db.add(default_settings)
        
        db.commit()
        print("Default app settings created successfully for all admins")
    except Exception as e:
        print(f"Error creating default settings: {str(e)}")
        db.rollback()
    finally:
        db.close()


def create_default_email_template():
    """Create a default email template for digital products for each admin"""
    db = SessionLocal()
    try:
        # Get all admin users
        admins = db.query(models.User).filter(models.User.is_admin == True).all()
        
        if not admins:
            print("No admin users found. Skipping default email template creation.")
            return
        
        # Create default template for each admin's business
        for admin in admins:
            # Check if default template already exists for this business
            existing = db.query(models.EmailTemplate).filter(
                models.EmailTemplate.name == "Default Digital Product Template",
                models.EmailTemplate.business_id == admin.id
            ).first()
            
            if existing:
                continue
            
            default_template = models.EmailTemplate(
                name="Default Digital Product Template",
                body="""1. Отправьте ваш зарегистрированный email в чат заказа на Маркете. В течение нескольких минут вы получите одноразовый код (OTP) на почту для входа в аккаунт — отправьте этот код в чат заказа.""",
                random_key=True,
                required_login=False,
                business_id=admin.id
            )
            
            db.add(default_template)
        
        db.commit()
        print("Default email template created successfully for all admins")
    except Exception as e:
        print(f"Error creating default template: {str(e)}")
        db.rollback()
    finally:
        db.close()


def create_default_marketing_email_template():
    """Legacy hook — digital marketing defaults are created per store in store_defaults.seed_store_type_defaults."""
    db = SessionLocal()
    try:
        from app.store_defaults import seed_store_type_defaults

        for store in db.query(models.MarketStore).order_by(models.MarketStore.id.asc()).all():
            kinds = [str(k).strip().lower() for k in (store.store_types or []) if str(k).strip()]
            if kinds:
                seed_store_type_defaults(db, store.owner_id, store.id, kinds)
        db.commit()
        print("Store-type marketing defaults ensured for configured stores")
    except Exception as e:
        print(f"Error creating default marketing template: {str(e)}")
        db.rollback()
    finally:
        db.close()


def create_default_documentation():
    """Create default fulfillment documentation for each admin (same idea as activation template)."""
    db = SessionLocal()
    try:
        admins = db.query(models.User).filter(models.User.is_admin.is_(True)).all()
        if not admins:
            print("No admin users found. Skipping default documentation creation.")
            return

        for admin in admins:
            existing = (
                db.query(models.Documentation)
                .filter(
                    models.Documentation.business_id == admin.id,
                    models.Documentation.name == "Стандартная инструкция по выполнению заказа",
                )
                .first()
            )
            if existing:
                continue

            db.add(
                models.Documentation(
                    business_id=admin.id,
                    name="Стандартная инструкция по выполнению заказа",
                    description="Базовые шаги для цифровых заказов на Яндекс Маркете.",
                    type="text",
                    content=(
                        "<p>1. Подтвердите сообщение покупателя в чате заказа на Маркете.</p>"
                        "<p>2. Отправьте инструкции по активации из связанного шаблона.</p>"
                        "<p>3. Завершите заказ после подтверждения доступа покупателем.</p>"
                    ),
                )
            )

        db.commit()
        print("Default documentation created successfully for all admins")
    except Exception as e:
        print(f"Error creating default documentation: {str(e)}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_default_email_template()
