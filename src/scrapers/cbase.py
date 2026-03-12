from __future__ import annotations
import logging
from datetime import datetime

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class CBaseScraper(BaseScraper):
    name = "c-base"

    ICS_URL = "https://c-base.org/calendar/exported/c-base-events.ics"

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        try:
            resp = self._get(self.ICS_URL)
        except Exception as e:
            logger.error(f"c-base iCal fetch failed: {e}")
            return []

        try:
            from icalendar import Calendar
        except ImportError:
            logger.error("icalendar not installed — skipping c-base scraper")
            return []

        try:
            cal = Calendar.from_ical(resp.content)
        except Exception as e:
            logger.error(f"c-base iCal parse failed: {e}")
            return []

        events = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            event = self._parse_vevent(component)
            if event:
                events.append(event)

        return events

    def _parse_vevent(self, vevent) -> Event | None:
        title = str(vevent.get("SUMMARY", ""))
        if not title:
            return None

        dtstart = vevent.get("DTSTART")
        if not dtstart:
            return None

        dt = dtstart.dt
        # Handle date vs datetime
        if not isinstance(dt, datetime):
            dt = datetime.combine(dt, datetime.min.time())
        # Strip timezone for consistency
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)

        url = str(vevent.get("URL", ""))
        if not url:
            uid = str(vevent.get("UID", ""))
            url = f"https://c-base.org/calendar/{uid}" if uid else "https://c-base.org"

        location = str(vevent.get("LOCATION", "")) or "c-base, Berlin"
        description = str(vevent.get("DESCRIPTION", ""))

        # Parse end date
        end_date = None
        dtend = vevent.get("DTEND")
        if dtend:
            end_dt = dtend.dt
            if not isinstance(end_dt, datetime):
                end_dt = datetime.combine(end_dt, datetime.min.time())
            if end_dt.tzinfo is not None:
                end_dt = end_dt.replace(tzinfo=None)
            end_date = end_dt

        return Event(
            title=title[:150],
            date=dt,
            url=url,
            source=self.name,
            location=location if location else "c-base, Berlin",
            summary=description[:300],
            end_date=end_date,
            price="Unknown",
        )
