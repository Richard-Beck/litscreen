# litscreen

A daily, keyword-screened literature page built from bioRxiv, Europe PMC, and
Crossref. The workflow harvests, filters, deduplicates, flags publication events,
and publishes a static GitHub Pages artifact. Generated lists are never committed.

Repository: https://github.com/Richard-Beck/litscreen

Site: https://richard-beck.github.io/litscreen/

Daily refresh is scheduled for **03:00 America/New_York** (Eastern time,
automatically following daylight saving time). Pushes to `main` and the workflow's
**Run workflow** button also trigger a fresh build. GitHub can delay scheduled
runs. The page displays the actual last harvest time and a stale-data notice
after 36 hours. If one source fails, completed sources still publish; the page
lists the missing source and the JSON records its error. If every source fails,
the job fails and the last deployment remains available.

In repository **Settings → Pages**, the publishing source must be **GitHub
Actions**. The workflow uses the built-in token and needs no API keys. Its
deployment job has Pages/OIDC write permissions; it has no repository-content
write permission and never pushes generated data to a branch.

GitHub disables schedules in public repositories after 60 days without
repository activity. If this occurs, re-enable the workflow in the Actions tab.
See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

`data/literature_keyword_filter.json` is the only tracked file under `data/`.
It is the editable filter configuration, not a generated list. All other data,
the `_site/` build directory, and local tools are ignored. The deployed artifact
contains the page and a downloadable copy of the screened JSON.

To refresh and preview locally:

```powershell
python fetch_articles.py
python filter_articles.py
python prepare_screening.py
python build_site.py
python -m http.server 8000 --directory _site
```

Open http://localhost:8000. No JavaScript build tools or Python dependencies are
required. Search and filters run in the browser; article text is rendered as
escaped plain text. All original source records remain in the JSON download.

Fetch recent bioRxiv, Europe PMC, and Crossref metadata with Python 3.9+.
No dependencies or API key are needed.

```powershell
python fetch_articles.py
```

Writes `data/articles_recent.json`, replacing the previous successful result
only after all selected sources finish. The JSON contains query details,
counts per source, and an `articles` list with source identifiers, title, DOI,
authors, date, abstract, keywords, subjects, and a link when available.
Source-specific fields include bioRxiv version/category and journal names.
Missing scalar fields are null and missing keywords/subjects are empty lists.
Abstracts and titles retain any markup supplied by the source.

```powershell
python fetch_articles.py --hours 48 --output data/articles_48h.json
python fetch_articles.py --sources europe_pmc crossref
```

The default lookback is 24 hours, approximated by the inclusive calendar dates
overlapping that UTC window. Publication dates lack exact times; records may
be older than 24 hours, and delayed indexing means this is not a complete feed
of everything published during the window. The sources use these filters:

| Source | Date and scope | Keywords/subjects |
| --- | --- | --- |
| [bioRxiv](https://api.biorxiv.org/) | Posting date, including revisions | Category; no keywords |
| [Europe PMC](https://europepmc.org/RestfulWebService) | `FIRST_PDATE`, earliest publication date, all matching records | Keywords and MeSH descriptors when available |
| [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/) | `from-pub-date` / `until-pub-date`, journal articles across all subjects | Subject labels when deposited; no keyword field |

Crossref print and online dates are also saved. Europe PMC can supply inferred
dates when publication metadata is incomplete. These queries target publication
or posting dates, not when a record was added to an index.

All pages are retrieved, with up to six attempts per request for transient
network failures, invalid JSON, and invalid bioRxiv/Europe PMC response envelopes.
Retries stay on the failed page, with waits of 5, 10, 20, 40, and 60 seconds;
exhausted retries mark that source as failed. Only fully harvested source
results are included; partial pages from a failed source are discarded.
Each source is
fetched concurrently with the others, with sequential requests within a source.
Duplicates are removed within a source by its identifier (DOI/version for
bioRxiv); overlaps across sources remain separate for development/comparison.
The total is therefore a source-record count, not a unique-paper count.

The original bioRxiv-only command remains available:

```powershell
python fetch_biorxiv.py
```

It writes `data/biorxiv_recent.json` as before.

Run offline checks with `python -m unittest discover -s tests`.

Filter the harvested records using `data/literature_keyword_filter.json`:

```powershell
python filter_articles.py
```

Writes `data/articles_filtered.json`. Retains records satisfying any rule:

- At least one strong keyword in the title.
- At least two distinct weak keywords in the title and/or abstract.
- Keywords from at least two different buckets in the title and/or abstract,
  regardless of strength.

Matching ignores case and markup, treats hyphens and spaces as equivalent,
and uses whole words/phrases without stemming or inferred synonyms. Repeated
occurrences of one keyword count once. Only configured keywords are used.
Each retained record includes matching keywords, fields, buckets, and rules.
Source overlaps are preserved, and rule counts can overlap. Override paths
with `--input`, `--config`, and `--output`.

Prepare the filtered set for screening:

```powershell
python prepare_screening.py
```

Writes `data/articles_screening.json`, consolidating exact normalized DOI
matches. Records without a DOI match only on an identical source/database/ID;
records without either identifier stay separate. Different preprint and journal
DOIs are not linked by title. Each article retains all original `source_records`,
including version-specific metadata and keyword evidence. Top-level fields use
the latest bioRxiv version if available, otherwise the record with the longest
abstract.

Flags identify bioRxiv first versions/revisions and explicit notice-style title
prefixes (correction, corrigendum, erratum, retraction, expression of concern).
These conservative flags can miss notices with other titles. Unflagged journal
articles remain `unclassified`; no new-publication status is inferred from
indexing or metadata update dates. Flagged records stay in the output, and no
date-based exclusions are added. Counts of flags may overlap.
