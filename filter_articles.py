"""Filter harvested titles/abstracts using configured keyword strengths and buckets."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unicodedata


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag.split(":")[-1] in {"p", "br", "div", "title", "sec"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        self.handle_starttag(tag, [])


def normalize(text):
    parser = PlainText()
    parser.feed(text or "")
    parser.close()
    text = unicodedata.normalize("NFKC", "".join(parser.parts)).casefold()
    text = "".join(" " if unicodedata.category(char) == "Pd" else char for char in text)
    return " ".join(text.split())


def compile_keywords(config):
    compiled = []
    seen = set()
    for item in config["keywords"]:
        keyword, strength, bucket = item["keyword"], item["strength"], item["bucket"]
        normalized = normalize(keyword)
        if not normalized or strength not in {"strong", "weak"} or not bucket:
            raise ValueError(f"Invalid keyword configuration: {item!r}")
        if normalized in seen:
            raise ValueError(f"Duplicate normalized keyword: {keyword}")
        seen.add(normalized)
        compiled.append((item, re.compile(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)")))
    return compiled


def evaluate(article, keywords):
    fields = {field: normalize(article.get(field)) for field in ("title", "abstract")}
    matches = []
    for item, pattern in keywords:
        matched_fields = [field for field, text in fields.items() if pattern.search(text)]
        if matched_fields:
            matches.append(dict(item, fields=matched_fields))
    strong_title = [m["keyword"] for m in matches if m["strength"] == "strong" and "title" in m["fields"]]
    weak = [m["keyword"] for m in matches if m["strength"] == "weak"]
    buckets = sorted({m["bucket"] for m in matches})
    rules = []
    if strong_title:
        rules.append("strong_keyword_in_title")
    if len(weak) >= 2:
        rules.append("two_distinct_weak_keywords")
    if len(buckets) >= 2:
        rules.append("keywords_from_two_buckets")
    return {"rules": rules, "matches": matches, "buckets": buckets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/articles_recent.json"))
    parser.add_argument("--config", type=Path, default=Path("data/literature_keyword_filter.json"))
    parser.add_argument("--output", type=Path, default=Path("data/articles_filtered.json"))
    args = parser.parse_args()
    if args.output.resolve() in {args.input.resolve(), args.config.resolve()}:
        parser.error("Output must differ from input and keyword configuration")
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        keywords = compile_keywords(config)
        retained = []
        for article in data["articles"]:
            evidence = evaluate(article, keywords)
            if evidence["rules"]:
                retained.append(dict(article, filter_match=evidence))
        result = {
            "filtered_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_file": str(args.input), "config_file": str(args.config),
            "keyword_config": config,
            "matching_note": "Distinct configured keywords; case-insensitive whole words/phrases; hyphens and spaces equivalent; markup removed for matching; no stemming. Only title and abstract searched. Source records remain separate.",
            "input_record_count": len(data["articles"]),
            "record_count": len(retained),
            "source_counts": dict(Counter(a.get("source", "unknown") for a in retained)),
            "rule_counts": dict(Counter(rule for a in retained for rule in a["filter_match"]["rules"])),
            "harvest_metadata": {k: v for k, v in data.items() if k != "articles"},
            "articles": retained,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Filter failed: {exc}", file=sys.stderr)
        return 1
    print(f"Retained {len(retained)} of {len(data['articles'])} records; saved to {args.output}")
    print(f"By source: {result['source_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
