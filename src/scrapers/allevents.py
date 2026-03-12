from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class AllEventsScraper(BaseScraper):
    name = "allevents"

    SEARCH_URLS = [
        "https://allevents.in/berlin/technology",
        "https://allevents.in/berlin/startups",
        "https://allevents.in/berlin/science-and-tech",
    ]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        for url in self.SEARCH_URLS:
            events = self._scrape_page(url, start, end)
            all_events.extend(events)
        return all_events

    def _scrape_page(self, url: str, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(url)
        except Exception as e:
            logger.error(f"AllEvents fetch failed for {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "ItemList":
                        for el in item.get("itemListElement", []):
                            event = self._parse_jsonld(el, start, end)
                            if event:
                                events.append(event)
                    else:
                        event = self._parse_jsonld(item, start, end)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # Fallback: HTML cards
        if not events:
            for card in soup.select(".event-item, .event-card, [itemtype*='Event']"):
                event = self._parse_card(card, start, end)
                if event:
                    events.append(event)

        return events

    def _parse_jsonld(self, data: dict, start: datetime, end: datetime) -> Event | None:
        if data.get("@type") not in ("Event", "SocialEvent", "BusinessEvent", "EducationEvent"):
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
        link = card.find("a", href=True)
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://allevents.in{url}"

        title = link.get_text(strip=True)[:150]
        if not title:
            return None

        time_el = card.find("time") or card.find("[datetime]")
        if time_el:
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str)
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
