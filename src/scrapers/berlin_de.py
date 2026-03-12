from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class BerlinDeScraper(BaseScraper):
    name = "berlin.de"

    URLS = [
        "https://www.berlin.de/en/events/",
        "https://www.berlin.de/events/",
    ]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        for url in self.URLS:
            events = self._scrape_page(url, start, end)
            all_events.extend(events)
        return all_events

    def _scrape_page(self, url: str, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(url)
        except Exception as e:
            logger.error(f"berlin.de fetch failed for {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD
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

        # Fallback: parse event listing HTML
        if not events:
            for card in soup.select(".event, .veranstaltung, article"):
                event = self._parse_card(card, start, end)
                if event:
                    events.append(event)

        return events

    def _parse_jsonld(self, data: dict, start: datetime, end: datetime) -> Event | None:
        if data.get("@type") not in ("Event", "SocialEvent", "BusinessEvent", "EducationEvent"):
            return None

        title = data.get("name", "")
        url = data.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://www.berlin.de{url}"

        try:
            dt = dateparser.parse(data.get("startDate", ""))
            if dt is None or dt < start or dt > end:
                return None
        except (ValueError, TypeError):
            return None

        location_data = data.get("location", {})
        if isinstance(location_data, dict):
            location = location_data.get("name", "")
            address = location_data.get("address", {})
            if isinstance(address, dict):
                street = address.get("streetAddress", "")
                city = address.get("addressLocality", "Berlin")
                parts = [p for p in [location, street, city] if p]
                location = ", ".join(parts)
        else:
            location = str(location_data) if location_data else "Berlin"

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

    def _parse_card(self, card, start: datetime, end: datetime) -> Event | None:
        link = card.find("a", href=True)
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://www.berlin.de{url}"

        title_el = card.find(["h2", "h3", "h4"]) or link
        title = title_el.get_text(strip=True)[:150]
        if not title:
            return None

        # Look for date in various formats
        date_el = card.find("time") or card.find(class_=lambda c: c and "date" in c.lower() if c else False)
        if date_el:
            dt_str = date_el.get("datetime") or date_el.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str, fuzzy=True)
                if dt and start <= dt <= end:
                    location = "Berlin"
                    loc_el = card.find(class_=lambda c: c and ("location" in c.lower() or "ort" in c.lower()) if c else False)
                    if loc_el:
                        location = loc_el.get_text(strip=True)

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
