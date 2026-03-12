from __future__ import annotations
import logging
import re
from datetime import datetime

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
    text = f"{event.title} {event.summary} {event.event_type}".lower()

    for keyword in KEYWORDS:
        if keyword.lower() in text:
            return True

    return False


def filter_events(events: list[Event], start: datetime, end: datetime) -> list[Event]:
    """Filter events by location, keywords, and date window."""
    filtered = []
    for event in events:
        if event.date < start or event.date > end:
            continue
        if not is_in_berlin(event):
            logger.debug(f"Filtered out (not Berlin): {event.title}")
            continue
        if not matches_keywords(event):
            logger.debug(f"Filtered out (no keyword match): {event.title}")
            continue
        filtered.append(event)

    logger.info(f"Filtered {len(events)} → {len(filtered)} events")
    return filtered
