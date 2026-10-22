"""Thin client for the Trading 212 Public API (v0).

Only Invest and Stocks ISA accounts are supported by the API. Sell orders are
sent as market orders with a negative quantity.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)


class T212Error(RuntimeError):
    pass


class Trading212Client:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str = "",
        dry_run: bool = True,
        session: requests.Session | None = None,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.session = session or requests.Session()
        if api_secret:
            token = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
            self.session.headers["Authorization"] = f"Basic {token}"
        else:
            # Legacy single-key auth.
            self.session.headers["Authorization"] = api_key
        self.session.headers["Content-Type"] = "application/json"

    # ------------------------------------------------------------------ http
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(1, self.max_retries + 1):
            resp = self.session.request(method, url, timeout=15, **kwargs)
            if resp.status_code == 429:
                # Rate limited: honour the reset header if present, else back off.
                reset = resp.headers.get("x-ratelimit-reset")
                wait = max(1.0, float(reset) - time.time()) if reset else 2.0 * attempt
                log.warning("Rate limited on %s %s, sleeping %.1fs", method, path, wait)
                time.sleep(min(wait, 60))
                continue
            if resp.status_code >= 500 and attempt < self.max_retries:
                time.sleep(2.0 * attempt)
                continue
            if not resp.ok:
                raise T212Error(f"{method} {path} -> {resp.status_code}: {resp.text}")
            return resp.json() if resp.content else None
        raise T212Error(f"{method} {path} failed after {self.max_retries} retries")

    # --------------------------------------------------------------- account
    def account_cash(self) -> dict:
        return self._request("GET", "/equity/account/cash")

    def account_info(self) -> dict:
        return self._request("GET", "/equity/account/info")

    def positions(self) -> list[dict]:
        return self._request("GET", "/equity/portfolio")

    def instruments(self) -> list[dict]:
        return self._request("GET", "/equity/metadata/instruments")

    def open_orders(self) -> list[dict]:
        return self._request("GET", "/equity/orders")

    # ---------------------------------------------------------------- orders
    def market_order(self, ticker: str, quantity: float) -> dict:
        """Positive quantity buys, negative quantity sells."""
        body = {"ticker": ticker, "quantity": round(quantity, 6)}
        if self.dry_run:
            log.info("[DRY RUN] market order %s", body)
            return {"id": None, "dryRun": True, **body}
        return self._request("POST", "/equity/orders/market", json=body)

    def cancel_order(self, order_id: int) -> None:
        if self.dry_run:
            log.info("[DRY RUN] cancel order %s", order_id)
            return
        self._request("DELETE", f"/equity/orders/{order_id}")
