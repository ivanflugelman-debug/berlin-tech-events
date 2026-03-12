from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class IhkBerlinScraper(BaseScraper):
    name = "ihk-berlin"

    EVENTS_URL = "https://www.ihk.de/berlin/veranstaltungen"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(self.EVENTS_URL)
        except Exception as e:
            logger.error(f"IHK Berlin fetch failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    event = self._parse_jsonld(item)
                    if event:
                        events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # HTML fallback: teaser cards
        if not events:
            for card in soup.select("article, .teaser, .event-teaser, .veranstaltung, [class*='event'], [class*='teaser']"):
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
        if url and not url.startswith("http"):
            url = f"https://www.ihk.de{url}"

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
                city = address.get("addressLocality", "Berlin")
                parts = [p for p in [loc_name, city] if p]
                location = ", ".join(parts) if parts else "Berlin"
            elif loc_name:
                location = loc_name

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            summary=data.get("description", "")[:300],
            price="Unknown",
        )

    def _parse_card(self, card) -> Event | None:
        link = card.find("a", href=True)
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://www.ihk.de{url}"

        title_el = card.find(["h2", "h3", "h4"]) or link
        title = title_el.get_text(strip=True)[:150]
        if not title or len(title) < 4:
            return None

        # Try <time> tag
        time_el = card.find("time")
        date_el = card.find(class_=lambda c: c and ("date" in c.lower() or "datum" in c.lower()) if c else False)

        dt_source = time_el or date_el
        if dt_source:
            dt_str = dt_source.get("datetime", "") if time_el else ""
            if not dt_str:
                dt_str = dt_source.get_text(strip=True)
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
