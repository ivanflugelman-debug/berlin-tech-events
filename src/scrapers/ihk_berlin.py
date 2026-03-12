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


class IhkBerlinScraper(BaseScraper):
    name = "ihk-berlin"

    URLS = [
        "https://www.ihk.de/berlin/veranstaltungen",
        "https://www.ihk.de/berlin/veranstaltungen-und-termine",
    ]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        seen_urls = set()

        for page_url in self.URLS:
            events = self._scrape_page(page_url)
            for event in events:
                if event.url not in seen_urls:
                    all_events.append(event)
                    seen_urls.add(event.url)

        return all_events

    def _scrape_page(self, url: str) -> list[Event]:
        try:
            resp = self._get(url)
        except Exception as e:
            logger.warning(f"IHK Berlin fetch failed for {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    etype = item.get("@type", "")
                    if isinstance(etype, str) and "Event" in etype:
                        event = self._parse_jsonld(item)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        # HTML: parse any links to veranstaltungen-und-termine detail pages
        for a_tag in soup.find_all("a", href=re.compile(r"/veranstaltungen")):
            href = a_tag.get("href", "")
            if href == url or href.endswith("/veranstaltungen") or href.endswith("/veranstaltungen/"):
                continue  # Skip self-links

            full_url = href if href.startswith("http") else f"https://www.ihk.de{href}"
            title = a_tag.get_text(strip=True)[:150]
            if not title or len(title) < 5:
                # Try parent heading
                parent = a_tag.parent
                if parent:
                    heading = parent.find(["h2", "h3", "h4"])
                    if heading:
                        title = heading.get_text(strip=True)[:150]
            if not title or len(title) < 5:
                continue

            # Try to find date in surrounding text
            parent = a_tag.parent
            dt = None
            for ancestor in [parent, parent.parent if parent else None]:
                if not ancestor:
                    continue
                text = ancestor.get_text(" ", strip=True)
                # Look for German date patterns: "6. Mai 2026", "17. März 2026"
                date_match = re.search(
                    r'(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})',
                    text,
                )
                if date_match:
                    try:
                        dt = dateparser.parse(date_match.group(0), languages=["de"], fuzzy=True)
                    except (ValueError, TypeError):
                        pass
                    if dt:
                        break

                # Also try generic date parsing
                try:
                    dt = dateparser.parse(text, fuzzy=True)
                    if dt and dt.year >= 2026:
                        break
                    dt = None
                except (ValueError, TypeError):
                    dt = None

            if dt:
                events.append(Event(
                    title=title,
                    date=dt,
                    url=full_url,
                    source=self.name,
                    location="Berlin",
                    price="Unknown",
                ))

        return events

    def _parse_jsonld(self, data: dict) -> Event | None:
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
            if loc_name:
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
