from __future__ import annotations
import logging
from datetime import datetime

from src.config import SERPAPI_KEY, SEARCH_QUERIES
from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SerpApiScraper(BaseScraper):
    name = "serpapi"

    def __init__(self):
        super().__init__()
        self.api_key = SERPAPI_KEY

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        if not self.api_key:
            logger.warning("SERPAPI_KEY not set, skipping SerpAPI scraper")
            return []

        all_events = []
        for query in SEARCH_QUERIES:
            events = self._search_events(query, start, end)
            all_events.extend(events)
        return all_events

    def _search_events(self, query: str, start: datetime, end: datetime) -> list[Event]:
        """Search Google Events via SerpAPI for a single query."""
        params = {
            "engine": "google_events",
            "q": query,
            "api_key": self.api_key,
            "hl": "en",
            "gl": "de",
        }

        try:
            resp = self._get("https://serpapi.com/search", params=params)
            data = resp.json()
        except Exception as e:
            logger.error(f"SerpAPI query '{query}' failed: {e}")
            return []

        events = []
        for item in data.get("events_results", []):
            event = self._parse_event(item, start, end)
            if event:
                events.append(event)
        return events

    def _parse_event(self, item: dict, start: datetime, end: datetime) -> Event | None:
        """Parse a single event from SerpAPI response."""
        from dateutil import parser as dateparser

        title = item.get("title", "")
        link = item.get("link", "")

        # Parse date
        date_info = item.get("date", {})
        when = date_info.get("start_date") or date_info.get("when", "")
        if not when:
            return None

        try:
            dt = dateparser.parse(str(when), fuzzy=True)
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        # Check date window
        if dt < start or dt > end:
            return None

        # Location
        address_parts = item.get("address", [])
        if isinstance(address_parts, list):
            location = ", ".join(address_parts)
        else:
            location = str(address_parts)

        venue = item.get("venue", {})
        if isinstance(venue, dict):
            venue_name = venue.get("name", "")
        else:
            venue_name = str(venue) if venue else ""

        if venue_name and venue_name not in location:
            location = f"{venue_name}, {location}" if location else venue_name

        # Determine price
        ticket_info = item.get("ticket_info", {})
        if isinstance(ticket_info, dict):
            price_str = ticket_info.get("price", "")
        elif isinstance(ticket_info, list) and ticket_info:
            price_str = str(ticket_info[0])
        else:
            price_str = ""

        if price_str:
            price_lower = str(price_str).lower()
            if "free" in price_lower or price_lower == "0":
                price = "Free"
            else:
                price = "Paid"
        else:
            price = "Unknown"

        summary = item.get("description", "")

        return Event(
            title=title,
            date=dt,
            url=link,
            source=self.name,
            location=location,
            organizer=venue_name,
            summary=summary[:300] if summary else "",
            price=price,
        )
