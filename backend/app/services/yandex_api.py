import httpx
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse
from app.config import settings
from app import models
from app.database import SessionLocal
from app.yandex_campaigns import next_page_token


class YandexMarketAPI:
    """Service for interacting with Yandex Market Partner API"""
    
    def __init__(self, business_id: int = None, db=None, store_id: int = None):
        """Initialize YandexMarketAPI with business-specific settings
        
        Args:
            business_id: The business ID to get settings for (required)
            db: Database session (optional, will create one if not provided)
        """
        if not business_id:
            raise ValueError("business_id is required. Each business must configure their own Yandex API settings.")
        
        # Get settings from database for this business
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
        
        try:
            from app.services.config_validator import validate_yandex_config
            app_settings = validate_yandex_config(business_id, db, store_id)
            self.store_id = store_id
            
            # Use database settings only
            self.api_token = app_settings.yandex_api_token.strip() if app_settings.yandex_api_token else None
            self.business_id = app_settings.yandex_business_id.strip() if app_settings.yandex_business_id else None
            self.campaign_id = app_settings.yandex_campaign_id.strip() if app_settings.yandex_campaign_id else None
            self.base_url = app_settings.yandex_api_url.strip() if app_settings.yandex_api_url else "https://api.partner.market.yandex.ru"
        finally:
            if close_db:
                db.close()
        
        if not self.api_token:
            raise ValueError("Yandex Market API token is not configured. Please configure it in the Settings page.")
        
        # Detect token type: ACMA tokens work with Campaign API, OAuth tokens work with Business API
        self.is_acma_token = self.api_token.startswith("ACMA:")
        
        if self.is_acma_token:
            if not self.campaign_id and not self.business_id:
                raise ValueError(
                    "Configure Yandex Market campaign_id or business_id for ACMA tokens in Settings."
                )
            if self.campaign_id and self.business_id:
                print(
                    "ℹ️  ACMA token — campaign_id {} and business_id {}".format(
                        self.campaign_id, self.business_id
                    )
                )
            elif self.campaign_id:
                print("ℹ️  ACMA token — campaign_id {}".format(self.campaign_id))
            else:
                print("ℹ️  ACMA token — business_id {} (no campaign yet)".format(self.business_id))
        else:
            # OAuth tokens use Business API - need business_id
            if not self.business_id:
                raise ValueError("Yandex Market Business ID is required when using OAuth tokens. Please configure it in the Settings page.")
            print("ℹ️  Using OAuth token with Business API (business_id: {})".format(self.business_id))
    
    def _get_api_base_path(self) -> str:
        """Get the base API path based on token type"""
        if self.is_acma_token:
            # ACMA tokens use Campaign API
            return f"{self.base_url}/v2/campaigns/{self.campaign_id}"
        else:
            # OAuth tokens use Business API
            return f"{self.base_url}/v2/businesses/{self.business_id}"
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        # Yandex Market Partner API authentication
        # ACMA tokens use Api-Key header, OAuth tokens use Authorization header
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_token.startswith("ACMA:"):
            # ACMA application tokens use Api-Key header (not Authorization!)
            headers["Api-Key"] = self.api_token
        elif self.api_token.startswith("OAuth "):
            # Already has OAuth prefix
            headers["Authorization"] = self.api_token
        else:
            # Regular OAuth token - add OAuth prefix
            headers["Authorization"] = f"OAuth {self.api_token}"

        if self.business_id:
            headers["X-Business-Id"] = str(self.business_id)
        
        return headers
    
    def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make HTTP request with error logging"""
        try:
            with httpx.Client() as client:
                response = client.request(method, url, **kwargs)
                # Log error responses for debugging
                if response.status_code in [401, 403]:
                    print(f"Authentication error ({response.status_code}) for {method} {url}")
                    print(f"Response: {response.text}")
                    print(f"Headers sent: {kwargs.get('headers', {})}")
                elif not response.is_success:
                    print(f"Request failed ({response.status_code}) for {method} {url}")
                    print(f"Response: {response.text}")
                return response
        except httpx.HTTPError as e:
            print(f"HTTP error for {method} {url}: {str(e)}")
            raise
    
    def create_product(self, product: models.Product) -> Dict:
        """Create a product on Yandex Market using offer-mappings/update endpoint
        
        According to Yandex API documentation:
        - Business API: POST /v2/businesses/{businessId}/offer-mappings/update
        - Campaign API: POST /v2/campaigns/{campaignId}/offers/update
        """
        # Use correct API endpoint based on token type
        if self.is_acma_token:
            # Campaign API
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers/update"
        else:
            # Business API uses offer-mappings/update
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/update"
        
        # Get data from yandex_full_data if available, otherwise use product fields
        yandex_data = product.yandex_full_data or {}
        
        # Extract images and videos from yandex_full_data
        images = yandex_data.get("pictures") or yandex_data.get("images") or []
        videos = yandex_data.get("videos") or []
        
        # If stored as JSON strings, parse them
        if isinstance(images, str):
            try:
                images = json.loads(images)
            except:
                images = []
        if isinstance(videos, str):
            try:
                videos = json.loads(videos)
            except:
                videos = []
        
        # Build offer payload - Business API format
        shop_sku = product.yandex_market_sku or yandex_data.get("offerId") or f"SKU-{product.id}"
        
        offer = {
            "shopSku": shop_sku,
            "name": product.name,
            "description": product.description or "",
            "price": {
                "value": product.selling_price,
                "currencyId": yandex_data.get("basicPrice", {}).get("currencyId") or "RUR"
            },
            "vat": yandex_data.get("vat") or product.vat_rate or "NOT_APPLICABLE",
            "availability": "ACTIVE" if product.is_active else "INACTIVE",
        }
        
        # Add parameterValues if available in yandex_full_data
        if "parameterValues" in yandex_data and isinstance(yandex_data["parameterValues"], list):
            offer["parameterValues"] = yandex_data["parameterValues"]
        
        # Add barcode if available
        if yandex_data.get("barcode") or product.barcode:
            barcode = yandex_data.get("barcode") or product.barcode
            offer["barcode"] = [barcode] if isinstance(barcode, str) else barcode
        
        # Add dimensions for physical products
        if yandex_data.get("dimensions"):
            offer["dimensions"] = yandex_data["dimensions"]
        elif product.width_cm or product.height_cm or product.length_cm or product.weight_kg:
            dimensions = {}
            if product.width_cm:
                dimensions["width"] = product.width_cm
            if product.height_cm:
                dimensions["height"] = product.height_cm
            if product.length_cm:
                dimensions["length"] = product.length_cm
            if product.weight_kg:
                dimensions["weight"] = product.weight_kg
            if dimensions:
                offer["dimensions"] = dimensions
        
        # Add oldPrice if available
        if yandex_data.get("oldPrice") or (product.crossed_out_price and product.crossed_out_price > product.selling_price):
            old_price = yandex_data.get("oldPrice") or product.crossed_out_price
            if old_price and old_price > product.selling_price:
                offer["oldPrice"] = {"value": old_price, "currencyId": "RUR"}
        
        # For digital products, use DBS model
        if product.product_type == models.ProductType.DIGITAL:
            offer["type"] = "DIGITAL"
            offer["model"] = yandex_data.get("model") or product.yandex_model or "DBS"
        else:
            offer["type"] = "PHYSICAL"
            if yandex_data.get("model") or product.yandex_model:
                offer["model"] = yandex_data.get("model") or product.yandex_model
        
        # Category information
        if yandex_data.get("mapping", {}).get("marketCategoryId"):
            offer["categoryId"] = yandex_data["mapping"]["marketCategoryId"]
        elif yandex_data.get("categoryId"):
            offer["categoryId"] = yandex_data["categoryId"]
        elif product.yandex_category_id:
            offer["categoryId"] = product.yandex_category_id
        
        # Images
        if images:
            offer["pictures"] = images
        
        # Videos
        if videos:
            offer["videos"] = videos
        
        # Build payload according to API
        if self.is_acma_token:
            # Campaign API expects {"offers": [offer]}
            payload = {"offers": [offer]}
        else:
            # Business API expects {"offerMappingEntries": [{"offer": {...}}]}
            payload = {
                "offerMappingEntries": [{
                    "offer": offer
                }]
            }
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                # Return the created offer data
                if self.is_acma_token:
                    # Campaign API response format
                    return result
                else:
                    # Business API response format - extract offer from response
                    if "result" in result and "offerMappingEntries" in result["result"]:
                        entries = result["result"]["offerMappingEntries"]
                        if entries:
                            return entries[0].get("offer", {})
                    return result
        except httpx.HTTPError as e:
            error_msg = f"Failed to create product on Yandex Market: {str(e)}"
            if hasattr(e, 'response') and e.response:
                error_msg += f" - Response: {e.response.text}"
            raise Exception(error_msg)
    
    def update_product(self, product: models.Product, field_updates: Dict = None) -> Dict:
        """Update a product on Yandex Market using yandex_full_data JSON"""
        if not product.yandex_market_id:
            raise ValueError("Product not synced with Yandex Market")
        
        if self.is_acma_token:
            # Campaign API: Use POST /v2/campaigns/*/offers/update or POST /v2/campaigns/*/offer-mapping-entries/updates
            # Based on endpoint list: POST /v2/campaigns/*/offers/update exists
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers/update"
        else:
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/update"
        
        # Get base data from yandex_full_data, merge with field_updates
        base_data = product.yandex_full_data or {}
        if field_updates:
            base_data = {**base_data, **field_updates}
        
        # Build offer payload from yandex_full_data
        # Use the structure that Yandex expects
        shop_sku = product.yandex_market_sku or base_data.get("offerId") or product.yandex_market_id
        
        # Get price - handle both object and number formats
        price_value = product.selling_price
        if base_data.get("basicPrice"):
            price_value = base_data["basicPrice"].get("value", price_value) if isinstance(base_data["basicPrice"], dict) else price_value
        elif base_data.get("price"):
            price_value = base_data["price"].get("value", price_value) if isinstance(base_data["price"], dict) else base_data["price"]
        
        currency_id = "RUR"
        if base_data.get("basicPrice", {}).get("currencyId"):
            currency_id = base_data["basicPrice"]["currencyId"]
        elif base_data.get("price", {}).get("currencyId"):
            currency_id = base_data["price"]["currencyId"]
        
        offer = {
            "shopSku": shop_sku,
            "name": base_data.get("name") or product.name,
            "description": base_data.get("description") or product.description or "",
            "price": {
                "value": price_value,
                "currencyId": currency_id
            },
            "vat": base_data.get("vat") or base_data.get("vat_rate") or "NOT_APPLICABLE",
            "availability": "ACTIVE" if product.is_active else "INACTIVE",
        }
        
        # Add parameterValues if available
        if "parameterValues" in base_data and isinstance(base_data["parameterValues"], list):
            offer["parameterValues"] = base_data["parameterValues"]
        
        # Add fields from yandex_full_data that Yandex expects
        if "barcode" in base_data:
            barcode = base_data["barcode"]
            offer["barcode"] = [barcode] if isinstance(barcode, str) else barcode
        
        if "dimensions" in base_data:
            offer["dimensions"] = base_data["dimensions"]
        elif any(key in base_data for key in ["width", "height", "length", "weight"]):
            dimensions = {}
            if "width" in base_data:
                dimensions["width"] = base_data["width"]
            if "height" in base_data:
                dimensions["height"] = base_data["height"]
            if "length" in base_data:
                dimensions["length"] = base_data["length"]
            if "weight" in base_data:
                dimensions["weight"] = base_data["weight"]
            if dimensions:
                offer["dimensions"] = dimensions
        
        if "oldPrice" in base_data or "crossed_out_price" in base_data:
            old_price = base_data.get("oldPrice")
            if isinstance(old_price, dict):
                old_price = old_price.get("value")
            elif not old_price:
                old_price = base_data.get("crossed_out_price")
            
            if old_price and old_price > price_value:
                offer["oldPrice"] = {"value": old_price, "currencyId": currency_id}
        
        if "model" in base_data:
            offer["model"] = base_data["model"]
        elif product.product_type == models.ProductType.DIGITAL:
            offer["model"] = "DBS"
        
        # Category from mapping or direct
        if base_data.get("mapping", {}).get("marketCategoryId"):
            offer["categoryId"] = base_data["mapping"]["marketCategoryId"]
        elif "categoryId" in base_data:
            offer["categoryId"] = base_data["categoryId"]
        elif base_data.get("marketCategoryId"):
            offer["marketCategoryId"] = base_data["marketCategoryId"]
        
        # Extract params from yandex_full_data
        params = base_data.get("params", {})
        if not params:
            # Try to build params from individual fields in base_data
            if "vendor" in base_data or "brand" in base_data:
                params["vendor"] = base_data.get("vendor") or base_data.get("brand")
            if "platform" in base_data:
                params["platform"] = base_data["platform"]
            if "localization" in base_data:
                params["localization"] = base_data["localization"]
            if "publicationType" in base_data:
                params["publicationType"] = base_data["publicationType"]
            if "activationTerritory" in base_data:
                params["activationTerritory"] = base_data["activationTerritory"]
            if "edition" in base_data:
                params["edition"] = base_data["edition"]
            if "series" in base_data:
                params["series"] = base_data["series"]
            if "ageRestriction" in base_data:
                params["ageRestriction"] = base_data["ageRestriction"]
            if "hasActivationInstructions" in base_data:
                params["hasActivationInstructions"] = base_data["hasActivationInstructions"]
        
        # Images and videos from yandex_full_data
        if "pictures" in base_data:
            offer["pictures"] = base_data["pictures"]
        elif "images" in base_data:
            offer["pictures"] = base_data["images"]
        
        if "videos" in base_data:
            offer["videos"] = base_data["videos"]
        
        # Add params if any
        if params:
            offer["params"] = params
        
        if self.is_acma_token:
            # Campaign API: POST /v2/campaigns/*/offers/update expects offers array
            payload = {
                "offers": [offer]
            }
        else:
            # Business API expects {"offerMappingEntries": [{"offer": {...}}]}
            payload = {
                "offerMappingEntries": [{
                    "offer": offer
                }]
            }
        
        try:
            with httpx.Client() as client:
                # Both APIs use POST for updates
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update product on Yandex Market: {str(e)}")
    
    def _offers_from_response(self, data: Dict[str, Any]) -> List[Dict]:
        if "offers" in data:
            offers = data.get("offers") or []
        else:
            result = data.get("result") or {}
            offers = result.get("offers") or []
        return offers if isinstance(offers, list) else []

    def _fetch_v1_business_orders(
        self,
        body: Dict[str, Any],
        *,
        log_first_page: bool = False,
    ) -> List[Dict]:
        """POST v1/businesses/{businessId}/orders (replaces deprecated GET campaign orders)."""
        if not self.business_id:
            raise ValueError("business_id is required to fetch orders")
        url = f"{self.base_url}/v1/businesses/{self.business_id}/orders"
        collected: List[Dict] = []
        page_token: Optional[str] = None
        log_raw = log_first_page
        while True:
            params: Dict[str, Any] = {"limit": 50}
            if page_token:
                params["page_token"] = page_token
            response = self._make_request(
                "POST",
                url,
                params=params,
                json=body,
                headers=self._get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            if log_raw:
                print("=" * 80)
                print("📋 RAW YANDEX v1 ORDERS RESPONSE (first page):")
                print("=" * 80)
                print(json.dumps(data, indent=2, ensure_ascii=False))
                print("=" * 80)
                log_raw = False
            result = data.get("result") or {}
            batch = result.get("orders", data.get("orders", []))
            if isinstance(batch, list):
                collected.extend(batch)
            page_token = next_page_token(data)
            if not page_token:
                break
        return collected

    def _query_offer_mapping_entries(self, body: Dict[str, Any]) -> List[Dict]:
        """POST v2/businesses/{businessId}/offer-mappings (replaces GET offer-mapping-entries)."""
        if not self.business_id:
            raise ValueError("business_id is required")
        url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings"
        offer_ids = body.get("offerIds")
        entries: List[Dict] = []
        page_token: Optional[str] = None
        while True:
            params: Dict[str, Any] = {"limit": 100}
            if page_token:
                params["page_token"] = page_token
            response = self._make_request(
                "POST",
                url,
                params=params,
                json=body,
                headers=self._get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("result") or {}
            batch = result.get("offerMappingEntries") or []
            if isinstance(batch, list):
                entries.extend(batch)
            if offer_ids:
                break
            page_token = next_page_token(data)
            if not page_token:
                break
        return entries

    def _campaign_offer_rows(self, offer_ids: List[str]) -> List[Dict]:
        """POST v2/campaigns/{campaignId}/offers with offerIds (not GET offer-mapping-entries)."""
        if not self.campaign_id:
            raise ValueError("campaign_id is required")
        url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers"
        rows: List[Dict] = []
        for i in range(0, len(offer_ids), 200):
            batch = offer_ids[i : i + 200]
            response = self._make_request(
                "POST",
                url,
                params={"limit": len(batch)},
                json={"offerIds": batch},
                headers=self._get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            rows.extend(self._offers_from_response(data))
        return rows

    def get_products(self) -> List[Dict]:
        """Get all products from Yandex Market"""
        if self.is_acma_token:
            urls_to_try = [
                f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers",
            ]
            last_error: Optional[Exception] = None
            for url in urls_to_try:
                all_offers: List[Dict] = []
                page_token: Optional[str] = None
                try:
                    while True:
                        params: Dict[str, Any] = {"limit": 100}
                        if page_token:
                            params["page_token"] = page_token
                        print(f"🔍 Fetching products from: {url}")
                        response = self._make_request(
                            "POST",
                            url,
                            params=params,
                            json={},
                            headers=self._get_headers(),
                            timeout=30.0,
                        )
                        response.raise_for_status()
                        data = response.json()
                        batch = self._offers_from_response(data)
                        all_offers.extend(batch)
                        page_token = next_page_token(data)
                        if not page_token:
                            break
                    print(f"📦 Found {len(all_offers)} offers")
                    if all_offers:
                        print("=" * 80)
                        print(f"RAW YANDEX API RESPONSE (Campaign API) - ALL {len(all_offers)} PRODUCTS:")
                        print("=" * 80)
                        print(json.dumps(all_offers, indent=2, ensure_ascii=False))
                        print("=" * 80)
                    return all_offers
                except httpx.HTTPError as e:
                    last_error = e
                    print(f"⚠️  {url} failed, trying next endpoint...")
                    continue
            print(f"❌ Error getting products from Campaign API: {str(last_error)}")
            if isinstance(last_error, httpx.HTTPError) and last_error.response:
                print(f"Response status: {last_error.response.status_code}")
                print(f"Response body: {last_error.response.text}")
            raise Exception(f"Failed to get products from Yandex Market: {str(last_error)}")
        else:
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings"
            offer_mappings: List[Dict] = []
            page_token: Optional[str] = None
            try:
                while True:
                    params: Dict[str, Any] = {"limit": 100}
                    if page_token:
                        params["page_token"] = page_token
                    response = self._make_request(
                        "POST",
                        url,
                        params=params,
                        json={},
                        headers=self._get_headers(),
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    result = data.get("result") or {}
                    batch = result.get("offerMappingEntries") or []
                    if isinstance(batch, list):
                        offer_mappings.extend(batch)
                    page_token = next_page_token(data)
                    if not page_token:
                        break
                if offer_mappings:
                    print("=" * 80)
                    print(
                        f"RAW YANDEX API RESPONSE (Business API - offer-mappings) - "
                        f"ALL {len(offer_mappings)} PRODUCTS:"
                    )
                    print("=" * 80)
                    print(json.dumps(offer_mappings, indent=2, ensure_ascii=False))
                    print("=" * 80)
                return offer_mappings
            except httpx.HTTPError as e:
                print(f"❌ Error getting products from Business API: {str(e)}")
                if hasattr(e, 'response') and e.response:
                    print(f"Response status: {e.response.status_code}")
                    print(f"Response body: {e.response.text}")
                raise Exception(f"Failed to get products from Yandex Market: {str(e)}")
    
    def get_product_card(self, offer_id: str) -> Optional[Dict]:
        """
        Get full product card details from Yandex Market (name, description, images, videos, characteristics, etc.)
        This endpoint provides complete product information including media attachments.
        
        Uses Business API endpoint /v2/businesses/*/offer-cards which works with both ACMA and OAuth tokens
        as long as business_id is available. The Campaign API endpoint is deprecated.
        """
        # Use Business API endpoint if business_id is available (works with both ACMA and OAuth tokens)
        # The Campaign API offer-mapping-entries endpoint is deprecated
        if not self.business_id or (isinstance(self.business_id, str) and not self.business_id.strip()):
            print(f"⚠️  Warning: business_id is required to fetch product card. Skipping product card fetch for {offer_id}")
            return None
        
        try:
            # Business API: Use POST /v2/businesses/*/offer-cards (works with both ACMA and OAuth tokens)
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-cards"
            payload = {
                "offerIds": [offer_id]
            }
            response = self._make_request("POST", url, json=payload, headers=self._get_headers(), timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            # Business API returns result.offerCards array
            cards = data.get("result", {}).get("offerCards", [])
            if cards:
                card_data = cards[0]
                # Log the raw response
                print("=" * 80)
                print(f"RAW YANDEX PRODUCT CARD API RESPONSE (Business API) FOR {offer_id}:")
                print("=" * 80)
                import json
                print(json.dumps(card_data, indent=2, ensure_ascii=False))
                print("=" * 80)
                return card_data
            return None
        except httpx.HTTPError as e:
            print(f"⚠️  Warning: Could not fetch product card for {offer_id}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            # Don't raise - return None so we can still use basic offer data
            return None
        except Exception as e:
            print(f"⚠️  Warning: Error fetching product card for {offer_id}: {str(e)}")
            return None
    
    def get_orders(self, status: Optional[str] = None, include_test: bool = True) -> List[Dict]:
        """Get orders from Yandex Market
        
        Yandex Market order response format:
        {
            "orders": [
                {
                    "id": 12345,
                    "status": "PROCESSING",
                    "items": [
                        {
                            "id": 987654,       # Item ID (needed for deliverDigitalGoods)
                            "offerId": "MRKT-SJD3W00P",  # Matches Product.yandex_market_id
                            "offerName": "Product Name",
                            "count": 1,
                            "price": 100.0,
                            "digitalItem": true
                        }
                    ],
                    "buyer": {"id": "...", "type": "PERSON"},
                    "total": 100.0,
                    "itemsTotal": 100.0
                }
            ]
        }
        """
        all_orders: List[Dict] = []
        if not self.business_id:
            print("❌ business_id is required to fetch orders (v1 API)")
            return all_orders

        body: Dict[str, Any] = {}
        if self.campaign_id:
            try:
                body["campaignIds"] = [int(self.campaign_id)]
            except ValueError:
                body["campaignIds"] = [self.campaign_id]
        if status:
            body["statuses"] = [status]

        try:
            print("🔍 Fetching orders via POST v1/businesses/.../orders")
            orders = self._fetch_v1_business_orders(body, log_first_page=True)
            print(f"📋 Found {len(orders)} orders")
            for order in orders:
                print(
                    f"  Order #{order.get('id')}: status={order.get('status')}, "
                    f"items={len(order.get('items', []))}, "
                    f"fake={order.get('fake', False)}"
                )
            all_orders.extend(orders)
        except httpx.HTTPError as e:
            print(f"⚠️  v1 orders failed: {str(e)}")
            if hasattr(e, "response") and e.response:
                print(f"  Response status: {e.response.status_code}")
                print(f"  Response body: {e.response.text}")

        if include_test:
            try:
                test_body = {**body, "fake": True}
                test_orders = self._fetch_v1_business_orders(test_body)
                if test_orders:
                    print(f"🧪 Found {len(test_orders)} test orders")
                    existing_ids = {o.get("id") for o in all_orders}
                    for test_order in test_orders:
                        if test_order.get("id") not in existing_ids:
                            all_orders.append(test_order)
            except Exception as e:
                print(f"⚠️  Could not fetch test orders: {str(e)}")
        
        print(f"📦 Total orders fetched: {len(all_orders)}")
        return all_orders
    
    def get_order(self, order_id: str) -> Dict:
        """Get a single order by ID from Yandex Market
        
        Returns the complete order data including all items.
        This is critical for delivering digital goods - we need ALL items from Yandex.
        """
        if not self.business_id:
            raise ValueError("business_id is required to get order details")

        try:
            order_id_int = int(str(order_id).strip())
        except ValueError:
            raise ValueError(f"Invalid Yandex order id: {order_id}")

        body: Dict[str, Any] = {"orderIds": [order_id_int]}
        if self.campaign_id:
            try:
                body["campaignIds"] = [int(self.campaign_id)]
            except ValueError:
                body["campaignIds"] = [self.campaign_id]

        try:
            print(f"🔍 Fetching order {order_id} via POST v1/businesses/.../orders")
            orders = self._fetch_v1_business_orders(body, log_first_page=True)
            if not orders:
                raise Exception(f"Order {order_id} not found in v1 API response")
            order_data = orders[0]
            print(f"✅ Retrieved order {order_id} with {len(order_data.get('items', []))} items")
            return order_data
        except httpx.HTTPError as e:
            error_detail = ""
            if hasattr(e, "response") and e.response:
                error_detail = f" - Status: {e.response.status_code}, Body: {e.response.text}"
            raise Exception(f"Failed to get order {order_id} from Yandex Market{error_detail}")
    
    def accept_order(self, order_id: str) -> Dict:
        """Accept an order on Yandex Market (for digital products)"""
        if not self.business_id:
            raise ValueError("business_id is required to accept orders")
        url = f"{self.base_url}/v1/businesses/{self.business_id}/orders/{order_id}/accept"

        try:
            response = self._make_request(
                "POST", url, headers=self._get_headers(), timeout=30.0
            )
            response.raise_for_status()
            if response.text:
                return response.json()
            return {"success": True}
        except httpx.HTTPError as e:
            raise Exception(f"Failed to accept order on Yandex Market: {str(e)}")
    
    def deliver_digital_goods(self, order_id: str, items: List[Dict]) -> Dict:
        """Deliver digital goods for an order (DBS model)
        
        Uses POST /campaigns/{campaignId}/orders/{orderId}/deliverDigitalGoods
        
        Args:
            order_id: Yandex Market order ID
            items: List of items to deliver, each with:
                - id: Order item ID (from order.items[].id)
                - codes: Array of activation codes/keys (REQUIRED - must be array, not single string)
                - slip: Activation instructions (max 10000 chars, can use HTML)
                - activate_till: Activation code expiry date in YYYY-MM-DD format (REQUIRED - snake_case with underscore!)
        
        Example items:
            [{"id": 987654, "codes": ["XXXX-YYYY"], "slip": "Instructions text", "activate_till": "2026-03-08"}]
        """
        if not self.campaign_id:
            raise ValueError("campaign_id is required for deliverDigitalGoods. Set YANDEX_MARKET_CAMPAIGN_ID.")
        
        url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/orders/{order_id}/deliverDigitalGoods"
        
        payload = {
            "items": items
        }
        
        # Debug: Print the actual payload being sent
        import json
        print(f"📤 Delivering digital goods for order {order_id}")
        print(f"   URL: {url}")
        print(f"   Items: {len(items)}")
        print(f"   Payload JSON: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        
        # Verify activate_till is present in all items (snake_case, not camelCase!)
        for idx, item in enumerate(items):
            if "activate_till" not in item or item["activate_till"] is None:
                raise ValueError(f"Item at index {idx} is missing activate_till field: {item}")
            if "codes" not in item or not item["codes"]:
                raise ValueError(f"Item at index {idx} is missing codes array: {item}")
            print(f"   Item {idx}: id={item.get('id')}, codes={item.get('codes')}, activate_till={item.get('activate_till')}")
        
        try:
            # Manually serialize JSON to ensure activateTill is included
            import json as json_lib
            json_bytes = json_lib.dumps(payload, ensure_ascii=False).encode('utf-8')
            
            # Double-check activate_till and codes are in the serialized JSON
            json_str_check = json_bytes.decode('utf-8')
            if '"activate_till"' not in json_str_check:
                raise ValueError(f"activate_till missing from serialized JSON! JSON: {json_str_check}")
            if '"codes"' not in json_str_check:
                raise ValueError(f"codes missing from serialized JSON! JSON: {json_str_check}")
            
            # Use data parameter with manually serialized JSON and explicit Content-Type
            headers = {**self._get_headers(), "Content-Type": "application/json; charset=utf-8"}
            response = self._make_request(
                "POST", url, 
                data=json_bytes,
                headers=headers, 
                timeout=30.0
            )
            response.raise_for_status()
            print(f"✅ Digital goods delivered successfully for order {order_id}")
            # deliverDigitalGoods returns 200 OK with empty body on success
            try:
                return response.json()
            except:
                return {"success": True, "message": "Digital goods delivered"}
        except httpx.HTTPError as e:
            error_detail = ""
            if hasattr(e, 'response') and e.response:
                error_detail = f" - Status: {e.response.status_code}, Body: {e.response.text}"
            raise Exception(f"Failed to deliver digital goods for order {order_id}{error_detail}")
    
    def complete_order(self, order_id: str, activation_code: str, activation_instructions: str, item_id: int = None, activate_till: str = None) -> Dict:
        """Complete an order by delivering digital goods
        
        This is a convenience wrapper around deliver_digital_goods.
        For DBS digital products, uses POST /campaigns/{campaignId}/orders/{orderId}/deliverDigitalGoods
        
        Args:
            order_id: Yandex Market order ID
            activation_code: The activation code/key
            activation_instructions: Full formatted message to send to customer
            item_id: The order item ID (from order.items[].id). Required for digital goods delivery.
            activate_till: Activation code expiry date in YYYY-MM-DD format (date only, no time).
                          Defaults to 30 days from now if not provided.
        """
        if item_id is None:
            raise ValueError("item_id is required for digital goods delivery. "
                           "It should come from the order's items[].id field stored in yandex_order_data.")
        
        # Ensure item_id is an integer (Yandex API expects integer)
        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            raise ValueError(f"item_id must be a valid integer, got: {type(item_id).__name__} = {item_id}")
        
        # Calculate activate_till date in YYYY-MM-DD format if not provided
        # Yandex Market API requires just the date (YYYY-MM-DD), no time, no timezone
        if not activate_till:
            from app.activation_dates import yandex_activate_till_date
            activate_till = yandex_activate_till_date(30)
        
        # Ensure activate_till is a non-empty string
        if not activate_till or not isinstance(activate_till, str) or len(activate_till.strip()) == 0:
            raise ValueError(f"activate_till must be a non-empty string in YYYY-MM-DD format, got: {activate_till}")
        
        # Build items array - ensure all fields are properly typed and not None
        # IMPORTANT: Include activateTill in the initial dict construction to ensure it's not dropped
        activate_till_str = str(activate_till).strip() if activate_till else None
        if not activate_till_str:
            raise ValueError(f"activateTill cannot be None or empty. Got: {repr(activate_till)}")
        
        # Yandex Market API requires just YYYY-MM-DD format (date only, no time, no timezone)
        # Extract just the date part if it's a datetime string
        if 'T' in activate_till_str:
            activate_till_str = activate_till_str.split('T')[0]
        if len(activate_till_str) > 10:
            activate_till_str = activate_till_str[:10]
        # Ensure it's in YYYY-MM-DD format
        if len(activate_till_str) != 10 or activate_till_str.count('-') != 2:
            raise ValueError(f"activate_till must be in YYYY-MM-DD format, got: {activate_till_str}")
        
        # Build the complete item dict with all fields at once
        # CRITICAL: Yandex API uses snake_case, not camelCase!
        # Field name must be exactly "activate_till" (with underscore), NOT "activateTill"
        # Also, "codes" must be an array, NOT "code" as a single string
        # Date format: YYYY-MM-DD (just date, not datetime)
        
        # Extract just the date part (YYYY-MM-DD) if it's a datetime string
        activate_till_date = str(activate_till_str).strip()
        if 'T' in activate_till_date:
            activate_till_date = activate_till_date.split('T')[0]
        if len(activate_till_date) > 10:
            activate_till_date = activate_till_date[:10]
        
        item_dict = {
            "id": int(item_id),  # Explicitly convert to int
            "codes": [str(activation_code)] if activation_code else [],  # CRITICAL: Must be array, not single string
            "slip": str(activation_instructions[:10000]) if activation_instructions else "",  # Yandex limits slip to 10000 chars (not 2000!)
            "activate_till": activate_till_date  # CRITICAL: snake_case with underscore, YYYY-MM-DD format
        }
        
        items = [item_dict]
        
        # Debug: Print item structure
        print(f"🔍 Item structure before sending:")
        import json
        print(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"   activate_till in dict: {'activate_till' in item_dict}")
        print(f"   activate_till value: {repr(item_dict.get('activate_till'))}")
        print(f"   codes in dict: {'codes' in item_dict}")
        print(f"   codes value: {repr(item_dict.get('codes'))}")
        
        # Verify the field is actually in the JSON string
        json_str = json.dumps(items, ensure_ascii=False)
        if '"activate_till"' not in json_str:
            raise ValueError(f"activate_till field missing from JSON serialization! JSON: {json_str}")
        if '"codes"' not in json_str:
            raise ValueError(f"codes field missing from JSON serialization! JSON: {json_str}")
        
        return self.deliver_digital_goods(order_id, items)
    
    # Reviews and Comments Management
    def get_product_reviews(self, product_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get product reviews from Yandex Market"""
        # Reviews use Business API endpoint with business_id (works with both ACMA and OAuth tokens)
        if not self.business_id:
            print("⚠️  business_id is required for reviews. Reviews are not available without business_id.")
            return []
        
        url = f"{self.base_url}/v2/businesses/{self.business_id}/goods-feedback"

        try:
            if self.is_acma_token:
                # ACMA tokens use POST for Business API endpoints
                payload: Dict = {"limit": limit}
                if product_id:
                    payload["productId"] = product_id
                response = self._make_request("POST", url, json=payload, headers=self._get_headers(), timeout=30.0)
            else:
                # OAuth tokens use GET
                params = {"limit": limit}
                if product_id:
                    params["productId"] = product_id
                response = self._make_request("GET", url, params=params, headers=self._get_headers(), timeout=30.0)
            
            response.raise_for_status()
            data = response.json()
            
            result = data.get("result", {}) or {}
            raw_items = result.get("feedbacks") or result.get("reviews") or []

            reviews: List[Dict[str, Any]] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
                rating_val = item.get("rating")
                if rating_val is None:
                    rating_val = stats.get("rating") if isinstance(stats, dict) else None
                if rating_val is None:
                    rating_val = item.get("grade")
                try:
                    rating_num = int(rating_val) if rating_val is not None else 0
                except Exception:
                    try:
                        rating_num = int(float(rating_val))
                    except Exception:
                        rating_num = 0

                author_obj = item.get("author")
                if isinstance(author_obj, dict):
                    author_name = author_obj.get("name") or "Anonymous"
                    author_id = author_obj.get("id")
                elif isinstance(author_obj, str):
                    author_name = author_obj or "Anonymous"
                    author_id = None
                else:
                    author_name = item.get("authorName") or "Anonymous"
                    author_id = None

                desc = item.get("description") if isinstance(item.get("description"), dict) else None
                if desc:
                    advantages = (desc.get("advantages") or "").strip()
                    disadvantages = (desc.get("disadvantages") or "").strip()
                    comment = (desc.get("comment") or "").strip()
                    parts = []
                    if advantages:
                        parts.append(f"Advantages: {advantages}")
                    if disadvantages:
                        parts.append(f"Disadvantages: {disadvantages}")
                    if comment:
                        parts.append(f"Comment: {comment}")
                    text_val = "\n".join(parts).strip()
                else:
                    text_val = item.get("text")
                    if text_val is None:
                        text_val = item.get("comment")
                    if text_val is None:
                        text_val = ""

                reviews.append(
                    {
                        "id": item.get("id") or item.get("feedbackId"),
                        "rating": rating_num,
                        "text": str(text_val or ""),
                        "author": {"name": author_name, "id": author_id},
                        "created_at": item.get("createdAt") or item.get("created_at") or item.get("date") or item.get("created"),
                        "product": item.get("product", {}) if isinstance(item.get("product"), dict) else {},
                    }
                )
            return reviews
        except httpx.HTTPError as e:
            raise Exception(f"Failed to get product reviews: {str(e)}")
    
    def reply_to_review(self, review_id: str, reply_text: str) -> Dict:
        """Reply to a product review"""
        if not self.business_id:
            raise ValueError("business_id is required to reply to reviews")
        
        url = f"{self.base_url}/v2/businesses/{self.business_id}/goods-feedback/comments/update"
        payload = {"text": reply_text, "gradeId": review_id}
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to reply to review: {str(e)}")
    
    def get_shop_reviews(self, limit: int = 50) -> List[Dict]:
        """Get shop reviews from Yandex Market"""
        # Reviews use Business API endpoint with business_id (works with both ACMA and OAuth tokens)
        if not self.business_id or (isinstance(self.business_id, str) and not self.business_id.strip()):
            print("⚠️  business_id is required for reviews. Reviews are not available without business_id.")
            print(f"   Current business_id value: {repr(self.business_id)}")
            return []
        
        url = f"{self.base_url}/v2/businesses/{self.business_id}/goods-feedback"

        try:
            if self.is_acma_token:
                # ACMA tokens use POST for Business API endpoints
                payload: Dict = {"limit": limit}
                response = self._make_request("POST", url, json=payload, headers=self._get_headers(), timeout=30.0)
            else:
                # OAuth tokens use GET
                params = {"limit": limit}
                response = self._make_request("GET", url, params=params, headers=self._get_headers(), timeout=30.0)
            
            response.raise_for_status()
            data = response.json()
            
            result = data.get("result", {}) or {}
            raw_items = result.get("feedbacks") or result.get("reviews") or []

            reviews: List[Dict[str, Any]] = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
                rating_val = item.get("rating")
                if rating_val is None:
                    rating_val = stats.get("rating") if isinstance(stats, dict) else None
                if rating_val is None:
                    rating_val = item.get("grade")
                try:
                    rating_num = int(rating_val) if rating_val is not None else 0
                except Exception:
                    try:
                        rating_num = int(float(rating_val))
                    except Exception:
                        rating_num = 0

                author_obj = item.get("author")
                if isinstance(author_obj, dict):
                    author_name = author_obj.get("name") or "Anonymous"
                    author_id = author_obj.get("id")
                elif isinstance(author_obj, str):
                    author_name = author_obj or "Anonymous"
                    author_id = None
                else:
                    author_name = item.get("authorName") or "Anonymous"
                    author_id = None

                desc = item.get("description") if isinstance(item.get("description"), dict) else None
                if desc:
                    advantages = (desc.get("advantages") or "").strip()
                    disadvantages = (desc.get("disadvantages") or "").strip()
                    comment = (desc.get("comment") or "").strip()
                    parts = []
                    if advantages:
                        parts.append(f"Advantages: {advantages}")
                    if disadvantages:
                        parts.append(f"Disadvantages: {disadvantages}")
                    if comment:
                        parts.append(f"Comment: {comment}")
                    text_val = "\n".join(parts).strip()
                else:
                    text_val = item.get("text")
                    if text_val is None:
                        text_val = item.get("comment")
                    if text_val is None:
                        text_val = ""

                reviews.append(
                    {
                        "id": item.get("id") or item.get("feedbackId"),
                        "rating": rating_num,
                        "text": str(text_val or ""),
                        "author": {"name": author_name, "id": author_id},
                        "created_at": item.get("createdAt") or item.get("created_at") or item.get("date") or item.get("created"),
                    }
                )
            return reviews
        except httpx.HTTPError as e:
            raise Exception(f"Failed to get shop reviews: {str(e)}")
    
    def reply_to_shop_review(self, review_id: str, reply_text: str) -> Dict:
        """Reply to a shop review"""
        if not self.business_id:
            raise ValueError("business_id is required to reply to reviews")
        
        url = f"{self.base_url}/v2/businesses/{self.business_id}/goods-feedback/comments/update"
        payload = {"text": reply_text, "gradeId": review_id}
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to reply to shop review: {str(e)}")
    
    # Order Chat Management
    def get_chats(self, limit: int = 20, page_token: Optional[str] = None) -> Dict:
        """Get available chats for the business (ORDER/RETURN/DIRECT)."""
        if not self.business_id:
            raise ValueError("business_id is required for chat operations")

        url = f"{self.base_url}/v2/businesses/{self.business_id}/chats"
        params: Dict[str, Any] = {"limit": max(1, min(20, int(limit)))}
        if page_token:
            params["page_token"] = page_token

        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    params=params,
                    json={},  # No filters -> return all chats available to the business
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                result = data.get("result", {}) or {}
                return {
                    "chats": result.get("chats", []) or [],
                    "nextPageToken": (result.get("paging", {}) or {}).get("nextPageToken"),
                }
        except httpx.HTTPError as e:
            error_msg = "Failed to get chats"
            if hasattr(e, 'response') and e.response:
                error_msg += f": {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg)

    def get_chat_history(self, chat_id: int, limit: int = 100, page_token: Optional[str] = None) -> Dict:
        """Get message history for a chat."""
        if not self.business_id:
            raise ValueError("business_id is required for chat operations")

        url = f"{self.base_url}/v2/businesses/{self.business_id}/chats/history"
        params: Dict[str, Any] = {"chatId": int(chat_id), "limit": max(1, min(100, int(limit)))}
        if page_token:
            params["page_token"] = page_token

        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    params=params,
                    json={},
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                result = data.get("result", {}) or {}
                return {
                    "context": result.get("context") or {},
                    "messages": result.get("messages", []) or [],
                    "nextPageToken": (result.get("paging", {}) or {}).get("nextPageToken"),
                }
        except httpx.HTTPError as e:
            error_msg = f"Failed to get chat history for chat {chat_id}"
            if hasattr(e, 'response') and e.response:
                error_msg += f": {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg)

    def create_chat_for_order(self, order_id: int) -> int:
        """Create (or return existing) chat for an order and return chatId."""
        if not self.business_id:
            raise ValueError("business_id is required for chat operations")

        url = f"{self.base_url}/v2/businesses/{self.business_id}/chats/new"
        payload = {"orderId": int(order_id), "context": {"type": "ORDER", "id": int(order_id)}}

        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                chat_id = (data.get("result") or {}).get("chatId")
                if not chat_id:
                    raise Exception(f"Chat creation did not return chatId: {data}")
                return int(chat_id)
        except httpx.HTTPError as e:
            error_msg = f"Failed to create chat for order {order_id}"
            if hasattr(e, 'response') and e.response:
                error_msg += f": {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg)

    def send_message_to_chat(self, chat_id: int, message_text: str) -> Dict:
        """Send a message to a chat by chatId."""
        if not self.business_id:
            raise ValueError("business_id is required for chat operations")

        url = f"{self.base_url}/v2/businesses/{self.business_id}/chats/message"
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    params={"chatId": int(chat_id)},
                    json={"message": message_text},
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            error_msg = f"Failed to send chat message to chat {chat_id}"
            if hasattr(e, 'response') and e.response:
                error_msg += f": {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg)

    def get_chat_by_id(self, chat_id: int) -> Optional[Dict]:
        """Fetch one chat (GET /v2/businesses/{businessId}/chat)."""
        if not self.business_id:
            return None
        url = f"{self.base_url}/v2/businesses/{self.business_id}/chat"
        try:
            with httpx.Client() as client:
                response = client.get(
                    url,
                    params={"chatId": int(chat_id)},
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                if response.status_code != 200:
                    return None
                return response.json().get("result") or None
        except Exception:
            return None

    def get_chat_for_order(self, order_id: str) -> Optional[Dict]:
        """Return Yandex chat record for an order, or None if no chat exists."""
        if not self.business_id:
            return None
        try:
            order_id_int = int(str(order_id).strip())
        except ValueError:
            return None
        url = f"{self.base_url}/v2/businesses/{self.business_id}/chats"
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json={"orderIds": [order_id_int]},
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                if response.status_code != 200:
                    return None
                chats = response.json().get("result", {}).get("chats", []) or []
                if not chats:
                    return None
                chat = chats[0]
                chat_id = chat.get("chatId")
                if chat_id:
                    detail = self.get_chat_by_id(int(chat_id))
                    if detail:
                        return detail
                return chat
        except Exception:
            return None

    def get_order_chat_messages(self, order_id: str) -> List[Dict]:
        """Get chat messages for an order
        
        According to Yandex API documentation:
        - First get the chat for the order using POST /v2/businesses/{businessId}/chats with orderIds filter
        - Then get the chat history using POST /v2/businesses/{businessId}/chats/history with chatId query parameter
        """
        if not self.business_id:
            raise ValueError("business_id is required for chat operations")

        try:
            order_id_int = int(order_id)
        except Exception:
            # Some systems store Yandex order id as non-numeric string; chats API requires integer.
            return []
        
        # Step 1: Get the chat for this order
        # According to docs: POST /v2/businesses/{businessId}/chats with body containing orderIds
        url = f"{self.base_url}/v2/businesses/{self.business_id}/chats"
        
        try:
            with httpx.Client() as client:
                # Use POST with orderIds filter in body (as per documentation)
                # Note: API only allows ONE filter type - either orderIds, contextTypes, or contexts
                payload = {
                    "orderIds": [order_id_int]
                }
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                
                if response.status_code == 404:
                    # No chat exists yet, return empty list
                    return []
                
                response.raise_for_status()
                data = response.json()
                
                # Handle response structure - result.chats array
                chats = data.get("result", {}).get("chats", [])
                if not chats:
                    # No chat found for this order
                    return []
                
                # Get the first chat (there should typically be one chat per order)
                chat = chats[0]
                chat_id = chat.get("chatId")  # Note: field is "chatId", not "id"
                
                if not chat_id:
                    return []
                
                # Step 2: Get chat history using chat ID
                # According to docs: POST /v2/businesses/{businessId}/chats/history with chatId query parameter
                history_url = f"{self.base_url}/v2/businesses/{self.business_id}/chats/history"
                
                history_response = client.post(
                    history_url,
                    params={"chatId": chat_id},
                    json={},  # Optional body with messageIdFrom if needed
                    headers=self._get_headers(),
                    timeout=30.0
                )
                
                if history_response.status_code == 200:
                    history_data = history_response.json()
                    messages = history_data.get("result", {}).get("messages", [])
                    return messages
                else:
                    # If history endpoint fails, return empty list
                    print(f"⚠️  Failed to get chat history: {history_response.status_code} - {history_response.text}")
                    return []
                
        except httpx.HTTPError as e:
            error_msg = f"Failed to get order chat messages for order {order_id}"
            if hasattr(e, 'response') and e.response:
                error_msg += f": {e.response.status_code} - {e.response.text}"
            print(f"⚠️  {error_msg}")
            # Return empty list instead of raising to prevent 500 errors
            return []
        except Exception as e:
            print(f"⚠️  Error getting chat messages: {str(e)}")
            return []
    
    def send_order_chat_message(self, order_id: str, message_text: str) -> Dict:
        """Send a message in order chat
        
        According to Yandex API documentation:
        - First get the chat for the order using POST /v2/businesses/{businessId}/chats
        - Then send message using POST /v2/businesses/{businessId}/chats/message with chatId query parameter
        """
        if not self.business_id:
            raise ValueError("business_id is required for chat operations")

        try:
            order_id_int = int(order_id)
        except Exception:
            raise ValueError(f"Order id must be numeric for chats API: {order_id}")
        
        # Step 1: Get chat for the order
        chats_url = f"{self.base_url}/v2/businesses/{self.business_id}/chats"
        
        try:
            with httpx.Client() as client:
                # Get existing chat using POST with orderIds filter
                # Note: API only allows ONE filter type - either orderIds, contextTypes, or contexts
                payload = {
                    "orderIds": [order_id_int]
                }
                response = client.post(
                    chats_url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                
                chat_id = None
                if response.status_code == 200:
                    data = response.json()
                    chats = data.get("result", {}).get("chats", [])
                    if chats:
                        chat_id = chats[0].get("chatId")  # Note: field is "chatId", not "id"
                
                # If no chat exists, we need to create one first
                if not chat_id:
                    # Create chat for the order (or return previously created one)
                    create_url = f"{self.base_url}/v2/businesses/{self.business_id}/chats/new"
                    create_payload = {"orderId": order_id_int, "context": {"type": "ORDER", "id": order_id_int}}
                    create_resp = client.post(
                        create_url,
                        json=create_payload,
                        headers=self._get_headers(),
                        timeout=30.0,
                    )
                    create_resp.raise_for_status()
                    create_data = create_resp.json()
                    chat_id = (create_data.get("result") or {}).get("chatId")
                
                if not chat_id:
                    raise ValueError(f"Could not find chat for order {order_id}. Chat may need to be created first.")
                
                # Step 2: Send message to the chat
                # According to docs: POST /v2/businesses/{businessId}/chats/message with chatId query parameter
                return self.send_message_to_chat(int(chat_id), message_text)
                
        except httpx.HTTPError as e:
            error_msg = f"Failed to send order chat message for order {order_id}"
            if hasattr(e, 'response') and e.response:
                error_msg += f": {e.response.status_code} - {e.response.text}"
            raise Exception(error_msg)
    
    def download_media_file(self, url: str, save_path: Path) -> str:
        """Download a media file from URL and save it locally"""
        try:
            with httpx.Client() as client:
                response = client.get(url, timeout=60.0, follow_redirects=True)
                response.raise_for_status()
                
                # Ensure directory exists
                save_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Save file
                with open(save_path, "wb") as f:
                    f.write(response.content)
                
                # Return relative path
                return str(save_path.relative_to(Path("media")))
        except httpx.HTTPError as e:
            raise Exception(f"Failed to download media file: {str(e)}")
    
    def download_product_media(self, product_data: Dict, media_dir: Path) -> tuple[List[str], List[str]]:
        """Download all media files for a product from Yandex Market"""
        images = []
        videos = []
        
        # Get images from product data
        product_images = product_data.get("pictures", []) or product_data.get("images", [])
        for idx, img_url in enumerate(product_images):
            if not img_url:
                continue
            try:
                # Determine file extension from URL or content type
                parsed_url = urlparse(img_url)
                ext = Path(parsed_url.path).suffix or ".jpg"
                filename = f"product_{product_data.get('id', 'unknown')}_img_{idx}{ext}"
                save_path = media_dir / "images" / filename
                
                relative_path = self.download_media_file(img_url, save_path)
                images.append(relative_path)
            except Exception as e:
                print(f"Failed to download image {img_url}: {str(e)}")
                continue
        
        # Get videos from product data
        product_videos = product_data.get("videos", [])
        for idx, vid_url in enumerate(product_videos):
            if not vid_url:
                continue
            try:
                parsed_url = urlparse(vid_url)
                ext = Path(parsed_url.path).suffix or ".mp4"
                filename = f"product_{product_data.get('id', 'unknown')}_vid_{idx}{ext}"
                save_path = media_dir / "videos" / filename
                
                relative_path = self.download_media_file(vid_url, save_path)
                videos.append(relative_path)
            except Exception as e:
                print(f"Failed to download video {vid_url}: {str(e)}")
                continue
        
        return images, videos
    
    def list_campaigns(self) -> List[Dict]:
        """GET v2/campaigns — list stores (limit + page_token; no page/pageSize)."""
        from app.yandex_campaigns import fetch_campaigns_list

        return fetch_campaigns_list(
            self.api_token,
            base_url=self.base_url,
            business_id=self.business_id,
            limit=100,
        )

    def verify_api_access(self) -> Dict:
        """POST v2/auth/token — check token and return grant metadata."""
        url = f"{self.base_url}/v2/auth/token"
        response = self._make_request("POST", url, headers=self._get_headers(), timeout=30.0)
        try:
            return response.json()
        except Exception:
            return {"status": "ERROR", "http_status": response.status_code, "body": response.text}

    def get_partner_warehouses(self) -> List[Dict]:
        """POST v3/businesses/{businessId}/warehouses — partner warehouses (2026 API)."""
        url = f"{self.base_url}/v3/businesses/{self.business_id}/warehouses"
        response = self._make_request("POST", url, json={}, headers=self._get_headers(), timeout=30.0)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {}).get("warehouses", data.get("warehouses", []))

    def _default_partner_warehouse_id(self, warehouse_id: Optional[int] = None) -> int:
        if warehouse_id:
            return warehouse_id
        warehouses = self.get_partner_warehouses()
        if not warehouses:
            raise ValueError(
                "partnerWarehouseId is required: no warehouses returned from v3/businesses/warehouses"
            )
        wh = warehouses[0]
        wid = wh.get("id") or wh.get("warehouseId") or wh.get("partnerWarehouseId")
        if wid is None:
            raise ValueError("Could not determine partner warehouse id from Yandex API response")
        return int(wid)

    def update_product_stock(self, shop_sku: str, count: int, warehouse_id: Optional[int] = None) -> Dict:
        """POST v3/businesses/{businessId}/offers/stocks/update"""
        from datetime import datetime, timezone

        partner_wh = self._default_partner_warehouse_id(warehouse_id)
        url = f"{self.base_url}/v3/businesses/{self.business_id}/offers/stocks/update"
        payload = {
            "skuItems": [{
                "sku": shop_sku,
                "partnerWarehouseId": partner_wh,
                "count": count,
                "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }]
        }
        response = self._make_request(
            "POST", url, json=payload, headers=self._get_headers(), timeout=30.0
        )
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update product stock: {str(e)}") from e

    def update_bulk_stocks(self, stocks: List[Dict[str, int]]) -> Dict:
        """POST v3/businesses/{businessId}/offers/stocks/update (bulk)."""
        from datetime import datetime, timezone

        partner_wh = self._default_partner_warehouse_id(
            stocks[0].get("warehouse_id") if stocks else None
        )
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{self.base_url}/v3/businesses/{self.business_id}/offers/stocks/update"
        payload = {
            "skuItems": [
                {
                    "sku": stock["sku"],
                    "partnerWarehouseId": stock.get("warehouse_id") or partner_wh,
                    "count": stock["count"],
                    "updatedAt": updated_at,
                }
                for stock in stocks
            ]
        }
        response = self._make_request(
            "POST", url, json=payload, headers=self._get_headers(), timeout=30.0
        )
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update bulk stocks: {str(e)}") from e

    def get_product_stock(self, shop_sku: str, warehouse_id: Optional[int] = None) -> Dict:
        """POST v3/businesses/{businessId}/offers/stocks"""
        partner_wh = self._default_partner_warehouse_id(warehouse_id)
        url = f"{self.base_url}/v3/businesses/{self.business_id}/offers/stocks"
        payload = {
            "partnerWarehouseId": partner_wh,
            "offerIds": [shop_sku],
            "archived": False,
        }
        response = self._make_request(
            "POST", url, json=payload, headers=self._get_headers(), timeout=30.0
        )
        try:
            response.raise_for_status()
            return response.json().get("result", response.json())
        except httpx.HTTPError as e:
            raise Exception(f"Failed to get product stock: {str(e)}") from e
    
    # Price Management
    def update_product_price(self, shop_sku: str, price: float, old_price: Optional[float] = None) -> Dict:
        """
        Update product price on Yandex Market
        Can update price separately from other product data
        """
        url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-prices/updates"
        
        items = [{
            "offerId": shop_sku,
            "price": {
                "value": price,
                "currencyId": "RUR"
            }
        }]
        
        if old_price:
            items[0]["price"]["oldValue"] = old_price
        
        payload = {"offers": items}
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update product price: {str(e)}")
    
    def update_bulk_prices(self, prices: List[Dict[str, float]]) -> Dict:
        """
        Update prices for multiple products at once
        prices: List of dicts with 'sku', 'price', and optionally 'old_price' keys
        """
        url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-prices/updates"
        
        items = []
        for price_data in prices:
            item = {
                "offerId": price_data["sku"],
                "price": {
                    "value": price_data["price"],
                    "currencyId": "RUR"
                }
            }
            if "old_price" in price_data:
                item["price"]["oldValue"] = price_data["old_price"]
            items.append(item)
        
        payload = {"offers": items}
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update bulk prices: {str(e)}")
    
    # Product Visibility Management
    def update_product_availability(self, shop_sku: str, available: bool) -> Dict:
        """Show or hide offer on storefront (hidden-offers; availability on offers/update is deprecated)."""
        if not self.campaign_id:
            raise ValueError("campaign_id is required to change offer visibility")
        if available:
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/hidden-offers/delete"
            payload = {"hiddenOffers": [{"offerId": shop_sku}]}
        else:
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/hidden-offers"
            payload = {"hiddenOffers": [{"offerId": shop_sku}]}
        try:
            response = self._make_request(
                "POST", url, json=payload, headers=self._get_headers(), timeout=30.0
            )
            response.raise_for_status()
            if response.text:
                return response.json()
            return {"success": True}
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update product availability: {str(e)}")
    
    def update_bulk_availability(self, availabilities: List[Dict[str, bool]]) -> Dict:
        """
        Update availability for multiple products at once
        availabilities: List of dicts with 'sku' and 'available' keys
        """
        results = []
        errors = []
        
        for avail_data in availabilities:
            try:
                result = self.update_product_availability(avail_data["sku"], avail_data["available"])
                results.append(result)
            except Exception as e:
                errors.append(f"Failed to update {avail_data['sku']}: {str(e)}")
        
        return {
            "success": len(errors) == 0,
            "updated": len(results),
            "errors": errors
        }
    
    # Document Management (for product specifications, certificates, etc.)
    def upload_product_document(self, shop_sku: str, document_url: str, document_type: str = "SPECIFICATION") -> Dict:
        """
        Upload/attach a document to a product
        document_type: SPECIFICATION, CERTIFICATE, MANUAL, etc.
        Note: Document endpoints may not be available in Business API
        """
        if self.is_acma_token:
            # Campaign API: Use POST /v2/campaigns/*/offers/update or POST /v2/campaigns/*/offer-mapping-entries/updates
            # Based on endpoint list: POST /v2/campaigns/*/offers/update exists
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers/update"
        else:
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/update"
        
        payload = {
            "document": {
                "type": document_type,
                "url": document_url
            }
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to upload product document: {str(e)}")
    
    def get_product_documents(self, shop_sku: str) -> List[Dict]:
        """Get all documents attached to a product"""
        # Note: May need to use offer-mappings with specific SKU filter
        try:
            entries = self._query_offer_mapping_entries({"offerIds": [shop_sku]})
            documents: List[Dict] = []
            for entry in entries:
                offer = entry.get("offer") if isinstance(entry, dict) else {}
                if isinstance(offer, dict) and offer.get("documents"):
                    documents.extend(offer["documents"])
            return documents
        except httpx.HTTPError as e:
            raise Exception(f"Failed to get product documents: {str(e)}")
    
    def delete_product_document(self, shop_sku: str, document_id: str) -> Dict:
        """Delete a document from a product"""
        # Document deletion may not be available in Business API
        url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/update"
        payload = {
            "offerMappings": [{
                "offer": {"shopSku": shop_sku},
                "deleteDocuments": [document_id],
            }]
        }
        try:
            response = self._make_request(
                "POST", url, json=payload, headers=self._get_headers(), timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to delete product document: {str(e)}")
    
    def delete_product(self, shop_sku: str) -> Dict:
        """Delete a product from Yandex Market"""
        if self.is_acma_token:
            # Campaign API uses POST /offers/delete with offerIds array
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers/delete"
            payload = {"offerIds": [shop_sku]}
            try:
                response = self._make_request("POST", url, json=payload, headers=self._get_headers(), timeout=30.0)
                response.raise_for_status()
                # Delete endpoint may return 204 No Content
                if response.status_code == 204:
                    return {"success": True, "message": "Product deleted successfully"}
                return response.json()
            except httpx.HTTPError as e:
                raise Exception(f"Failed to delete product from Yandex: {str(e)}")
        else:
            # Business API uses POST with payload
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/delete"
            payload = {"offerIds": [shop_sku]}
            try:
                response = self._make_request("POST", url, json=payload, headers=self._get_headers(), timeout=30.0)
                response.raise_for_status()
                # Delete endpoint may return 204 No Content
                if response.status_code == 204:
                    return {"success": True, "message": "Product deleted successfully"}
                return response.json()
            except httpx.HTTPError as e:
                raise Exception(f"Failed to delete product from Yandex: {str(e)}")
    
    # Bulk Product Operations
    def create_bulk_products(self, products: List[models.Product]) -> Dict:
        """
        Create multiple products at once (bulk operation)
        More efficient than creating products one by one
        """
        if self.is_acma_token:
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers/update"
        else:
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/update"

        if self.is_acma_token:
            payload = {"offers": [self._build_offer_payload(product) for product in products]}
        else:
            payload = {
                "offerMappings": [
                    {"offer": self._build_offer_payload(product)} for product in products
                ]
            }

        try:
            response = self._make_request(
                "POST", url, json=payload, headers=self._get_headers(), timeout=60.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to create bulk products: {str(e)}")
    
    def update_bulk_products(self, products: List[models.Product]) -> Dict:
        """
        Update multiple products at once (bulk operation)
        """
        results = []
        errors = []
        
        for product in products:
            if not product.yandex_market_id:
                errors.append(f"Product {product.id} not synced with Yandex Market")
                continue
            
            try:
                result = self.update_product(product)
                results.append(result)
            except Exception as e:
                errors.append(f"Failed to update product {product.id}: {str(e)}")
        
        return {
            "success": len(errors) == 0,
            "updated": len(results),
            "errors": errors
        }
    
    # Helper method to build offer payload (extracted for reuse)
    def _build_offer_payload(self, product: models.Product) -> Dict:
        """Build offer payload from product model"""
        # Get images and videos from yandex_full_data if available
        images = []
        videos = []
        if product.yandex_full_data:
            images = product.yandex_full_data.get("pictures") or product.yandex_full_data.get("images") or []
            videos = product.yandex_full_data.get("videos") or []
            if not isinstance(images, list):
                images = []
            if not isinstance(videos, list):
                videos = []
        
        offer = {
            "shopSku": product.yandex_market_sku or f"SKU-{product.id}",
            "name": product.name,
            "description": product.description or "",
            "price": product.selling_price,
            "vat": "VAT_20",
            "availability": "ACTIVE" if product.is_active else "INACTIVE",
        }
        
        # For digital products, use DBS model
        if product.product_type == models.ProductType.DIGITAL:
            offer["type"] = "DIGITAL"
            offer["model"] = product.yandex_model or "DBS"
        else:
            offer["type"] = "PHYSICAL"
            if product.yandex_model:
                offer["model"] = product.yandex_model
        
        # Category information
        if product.yandex_category_id:
            offer["categoryId"] = product.yandex_category_id
        elif product.yandex_category_id:
            offer["marketCategoryId"] = product.yandex_category_id
        
        # Product parameters
        params = {}
        if product.yandex_brand:
            params["vendor"] = product.yandex_brand
        if product.yandex_platform:
            params["platform"] = product.yandex_platform
        if product.yandex_localization:
            params["localization"] = product.yandex_localization
        if product.yandex_publication_type:
            params["publicationType"] = product.yandex_publication_type
        if product.yandex_activation_territory:
            params["activationTerritory"] = product.yandex_activation_territory
        if product.yandex_edition:
            params["edition"] = product.yandex_edition
        if product.yandex_series:
            params["series"] = product.yandex_series
        if product.yandex_age_restriction:
            params["ageRestriction"] = product.yandex_age_restriction
        if product.yandex_activation_instructions is not None:
            params["hasActivationInstructions"] = product.yandex_activation_instructions
        
        if params:
            offer["params"] = params
        
        # Pricing with discount
        if product.original_price and product.original_price > product.selling_price:
            offer["oldPrice"] = product.original_price
        
        # Media
        if images:
            offer["pictures"] = images
        if videos:
            offer["videos"] = videos
        
        return offer
    
    # Get product by SKU with full details
    def get_product_by_sku(self, shop_sku: str) -> Optional[Dict]:
        """Get a specific product by SKU with all details"""
        try:
            if self.business_id:
                entries = self._query_offer_mapping_entries({"offerIds": [shop_sku]})
                return entries[0] if entries else None
            if self.campaign_id:
                offers = self._campaign_offer_rows([shop_sku])
                if offers:
                    return {"offer": offers[0]}
            return None
        except httpx.HTTPError as e:
            raise Exception(f"Failed to get product by SKU: {str(e)}")
    
    # Update only product specifications/parameters (without changing other fields)
    def update_product_specifications(self, shop_sku: str, specifications: Dict) -> Dict:
        """
        Update only product specifications/parameters
        specifications: Dict with parameter keys and values
        """
        # Business API uses offer-mappings/update
        if self.is_acma_token:
            # Campaign API: Use POST /v2/campaigns/*/offers/update or POST /v2/campaigns/*/offer-mapping-entries/updates
            # Based on endpoint list: POST /v2/campaigns/*/offers/update exists
            url = f"{self.base_url}/v2/campaigns/{self.campaign_id}/offers/update"
        else:
            url = f"{self.base_url}/v2/businesses/{self.business_id}/offer-mappings/update"
        
        if self.is_acma_token:
            payload = {"offers": [{"shopSku": shop_sku, "params": specifications}]}
        else:
            payload = {
                "offerMappings": [{
                    "offer": {"shopSku": shop_sku, "params": specifications},
                }]
            }

        try:
            response = self._make_request("POST", url, json=payload, headers=self._get_headers(), timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise Exception(f"Failed to update product specifications: {str(e)}")