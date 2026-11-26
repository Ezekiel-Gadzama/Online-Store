"""Track which staff user sent each Yandex partner chat message."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app import models
from app.services.yandex_api import YandexMarketAPI


def _staff_display_name(user: models.User) -> str:
    name = (user.name or "").strip()
    if name:
        return name
    return (user.email or f"User {user.id}").strip()


def attribute_partner_message(
    db: Session,
    *,
    business_id: int,
    sent_by_user_id: int,
    chat_id: int,
    message_text: str,
    yandex_api: YandexMarketAPI,
    order_id: Optional[str] = None,
) -> None:
    """After send, match the newest unattributed PARTNER line with this text."""
    try:
        history = yandex_api.get_chat_history(chat_id=int(chat_id), limit=30)
    except Exception as e:
        print(f"⚠️  Chat attribution: could not load history for chat {chat_id}: {e}")
        return

    messages = history.get("messages") or []
    text_norm = (message_text or "").strip()
    if not text_norm:
        return

    for msg in reversed(messages):
        if str(msg.get("sender", "")).upper() != "PARTNER":
            continue
        body = (msg.get("message") or "").strip()
        if body != text_norm:
            continue
        mid = str(msg.get("messageId", "")).strip()
        if not mid:
            continue
        exists = (
            db.query(models.ChatMessageSender)
            .filter(
                models.ChatMessageSender.business_id == business_id,
                models.ChatMessageSender.yandex_message_id == mid,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            models.ChatMessageSender(
                business_id=business_id,
                yandex_message_id=mid,
                chat_id=int(chat_id),
                order_id=str(order_id).strip() if order_id else None,
                sent_by_user_id=sent_by_user_id,
            )
        )
        db.commit()
        return


def enrich_seller_sender_names(
    db: Session,
    business_id: int,
    messages: List[Dict[str, Any]],
) -> None:
    seller_ids = [
        str(m.get("id", "")).strip()
        for m in messages
        if m.get("author") == "SELLER" and str(m.get("id", "")).strip()
    ]
    if not seller_ids:
        return

    rows = (
        db.query(models.ChatMessageSender, models.User)
        .join(models.User, models.User.id == models.ChatMessageSender.sent_by_user_id)
        .filter(
            models.ChatMessageSender.business_id == business_id,
            models.ChatMessageSender.yandex_message_id.in_(seller_ids),
        )
        .all()
    )
    by_mid = {row.yandex_message_id: _staff_display_name(user) for row, user in rows}
    for m in messages:
        if m.get("author") != "SELLER":
            continue
        mid = str(m.get("id", "")).strip()
        name = by_mid.get(mid)
        if name:
            m["sender_name"] = name