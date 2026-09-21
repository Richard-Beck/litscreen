"""Fetch bioRxiv metadata using only the Python standard library."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API = "https://api.biorxiv.org/details/biorxiv"
FIELDS = ("doi", "title", "authors", "date", "version", "category", "abstract")


def get_page(url):
    """Retry temporary network/server failures, with a timeout per request."""
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "litscreen-dev/0.1"})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except (URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code != 429 and exc.code < 500:
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def fetch_articles(start_date, end_date):
    """Read every page; retain each distinct DOI/version returned in the window."""
    articles = {}
    cursor = 0
    while True:
        url = f"{API}/{start_date}/{end_date}/{cursor}"
        payload = get_page(url)
        messages = payload.get("messages", [])
        if not messages or messages[0].get("status") != "ok":
            raise ValueError(f"bioRxiv API error at {url}: {messages!r}")
        total = int(messages[0]["total"])
        page = payload["collection"]
        if not page and cursor < total:
            raise ValueError(f"Unexpected empty page at cursor {cursor} of {total}")
        for item in page:
            key = (item["doi"], item["version"])
            article = {field: item.get(field) for field in FIELDS}
            article["url"] = f"https://doi.org/{item['doi']}"
            articles[key] = article
        cursor += len(page)
        print(f"Fetched {cursor}/{total} records", file=sys.stderr)
        if cursor >= total:
            break
        time.sleep(0.5)
    return sorted(articles.values(), key=lambda row: (row["date"], row["doi"], int(row["version"])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24, help="Lookback in hours (default: 24; date precision only)")
    parser.add_argument("--output", type=Path, default=Path("data/biorxiv_recent.json"))
    args = parser.parse_args()
    if args.hours <= 0:
        parser.error("--hours must be positive")

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=args.hours)
    start_date, end_date = start.date().isoformat(), now.date().isoformat()
    print("Date-only API: results may include posts older than the requested lookback.", file=sys.stderr)
    try:
        articles = fetch_articles(start_date, end_date)
        result = {
            "source": API,
            "requested_at_utc": now.isoformat(),
            "requested_since_utc": start.isoformat(),
            "query_start_date": start_date,
            "query_end_date": end_date,
            "date_precision_note": "Inclusive calendar dates overlapping the requested UTC window; exact posting times are unavailable.",
            "keywords_note": "The API does not provide keywords; category and abstract are retained instead.",
            "record_count": len(articles),
            "articles": articles,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Replace only after a complete fetch and successful serialization.
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Failed to fetch/save metadata: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {len(articles)} records to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
