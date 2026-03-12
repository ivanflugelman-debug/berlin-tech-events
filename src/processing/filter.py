from __future__ import annotations
import logging
from datetime import datetime, timezone

from src.config import (
    KEYWORDS, BERLIN_INDICATORS, ONLINE_INDICATORS,
    ONLINE_LOCATION_EXACT, ONLINE_TITLE_SIGNALS,
)
from src.models import Event

logger = logging.getLogger(__name__)


def _is_online_event(event: Event) -> bool:
    """Detect if an event is online-only using multiple signals."""
    title_lower = event.title.lower()
    loc_lower = event.location.strip().lower()
    text = f"{event.title} {event.location} {event.summary}".lower()

    # 1. Location is exactly an online indicator
    if loc_lower in ONLINE_LOCATION_EXACT:
        return True

    # 2. Location starts with online indicator (e.g. "Online, Zoom")
    for exact in ONLINE_LOCATION_EXACT:
        if loc_lower.startswith(exact + ",") or loc_lower.startswith(exact + " "):
            return True

    # 3. Multi-word online phrases in title/location/summary
    for indicator in ONLINE_INDICATORS:
        if indicator in text:
            return True

    # 4. Title contains bracketed/parenthesized online signals
    for signal in ONLINE_TITLE_SIGNALS:
        if signal in title_lower:
            return True

    # 5. No physical location and title suggests online
    #    (location is empty or generic "Berlin" but title has online hints)
    if loc_lower in ("", "berlin", "tbd"):
        online_words = {"online", "virtual", "remote", "webinar", "zoom", "livestream"}
        title_words = set(title_lower.replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").split())
        if title_words & online_words:
            return True

    return False


def is_in_berlin(event: Event) -> bool:
    """Check if event is located in Berlin (and not online-only)."""
    # Reject online-only events
    if _is_online_event(event):
        return False

    # Check for Berlin indicators in title, location, organizer
    text = f"{event.title} {event.location} {event.organizer}".lower()
    for indicator in BERLIN_INDICATORS:
        if indicator.lower() in text:
            return True

    return False


def matches_keywords(event: Event) -> bool:
    """Check if event matches any tech/AI keywords."""
    text = f"{event.title} {event.summary} {event.event_type} {event.organizer}".lower()

    for keyword in KEYWORDS:
        if keyword.lower() in text:
            return True

    return False


def filter_events(events: list[Event], start: datetime, end: datetime) -> list[Event]:
    """Filter events by location, keywords, and date window."""
    filtered = []
    skipped_date = 0
    skipped_location = 0
    skipped_keyword = 0
    skipped_online = 0

    for event in events:
        if event.date < start or event.date > end:
            skipped_date += 1
            logger.info(f"Filtered (date {event.date.date()}): {event.title}")
            continue
        if _is_online_event(event):
            skipped_online += 1
            logger.info(f"Filtered (online): {event.title} | loc={event.location}")
            continue
        if not is_in_berlin(event):
            skipped_location += 1
            logger.info(f"Filtered (not Berlin): {event.title} | loc={event.location}")
            continue
        if not matches_keywords(event):
            skipped_keyword += 1
            logger.info(f"Filtered (no keyword): {event.title}")
            continue
        filtered.append(event)

    logger.info(
        f"Filter: {len(events)} total → {len(filtered)} kept "
        f"(dropped: {skipped_date} date, {skipped_online} online, "
        f"{skipped_location} location, {skipped_keyword} keyword)"
    )
    return filtered
