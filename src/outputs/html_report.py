from __future__ import annotations
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.models import Event

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "docs"


def generate_html(events: list[Event], mode: str, start: datetime, end: datetime, sources: list[str]) -> Path:
    """Generate the HTML report and write to docs/."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Sort events by date
    events_sorted = sorted(events, key=lambda e: e.date)

    # Group by date
    grouped = defaultdict(list)
    for event in events_sorted:
        grouped[event.date.strftime("%A, %B %d, %Y")].append(event)

    events_by_date = list(grouped.items())

    # Render
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("report.html")

    html = template.render(
        mode=mode,
        start_date=start.strftime("%b %d"),
        end_date=end.strftime("%b %d, %Y"),
        total_events=len(events),
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        events_by_date=events_by_date,
        sources=sources,
    )

    # Write output — weekly goes to index.html, monthly to monthly.html
    filename = "index.html" if mode == "weekly" else "monthly.html"
    output_path = OUTPUT_DIR / filename
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"Written {output_path} ({len(events)} events)")
    return output_path
