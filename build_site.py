"""Build a static, searchable page from the screened article artifact."""

import argparse
from html import escape
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from filter_articles import PlainText


LABELS = {"first_preprint_version": "First preprint version", "preprint_revision": "Preprint revision",
          "correction_notice": "Correction notice", "retraction_notice": "Retraction notice",
          "expression_of_concern": "Expression of concern", "unclassified": "Unclassified"}


def plain(value):
    parser = PlainText()
    parser.feed(value or "")
    parser.close()
    return " ".join("".join(parser.parts).split())


def card(article):
    title = escape(plain(article.get("title")) or "Untitled article")
    url = article.get("url") or ""
    if urlsplit(url).scheme in {"http", "https"}:
        title = f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{title}</a>'
    records = article.get("source_records", [article])
    sources = article.get("sources", [article.get("source", "unknown")])
    flags = article.get("event_flags") or ["unclassified"]
    matches = sorted({m["keyword"] for r in records for m in r.get("filter_match", {}).get("matches", [])})
    buckets = sorted({b for r in records for b in r.get("filter_match", {}).get("buckets", [])})
    search_text = " ".join(plain(r.get(field)) for r in records for field in ("title", "abstract", "authors", "doi"))
    search_text += " " + " ".join(matches)
    attributes = " ".join(f'data-{key}="{escape(value, quote=True)}"' for key, value in {
        "search": search_text.casefold(), "sources": " ".join(sources),
        "flags": " ".join(flags), "buckets": " ".join(buckets)}.items())
    badges = " ".join(f'<span class="badge">{escape(LABELS.get(flag, flag))}</span>' for flag in flags)
    abstract = escape(plain(article.get("abstract")) or "No abstract supplied by this source.")
    provenance = "".join('<li>' + escape(" · ".join(filter(None, [
        r.get("source"), r.get("date"), f"v{r['version']}" if r.get("version") else None,
        r.get("doi") or r.get("source_id")]))) + '</li>' for r in records)
    return f'''<article class="paper" {attributes}>
<div class="paper-meta">{escape(article.get('date') or 'Date unavailable')} · {escape(' / '.join(sources))}</div>
<h2>{title}</h2><div class="badges">{badges}</div>
<p class="authors">{escape(plain(article.get('authors')))}</p>
<p class="matches"><strong>Matched:</strong> {escape(', '.join(matches))}</p>
<details><summary>Abstract and source details</summary><p class="abstract">{abstract}</p>
<p>{escape(article.get('journal') or '')}</p><ul>{provenance}</ul></details></article>'''


def render(data):
    articles = data["articles"]
    harvest = data.get("input_metadata", {}).get("harvest_metadata", {})
    timestamp = harvest.get("requested_at_utc", data["prepared_at_utc"])
    sources = sorted({s for a in articles for s in a.get("sources", [])})
    buckets = sorted({b for a in articles for r in a.get("source_records", [a])
                      for b in r.get("filter_match", {}).get("buckets", [])})
    def options(values):
        return "".join(f'<option value="{escape(v, quote=True)}">{escape(LABELS.get(v, v.replace("_", " ")))}</option>' for v in values)
    template = Path("web/template.html").read_text(encoding="utf-8")
    values = {
        "COUNT": str(len(articles)), "TIMESTAMP": escape(timestamp),
        "WINDOW": escape(f"{harvest.get('query_start_date', '?')} – {harvest.get('query_end_date', '?')}"),
        "SOURCE_OPTIONS": options(sources), "FLAG_OPTIONS": options(LABELS),
        "BUCKET_OPTIONS": options(buckets),
        "CARDS": "\n".join(card(a) for a in sorted(articles, key=lambda a: a.get("date") or "", reverse=True)),
    }
    # One substitution pass keeps source text from being treated as a template.
    import re
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda match: values[match[1]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/articles_screening.json"))
    parser.add_argument("--output", type=Path, default=Path("_site"))
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    html = render(data)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "index.html").write_text(html, encoding="utf-8")
    for name in ("style.css", "app.js"):
        shutil.copyfile(Path("web") / name, args.output / name)
    shutil.copyfile(args.input, args.output / "articles.json")
    (args.output / ".nojekyll").touch()
    print(f"Built {len(data['articles'])} articles into {args.output}")


if __name__ == "__main__":
    main()
