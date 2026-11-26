"""Per-store default records (activation templates, documentation, marketing, etc.)."""
from sqlalchemy.orm import Session

from app import models

DIGITAL_MARKETING_NAME = "Стандартное digital-письмо для рассылки"
DIGITAL_MARKETING_SUBJECT = "Срок подписки истёк"
DIGITAL_MARKETING_BODY = "<p>Дополнительная информация для рассылки клиентам.</p>"

DIGITAL_ACTIVATION_NAME = "Стандартный шаблон активации (digital)"

DIGITAL_TEMPLATE_BODY = (
    "1. Отправьте ваш зарегистрированный email в чат заказа на Маркете. "
    "В течение нескольких минут вы получите одноразовый код (OTP) на почту для входа в аккаунт "
    "— отправьте этот код в чат заказа."
)

DIGITAL_DOC_NAME = "Стандартная инструкция по выполнению заказа"
DIGITAL_DOC_HTML = (
    "<p>1. Подтвердите сообщение покупателя в чате заказа на Маркете.</p>"
    "<p>2. Отправьте инструкции по активации из связанного шаблона.</p>"
    "<p>3. Завершите заказ после подтверждения доступа покупателем.</p>"
)


LEGACY_ACTIVATION_NAMES = (
    "Default Digital Product Template",
    "Default Digital Activation Template",
)
LEGACY_DOC_NAMES = ("Default Order Fulfillment Guide",)


def _unlink_products_email_templates(db: Session, template_ids: list[int]) -> None:
    if not template_ids:
        return
    db.query(models.Product).filter(models.Product.email_template_id.in_(template_ids)).update(
        {models.Product.email_template_id: None},
        synchronize_session=False,
    )


def _unlink_products_documentation(db: Session, doc_ids: list[int]) -> None:
    if not doc_ids:
        return
    db.query(models.Product).filter(models.Product.documentation_id.in_(doc_ids)).update(
        {models.Product.documentation_id: None},
        synchronize_session=False,
    )


def _delete_store_activation_templates(
    db: Session, business_id: int, store_id: int | None, names: tuple[str, ...]
) -> None:
    q = db.query(models.EmailTemplate).filter(
        models.EmailTemplate.business_id == business_id,
        models.EmailTemplate.name.in_(names),
    )
    if store_id is None:
        q = q.filter(models.EmailTemplate.store_id.is_(None))
    else:
        q = q.filter(models.EmailTemplate.store_id == store_id)
    rows = q.all()
    if not rows:
        return
    _unlink_products_email_templates(db, [r.id for r in rows])
    for row in rows:
        db.delete(row)


def _delete_store_documentation(
    db: Session, business_id: int, store_id: int, names: tuple[str, ...]
) -> None:
    rows = (
        db.query(models.Documentation)
        .filter(
            models.Documentation.business_id == business_id,
            models.Documentation.store_id == store_id,
            models.Documentation.name.in_(names),
        )
        .all()
    )
    if not rows:
        return
    _unlink_products_documentation(db, [r.id for r in rows])
    for row in rows:
        db.delete(row)


def clear_store_buyer_message_settings(db: Session, store_id: int) -> None:
    row = db.query(models.AppSettings).filter(models.AppSettings.store_id == store_id).first()
    if not row:
        return
    row.processing_time_min = None
    row.processing_time_max = None
    row.maximum_wait_time_value = None
    row.maximum_wait_time_unit = None
    row.working_hours_text = None
    row.company_email = None


def cleanup_legacy_store_defaults(db: Session, business_id: int, store_id: int) -> None:
    for name in LEGACY_ACTIVATION_NAMES:
        _delete_store_activation_templates(db, business_id, store_id, (name,))
    _delete_store_activation_templates(db, business_id, None, LEGACY_ACTIVATION_NAMES)
    dupes = (
        db.query(models.EmailTemplate)
        .filter(
            models.EmailTemplate.business_id == business_id,
            models.EmailTemplate.store_id == store_id,
            models.EmailTemplate.name == DIGITAL_ACTIVATION_NAME,
        )
        .order_by(models.EmailTemplate.id.asc())
        .all()
    )
    if len(dupes) > 1:
        _unlink_products_email_templates(db, [r.id for r in dupes[1:]])
        for row in dupes[1:]:
            db.delete(row)
    _delete_store_documentation(db, business_id, store_id, LEGACY_DOC_NAMES)
    old_marketing = (
        db.query(models.MarketingEmailTemplate)
        .filter(
            models.MarketingEmailTemplate.business_id == business_id,
            models.MarketingEmailTemplate.store_id == store_id,
            models.MarketingEmailTemplate.name.in_(
                ("Default Marketing Template", "Default Digital Marketing Email")
            ),
        )
        .all()
    )
    for row in old_marketing:
        if row.name != DIGITAL_MARKETING_NAME:
            db.delete(row)
        else:
            row.subject = DIGITAL_MARKETING_SUBJECT
            row.body = DIGITAL_MARKETING_BODY


DIGITAL_DEFAULT_NAMES = {
    "activation": (DIGITAL_ACTIVATION_NAME, *LEGACY_ACTIVATION_NAMES, "Default Digital Product Template"),
    "doc": (DIGITAL_DOC_NAME, *LEGACY_DOC_NAMES),
    "marketing": (DIGITAL_MARKETING_NAME, "Default Marketing Template", "Default Digital Marketing Email"),
}


def remove_digital_store_defaults(db: Session, business_id: int, store_id: int) -> None:
    _delete_store_activation_templates(db, business_id, store_id, DIGITAL_DEFAULT_NAMES["activation"])
    _delete_store_documentation(db, business_id, store_id, DIGITAL_DEFAULT_NAMES["doc"])
    mkt_names = DIGITAL_DEFAULT_NAMES["marketing"]
    db.query(models.MarketingEmailTemplate).filter(
        models.MarketingEmailTemplate.business_id == business_id,
        models.MarketingEmailTemplate.store_id == store_id,
        models.MarketingEmailTemplate.name.in_(mkt_names),
    ).delete(synchronize_session=False)


def apply_store_type_changes(
    db: Session,
    business_id: int,
    store_id: int,
    prev_types: set[str],
    next_types: set[str],
) -> None:
    added = next_types - prev_types
    removed = prev_types - next_types
    if "digital" in added:
        seed_store_type_defaults(db, business_id, store_id, list(added))
    if "digital" in removed:
        remove_digital_store_defaults(db, business_id, store_id)


def seed_store_type_defaults(db: Session, business_id: int, store_id: int, store_types: list[str]) -> None:
    kinds = {str(k).strip().lower() for k in store_types if str(k).strip()}
    if "digital" not in kinds:
        return
    cleanup_legacy_store_defaults(db, business_id, store_id)

    tpl = (
        db.query(models.EmailTemplate)
        .filter(
            models.EmailTemplate.business_id == business_id,
            models.EmailTemplate.store_id == store_id,
            models.EmailTemplate.name == DIGITAL_ACTIVATION_NAME,
        )
        .first()
    )
    if not tpl:
        legacy = (
            db.query(models.EmailTemplate)
            .filter(
                models.EmailTemplate.business_id == business_id,
                models.EmailTemplate.store_id == store_id,
                models.EmailTemplate.name == "Default Digital Product Template",
            )
            .first()
        )
        if legacy:
            legacy.name = DIGITAL_ACTIVATION_NAME
        else:
            db.add(
                models.EmailTemplate(
                    business_id=business_id,
                    store_id=store_id,
                    name=DIGITAL_ACTIVATION_NAME,
                    body=DIGITAL_TEMPLATE_BODY,
                    random_key=True,
                    required_login=False,
                )
            )

    mkt = (
        db.query(models.MarketingEmailTemplate)
        .filter(
            models.MarketingEmailTemplate.business_id == business_id,
            models.MarketingEmailTemplate.store_id == store_id,
            models.MarketingEmailTemplate.name == DIGITAL_MARKETING_NAME,
        )
        .first()
    )
    if not mkt:
        db.add(
            models.MarketingEmailTemplate(
                business_id=business_id,
                store_id=store_id,
                name=DIGITAL_MARKETING_NAME,
                subject=DIGITAL_MARKETING_SUBJECT,
                body=DIGITAL_MARKETING_BODY,
                is_default=True,
                auto_broadcast_enabled=False,
            )
        )

    doc = (
        db.query(models.Documentation)
        .filter(
            models.Documentation.business_id == business_id,
            models.Documentation.store_id == store_id,
            models.Documentation.name == DIGITAL_DOC_NAME,
        )
        .first()
    )
    if not doc:
        db.add(
            models.Documentation(
                business_id=business_id,
                store_id=store_id,
                name=DIGITAL_DOC_NAME,
                description="Базовые шаги для цифровых заказов.",
                type="text",
                content=DIGITAL_DOC_HTML,
            )
        )