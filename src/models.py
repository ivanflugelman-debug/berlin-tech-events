from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScrapeResult:
    """Per-source scraping statistics."""
    source: str
    raw_count: int = 0
    duration: float = 0.0
    error: str = ""


@dataclass
class Event:
    title: str
    date: datetime
    url: str
    source: str  # which scraper found it
    location: str = ""
    organizer: str = ""
    summary: str = ""
    event_type: str = ""  # e.g. "Meetup", "Conference", "Workshop", "Hackathon"
    price: str = "Unknown"  # "Free", "Paid", or "Unknown"
    end_date: Optional[datetime] = None
    normalized_url: str = ""  # for dedup

    def __post_init__(self):
        # Normalize timezone-aware dates to naive (UTC) for consistent comparison
        if self.date and self.date.tzinfo is not None:
            self.date = self.date.replace(tzinfo=None)
        if self.end_date and self.end_date.tzinfo is not None:
            self.end_date = self.end_date.replace(tzinfo=None)
        if not self.normalized_url:
            self.normalized_url = self._normalize_url(self.url)

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip UTM/tracking params for dedup comparison."""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(url)
        params = {k: v for k, v in parse_qs(parsed.query).items()
                  if not k.startswith(('utm_', 'ref', 'fbclid', 'gclid', 'mc_'))}
        clean_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=clean_query, fragment=''))
