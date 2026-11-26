from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.database import get_db
from app.auth import get_current_active_user, get_business_id
from app.store_context import get_current_store
from app import models as db_models
from app.services.yandex_api import YandexMarketAPI
from app.chat_staff_attribution import attribute_partner_message, enrich_seller_sender_names


def _yandex_api(business_id: int, db: Session, store: db_models.MarketStore) -> YandexMarketAPI:
    return YandexMarketAPI(business_id=business_id, db=db, store_id=store.id)

router = APIRouter()


class MessageRequest(BaseModel):
    text: str
    # Optional unified attachments; stored and echoed back for UI, not sent to Yandex
    # Format matches existing attachments structure elsewhere in the app
    attachments: list[dict] | None = None


class ChatMessageRequest(BaseModel):
    text: str


class OrderChatMetaRequest(BaseModel):
    order_ids: list[str]


def _unread_from_messages(messages: list, last_viewed_at) -> int:
    from datetime import datetime, timezone

    if not messages:
        return 0
    if last_viewed_at and last_viewed_at.tzinfo is None:
        last_viewed_at = last_viewed_at.replace(tzinfo=timezone.utc)
    unread = 0
    for msg in messages:
        sender = str(msg.get("sender", "")).upper()
        if sender not in ("CUSTOMER", "MARKET", "SUPPORT"):
            continue
        if not last_viewed_at:
            unread += 1
            continue
        msg_created_at_str = msg.get("createdAt", "")
        if not msg_created_at_str:
            unread += 1
            continue
        try:
            iso_str = msg_created_at_str.replace(" ", "T")
            if "+" in iso_str or iso_str.endswith("Z"):
                msg_created_at = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            else:
                msg_created_at = datetime.fromisoformat(iso_str + "+00:00")
            if msg_created_at.tzinfo is None:
                msg_created_at = msg_created_at.replace(tzinfo=timezone.utc)
            if msg_created_at > last_viewed_at:
                unread += 1
        except Exception:
            unread += 1
    return unread


@router.post("/orders/meta", response_model=Dict)
def order_chat_meta(
    body: OrderChatMetaRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Batch has_chat + unread counts for order rows."""
    business_id = get_business_id(current_user)
    out: Dict[str, Dict[str, Any]] = {}
    ids = [str(x).strip() for x in (body.order_ids or []) if str(x).strip()][:25]
    if not ids:
        return {"orders": out}
    try:
        yandex_api = _yandex_api(business_id, db, store)
    except Exception:
        for oid in ids:
            out[oid] = {"has_chat": False, "unread_count": 0}
        return {"orders": out}
    for oid in ids:
        try:
            import httpx

            order_id_int = int(oid)
            url = f"{yandex_api.base_url}/v2/businesses/{yandex_api.business_id}/chats"
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json={"orderIds": [order_id_int]},
                    headers=yandex_api._get_headers(),
                    timeout=20.0,
                )
            if response.status_code == 404:
                out[oid] = {"has_chat": False, "unread_count": 0}
                continue
            response.raise_for_status()
            chats = response.json().get("result", {}).get("chats", []) or []
            if not chats:
                out[oid] = {"has_chat": False, "unread_count": 0}
                continue
            read_status = db.query(db_models.ChatReadStatus).filter(db_models.ChatReadStatus.order_id == oid).first()
            last_viewed = read_status.last_viewed_at if read_status else None
            messages = yandex_api.get_order_chat_messages(oid)
            unread = _unread_from_messages(messages, last_viewed)
            out[oid] = {"has_chat": True, "unread_count": unread}
        except Exception:
            out[oid] = {"has_chat": False, "unread_count": 0}
    return {"orders": out}


@router.get("/orders/{order_id}/marketplace-url", response_model=Dict)
def order_marketplace_chat_url(
    order_id: str,
    marketplace: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    from app.marketplace_urls import marketplace_order_chat_url

    business_id = get_business_id(current_user)
    url = marketplace_order_chat_url(db, business_id, store.id, marketplace, order_id)
    if not url:
        raise HTTPException(status_code=404, detail="Marketplace chat link is not available for this order")
    return {"url": url}


@router.get("/orders/{order_id}/unread-count", response_model=Dict)
def get_order_chat_unread_count(
    order_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Get unread message count for an order
    
    Returns count of unread messages created after the last viewed timestamp.
    Only counts messages from CUSTOMER, MARKET, or SUPPORT (not from PARTNER).
    """
    try:
        from app import models
        from datetime import datetime, timezone
        
        business_id = get_business_id(current_user)
        yandex_api = _yandex_api(business_id, db, store)

        if not yandex_api.business_id:
            return {"unread_count": 0}
        
        # Get last viewed timestamp from database
        read_status = db.query(models.ChatReadStatus).filter(
            models.ChatReadStatus.order_id == order_id
        ).first()
        last_viewed_at = read_status.last_viewed_at if read_status else None
        
        # Ensure last_viewed_at is timezone-aware if it exists
        if last_viewed_at and last_viewed_at.tzinfo is None:
            last_viewed_at = last_viewed_at.replace(tzinfo=timezone.utc)
        
        url = f"{yandex_api.base_url}/v2/businesses/{yandex_api.business_id}/chats"
        import httpx
        
        with httpx.Client() as client:
            payload = {"orderIds": [int(order_id)]}
            response = client.post(
                url,
                json=payload,
                headers=yandex_api._get_headers(),
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                chats = data.get("result", {}).get("chats", [])
                if chats:
                    chat = chats[0]
                    # If status is WAITING_FOR_PARTNER, there might be unread messages
                    status = chat.get("status", "")
                    if status == "WAITING_FOR_PARTNER":
                        # Get raw messages to count unread ones
                        chat_id = chat.get("chatId")
                        if chat_id:
                            history_url = f"{yandex_api.base_url}/v2/businesses/{yandex_api.business_id}/chats/history"
                            history_response = client.post(
                                history_url,
                                params={"chatId": chat_id},
                                json={},
                                headers=yandex_api._get_headers(),
                                timeout=30.0
                            )
                            if history_response.status_code == 200:
                                history_data = history_response.json()
                                messages = history_data.get("result", {}).get("messages", [])
                                
                                # Count messages from CUSTOMER, MARKET, or SUPPORT that are unread
                                unread_count = 0
                                for msg in messages:
                                    sender = msg.get("sender", "").upper()
                                    if sender in ["CUSTOMER", "MARKET", "SUPPORT"]:
                                        # Check if message was created after last viewed timestamp
                                        if last_viewed_at:
                                            msg_created_at_str = msg.get("createdAt", "")
                                            if msg_created_at_str:
                                                try:
                                                    # Parse Yandex timestamp format (ISO 8601)
                                                    # Try fromisoformat first (Python 3.7+)
                                                    if 'T' in msg_created_at_str or ' ' in msg_created_at_str:
                                                        # Replace space with T for ISO format
                                                        iso_str = msg_created_at_str.replace(' ', 'T')
                                                        # Remove timezone info if present and add Z
                                                        if '+' in iso_str or iso_str.endswith('Z'):
                                                            # Already has timezone
                                                            msg_created_at = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
                                                        else:
                                                            # No timezone, assume UTC
                                                            msg_created_at = datetime.fromisoformat(iso_str + '+00:00')
                                                    else:
                                                        # Fallback: try strptime
                                                        msg_created_at = datetime.strptime(msg_created_at_str, "%Y-%m-%dT%H:%M:%S")
                                                        msg_created_at = msg_created_at.replace(tzinfo=timezone.utc)
                                                    
                                                    # Ensure message timestamp is timezone-aware
                                                    if msg_created_at.tzinfo is None:
                                                        msg_created_at = msg_created_at.replace(tzinfo=timezone.utc)
                                                    
                                                    # Compare with last_viewed_at (already timezone-aware)
                                                    if msg_created_at > last_viewed_at:
                                                        unread_count += 1
                                                except Exception as parse_error:
                                                    # If parsing fails, count as unread to be safe
                                                    print(f"⚠️  Error parsing message timestamp '{msg_created_at_str}': {parse_error}")
                                                    unread_count += 1
                                        else:
                                            # No last viewed timestamp, count all messages as unread
                                            unread_count += 1
                                
                                return {"unread_count": unread_count}
                        # If we can't get messages, but status is WAITING_FOR_PARTNER, return 1 if not viewed
                        if not last_viewed_at:
                            return {"unread_count": 1}
                        return {"unread_count": 0}
            
            return {"unread_count": 0}
    except Exception as e:
        # Return 0 on error to prevent UI issues
        print(f"⚠️  Error getting unread count for order {order_id}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"unread_count": 0}


@router.get("/orders/{order_id}/messages", response_model=List[Dict])
def get_order_chat_messages(
    order_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Get chat messages for an order
    
    Transforms Yandex API message format to frontend format:
    - sender (PARTNER/CUSTOMER/MARKET/SUPPORT) -> author (SELLER/CUSTOMER/SYSTEM)
    - message -> text
    - messageId -> id
    - createdAt -> created_at
    """
    try:
        business_id = get_business_id(current_user)
        yandex_api = _yandex_api(business_id, db, store)
        raw_messages = yandex_api.get_order_chat_messages(order_id)
        
        if not raw_messages:
            return []
        
        # Transform messages to match frontend interface
        transformed_messages = []
        for msg in raw_messages:
            # Map sender to author
            sender = msg.get("sender", "").upper()
            if sender == "PARTNER":
                author = "SELLER"
            elif sender == "CUSTOMER":
                author = "CUSTOMER"
            else:  # MARKET, SUPPORT, or unknown
                author = "SYSTEM"
            
            transformed_msg = {
                "id": str(msg.get("messageId", "")),
                "text": msg.get("message", ""),
                "author": author,
                "created_at": msg.get("createdAt", ""),
                "order_id": order_id
            }
            transformed_messages.append(transformed_msg)

        enrich_seller_sender_names(db, business_id, transformed_messages)
        return transformed_messages
    except ValueError as e:
        # Configuration errors (missing business_id, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log the error but return empty list instead of 500 to prevent frontend errors
        import traceback
        print(f"⚠️  Error getting chat messages for order {order_id}: {str(e)}")
        print(traceback.format_exc())
        return []  # Return empty list instead of raising 500 error


@router.get("/chats", response_model=Dict)
def get_chats(
    limit: int = Query(20, ge=1, le=20),
    page_token: Optional[str] = Query(None, alias="page_token"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Get all chats for the business (includes DIRECT chats)."""
    business_id = get_business_id(current_user)
    try:
        yandex_api = _yandex_api(business_id, db, store)
        return yandex_api.get_chats(limit=limit, page_token=page_token)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/chats/{chat_id}/messages", response_model=Dict)
def get_chat_messages(
    chat_id: int,
    limit: int = Query(100, ge=1, le=100),
    page_token: Optional[str] = Query(None, alias="page_token"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Get messages for a chat by chatId."""
    business_id = get_business_id(current_user)
    yandex_api = _yandex_api(business_id, db, store)
    history = yandex_api.get_chat_history(chat_id=int(chat_id), limit=limit, page_token=page_token)

    messages = history.get("messages", []) or []
    transformed_messages: List[Dict[str, Any]] = []
    for msg in messages:
        sender = str(msg.get("sender", "")).upper()
        if sender == "PARTNER":
            author = "SELLER"
        elif sender == "CUSTOMER":
            author = "CUSTOMER"
        else:
            author = "SYSTEM"
        transformed_messages.append(
            {
                "id": str(msg.get("messageId", "")),
                "text": msg.get("message", "") or "",
                "author": author,
                "created_at": msg.get("createdAt", ""),
                "payload": msg.get("payload"),
            }
        )

    enrich_seller_sender_names(db, business_id, transformed_messages)
    return {
        "context": history.get("context") or {},
        "messages": transformed_messages,
        "nextPageToken": history.get("nextPageToken"),
    }


@router.post("/chats/{chat_id}/messages", response_model=Dict)
def send_chat_message(
    chat_id: int,
    body: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Send a message to a chat by chatId."""
    business_id = get_business_id(current_user)
    yandex_api = _yandex_api(business_id, db, store)
    result = yandex_api.send_message_to_chat(int(chat_id), body.text)
    attribute_partner_message(
        db,
        business_id=business_id,
        sent_by_user_id=current_user.id,
        chat_id=int(chat_id),
        message_text=body.text,
        yandex_api=yandex_api,
    )
    return {"success": True, "data": result}


@router.post("/orders/{order_id}/messages", response_model=Dict)
def send_order_chat_message(
    order_id: str,
    message: MessageRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    store: db_models.MarketStore = Depends(get_current_store),
):
    """Send a message in order chat"""
    try:
        business_id = get_business_id(current_user)
        yandex_api = _yandex_api(business_id, db, store)
        result = yandex_api.send_order_chat_message(order_id, message.text)
        chat = yandex_api.get_chat_for_order(order_id)
        chat_id = int(chat["chatId"]) if chat and chat.get("chatId") else None
        if chat_id:
            attribute_partner_message(
                db,
                business_id=business_id,
                sent_by_user_id=current_user.id,
                chat_id=chat_id,
                message_text=message.text,
                yandex_api=yandex_api,
                order_id=order_id,
            )

        return {"success": True, "message": "Message sent successfully", "data": result}
    except Exception as e:
        import traceback
        print(f"⚠️  Error sending chat message: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to send order chat message: {str(e)}")


@router.post("/orders/{order_id}/mark-read", response_model=Dict)
def mark_order_chat_as_read(
    order_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    """Mark chat messages as read for an order
    
    Updates the last viewed timestamp to the current time.
    This should be called when the user opens the chat modal.
    """
    try:
        from app import models
        from datetime import datetime, timezone
        
        # Get or create read status
        read_status = db.query(models.ChatReadStatus).filter(
            models.ChatReadStatus.order_id == order_id
        ).first()
        
        if read_status:
            # Update existing record
            read_status.last_viewed_at = datetime.now(timezone.utc)
        else:
            # Create new record
            read_status = models.ChatReadStatus(
                order_id=order_id,
                last_viewed_at=datetime.now(timezone.utc)
            )
            db.add(read_status)
        
        db.commit()
        db.refresh(read_status)
        
        return {"success": True, "message": "Chat marked as read", "last_viewed_at": read_status.last_viewed_at.isoformat()}
    except Exception as e:
        db.rollback()
        import traceback
        print(f"⚠️  Error marking chat as read for order {order_id}: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to mark chat as read: {str(e)}")
