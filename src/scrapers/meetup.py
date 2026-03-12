from __future__ import annotations
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.config import KEYWORDS
from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class MeetupScraper(BaseScraper):
    name = "meetup"

    SEARCH_URL = "https://www.meetup.com/find/"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        for keyword in ["tech", "AI", "startup", "developer", "data", "machine-learning"]:
            events = self._search(keyword, start, end)
            all_events.extend(events)
        return all_events

    def _search(self, keyword: str, start: datetime, end: datetime) -> list[Event]:
        params = {
            "keywords": keyword,
            "location": "Berlin, Germany",
            "source": "EVENTS",
        }
        try:
            resp = self._get(self.SEARCH_URL, params=params)
        except Exception as e:
            logger.error(f"Meetup search '{keyword}' failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Meetup renders event cards — try JSON-LD first, then HTML parsing
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        event = self._parse_jsonld(item, start, end)
                        if event:
                            events.append(event)
                elif isinstance(data, dict):
                    event = self._parse_jsonld(data, start, end)
                    if event:
                        events.append(event)
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Meetup JSON-LD parse error: {e}")

        # Fallback: parse event cards from HTML
        if not events:
            for card in soup.select("[data-testid='categoryResults-eventCard'], .eventCard, a[href*='/events/']"):
                event = self._parse_card(card, start, end)
                if event:
                    events.append(event)

        return events

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

        # Price
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

    def _parse_card(self, card, start: datetime, end: datetime) -> Event | None:
        """Fallback HTML card parsing."""
        link = card.find("a", href=True)
        if not link:
            if card.name == "a" and card.get("href"):
                link = card
            else:
                return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://www.meetup.com{url}"

        title = link.get_text(strip=True) or card.get_text(strip=True)[:100]
        if not title:
            return None

        # Try to find time element
        time_el = card.find("time")
        if time_el and time_el.get("datetime"):
            try:
                dt = dateparser.parse(time_el["datetime"])
                if dt and start <= dt <= end:
                    return Event(
                        title=title,
                        date=dt,
                        url=url,
                        source=self.name,
                        price="Unknown",
                    )
            except (ValueError, TypeError):
                pass

        return None
