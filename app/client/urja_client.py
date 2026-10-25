"""Upstream HTTP client for communicating with the Urja Meter Ops legacy portal."""

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.client.session import SessionManager
from app.config import settings

logger = logging.getLogger(__name__)


class UrjaClient:
    """Async client providing typed, authenticated access to Urja Meter Ops endpoints.

    Handles:
    - Automatic session authentication and retry on 401 Unauthorized.
    - Dynamic HMAC-SHA256 signature generation for /portal/export bulk API.
    - SvelteKit devalue / __data.json response parsing for SSR detail views.
    - Query parameter mapping for energy time-series date filters.
    """

    def __init__(
        self,
        portal_url: Optional[str] = None,
        session_manager: Optional[SessionManager] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.portal_url = (portal_url or settings.urja_portal_url).rstrip("/")
        self.session_manager = session_manager or SessionManager(portal_url=self.portal_url)
        self._external_client = client
        self._client: Optional[httpx.AsyncClient] = client

    async def get_client(self) -> httpx.AsyncClient:
        """Get or initialize the underlying httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=settings.request_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "FlockEnergy-API-Service/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close client sessions."""
        if self._client and not self._client.is_closed and self._client != self._external_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Any] = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """Execute an authenticated request with automatic 401 re-auth retry."""
        client = await self.get_client()
        cookie_header = await self.session_manager.get_cookie_header(client)

        req_headers = {"Cookie": cookie_header}
        if headers:
            req_headers.update(headers)

        url = f"{self.portal_url}{path}"
        try:
            resp = await client.request(
                method,
                url,
                params=params,
                headers=req_headers,
                data=data,
                json=json_data,
            )
        except httpx.RequestError as exc:
            logger.error(f"Network error requesting {url}: {exc}")
            raise RuntimeError(f"Connection error to Urja portal: {exc}") from exc

        # If token was rejected upstream, invalidate, re-authenticate and retry once
        if resp.status_code == 401 and retry_on_401:
            logger.warning(f"Received 401 on {path}. Refreshing session and retrying...")
            self.session_manager.invalidate()
            new_cookie = await self.session_manager.get_cookie_header(client, force_refresh=True)
            req_headers["Cookie"] = new_cookie
            resp = await client.request(
                method,
                url,
                params=params,
                headers=req_headers,
                data=data,
                json=json_data,
            )

        return resp

    # -------------------------------------------------------------------------
    # Keys & HMAC Signing
    # -------------------------------------------------------------------------

    async def get_signing_secret(self) -> str:
        """Fetch current HMAC signing secret from /portal/keys."""
        resp = await self._request("GET", "/portal/keys")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch signing secret (status {resp.status_code}): {resp.text}")
        payload = resp.json()
        secret = payload.get("data", {}).get("signingSecret")
        if not secret:
            raise ValueError(f"No signingSecret in /portal/keys response: {payload}")
        return secret

    def sign_request(self, method: str, path: str, query_string: str, secret: str) -> Tuple[str, str]:
        """Compute timestamp and HMAC-SHA256 signature for signed endpoints.

        Format: METHOD\nPATH\nQUERYSTRING\nTIMESTAMP
        Tolerance window: 300 seconds (5 minutes)
        """
        timestamp = str(int(time.time()))
        payload = f"{method}\n{path}\n{query_string}\n{timestamp}".encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return timestamp, signature

    # -------------------------------------------------------------------------
    # Bulk Export (High-Performance Path)
    # -------------------------------------------------------------------------

    async def export_all_meters(self, page: int = 1) -> List[Dict[str, Any]]:
        """Fetch bulk meters export via HMAC-signed /portal/export endpoint.

        Returns complete list of 403 meters with rich hierarchy and geo data.
        """
        secret = await self.get_signing_secret()
        qs = f"page={page}"
        path = "/portal/export"
        timestamp, signature = self.sign_request("GET", path, qs, secret)

        headers = {
            "x-timestamp": timestamp,
            "x-signature": signature,
        }
        resp = await self._request("GET", f"{path}?{qs}", headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Bulk export failed (status {resp.status_code}): {resp.text}")

        data = resp.json()
        return data.get("data", [])

    # -------------------------------------------------------------------------
    # Meters Search & Detail
    # -------------------------------------------------------------------------

    async def search_meters(self, query: str = "", page: int = 1) -> Dict[str, Any]:
        """Query portal's native meter search endpoint."""
        params = {"q": query, "page": page}
        resp = await self._request("GET", "/portal/meters/search", params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"Search failed (status {resp.status_code}): {resp.text}")
        return resp.json()

    async def get_meter_geo(self, meter_id: str) -> Optional[Dict[str, float]]:
        """Fetch latitude and longitude for a meter from /portal/meters/{id}/geo."""
        resp = await self._request("GET", f"/portal/meters/{meter_id}/geo")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch geo for {meter_id} (status {resp.status_code})")
        data = resp.json().get("data", {})
        try:
            return {
                "latitude": float(data["latitude"]),
                "longitude": float(data["longitude"]),
            }
        except (KeyError, ValueError, TypeError):
            return None

    async def get_meter_energy(
        self,
        meter_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch time-series energy readings for a meter.

        Supports date filtering via 'from' and 'to' query parameters.
        Format: YYYY-MM-DD or DD/MM/YYYY.
        """
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = await self._request("GET", f"/portal/meters/{meter_id}/energy", params=params)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch energy for {meter_id} (status {resp.status_code}): {resp.text}")
        return resp.json().get("data", [])

    async def get_meter_detail_ssr(self, meter_id: str) -> Optional[Dict[str, Any]]:
        """Fetch server-rendered meter detail from /meters/{id}/__data.json.

        Parses SvelteKit devalue data to extract nameplate and hierarchy.
        """
        resp = await self._request("GET", f"/meters/{meter_id}/__data.json")
        if resp.status_code != 200:
            return None
        try:
            payload = resp.json()
            nodes = payload.get("nodes", [])
            for node in nodes:
                if not node or not isinstance(node, dict):
                    continue
                # Check for error node
                if node.get("type") == "error":
                    return None
                data = node.get("data")
                if isinstance(data, list) and len(data) > 0:
                    # SvelteKit flattened array
                    return self._parse_sveltekit_data(data)
        except Exception as exc:
            logger.warning(f"Error parsing SvelteKit __data.json for {meter_id}: {exc}")
        return None

    def _parse_sveltekit_data(self, data_list: List[Any]) -> Dict[str, Any]:
        """Reconstruct structured meter object from SvelteKit flattened references."""
        # data_list starts with index map or root object
        # Find dictionary with meterId or detail
        result = {}
        for item in data_list:
            if isinstance(item, dict):
                if "classData" in item:
                    # v2 meter format: classData points to a JSON string in data_list
                    cd_ref = item["classData"]
                    if isinstance(cd_ref, int) and cd_ref < len(data_list):
                        raw_json = data_list[cd_ref]
                        try:
                            parsed = json.loads(raw_json)
                            result["class_data"] = parsed.get("installed_meter", {})
                        except Exception:
                            pass
                elif "parameterName" in item and "parameterValue" in item:
                    pn_ref = item["parameterName"]
                    pv_ref = item["parameterValue"]
                    name = data_list[pn_ref] if isinstance(pn_ref, int) and pn_ref < len(data_list) else str(pn_ref)
                    val = data_list[pv_ref] if isinstance(pv_ref, int) and pv_ref < len(data_list) else str(pv_ref)
                    result.setdefault("parameters", []).append({"name": str(name), "value": str(val)})
        return result

    # -------------------------------------------------------------------------
    # Transformers
    # -------------------------------------------------------------------------

    async def get_transformers_page(self, page: int = 1) -> Dict[str, Any]:
        """Fetch paginated DTs from /portal/dts?page={page}."""
        resp = await self._request("GET", "/portal/dts", params={"page": page})
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch DTs (status {resp.status_code}): {resp.text}")
        return resp.json()

    async def get_all_transformers(self) -> List[Dict[str, Any]]:
        """Crawl all pages of transformers from /portal/dts."""
        page = 1
        all_dts: List[Dict[str, Any]] = []
        while True:
            res = await self.get_transformers_page(page=page)
            data = res.get("data", [])
            total = res.get("total", 0)
            all_dts.extend(data)
            if len(all_dts) >= total or not data:
                break
            page += 1
        return all_dts
