# 🏰 Das Schloss — ScholarTrace

Explore a researcher's publications, collaborators, and academic journey.
Runs on your computer, retrieves data online from OpenAlex, and supports English and Chinese.

## Quick start

**You need:** Git, Python 3.12 (recommended), and an internet connection. The commands below are for macOS / Linux.

**1. Download and start the app:**

```bash
git clone https://github.com/Bezel808/Das-Schloss.git
cd Das-Schloss
./run.sh
```

The script creates a Python environment, installs the locked dependencies, and starts the server. Keep this terminal open.

**2. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).**

**3. Open Settings, enter your [OpenAlex API key](https://openalex.org/settings/api), and search for a researcher.**

Use a name, ORCID, or OpenAlex author ID. Check the institution before opening a profile. Switch between **English / 中文** at the top of the page.

To stop the app, press **Ctrl+C** in the terminal. To start it again, run `./run.sh` from the project folder. Enter your key again after restarting; it is kept only in server memory. Open the local website, rather than the HTML file directly.

<details>
<summary>Already installed? Start without reinstalling dependencies</summary>

```bash
.venv/bin/python -m uvicorn scholartrace.server:app --host 127.0.0.1 --port 8000
```

If port 8000 is already in use, use `--port 8001` and open `http://127.0.0.1:8001`.

</details>

## What you can explore

- **Timeline:** publications, authorship roles, topics, and publication-time affiliations by year.
- **Collaboration network:** weighted coauthorship, colored communities, year playback, and filters explaining what each link represents. Click a link to inspect its papers.
- **Teams & newcomers:** collaboration subgroups, first-time collaborators, early-career publication histories, and continued collaboration. Missing member histories are fetched when you start an analysis.
- **Paper search:** BM25 keyword retrieval over the researcher's collected titles, abstracts, and topics. No language model or LLM API key is needed.
- **Annual statistics:** publication activity, network position, partner retention, and citation indicators within the collected corpus.
- **Exports:** paper and analysis data as JSON, annual panels, and collaboration graphs as SVG.

The **About** button explains the methods, their original sources, and how to interpret the results. Source names, paper titles, and abstracts remain in their original language.

## Data and interpretation

OpenAlex supplies the publication records. Check author identity, coverage, and missing-data notices before interpreting a result. ORCID search matches OpenAlex records; it does not import an ORCID CV.

Coauthorship is evidence of joint publication, not proof of supervision, employment, or lab membership. Newcomer analysis uses observed publication histories, not verified student status. Historical views reconstruct publication years from today's metadata; they are not archived database snapshots. Corpus-based citation indicators are not Google Scholar totals.

The collaboration graph uses the focal researcher's papers. The member graph in Teams & newcomers instead uses member papers without the focal researcher. Their different evidence boundaries matter when comparing subgroups or network positions. Papers with more than 200 authors remain in the evidence list but are excluded from network and annual calculations; coverage notices report exclusions.

By default, queries and results stay in bounded server memory; source data has a 512 MiB cap and is cleared after 30 minutes of inactivity or a restart. Export anything you want to keep. Setting `SCHOLARTRACE_DB` explicitly enables a separate, file-backed research mode. `OPENALEX_API_KEY` can optionally supply the key through the environment.

This is a single-user local app. Public hosting requires authentication, user isolation, and resource quotas. Relationship inference has been removed from the website; retained research code and experimental benchmarks are not personal predictions.

## Methods and engineering notes

Detailed notes are currently in Chinese:

- [Method references](docs/methods.md) and [temporal-network foundations](docs/research-foundation.md)
- [Teams & newcomers](docs/group-cohorts.md) and [annual statistics](docs/annual-insights.md)
- [On-demand retrieval and computation](docs/on-demand-computation.md)
- [Search, animated background, and rendering fallback](docs/search-and-visuals.md)
- [English / Chinese interface](docs/language-support.md)
- [Forecast benchmarks and reproduction](docs/forecast-validation.md)
- [Archived relationship-inference evaluation](docs/relationship-inference.md)
- [Research protocol and outstanding work](research/protocols/goal-and-review.md)
- [Original vision — not a list of current features](docs/original-vision.md)

## Development checks

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check scholartrace/static/app.js
```

Browser checks require Playwright, Chrome / Chromium, and a running local server. The bilingual UI check uses bundled fixtures and does not require an API key:

```bash
.venv/bin/python -m tests.browser_i18n
```

The broader `tests/browser_smoke.py` check requires two previously collected researcher profiles. See the test files for browser paths and prerequisites. Controlled fixtures test application behavior, not live upstream coverage or scientific prediction quality.

## Offline CLI

```bash
.venv/bin/python -m scholartrace --input examples/synthetic.json --author https://openalex.org/A1
```

This example uses fictional data for testing.
