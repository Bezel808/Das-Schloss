<div align="center">

# 🏰 Das Schloss

**TRACE THE WORK. UNDERSTAND THE JOURNEY.**

Explore the people, papers, and collaborations behind an academic life.

**OpenAlex** · **ORCID search** · **Temporal networks** · **No LLM required** · **EN / 中文**

[Get started](#quick-start) · [Explore](#a-researchers-journey-in-six-views) · [Methods](#built-on-established-methods)

</div>

---

> “Nothing could be seen of Castle Hill; mist and darkness surrounded it.”
>
> — Franz Kafka, *The Castle*, Chapter I. [German original](https://de.wikisource.org/wiki/Das_Schlo%C3%9F/Das_erste_Kapitel); English translation for this project.

A publication list records the work. The connections between its entries reveal a journey: recurring collaborators, new research topics, and the arrival of new people.

Named after Kafka’s *The Castle*, **Das Schloss — ScholarTrace** brings those connections into view. Start with one researcher, follow their publications through time, and explore the collaboration patterns behind them. Every coauthorship link leads back to its supporting papers.

Runs on your computer. Retrieves records online. Keeps you close to the evidence.

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

<a id="a-researchers-journey-in-six-views"></a>

## A researcher’s journey, in six views

| Explore | What you can discover |
| :--- | :--- |
| **01 · Timeline** | Follow publications, topics, authorship roles, and publication-time affiliations year by year. |
| **02 · Collaboration network** | Explore weighted links and colored communities. Replay the years, filter relationships, and open the papers behind each connection. |
| **03 · Teams & newcomers** | See collaboration subgroups, first-time collaborators, and early-career publishing patterns. Member histories are fetched when you start an analysis. |
| **04 · Paper search** | Find relevant papers across collected titles, abstracts, and topics with BM25 keyword search. No language model to configure. |
| **05 · Annual statistics** | Track publication activity, network position, partner retention, and citation indicators within the collected corpus. |
| **06 · Take it with you** | Export paper records, annual panels, and analysis data as JSON, or save collaboration graphs as SVG. |

**A good first exploration:** search for someone whose work you know → open their timeline → choose a year → inspect a collaboration → read the supporting paper.

The interface supports **English and Chinese**. Researcher names, paper titles, and abstracts stay in their original language.

## Built on established methods

The project draws on bibliometrics, network science, and information retrieval:

- **CoAuthra** inspires the interactive collaboration-map experience.
- **Newman’s fractional coauthorship weights** account for paper team size; **Louvain** identifies collaboration communities.
- **Team-assembly research** informs the distinction between newcomers, existing members, and repeated collaborations.
- **Community-role measures and Burt’s structural holes** describe network position within the observed data.
- **BM25** ranks keyword matches in the collected paper corpus.

Open **About → Algorithmic inspirations & sources** in the app for original references and a description of each adaptation. The [method notes](docs/methods.md), [team analysis](docs/group-cohorts.md), and [network foundations](docs/research-foundation.md) provide further detail.

## Reading the evidence

Coauthorship documents joint publication. It does not establish supervision, lab membership, or a person’s prospects. Check identity and data coverage, then follow the links back to the papers.

<details>
<summary><strong>Data coverage, graph boundaries, and interpretation</strong></summary>

OpenAlex supplies the publication records. Check author identity, coverage, and missing-data notices before interpreting a result. ORCID search matches OpenAlex records; it does not import an ORCID CV.

Coauthorship is evidence of joint publication, not proof of supervision, employment, or lab membership. Newcomer analysis uses observed publication histories, not verified student status. Historical views reconstruct publication years from today's metadata; they are not archived database snapshots. Corpus-based citation indicators are not Google Scholar totals.

The collaboration graph uses the focal researcher's papers. The member graph in Teams & newcomers instead uses member papers without the focal researcher. Their different evidence boundaries matter when comparing subgroups or network positions. Papers with more than 200 authors remain in the evidence list but are excluded from network and annual calculations; coverage notices report exclusions.

</details>

<details>
<summary><strong>Local storage and deployment</strong></summary>

By default, queries and results stay in bounded server memory; source data has a 512 MiB cap and is cleared after 30 minutes of inactivity or a restart. Export anything you want to keep. Setting `SCHOLARTRACE_DB` explicitly enables a separate, file-backed research mode. `OPENALEX_API_KEY` can optionally supply the key through the environment.

This is a single-user local app. Public hosting requires authentication, user isolation, and resource quotas. Relationship inference has been removed from the website; retained research code and experimental benchmarks are not personal predictions.

</details>

## Further reading

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

## For developers

<details>
<summary><strong>Run the checks</strong></summary>

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check scholartrace/static/app.js
```

Browser checks require Playwright, Chrome / Chromium, and a running local server. The bilingual UI check uses bundled fixtures and does not require an API key:

```bash
.venv/bin/python -m tests.browser_i18n
```

The broader `tests/browser_smoke.py` check requires two previously collected researcher profiles. See the test files for browser paths and prerequisites. Controlled fixtures test application behavior, not live upstream coverage or scientific prediction quality.

</details>

<details>
<summary><strong>Use the offline CLI</strong></summary>

```bash
.venv/bin/python -m scholartrace --input examples/synthetic.json --author https://openalex.org/A1
```

This example uses fictional data for testing.

</details>

---

<div align="center">

**Every paper is a point on a longer journey.**

[Start exploring](#quick-start) · [Report an issue](https://github.com/Bezel808/Das-Schloss/issues)

</div>
