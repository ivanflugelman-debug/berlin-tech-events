from __future__ import annotations
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class MeetupScraper(BaseScraper):
    name = "meetup"

    # Known Berlin tech meetup groups — these pages are public and location-stable
    BERLIN_GROUPS = [
        "berlin-ai-ml-meetup",
        "berlindatascience",
        "Berlin-Hack-and-Tell",
        "berlin-js",
        "berlin-python",
        "berlintechmeetups",
        "BerlinStartupJobs",
        "berlin-devops",
        "Berlin-Developers",
        "React-Berlin",
        "TypeScript-Berlin",
        "Berlin-Rust-Meetup",
        "golang-users-berlin",
        "Women-Techmakers-Berlin",
        "PyData-Berlin",
        "Berlin-Machine-Learning",
        "Cloud-Native-Computing-Berlin",
        "Berlin-CTO",
        "DevOps-Berlin",
        "OpenAI-Berlin",
        "Berlin-Generative-AI",
        "berlin-product-people",
        "Creative-Code-Berlin",
        "Data-Engineering-Berlin",
        "Berlin-Kotlin-Meetup",
        "AWS-Berlin",
        "Apache-Kafka-Berlin",
        "Berlin-Functional-Programming-Group",
        "GraphQL-Berlin",
    ]

    # Also search the general events page for Berlin
    SEARCH_URL = "https://www.meetup.com/find/?keywords={keyword}&location=de--Berlin&source=EVENTS"

    SEARCH_KEYWORDS = ["tech", "AI", "startup", "developer", "data", "hackathon"]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()

        # 1. Scrape known Berlin tech groups
        for group in self.BERLIN_GROUPS:
            events = self._scrape_group(group)
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)

        # 2. Also try keyword search
        for keyword in self.SEARCH_KEYWORDS:
            events = self._search_keyword(keyword)
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)

        return all_events

    def _scrape_group(self, group_slug: str) -> list[Event]:
        """Scrape upcoming events from a specific Meetup group page."""
        url = f"https://www.meetup.com/{group_slug}/events/"
        try:
            resp = self._get(url)
        except Exception as e:
            logger.debug(f"Meetup group '{group_slug}' failed: {e}")
            return []

        return self._parse_page(resp.text, group_slug)

    def _search_keyword(self, keyword: str) -> list[Event]:
        """Search Meetup for Berlin events by keyword."""
        url = self.SEARCH_URL.format(keyword=keyword)
        try:
            resp = self._get(url)
        except Exception as e:
            logger.debug(f"Meetup search '{keyword}' failed: {e}")
            return []

        return self._parse_page(resp.text, f"search:{keyword}")

    def _parse_page(self, html: str, source_label: str) -> list[Event]:
        """Parse events from a Meetup page (group or search results)."""
        soup = BeautifulSoup(html, "lxml")
        events = []

        # Try JSON-LD
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

        # Try __NEXT_DATA__
        if not events:
            next_script = soup.find("script", id="__NEXT_DATA__")
            if next_script and next_script.string:
                try:
                    data = json.loads(next_script.string)
                    events = self._extract_from_next_data(data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Meetup __NEXT_DATA__ ({source_label}): {e}")

        return events

    def _extract_from_next_data(self, data: dict) -> list[Event]:
        """Recursively find event-like objects in __NEXT_DATA__."""
        events = []

        def walk(obj, depth=0):
            if depth > 10 or not isinstance(obj, (dict, list)):
                return
            if isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)
                return
            # Check if this dict looks like an event
            if "title" in obj and ("dateTime" in obj or "eventUrl" in obj):
                event = self._parse_next_event(obj)
                if event:
                    events.append(event)
            elif "name" in obj and "startDate" in obj and "url" in obj:
                event = self._parse_jsonld(obj)
                if event:
                    events.append(event)
            # Recurse into values
            for val in obj.values():
                walk(val, depth + 1)

        walk(data)
        return events

    def _parse_next_event(self, node: dict) -> Event | None:
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

        fee = node.get("feeSettings") or {}
        if isinstance(fee, dict):
            amount = fee.get("amount", None)
            price = "Paid" if amount and amount > 0 else "Free"
        else:
            price = "Unknown"

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location if location else "Berlin",
            organizer=organizer,
            summary=(node.get("description", "") or "")[:300],
            price=price,
        )

    def _parse_jsonld(self, data: dict) -> Event | None:
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
            location=location if location else "Berlin",
            organizer=organizer,
            summary=data.get("description", "")[:300],
            price=price,
        )
