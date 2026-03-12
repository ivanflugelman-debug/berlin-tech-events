from __future__ import annotations
import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Pattern to match DD.MM.YYYY or DD.MM.YY dates common on German sites
DATE_PATTERN = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})')


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
                    event = self._parse_jsonld(item)
                    if event:
                        events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # HTML fallback: find all links that contain a DD.MM.YYYY date pattern
        if not events:
            events = self._parse_html_events(soup)

        return events

    def _parse_html_events(self, soup: BeautifulSoup) -> list[Event]:
        """Parse events by scanning for links with DD.MM.YYYY date patterns."""
        events = []
        seen_urls = set()

        # Strategy 1: Look for any element containing a date pattern and nearby link
        for a_tag in soup.find_all("a", href=True):
            url = a_tag.get("href", "")
            if not url or url in seen_urls:
                continue

            # Get the parent container text to find dates
            parent = a_tag.parent
            if parent is None:
                parent = a_tag

            # Check the link text and surrounding text for dates
            context_text = parent.get_text(" ", strip=True)
            date_match = DATE_PATTERN.search(context_text)
            if not date_match:
                # Check grandparent
                grandparent = parent.parent if parent else None
                if grandparent:
                    context_text = grandparent.get_text(" ", strip=True)
                    date_match = DATE_PATTERN.search(context_text)

            if not date_match:
                continue

            day, month, year = date_match.groups()
            if len(year) == 2:
                year = f"20{year}"

            try:
                dt = datetime(int(year), int(month), int(day))
            except (ValueError, TypeError):
                continue

            # Build URL
            if not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            # Get title from link text or heading
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 4:
                heading = parent.find(["h1", "h2", "h3", "h4", "h5"])
                if heading:
                    title = heading.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            # Skip navigation/generic links
            if title.lower() in ("read more", "more", "details", "link", "events", "home"):
                continue

            seen_urls.add(url)
            events.append(Event(
                title=title[:150],
                date=dt,
                url=url,
                source=self.name,
                location="Berlin",
                price="Unknown",
            ))

        # Strategy 2: Scan all text nodes for date patterns and associate with nearest link
        if not events:
            for el in soup.find_all(string=DATE_PATTERN):
                parent = el.parent
                if parent is None:
                    continue
                # Walk up to find container with a link
                container = parent
                for _ in range(5):
                    link = container.find("a", href=True) if hasattr(container, 'find') else None
                    if link:
                        break
                    container = container.parent if container and container.parent else container
                else:
                    continue

                if not link:
                    continue

                url = link.get("href", "")
                if not url or url in seen_urls:
                    continue
                if not url.startswith("http"):
                    url = f"{self.BASE_URL}{url}"

                date_match = DATE_PATTERN.search(str(el))
                if not date_match:
                    continue

                day, month, year = date_match.groups()
                if len(year) == 2:
                    year = f"20{year}"

                try:
                    dt = datetime(int(year), int(month), int(day))
                except (ValueError, TypeError):
                    continue

                title = link.get_text(strip=True)[:150]
                if not title or len(title) < 4:
                    continue

                seen_urls.add(url)
                events.append(Event(
                    title=title,
                    date=dt,
                    url=url,
                    source=self.name,
                    location="Berlin",
                    price="Unknown",
                ))

        return events

    def _parse_jsonld(self, data: dict) -> Event | None:
        if data.get("@type") not in ("Event", "SocialEvent", "BusinessEvent", "EducationEvent"):
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
