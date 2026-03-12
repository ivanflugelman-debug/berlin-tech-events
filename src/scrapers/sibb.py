from __future__ import annotations
import logging
import re
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

        # Strategy 1: Parse calendar grid — td cells with day number + event link
        events = self._parse_calendar_grid(soup, start, end)
        seen_urls.update(e.url for e in events)

        # Strategy 2: Parse swiper slides (featured events)
        for slide in soup.select(".swiper-slide"):
            event = self._parse_slide(slide)
            if event and event.url not in seen_urls:
                events.append(event)
                seen_urls.add(event.url)

        # Strategy 3: Any links to eventbrite-event pages
        for a_tag in soup.find_all("a", href=re.compile(r"/eventbrite-event/")):
            url = a_tag.get("href", "")
            if not url.startswith("http"):
                url = f"https://sibb.de{url}"
            if url in seen_urls:
                continue

            title = a_tag.get_text(strip=True)[:150]
            if not title or len(title) < 4:
                continue

            # Try to extract date from surrounding context
            parent = a_tag.parent
            dt = self._extract_date_nearby(parent)
            if not dt:
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

    def _parse_calendar_grid(self, soup: BeautifulSoup, start: datetime, end: datetime) -> list[Event]:
        """Parse the WordPress Eventbrite Calendar grid.

        Calendar cells look like: <td><strong>17</strong><a href="...">Event Title</a></td>
        The month/year context comes from the calendar header.
        """
        events = []

        # Try to find current month/year from calendar header
        now = datetime.now()
        cal_month = now.month
        cal_year = now.year

        # Look for month/year in calendar header (e.g. "March 2026")
        header = soup.find(class_=re.compile(r'(month|calendar).*(title|header|nav)', re.I))
        if not header:
            header = soup.find("caption") or soup.find("th", colspan=True)
        if header:
            header_text = header.get_text(strip=True)
            try:
                dt_header = dateparser.parse(header_text, fuzzy=True)
                if dt_header:
                    cal_month = dt_header.month
                    cal_year = dt_header.year
            except (ValueError, TypeError):
                pass

        # Parse td cells
        for td in soup.find_all("td"):
            # Find day number
            strong = td.find("strong")
            if not strong:
                continue
            day_text = strong.get_text(strip=True)
            try:
                day = int(day_text)
            except ValueError:
                continue

            # Find event links in this cell
            for link in td.find_all("a", href=True):
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = f"https://sibb.de{url}"

                title = link.get_text(strip=True)[:150]
                if not title or len(title) < 4:
                    continue

                try:
                    dt = datetime(cal_year, cal_month, day)
                except ValueError:
                    continue

                events.append(Event(
                    title=title,
                    date=dt,
                    url=url,
                    source=self.name,
                    location="Berlin",
                    price="Unknown",
                ))

        return events

    def _parse_slide(self, slide) -> Event | None:
        link = slide.find("a", href=True)
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = f"https://sibb.de{url}"

        title_el = slide.find(["h2", "h3", "h4"]) or link
        title = title_el.get_text(strip=True)[:150]
        if not title or len(title) < 4:
            return None

        dt = self._extract_date_nearby(slide)
        if not dt:
            # If no date, use the link text which might contain a date
            try:
                dt = dateparser.parse(slide.get_text(" ", strip=True), fuzzy=True)
            except (ValueError, TypeError):
                return None

        if not dt:
            return None

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location="Berlin",
            price="Unknown",
        )

    def _extract_date_nearby(self, el) -> datetime | None:
        if el is None:
            return None

        # Try <time> tag
        if hasattr(el, 'find'):
            time_el = el.find("time")
            if time_el:
                dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
                try:
                    return dateparser.parse(dt_str, fuzzy=True)
                except (ValueError, TypeError):
                    pass

            # Try date class
            date_el = el.find(class_=lambda c: c and "date" in c.lower() if c else False)
            if date_el:
                try:
                    return dateparser.parse(date_el.get_text(strip=True), fuzzy=True)
                except (ValueError, TypeError):
                    pass

        return None
