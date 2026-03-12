from __future__ import annotations
"""Berlin Tech Events Scraper — Entry point."""
import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import get_date_window
from src.models import ScrapeResult
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
from src.scrapers.sibb import SibbScraper
from src.scrapers.dev_events import DevEventsScraper
from src.scrapers.cbase import CBaseScraper
from src.scrapers.visitberlin import VisitBerlinScraper
from src.scrapers.ihk_berlin import IhkBerlinScraper

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
    SibbScraper,
    DevEventsScraper,
    CBaseScraper,
    VisitBerlinScraper,
    IhkBerlinScraper,
]


def _run_scraper(scraper_cls, start, end) -> tuple[str, list, ScrapeResult]:
    """Run a single scraper, return (name, events, result)."""
    scraper = scraper_cls()
    t0 = time.monotonic()
    try:
        events = scraper.safe_scrape(start, end)
        duration = time.monotonic() - t0
        result = ScrapeResult(
            source=scraper.name,
            raw_count=len(events),
            duration=round(duration, 1),
        )
        return scraper.name, events, result
    except Exception as e:
        duration = time.monotonic() - t0
        result = ScrapeResult(
            source=scraper.name,
            raw_count=0,
            duration=round(duration, 1),
            error=str(e),
        )
        return scraper.name, [], result


def main(mode: str = "weekly", source: str | None = None) -> None:
    logger.info(f"Starting Berlin Tech Events scraper (mode={mode})")

    start, end = get_date_window(mode)
    logger.info(f"Date window: {start.date()} → {end.date()}")

    # Filter to specific source if requested
    scrapers_to_run = SCRAPERS
    if source:
        scrapers_to_run = [s for s in SCRAPERS if s().name == source]
        if not scrapers_to_run:
            available = ", ".join(s().name for s in SCRAPERS)
            logger.error(f"Unknown source '{source}'. Available: {available}")
            sys.exit(1)
        logger.info(f"Running single source: {source}")

    # Scrape all sources in parallel
    all_events = []
    source_names = []
    scrape_results = []

    with ThreadPoolExecutor(max_workers=min(len(scrapers_to_run), 8)) as executor:
        futures = {
            executor.submit(_run_scraper, cls, start, end): cls
            for cls in scrapers_to_run
        }
        for future in as_completed(futures):
            name, events, result = future.result()
            source_names.append(name)
            all_events.extend(events)
            scrape_results.append(result)

    # Sort results by source name for consistent display
    scrape_results.sort(key=lambda r: r.source)

    logger.info(f"Total raw events: {len(all_events)}")
    for r in scrape_results:
        status = f"{r.raw_count} events in {r.duration}s"
        if r.error:
            status += f" (error: {r.error})"
        logger.info(f"  [{r.source}] {status}")

    # Filter
    filtered = filter_events(all_events, start, end)

    # Deduplicate
    unique = deduplicate(filtered)

    # Generate HTML
    output = generate_html(unique, mode, start, end, source_names, scrape_results)
    logger.info(f"Done! Output: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Berlin Tech Events Scraper")
    parser.add_argument(
        "--mode",
        choices=["weekly", "monthly"],
        default="weekly",
        help="Report mode: weekly (2-week lookahead) or monthly (4-week)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Run a single source by name (e.g. eventbrite, meetup, c-base)",
    )
    args = parser.parse_args()
    main(args.mode, args.source)
