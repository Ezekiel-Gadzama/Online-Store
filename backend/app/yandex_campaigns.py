"""Yandex Partner API token pagination (limit + page_token; not page/pageSize)."""
from typing import Any, Dict, List, Optional

import httpx


def _campaigns_headers(api_token: str, business_id: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_token.startswith("ACMA:"):
        headers["Api-Key"] = api_token
    elif api_token.startswith("OAuth "):
        headers["Authorization"] = api_token
    else:
        headers["Authorization"] = f"OAuth {api_token}"
    if business_id:
        headers["X-Business-Id"] = str(business_id)
    return headers


def next_page_token(data: Dict[str, Any]) -> Optional[str]:
    """nextPageToken from top-level or result.paging / pager (post–2026-10 API)."""
    if not isinstance(data, dict):
        return None
    containers = [data]
    result = data.get("result")
    if isinstance(result, dict):
        containers.append(result)
    for container in containers:
        paging = container.get("paging") or {}
        token = paging.get("nextPageToken")
        if token:
            return str(token)
        pager = container.get("pager") or {}
        token = pager.get("nextPageToken")
        if token:
            return str(token)
    return None


def fetch_campaigns_list(
    api_token: str,
    *,
    base_url: str = "https://api.partner.market.yandex.ru",
    business_id: Optional[str] = None,
    limit: int = 100,
    timeout: float = 30.0,
) -> List[Dict[str, Any]]:
    """All stores visible to the token (paginated)."""
    url = f"{base_url.rstrip('/')}/v2/campaigns"
    headers = _campaigns_headers(api_token, business_id)
    campaigns: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    cap = max(1, min(limit, 100))

    with httpx.Client() as client:
        while True:
            params: Dict[str, Any] = {"limit": cap}
            if page_token:
                params["page_token"] = page_token
            response = client.get(url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            campaigns.extend(data.get("campaigns", []))
            page_token = next_page_token(data)
            if not page_token:
                break
    return campaigns