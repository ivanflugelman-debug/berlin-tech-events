from __future__ import annotations
import json
import logging
from datetime import datetime

from dateutil import parser as dateparser

from src.models import Event
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class MeetupScraper(BaseScraper):
    name = "meetup"

    GRAPHQL_URL = "https://www.meetup.com/gql"

    SEARCH_KEYWORDS = ["tech", "AI", "startup", "developer", "data", "machine learning",
                        "software engineering", "coding", "hackathon", "cloud"]

    def scrape(self, start: datetime, end: datetime) -> list[Event]:
        all_events = []
        for keyword in self.SEARCH_KEYWORDS:
            events = self._search_graphql(keyword, start, end)
            all_events.extend(events)
        return all_events

    def _search_graphql(self, keyword: str, start: datetime, end: datetime) -> list[Event]:
        """Use Meetup's GraphQL API to search events."""
        query = """
        query($query: String!, $lat: Float!, $lon: Float!, $startDateRange: DateTime, $endDateRange: DateTime) {
          rankedEvents(filter: {
            query: $query,
            lat: $lat,
            lon: $lon,
            radius: 30,
            startDateRange: $startDateRange,
            endDateRange: $endDateRange
          }, first: 50) {
            edges {
              node {
                title
                dateTime
                endTime
                eventUrl
                description
                venue {
                  name
                  address
                  city
                }
                group {
                  name
                }
                feeSettings {
                  amount
                  currency
                }
                eventType
              }
            }
          }
        }
        """
        variables = {
            "query": keyword,
            "lat": 52.52,  # Berlin
            "lon": 13.405,
            "startDateRange": start.isoformat(),
            "endDateRange": end.isoformat(),
        }

        try:
            resp = self.session.post(
                self.GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers={
                    **self.session.headers,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Meetup GraphQL search '{keyword}' failed: {e}")
            # Fallback to HTML scraping
            return self._search_html(keyword, start, end)

        events = []
        ranked = data.get("data", {}).get("rankedEvents", {})
        edges = ranked.get("edges", []) if ranked else []

        for edge in edges:
            node = edge.get("node", {})
            event = self._parse_graphql_event(node, start, end)
            if event:
                events.append(event)

        if not events:
            # Fallback to HTML scraping
            return self._search_html(keyword, start, end)

        return events

    def _parse_graphql_event(self, node: dict, start: datetime, end: datetime) -> Event | None:
        title = node.get("title", "")
        url = node.get("eventUrl", "")

        dt_str = node.get("dateTime", "")
        if not dt_str:
            return None

        try:
            dt = dateparser.parse(dt_str)
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        venue = node.get("venue", {}) or {}
        venue_name = venue.get("name", "")
        venue_city = venue.get("city", "")
        venue_addr = venue.get("address", "")
        parts = [p for p in [venue_name, venue_addr, venue_city] if p]
        location = ", ".join(parts) if parts else ""

        group = node.get("group", {}) or {}
        organizer = group.get("name", "")

        fee = node.get("feeSettings", {}) or {}
        amount = fee.get("amount", None)
        if amount is None or amount == 0:
            price = "Free"
        else:
            price = "Paid"

        summary = node.get("description", "") or ""

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            organizer=organizer,
            summary=summary[:300],
            event_type=node.get("eventType", ""),
            price=price,
        )

    def _search_html(self, keyword: str, start: datetime, end: datetime) -> list[Event]:
        """Fallback: scrape Meetup search results page."""
        from bs4 import BeautifulSoup

        params = {
            "keywords": keyword,
            "location": "Berlin, Germany",
            "source": "EVENTS",
        }
        try:
            resp = self._get(f"https://www.meetup.com/find/", params=params)
        except Exception as e:
            logger.error(f"Meetup HTML search '{keyword}' failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        events = []

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Event", "SocialEvent", "BusinessEvent"):
                        event = self._parse_jsonld(item, start, end)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, Exception):
                continue

        return events

    def _parse_jsonld(self, data: dict, start: datetime, end: datetime) -> Event | None:
        title = data.get("name", "")
        url = data.get("url", "")

        try:
            dt = dateparser.parse(data.get("startDate", ""))
            if dt is None:
                return None
        except (ValueError, TypeError):
            return None

        location_data = data.get("location", {})
        if isinstance(location_data, dict):
            location = location_data.get("name", "")
            address = location_data.get("address", {})
            if isinstance(address, dict):
                city = address.get("addressLocality", "")
                if city:
                    location = f"{location}, {city}" if location else city
        else:
            location = str(location_data)

        organizer_data = data.get("organizer", {})
        organizer = organizer_data.get("name", "") if isinstance(organizer_data, dict) else ""

        offers = data.get("offers", {})
        if isinstance(offers, dict):
            price_val = offers.get("price", "")
            if price_val in (0, "0", "0.00"):
                price = "Free"
            elif price_val:
                price = "Paid"
            else:
                price = "Unknown"
        else:
            price = "Unknown"

        return Event(
            title=title,
            date=dt,
            url=url,
            source=self.name,
            location=location,
            organizer=organizer,
            summary=data.get("description", "")[:300],
            price=price,
        )
