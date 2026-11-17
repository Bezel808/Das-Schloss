# 🏰 Das Schloss (Project K.)

> *"It was late evening when K. arrived. The village lay deep in snow. There was nothing to be seen of Castle Hill, for mist and darkness surrounded it..."*
> — Franz Kafka, *Das Schloss* (1926)

**Mapping Kafka’s *Castle* of academia: decode collaboration networks and find your research trajectory at any stage.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Data: OpenAlex](https://img.shields.io/badge/Data-OpenAlex%20API-orange.svg)](https://openalex.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

---

## 🧭 Why *Das Schloss*?

For a research rookie, entering academia often feels like stepping into Franz Kafka’s *The Castle*.

You stand at the foot of a towering, opaque bureaucracy. Everyone seems to know the unwritten rules—who collaborates with whom, how lab hierarchies actually operate, and which path leads to the summit—while you don't even have a map. Worse still, conventional "survivor-bias" advice makes it feel as though missing a single early milestone means it is already too late.

**Das Schloss** is an open-source **academic trajectory explorer and collaboration network analyzer**. Like Land Surveyor K., our goal is not to tear down the Castle, but to **measure it, map its hidden corridors, and prove that it is never too late to chart a path that fits you.**

---

## ✨ Core Features

### 1. 🗺️ The Map — Collaboration Topology & Lab Transparency
Look beyond citation counts and h-indices to see how a research group actually functions:
* **Co-authorship Network Visualization**: Reveals whether a lab operates as a *centralized hub* (single-PI bottleneck) or a *distributed mesh* (high peer-to-peer collaboration).
* **Rookie-Friendliness Metrics**:
  * **First-Author Ratio**: Percentage of group publications led by students/junior researchers.
  * **Time-to-First-Paper**: Median time from a newcomer's first appearance in a group to their first core publication.
  * **Openness Index**: Ratio of cross-institutional and interdisciplinary collaborations.

### 2. 🧭 The Compass — Non-Linear Trajectory Matching
Break free from the anxiety of "falling behind" by matching your current state against real historical trajectories:
* **State-Vector Retrieval**: Input your current stage, domain shift, or constraints (e.g., late start, interdisciplinary pivot, industry-to-academia transition).
* **Empirical Path Recall**: Retrieves real researchers whose *early publication signatures* resemble your current baseline, visualizing their 3-, 5-, and 10-year evolution.
* **The Late-Bloomer Index**: Curated longitudinal profiles of researchers who published their breakthrough work later in their careers or after major domain switches.

### 3. 📖 Village Notes — Demystifying Unwritten Rules
A community-driven, structured Markdown knowledge base turning tacit academic intuition into actionable checklists:
* Cold-email frameworks tailored to lab archetypes (Junior AP vs. Senior Chair).
* Step-by-step protocols for reproducing baselines, evaluating lab fit, and pivoting research directions gracefully.

---

## 🏗️ Architecture & Tech Stack

Designed to be lightweight, reproducible, and zero-cost to deploy using open scholarly metadata:

* **Data Layer**: [OpenAlex API](https://openalex.org/) & [Semantic Scholar API](https://www.semanticscholar.org/product/api) (100% open metadata, no scraping required).
* **Graph & Matching Engine**: Python (`NetworkX`, `scikit-learn`, `PyTorch Geometric`) for structural feature extraction and trajectory embedding similarity.
* **Visualization**: Interactive web frontend (`Next.js` + `D3.js` / `ECharts`) deployable on Vercel or GitHub Pages.

---

## 🚀 Quick Start (Local Prototype)

```bash
# 1. Clone the repository
git clone [https://github.com/Bezel808/Das-Schloss.git](https://github.com/Bezel808/Das-Schloss.git)
cd Das-Schloss

# 2. Set up the environment
conda create -n das-schloss python=3.10 -y
conda activate das-schloss
pip install -r requirements.txt

# 3. Fetch sample collaboration graph & compute rookie metrics
python scripts/fetch_graph.py --author "Sample Researcher" --depth 2
