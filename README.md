# Berlin Tech Events

Automated scraper that discovers tech/AI/startup events in Berlin from 7+ sources and generates a static HTML page deployed to GitHub Pages.

## Sources

| Source | Approach |
|--------|----------|
| SerpAPI (Google Events) | REST API — meta-source aggregating across platforms |
| Meetup.com | HTML scraping + JSON-LD |
| Eventbrite | HTML scraping + JSON-LD |
| Lu.ma | `__NEXT_DATA__` JSON parsing |
| AllEvents.in | HTML scraping + JSON-LD |
| berlin.de | HTML scraping |
| ai-berlin.com | HTML scraping |

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set SerpAPI key** (optional but recommended):
   ```bash
   export SERPAPI_KEY="your_key_here"
   ```
   Sign up at [serpapi.com](https://serpapi.com) — free tier gives 100 searches/month.

3. **Run locally:**
   ```bash
   python -m src.main --mode weekly
   python -m src.main --mode monthly
   ```
   Output goes to `docs/index.html` (weekly) and `docs/monthly.html`.

## GitHub Pages Deployment

1. Create a GitHub repo and push this code
2. Go to **Settings → Pages** → set source to `docs/` folder on `main` branch
3. Add `SERPAPI_KEY` as a repository secret
4. The workflow runs automatically:
   - **Weekly:** Every Monday at 8am UTC
   - **Monthly:** 1st of each month at 8am UTC
   - **Manual:** Use "Run workflow" button in Actions tab

## How it works

1. All scrapers run independently (if one fails, others continue)
2. Events are filtered by Berlin location + tech/AI keywords
3. Duplicates are removed via URL normalization + fuzzy title matching
4. A clean HTML report is generated with weekly/monthly toggle
