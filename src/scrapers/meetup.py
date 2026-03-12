from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Berlin coordinates
BERLIN_LAT = 52.52
BERLIN_LON = 13.405


class MeetupScraper(BaseScraper):
    name = "meetup"

    SEARCH_KEYWORDS = ["tech", "AI", "startup", "developer", "data", "machine learning",
                        "software", "coding", "hackathon", "cloud", "devops"]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()
        for keyword in self.SEARCH_KEYWORDS:
            events = self._search(keyword, start, end)
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)
        return all_events

    def _search(self, keyword: str, start: datetime, end: datetime) -> list[Event]:
        """Search Meetup events using their search page with lat/lon parameters."""
        params = {
            "keywords": keyword,
            "location": "Berlin, Germany",
            "source": "EVENTS",
            "lat": str(BERLIN_LAT),
            "lon": str(BERLIN_LON),
            "radius": "25",  # 25 miles around Berlin
        }
        try:
            resp = self._get("https://www.meetup.com/find/", params=params)
        except Exception as e:
            logger.error(f"Meetup search '{keyword}' failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Parse JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Event", "SocialEvent", "BusinessEvent"):
                        event = self._parse_jsonld(item)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # Also try to parse the __NEXT_DATA__ for React-rendered content
        if not events:
            events = self._parse_next_data(soup)

        logger.debug(f"Meetup '{keyword}': found {len(events)} events")
        return events

    def _parse_next_data(self, soup: BeautifulSoup) -> list[Event]:
        """Parse Meetup's Next.js data."""
        events = []
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return events

        try:
            data = json.loads(script.string)
            props = data.get("props", {}).get("pageProps", {})

            # Navigate to events in the data structure
            for key in ("results", "events", "searchResults"):
                results = props.get(key)
                if results:
                    items = results if isinstance(results, list) else []
                    if isinstance(results, dict):
                        items = results.get("edges", results.get("items", results.get("events", [])))
                    for item in items:
                        node = item.get("node", item) if isinstance(item, dict) else item
                        event = self._parse_next_event(node)
                        if event:
                            events.append(event)
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"Meetup __NEXT_DATA__ parse error: {e}")

        return events

    def _parse_next_event(self, node: dict) -> Event | None:
        if not isinstance(node, dict):
            return None

        title = node.get("title", "") or node.get("name", "")
        url = node.get("eventUrl", "") or node.get("link", "")
        if not title or not url:
            return None

        dt_str = node.get("dateTime", "") or node.get("startDate", "")
        if not dt_str:
            return None

        try:
            dt = dateparser.parse(str(dt_str))
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        venue = node.get("venue", {}) or {}
        parts = [p for p in [venue.get("name", ""), venue.get("city", "")] if p]
        location = ", ".join(parts)

        group = node.get("group", {}) or {}
        organizer = group.get("name", "")

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            organizer=organizer,
            summary=(node.get("description", "") or "")[:300],
            price="Unknown",
        )

    def _parse_jsonld(self, data: dict) -> Event | None:
        title = data.get("name", "")
        url = data.get("url", "")

        try:
            dt = dateparser.parse(data.get("startDate", ""))
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        location_data = data.get("location", {})
        if isinstance(location_data, dict):
            location = location_data.get("name", "")
            address = location_data.get("address", {})
            if isinstance(address, dict):
                city = address.get("addressLocality", "")
                if city:
                    location = f"{location}, {city}" if location else city
        else:
            location = str(location_data)

        organizer_data = data.get("organizer", {})
        organizer = organizer_data.get("name", "") if isinstance(organizer_data, dict) else ""

        offers = data.get("offers", {})
        if isinstance(offers, dict):
            price_val = offers.get("price", "")
            if price_val in (0, "0", "0.00"):
                price = "Free"
            elif price_val:
                price = "Paid"
            else:
                price = "Unknown"
        else:
            price = "Unknown"

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            organizer=organizer,
            summary=data.get("description", "")[:300],
            price=price,
        )
