from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class DevEventsScraper(BaseScraper):
    name = "dev-events"

    BASE_URL = "https://dev.events"
    SEARCH_URL = "https://dev.events/?geo=Berlin"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()

        # Fetch first few pages
        for page in range(1, 4):
            events = self._scrape_page(page)
            if not events:
                break
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)

        return all_events

    def _scrape_page(self, page: int) -> list[Event]:
        url = self.SEARCH_URL if page == 1 else f"{self.SEARCH_URL}&page={page}"
        try:
            # Add referer to look like navigation from the site
            resp = self._get(url, headers={
                "Referer": "https://dev.events/",
            })
        except Exception as e:
            logger.warning(f"dev.events fetch failed (page {page}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Primary: Parse JSON-LD EducationEvent blocks
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "ItemList":
                        for el in item.get("itemListElement", []):
                            event = self._parse_jsonld(el)
                            if event:
                                events.append(event)
                    else:
                        event = self._parse_jsonld(item)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # Fallback: parse classless HTML structure
        # Pattern: <a href="/ical/...">DATE</a> <a href="/conferences/...">TITLE</a>
        if not events:
            events = self._parse_html(soup)

        return events

    def _parse_jsonld(self, data: dict) -> Event | None:
        etype = data.get("@type", "")
        if not isinstance(etype, str) or "Event" not in etype:
            return None

        title = data.get("name", "")
        url = data.get("url", "")
        if not title:
            return None

        try:
            dt = dateparser.parse(data.get("startDate", ""))
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        location_data = data.get("location", {})
        location = "Berlin"
        if isinstance(location_data, dict):
            loc_name = location_data.get("name", "")
            address = location_data.get("address", {})
            if isinstance(address, dict):
                city = address.get("addressLocality", "")
                parts = [p for p in [loc_name, city] if p]
                location = ", ".join(parts) if parts else "Berlin"
            elif loc_name:
                location = loc_name
        elif isinstance(location_data, str) and location_data:
            location = location_data

        organizer_data = data.get("organizer") or data.get("performer", {})
        organizer = organizer_data.get("name", "") if isinstance(organizer_data, dict) else ""

        # Check attendance mode
        attendance = data.get("eventAttendanceMode", "")
        if "Online" in str(attendance) and "Mixed" not in str(attendance):
            return None  # Skip online-only events

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            organizer=organizer,
            summary=data.get("description", "")[:300],
            price="Unknown",
        )

    def _parse_html(self, soup: BeautifulSoup) -> list[Event]:
        """Parse classless HTML: <a href="/ical/...">date</a> ... <a href="/conferences/...">title</a>"""
        events = []

        for ical_link in soup.find_all("a", href=lambda h: h and "/ical/" in h):
            date_text = ical_link.get_text(strip=True)
            try:
                dt = dateparser.parse(date_text, fuzzy=True)
                if not dt:
                    continue
            except (ValueError, TypeError):
                continue

            # Find the conference link nearby (next sibling <a>)
            parent = ical_link.parent
            if not parent:
                continue

            conf_link = parent.find("a", href=lambda h: h and "/conferences/" in h)
            if not conf_link:
                continue

            title = conf_link.get_text(strip=True)[:150]
            if not title:
                continue

            url = conf_link.get("href", "")
            if not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            events.append(Event(
                title=title,
                date=dt,
                url=url,
                source=self.name,
                location="Berlin",
                price="Unknown",
            ))

        return events
