"""Rate-limited, disk-cached HTTP client for SEC EDGAR.

SEC's fair-use policy requires (a) a descriptive User-Agent identifying the
requester and (b) staying under ~10 requests/second. We cap at 8/s with a
simple token-spacing limiter and back off exponentially on 429/503.

All responses are cached to disk via requests-cache (SQLite backend) so
development re-runs never re-hit EDGAR. The rate limiter is only applied to
requests that actually go over the wire (cache hits are free).
"""

from __future__ import annotations

import logging
import os
import threading
import time

import requests
import requests_cache

log = logging.getLogger(__name__)

SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "fundamental-screener research REPLACE_ME_contact@example.com"
)
MAX_REQUESTS_PER_SEC = 8
BACKOFF_BASE = 2.0
MAX_RETRIES = 5

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"


class EdgarClient:
    """Thin wrapper enforcing SEC etiquette on top of a cached session."""

    def __init__(
        self,
        cache_path: str = "data/http_cache",
        cache_ttl: int = 30 * 86400,
        user_agent: str = SEC_USER_AGENT,
    ):
        if "REPLACE_ME" in user_agent:
            log.warning(
                "SEC_USER_AGENT still contains the placeholder email — "
                "replace it with your real contact address (config.py or env var)."
            )
        self.session = requests_cache.CachedSession(
            cache_path, backend="sqlite", expire_after=cache_ttl
        )
        self.session.headers.update({"User-Agent": user_agent})
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._min_interval = 1.0 / MAX_REQUESTS_PER_SEC

    def _throttle(self) -> None:
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def get_json(self, url: str) -> dict | None:
        """GET a JSON document with throttling + exponential backoff.

        Returns None (with a logged warning) on persistent failure or 404,
        so callers can skip a company rather than crash the whole ingest.
        """
        for attempt in range(MAX_RETRIES):
            # Peek the cache first so cached hits skip the throttle entirely.
            if not self.session.cache.contains(url=url):
                self._throttle()
            try:
                resp = self.session.get(url, timeout=60)
            except requests.RequestException as exc:
                log.warning("Request error for %s (attempt %d): %s", url, attempt + 1, exc)
                time.sleep(BACKOFF_BASE * 2**attempt)
                continue
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    log.warning("Non-JSON response for %s", url)
                    return None
            if resp.status_code == 404:
                log.info("404 for %s — no companyfacts available", url)
                return None
            if resp.status_code in (429, 503):
                sleep_s = BACKOFF_BASE * 2**attempt
                log.warning("HTTP %d for %s — backing off %.1fs", resp.status_code, url, sleep_s)
                time.sleep(sleep_s)
                continue
            log.warning("HTTP %d for %s — giving up", resp.status_code, url)
            return None
        log.warning("Exhausted retries for %s", url)
        return None

    def get_ticker_cik_map(self) -> dict[str, str]:
        """Return {TICKER: zero-padded CIK} from SEC's official mapping file."""
        data = self.get_json(COMPANY_TICKERS_URL)
        if data is None:
            raise RuntimeError("Could not fetch SEC company_tickers.json")
        return {
            row["ticker"].upper(): f"{int(row['cik_str']):010d}"
            for row in data.values()
        }

    def get_companyfacts(self, cik: str) -> dict | None:
        return self.get_json(COMPANYFACTS_URL.format(cik=cik))
