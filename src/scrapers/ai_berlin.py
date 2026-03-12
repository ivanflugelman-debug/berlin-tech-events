from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class AiBerlinScraper(BaseScraper):
    name = "ai-berlin"

    BASE_URL = "https://ai-berlin.com"
    EVENTS_URL = "https://ai-berlin.com/events"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(self.EVENTS_URL)
        except Exception as e:
            logger.error(f"ai-berlin.com fetch failed: {e}")
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

        # Fallback: parse HTML
        if not events:
            for card in soup.select(".event-card, .event-item, article, .events-list li, [class*='event']"):
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
            url = f"{self.BASE_URL}{url}"

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
                city = address.get("addressLocality", "")
                if city:
                    location = f"{location}, {city}" if location else city
        else:
            location = str(location_data) if location_data else "Berlin"

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location if location else "Berlin",
            summary=data.get("description", "")[:300],
            price="Unknown",
        )

    def _parse_card(self, card, start: datetime, end: datetime) -> Event | None:
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

        # Look for date
        date_el = card.find("time") or card.find(class_=lambda c: c and "date" in c.lower() if c else False)
        if date_el:
            dt_str = date_el.get("datetime") or date_el.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str, fuzzy=True)
                if dt and start <= dt <= end:
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
