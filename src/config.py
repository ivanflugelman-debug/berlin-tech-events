from __future__ import annotations
import os
from datetime import datetime, timedelta

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

KEYWORDS = [
    "AI", "ML", "Artificial Intelligence", "Machine Learning",
    "Data", "Engineering", "Creative Technologies", "Cloud",
    "Developer", "Coding", "Startup", "Hackathon",
    "Deep Learning", "LLM", "GenAI", "DevOps", "Tech",
    "Kubernetes", "Docker", "Web3", "Cybersecurity", "UX",
    "Product", "SaaS", "Open Source", "NLP", "Python",
    "JavaScript", "React", "Robotics", "IoT", "FinTech",
]

BERLIN_INDICATORS = [
    "Berlin", "Mitte", "Kreuzberg", "Friedrichshain", "Prenzlauer Berg",
    "Neukölln", "Charlottenburg", "Schöneberg", "Tempelhof",
    "Wedding", "Moabit", "Spandau", "Steglitz", "Zehlendorf",
    "Treptow", "Köpenick", "Lichtenberg", "Pankow", "Reinickendorf",
    "Marzahn", "Hellersdorf"
]

ONLINE_INDICATORS = [
    "online only", "virtual event", "remote only", "webinar", "online event",
    "online-event", "virtual only", "zoom meeting", "livestream only",
]

ONLINE_LOCATION_EXACT = ["online", "virtual", "remote", "zoom", "online event"]

SEARCH_QUERIES = [
    "tech events Berlin",
    "AI meetup Berlin",
    "startup events Berlin",
    "developer conference Berlin",
    "hackathon Berlin",
    "machine learning Berlin",
    "data engineering Berlin",
]

def get_date_window(mode: str) -> tuple[datetime, datetime]:
    """Return (start, end) date window based on mode."""
    today = datetime.now()
    if mode == "weekly":
        # Current week only (Monday–Sunday)
        start = today - timedelta(days=today.weekday())  # This Monday
        end = start + timedelta(days=6)  # This Sunday
    elif mode == "monthly":
        # Events for next 6 weeks starting tomorrow
        start = today + timedelta(days=1)
        end = start + timedelta(weeks=6)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Set times to start/end of day
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end
