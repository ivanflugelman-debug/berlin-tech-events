from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class VisitBerlinScraper(BaseScraper):
    name = "visitberlin"

    BASE_URL = "https://www.visitberlin.de"
    EVENTS_URL = "https://www.visitberlin.de/en/event-calendar-berlin"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()

        # Scrape first 3 pages
        for page in range(3):
            url = self.EVENTS_URL if page == 0 else f"{self.EVENTS_URL}?page={page}"
            events = self._scrape_page(url)
            if not events:
                break
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)

        return all_events

    def _scrape_page(self, url: str) -> list[Event]:
        try:
            resp = self._get(url)
        except Exception as e:
            logger.error(f"visitBerlin fetch failed for {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD first
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

        # HTML fallback — parse event cards
        if not events:
            for card in soup.select("article, .teaser, .event-teaser, .views-row, [class*='event']"):
                event = self._parse_card(card)
                if event:
                    events.append(event)

        return events

    def _parse_jsonld(self, data: dict) -> Event | None:
        event_types = ("Event", "SocialEvent", "BusinessEvent", "EducationEvent", "Festival")
        if data.get("@type") not in event_types:
            return None

        title = data.get("name", "")
        url = data.get("url", "")
        if url and not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"

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
                street = address.get("streetAddress", "")
                city = address.get("addressLocality", "Berlin")
                parts = [p for p in [loc_name, street, city] if p]
                location = ", ".join(parts) if parts else "Berlin"
            elif loc_name:
                location = loc_name

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

        # Try <time> tag or date class
        time_el = card.find("time")
        date_el = card.find(class_=lambda c: c and "date" in c.lower() if c else False) if not time_el else None

        dt_source = time_el or date_el
        if dt_source:
            dt_str = dt_source.get("datetime", "") if time_el else ""
            if not dt_str:
                dt_str = dt_source.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str, fuzzy=True)
                if dt:
                    location = "Berlin"
                    loc_el = card.find(class_=lambda c: c and ("location" in c.lower() or "venue" in c.lower()) if c else False)
                    if loc_el:
                        location = loc_el.get_text(strip=True) or "Berlin"

                    return Event(
                        title=title,
                        date=dt,
                        url=url,
                        source=self.name,
                        location=location,
                        price="Unknown",
                    )
            except (ValueError, TypeError):
                pass

        return None
