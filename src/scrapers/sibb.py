from __future__ import annotations
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SibbScraper(BaseScraper):
    name = "sibb"

    EVENTS_URL = "https://sibb.de/events/"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(self.EVENTS_URL)
        except Exception as e:
            logger.error(f"SIBB fetch failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []
        seen_urls = set()

        # SIBB uses teaser cards with event info
        for card in soup.select("article, .event, .teaser, .tribe-events-calendar-list__event, .type-tribe_events, [class*='event']"):
            event = self._parse_card(card)
            if event and event.url not in seen_urls:
                events.append(event)
                seen_urls.add(event.url)

        # Also try finding links with date patterns
        if not events:
            for a_tag in soup.find_all("a", href=True):
                href = a_tag.get("href", "")
                # SIBB event links often point to Eventbrite or their own detail pages
                if "/event" not in href.lower() and "/veranstaltung" not in href.lower():
                    continue

                title = a_tag.get_text(strip=True)[:150]
                if not title or len(title) < 5:
                    continue

                url = href if href.startswith("http") else f"https://sibb.de{href}"
                if url in seen_urls:
                    continue

                # Try to find a date nearby
                parent = a_tag.parent
                dt = self._extract_date_from_element(parent)
                if not dt and parent:
                    dt = self._extract_date_from_element(parent.parent)

                if dt:
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

    def _parse_card(self, card) -> Event | None:
        link = card.find("a", href=True)
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://sibb.de{url}"

        title_el = card.find(["h1", "h2", "h3", "h4"]) or link
        title = title_el.get_text(strip=True)[:150]
        if not title or len(title) < 4:
            return None

        dt = self._extract_date_from_element(card)
        if not dt:
            return None

        # Location
        location = "Berlin"
        loc_el = card.find(class_=lambda c: c and ("location" in c.lower() or "venue" in c.lower() or "ort" in c.lower()) if c else False)
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

    def _extract_date_from_element(self, el) -> datetime | None:
        if el is None:
            return None

        # Try <time> tag first
        time_el = el.find("time") if hasattr(el, 'find') else None
        if time_el:
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            try:
                dt = dateparser.parse(dt_str, fuzzy=True)
                if dt:
                    return dt
            except (ValueError, TypeError):
                pass

        # Try date class
        date_el = el.find(class_=lambda c: c and "date" in c.lower() if c else False) if hasattr(el, 'find') else None
        if date_el:
            try:
                dt = dateparser.parse(date_el.get_text(strip=True), fuzzy=True)
                if dt:
                    return dt
            except (ValueError, TypeError):
                pass

        return None
