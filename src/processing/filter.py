from __future__ import annotations
import logging
from datetime import datetime, timezone

from src.config import KEYWORDS, BERLIN_INDICATORS, ONLINE_INDICATORS
from src.models import Event

logger = logging.getLogger(__name__)


def is_in_berlin(event: Event) -> bool:
    """Check if event is located in Berlin."""
    text = f"{event.title} {event.location} {event.organizer}".lower()

    # Reject online-only events
    for indicator in ONLINE_INDICATORS:
        if indicator in text:
            return False

    # Check for Berlin indicators
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

    for event in events:
        if event.date < start or event.date > end:
            skipped_date += 1
            logger.info(f"Filtered (date {event.date.date()}): {event.title}")
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
        f"(dropped: {skipped_date} date, {skipped_location} location, {skipped_keyword} keyword)"
    )
    return filtered
