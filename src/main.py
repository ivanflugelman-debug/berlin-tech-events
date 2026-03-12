from __future__ import annotations
"""Berlin Tech Events Scraper — Entry point."""
import argparse
import logging
import sys

from src.config import get_date_window
from src.processing.dedup import deduplicate
from src.processing.filter import filter_events
from src.outputs.html_report import generate_html
from src.scrapers.serpapi_google import SerpApiScraper
from src.scrapers.meetup import MeetupScraper
from src.scrapers.eventbrite import EventbriteScraper
from src.scrapers.luma import LumaScraper
from src.scrapers.allevents import AllEventsScraper
from src.scrapers.berlin_de import BerlinDeScraper
from src.scrapers.ai_berlin import AiBerlinScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPERS = [
    SerpApiScraper,
    MeetupScraper,
    EventbriteScraper,
    LumaScraper,
    AllEventsScraper,
    BerlinDeScraper,
    AiBerlinScraper,
]


def main(mode: str = "weekly") -> None:
    logger.info(f"Starting Berlin Tech Events scraper (mode={mode})")

    start, end = get_date_window(mode)
    logger.info(f"Date window: {start.date()} → {end.date()}")

    # Scrape all sources (each one is independent / fault-tolerant)
    all_events = []
    source_names = []
    for scraper_cls in SCRAPERS:
        scraper = scraper_cls()
        source_names.append(scraper.name)
        events = scraper.safe_scrape(start, end)
        all_events.extend(events)

    logger.info(f"Total raw events: {len(all_events)}")

    # Filter
    filtered = filter_events(all_events, start, end)

    # Deduplicate
    unique = deduplicate(filtered)

    # Generate HTML
    output = generate_html(unique, mode, start, end, source_names)
    logger.info(f"Done! Output: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Berlin Tech Events Scraper")
    parser.add_argument(
        "--mode",
        choices=["weekly", "monthly"],
        default="weekly",
        help="Report mode: weekly (2-week lookahead) or monthly (4-week)",
    )
    args = parser.parse_args()
    main(args.mode)
