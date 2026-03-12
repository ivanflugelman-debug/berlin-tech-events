from __future__ import annotations
import logging
from thefuzz import fuzz
from src.models import Event

logger = logging.getLogger(__name__)


def deduplicate(events: list[Event]) -> list[Event]:
    """Remove duplicate events using URL normalization and fuzzy title matching."""
    if not events:
        return []

    unique: list[Event] = []
    seen_urls: set[str] = set()

    for event in events:
        # 1. Exact URL match
        if event.normalized_url and event.normalized_url in seen_urls:
            logger.debug(f"Dedup (URL match): {event.title}")
            continue

        # 2. Fuzzy title + same date match
        is_dup = False
        for existing in unique:
            if event.date.date() == existing.date.date():
                similarity = fuzz.token_sort_ratio(event.title, existing.title)
                if similarity > 85:
                    logger.debug(
                        f"Dedup (fuzzy {similarity}%): '{event.title}' ~ '{existing.title}'"
                    )
                    is_dup = True
                    break

        if not is_dup:
            unique.append(event)
            if event.normalized_url:
                seen_urls.add(event.normalized_url)

    logger.info(f"Deduplication: {len(events)} → {len(unique)} events")
    return unique
