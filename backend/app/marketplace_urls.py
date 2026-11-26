"""Deep links to marketplace seller UI (order chat, etc.)."""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.services.yandex_api import YandexMarketAPI


def _yandex_partner_chat_token(chat: dict[str, Any]) -> Optional[str]:
    for key in ("encodedChatId", "externalChatId", "partnerChatId", "chatKey"):
        val = chat.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    cid = chat.get("chatId")
    if cid is None:
        return None
    if isinstance(cid, str) and cid.strip():
        return cid.strip()
    if isinstance(cid, int):
        return str(cid)
    return None


def marketplace_order_chat_url(
    db: Session,
    business_id: int,
    store_id: int,
    marketplace: Optional[str],
    order_id: str,
) -> Optional[str]:
    slug = (marketplace or "yandex").strip().lower()
    if slug != "yandex":
        return None
    try:
        api = YandexMarketAPI(business_id=business_id, db=db, store_id=store_id)
    except ValueError:
        return None
    yandex_business_id = (api.business_id or "").strip()
    if not yandex_business_id:
        return None
    chat = api.get_chat_for_order(str(order_id).strip())
    if not chat:
        return None
    chat_token = _yandex_partner_chat_token(chat)
    if not chat_token:
        return None
    query = urlencode({"chatId": chat_token, "tld": "ru", "chatGroup": "ORDER"})
    return f"https://partner.market.yandex.ru/business/{yandex_business_id}/arbiter?{query}"