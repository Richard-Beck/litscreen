"""Deduplicate filtered article records and flag explicit publication events."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

from filter_articles import normalize


def canonical_doi(value):
    value = unquote(value or "").strip().casefold()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)
    return value if re.fullmatch(r"10\.\d{4,9}/\S+", value) else None


def event_flags(record):
    """Only flag explicit evidence; absence of a flag does not establish novelty."""
    flags = []
    title = normalize(record.get("title"))
    for label, pattern in (
        ("correction_notice", r"correction|author correction|publisher correction|corrigendum|erratum"),
        ("retraction_notice", r"retraction|retraction notice"),
        ("expression_of_concern", r"expression of concern|editorial expression of concern"),
    ):
        # Require a notice-style delimiter or 'to', not a generic word.
        if re.search(r"^(?:\[(?:" + pattern + r")\]|(?:" + pattern +
                     r")(?:\s*:|\s+to\b|$))", title):
            flags.append({"type": label, "evidence": "explicit_title_prefix"})
    if record.get("source") == "biorxiv":
        try:
            version = int(record.get("version"))
        except (TypeError, ValueError):
            version = 0
        if version >= 1:
            flags.append({"type": "first_preprint_version" if version == 1 else "preprint_revision",
                          "evidence": f"biorxiv_version={version}"})
    return flags


def prepare(records):
    groups = {}
    for index, record in enumerate(records):
        doi = canonical_doi(record.get("doi"))
        # Without a valid DOI, match only identical IDs from the same database.
        key = ("doi", doi) if doi else (
            "id", record.get("source"), record.get("source_database"), record["source_id"]
        ) if record.get("source_id") else ("row", index)
        groups.setdefault(key, []).append(record)
    articles = []
    for key, rows in groups.items():
        def rank(row):
            try:
                version = int(row.get("version", 0))
            except (ValueError, TypeError):
                version = 0
            return (version if row.get("source") == "biorxiv" else 0,
                    len(row.get("abstract") or ""))
        # Prefer the latest bioRxiv version, otherwise the richest abstract.
        representative = max(rows, key=rank)
        article = dict(representative)
        if key[0] == "doi":
            article["doi"] = key[1]
        source_records = [dict(row, event_flags=event_flags(row)) for row in rows]
        flags = sorted({flag["type"] for row in source_records for flag in row["event_flags"]})
        article.update(
            sources=sorted({row.get("source", "unknown") for row in rows}),
            source_record_count=len(rows), source_records=source_records,
            event_flags=flags, publication_status="flagged" if flags else "unclassified",
        )
        articles.append(article)
    return articles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/articles_filtered.json"))
    parser.add_argument("--output", type=Path, default=Path("data/articles_screening.json"))
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Output must differ from input")
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        articles = prepare(data["articles"])
        counts = dict(Counter(flag for article in articles for flag in article["event_flags"]))
        result = {
            "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_file": str(args.input), "input_record_count": len(data["articles"]),
            "record_count": len(articles),
            "duplicate_records_consolidated": len(data["articles"]) - len(articles),
            "event_counts": counts,
            "unclassified_count": sum(not a["event_flags"] for a in articles),
            "policy": {
                "deduplication": "Exact normalized DOI; otherwise exact source/database/ID. No title matching or linking different preprint and journal DOIs. All source records and versions retained inside each article.",
                "representative": "Latest bioRxiv version if present; otherwise longest abstract. Top-level metadata and filter evidence belong to that representative; consult source_records for all other values.",
                "flags": "Notice-style title prefixes and bioRxiv version numbers only. Unclassified does not imply new. A first preprint version does not establish first publication elsewhere. No scientific revisions inferred from metadata update dates.",
                "dates": "No exclusions based on date discrepancies. The original date-only window and its uncertainty still apply.",
            },
            "input_metadata": {k: v for k, v in data.items() if k != "articles"},
            "articles": articles,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Screening preparation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Consolidated {len(data['articles'])} records into {len(articles)} articles; saved to {args.output}")
    print(f"Event flags: {counts}; unclassified: {result['unclassified_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
