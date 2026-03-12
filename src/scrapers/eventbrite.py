from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class EventbriteScraper(BaseScraper):
    name = "eventbrite"

    SEARCH_URLS = [
        "https://www.eventbrite.com/d/germany--berlin/tech/",
        "https://www.eventbrite.com/d/germany--berlin/ai/",
        "https://www.eventbrite.com/d/germany--berlin/startup/",
        "https://www.eventbrite.com/d/germany--berlin/data-science/",
        "https://www.eventbrite.com/d/germany--berlin/software-engineering/",
        "https://www.eventbrite.com/d/germany--berlin/science-and-tech/",
        "https://www.eventbrite.com/d/germany--berlin/networking/",
        "https://www.eventbrite.de/d/germany--berlin/tech/",
        "https://www.eventbrite.de/d/germany--berlin/ai/",
    ]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()
        for url in self.SEARCH_URLS:
            events = self._scrape_page(url)
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)
        return all_events

    def _scrape_page(self, url: str) -> list[Event]:
        try:
            resp = self._get(url)
        except Exception as e:
            logger.error(f"Eventbrite fetch failed for {url}: {e}")
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
                    elif item.get("@type") in ("Event", "SocialEvent", "BusinessEvent", "EducationEvent"):
                        event = self._parse_jsonld(item)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # Also try __NEXT_DATA__
        if not events:
            next_script = soup.find("script", id="__NEXT_DATA__")
            if next_script and next_script.string:
                try:
                    data = json.loads(next_script.string)
                    events = self._parse_next_data(data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Eventbrite __NEXT_DATA__ parse error: {e}")

        # Fallback: parse event cards
        if not events:
            for card in soup.select("[data-testid='event-card'], .search-event-card-wrapper, .eds-event-card, a[href*='/e/']"):
                event = self._parse_card(card)
                if event:
                    events.append(event)

        return events

    def _parse_next_data(self, data: dict) -> list[Event]:
        events = []
        try:
            props = data.get("props", {}).get("pageProps", {})
            for key in ("search_data", "events", "results"):
                val = props.get(key)
                if isinstance(val, dict):
                    items = val.get("events", val.get("results", []))
                elif isinstance(val, list):
                    items = val
                else:
                    continue
                for item in items:
                    event = self._parse_eb_event(item)
                    if event:
                        events.append(event)
        except Exception as e:
            logger.debug(f"Eventbrite next data parse: {e}")
        return events

    def _parse_eb_event(self, item: dict) -> Event | None:
        title = item.get("name", "") or item.get("title", "")
        url = item.get("url", "") or item.get("tickets_url", "")
        if not title:
            return None

        start_info = item.get("start", {}) or item.get("start_date", "")
        if isinstance(start_info, dict):
            dt_str = start_info.get("local", "") or start_info.get("utc", "")
        else:
            dt_str = str(start_info)

        if not dt_str:
            return None

        try:
            dt = dateparser.parse(dt_str)
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        venue = item.get("venue", {}) or {}
        location = venue.get("name", "")
        city = venue.get("city", "")
        if city:
            location = f"{location}, {city}" if location else city

        is_free = item.get("is_free", False)
        price = "Free" if is_free else "Paid"

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location if location else "Berlin",
            summary=(item.get("description", {}) or {}).get("text", "")[:300] if isinstance(item.get("description"), dict) else str(item.get("summary", ""))[:300],
            price=price,
        )

    def _parse_jsonld(self, data: dict) -> Event | None:
        if data.get("@type") not in ("Event", "SocialEvent", "BusinessEvent", "EducationEvent"):
            return None

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
                street = address.get("streetAddress", "")
                city = address.get("addressLocality", "")
                parts = [p for p in [location, street, city] if p]
                location = ", ".join(parts)
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
        elif isinstance(offers, list) and offers:
            first = offers[0] if isinstance(offers[0], dict) else {}
            price_val = first.get("price", "")
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

    def _parse_card(self, card, **kwargs) -> Event | None:
        link = card.find("a", href=True)
        if not link:
            if card.name == "a" and card.get("href"):
                link = card
            else:
                return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://www.eventbrite.com{url}"

        title = link.get_text(strip=True)[:150]
        if not title or len(title) < 5:
            return None

        time_el = card.find("time")
        if time_el:
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str)
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
