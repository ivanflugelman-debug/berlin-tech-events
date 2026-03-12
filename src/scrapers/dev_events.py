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

        # Fetch first few pages (htmx pagination uses ?page=N)
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
            resp = self._get(url)
        except Exception as e:
            logger.error(f"dev.events fetch failed (page {page}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD (EducationEvent blocks)
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

        # HTML fallback
        if not events:
            for card in soup.select("article, .event-card, [class*='event'], .card"):
                event = self._parse_card(card)
                if event:
                    events.append(event)

        return events

    def _parse_jsonld(self, data: dict) -> Event | None:
        event_types = ("Event", "SocialEvent", "BusinessEvent", "EducationEvent")
        if data.get("@type") not in event_types:
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

        organizer_data = data.get("organizer", {})
        organizer = organizer_data.get("name", "") if isinstance(organizer_data, dict) else ""

        offers = data.get("offers", {})
        price = "Unknown"
        if isinstance(offers, dict):
            price_val = offers.get("price", "")
            if price_val in (0, "0", "0.00"):
                price = "Free"
            elif price_val:
                price = "Paid"

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

    def _parse_card(self, card) -> Event | None:
        link = card.find("a", href=True)
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

        title_el = card.find(["h2", "h3", "h4"]) or link
        title = title_el.get_text(strip=True)[:150]
        if not title or len(title) < 4:
            return None

        time_el = card.find("time")
        if time_el:
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str, fuzzy=True)
                if dt:
                    return Event(
                        title=title,
                        date=dt,
                        url=url,
                        source=self.name,
                        location="Berlin",
                        price="Unknown",
                    )
            except (ValueError, TypeError):
                pass

        return None
