from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class LumaScraper(BaseScraper):
    name = "luma"

    DISCOVER_URL = "https://lu.ma/berlin"
    SEARCH_URLS = [
        "https://lu.ma/berlin",
        "https://lu.ma/discover?loc=Berlin",
    ]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()

        for url in self.SEARCH_URLS:
            events = self._scrape_page(url, start, end)
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)

        return all_events

    def _scrape_page(self, url: str, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(url)
        except Exception as e:
            logger.error(f"Lu.ma fetch failed for {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Lu.ma uses Next.js — look for __NEXT_DATA__
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                events = self._parse_next_data(data, start, end)
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Lu.ma __NEXT_DATA__ parse error: {e}")

        # Fallback: try JSON-LD
        if not events:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        event = self._parse_jsonld(item, start, end)
                        if event:
                            events.append(event)
                except (json.JSONDecodeError, Exception):
                    continue

        # Fallback: parse links to event pages
        if not events:
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/event/" in href or (href.startswith("/") and len(href) > 5 and not href.startswith("/berlin")):
                    event_url = href if href.startswith("http") else f"https://lu.ma{href}"
                    title = link.get_text(strip=True)
                    if title and len(title) > 3:
                        events.append(Event(
                            title=title[:150],
                            date=start,  # placeholder — will be filtered later
                            url=event_url,
                            source=self.name,
                            price="Unknown",
                        ))

        return events

    def _parse_next_data(self, data: dict, start: datetime, end: datetime) -> list[Event]:
        """Extract events from Next.js page data."""
        events = []
        props = data.get("props", {}).get("pageProps", {})

        # Try various keys where events might live
        event_lists = []
        for key in ("events", "initialData", "data"):
            val = props.get(key)
            if isinstance(val, list):
                event_lists.extend(val)
            elif isinstance(val, dict):
                for subkey in ("events", "featured_items", "items"):
                    subval = val.get(subkey)
                    if isinstance(subval, list):
                        event_lists.extend(subval)

        for item in event_lists:
            event = self._parse_luma_event(item, start, end)
            if event:
                events.append(event)

        return events

    def _parse_luma_event(self, item: dict, start: datetime, end: datetime) -> Event | None:
        """Parse a single event from Lu.ma's data format."""
        # Lu.ma nests event data in different structures
        event_data = item.get("event", item)

        title = event_data.get("name", "") or event_data.get("title", "")
        if not title:
            return None

        start_at = event_data.get("start_at") or event_data.get("startDate") or event_data.get("start_time")
        if not start_at:
            return None

        try:
            dt = dateparser.parse(str(start_at))
            if dt is None or dt < start or dt > end:
                return None
        except (ValueError, TypeError):
            return None

        url = event_data.get("url", "")
        if not url:
            slug = event_data.get("slug") or event_data.get("api_id")
            if slug:
                url = f"https://lu.ma/{slug}"

        location = event_data.get("geo_address_info", {})
        if isinstance(location, dict):
            location = location.get("full_address") or location.get("city", "")
        else:
            location = str(location) if location else ""

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            summary=event_data.get("description", "")[:300] if event_data.get("description") else "",
            price="Unknown",
        )

    def _parse_jsonld(self, data: dict, start: datetime, end: datetime) -> Event | None:
        if data.get("@type") not in ("Event", "SocialEvent", "BusinessEvent"):
            return None

        title = data.get("name", "")
        url = data.get("url", "")

        try:
            dt = dateparser.parse(data.get("startDate", ""))
            if dt is None or dt < start or dt > end:
                return None
        except (ValueError, TypeError):
            return None

        location_data = data.get("location", {})
        location = ""
        if isinstance(location_data, dict):
            location = location_data.get("name", "")

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            summary=data.get("description", "")[:300],
            price="Unknown",
        )
