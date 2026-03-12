from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from datetime import datetime

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Event

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all event scrapers."""

    name: str = "base"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _get(self, url: str, params: dict = None, **kwargs) -> requests.Response:
        """HTTP GET with retry and backoff."""
        kwargs.setdefault("timeout", 30)
        resp = self.session.get(url, params=params, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        """Scrape events within the given date window."""
        ...

    def safe_scrape(self, start: datetime, end: datetime) -> list[Event]:
        """Scrape with error handling — never crashes the pipeline."""
        try:
            events = self.scrape(start, end)
            logger.info(f"[{self.name}] Found {len(events)} events")
            return events
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}", exc_info=True)
            return []
