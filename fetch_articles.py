"""Harvest recent article metadata from bioRxiv, Europe PMC, and Crossref."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode

from fetch_biorxiv import fetch_articles as fetch_biorxiv, get_page


EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF = "https://api.crossref.org/works"


def fetch_europe_pmc(start, end):
    cursor = "*"
    articles = {}
    count = 0
    while True:
        payload = get_page(EPMC + "?" + urlencode({
            "query": f"FIRST_PDATE:[{start} TO {end}]",
            "format": "json", "resultType": "core", "pageSize": 1000,
            "cursorMark": cursor,
        }))
        total = int(payload["hitCount"])
        page = payload["resultList"]["result"]
        for item in page:
            key = (item["source"], item["id"])
            articles[key] = {
                "source": "europe_pmc", "source_id": item["id"],
                "source_database": item["source"], "doi": item.get("doi"),
                "title": item.get("title"), "authors": item.get("authorString"),
                "date": item.get("firstPublicationDate"),
                "abstract": item.get("abstractText"),
                "keywords": item.get("keywordList", {}).get("keyword", []),
                "subjects": [term["descriptorName"] for term in
                             item.get("meshHeadingList", {}).get("meshHeading", [])
                             if term.get("descriptorName")],
                "journal": item.get("journalInfo", {}).get("journal", {}).get("title"),
                "url": f"https://europepmc.org/article/{item['source']}/{item['id']}",
            }
        count += len(page)
        print(f"Europe PMC: fetched {count}/{total}", file=sys.stderr)
        if count >= total:
            break
        next_cursor = payload.get("nextCursorMark")
        if not page or not next_cursor or next_cursor == cursor:
            raise ValueError("Europe PMC pagination stopped before all results were retrieved")
        cursor = next_cursor
        time.sleep(0.5)
    return list(articles.values())


def crossref_date(value):
    """Keep the precision supplied by Crossref rather than inventing day/month."""
    parts = (value or {}).get("date-parts", [[]])[0]
    return "-".join(f"{part:04d}" if i == 0 else f"{part:02d}"
                    for i, part in enumerate(parts)) or None


def fetch_crossref(start, end):
    cursor = "*"
    articles = {}
    count = 0
    while True:
        payload = get_page(CROSSREF + "?" + urlencode({
            "filter": f"from-pub-date:{start},until-pub-date:{end},type:journal-article",
            "rows": 1000, "cursor": cursor,
            "select": "DOI,title,author,published,published-online,published-print,abstract,subject,container-title,URL",
        }))
        if payload.get("status") != "ok":
            raise ValueError(f"Crossref API error: {payload.get('message')}")
        message = payload["message"]
        total = int(message["total-results"])
        page = message["items"]
        before = len(articles)
        for item in page:
            doi = item["DOI"]
            articles[doi.lower()] = {
                "source": "crossref", "source_id": doi, "doi": doi,
                "title": " ".join(item.get("title", [])) or None,
                "authors": "; ".join(author.get("name") or " ".join(
                    filter(None, (author.get("given"), author.get("family"))))
                    for author in item.get("author", [])) or None,
                "date": crossref_date(item.get("published")),
                "online_date": crossref_date(item.get("published-online")),
                "print_date": crossref_date(item.get("published-print")),
                "abstract": item.get("abstract"), "keywords": [],
                "subjects": item.get("subject", []),
                "journal": "; ".join(item.get("container-title", [])) or None,
                "url": item.get("URL") or f"https://doi.org/{doi}",
            }
        count += len(page)
        print(f"Crossref: fetched {count}/{total}", file=sys.stderr)
        # Crossref's total can change during a harvest. A short/empty page or
        # absent next cursor ends the result stream; totals are only progress hints.
        next_cursor = message.get("next-cursor")
        if len(page) < 1000 or not next_cursor:
            break
        # A cursor may be reused by Crossref; detect repeated data, not token equality.
        if len(articles) == before:
            raise ValueError("Crossref pagination repeated a full page without new records")
        cursor = next_cursor
        time.sleep(0.5)
    return list(articles.values())


def fetch_biorxiv_normalized(start, end):
    return [dict(item, source="biorxiv", source_id=f"{item['doi']}v{item['version']}",
                 keywords=[], subjects=[item["category"]] if item.get("category") else [])
            for item in fetch_biorxiv(start, end)]


FETCHERS = {"biorxiv": fetch_biorxiv_normalized, "europe_pmc": fetch_europe_pmc,
            "crossref": fetch_crossref}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--sources", nargs="+", choices=FETCHERS, default=list(FETCHERS))
    parser.add_argument("--output", type=Path, default=Path("data/articles_recent.json"))
    args = parser.parse_args()
    if args.hours <= 0:
        parser.error("--hours must be positive")
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    start, end = since.date().isoformat(), now.date().isoformat()
    sources = list(dict.fromkeys(args.sources))
    print(f"Querying inclusive dates {start} through {end}; the {args.hours}-hour cutoff is approximate.", file=sys.stderr)
    try:
        results = {}
        with ThreadPoolExecutor(max_workers=len(sources)) as pool:
            futures = {pool.submit(FETCHERS[source], start, end): source for source in sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    results[source] = future.result()
                except Exception as exc:
                    raise RuntimeError(f"{source}: {exc}") from exc
        articles = [article for source in sources for article in results[source]]
        result = {
            "requested_at_utc": now.isoformat(), "requested_since_utc": since.isoformat(),
            "query_start_date": start, "query_end_date": end,
            "date_precision_note": "Inclusive calendar dates overlapping the requested UTC window; exact posting times are unavailable. Publication metadata may be incomplete or indexed late.",
            "source_date_fields": {"biorxiv": "date (new and revised posts)",
                                   "europe_pmc": "FIRST_PDATE (first publication)",
                                   "crossref": "from-pub-date/until-pub-date (journal articles, all subjects)"},
            "keywords_note": "Europe PMC keywords are retained when present. Crossref subjects and bioRxiv categories are separate from keywords. Abstracts may contain source markup.",
            "deduplication_note": "Source records are retained separately; record_count is not a unique-paper count.",
            "source_counts": {source: len(results[source]) for source in sources},
            "record_count": len(articles), "articles": articles,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Harvest failed; previous output retained: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {len(articles)} records to {args.output}; counts: {result['source_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
