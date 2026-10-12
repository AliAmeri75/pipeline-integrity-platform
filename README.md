# ALIRIM

**Asset Lifecycle Intelligence for Risk & Integrity Management**

A unified Streamlit gateway for the Pipeline Integrity Research Platform,
developed from the doctoral research of Mohammadali Ameri with Yong Li at the
University of Alberta.

## Platform structure

```text
ALIRIM — Asset Lifecycle Intelligence for Risk & Integrity Management
├── Home and research overview
├── Data Integration
│   ├── Try a fully synthetic sample or upload a TCAT/Psqr profile workbook
│   ├── Inspect 2D depth maps and axial maximum-depth profiles
│   └── Export feature size and location summaries to Excel or CSV
├── Educational Tutorial
│   ├── Guided failure-pressure calculation
│   ├── Probability-density plots and Monte Carlo POF
│   └── Maintenance interpretation and knowledge check
├── Static Multiple Inspection and Excavation Planning
│   ├── Integrated introduction
│   └── Open standalone simulation directly
├── Dynamic Inspection and Maintenance Planning
│   ├── Introduction
│   └── Open independent application
├── Static Single Delayed Inspection Planning — Journal 2
│   ├── Introduction
│   └── Open independent application
└── Publications, documentation and team
```

Each scientific application has its own GitHub repository and Streamlit
deployment. This repository provides a consistent gateway, documentation, and
new-tab launch links. The `education/` folder contains a deliberately small,
transparent learning model adapted from the inspection repository so students can
understand the path from ILI measurements to POF before opening the full research
applications. The Data Integration page prepares grid-profile measurements for those
planning workflows without modifying the source workbook. The preferred Static Multiple Inspection and Excavation Planning introduction is
included here, and its button opens the
standalone simulation directly so users do not pass through two introductions.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy

Deploy `streamlit_app.py` from the repository root on Streamlit Community Cloud.
No secret or large scientific dataset is required by this gateway. Each launch
page opens the corresponding independently deployed research application in a new
tab, avoiding Streamlit's cross-origin frame restriction.

## Editable content

- [`content/PLATFORM_ABSTRACT.md`](content/PLATFORM_ABSTRACT.md) controls the
  short research overview on the home page.
- [`content/PUBLICATIONS.md`](content/PUBLICATIONS.md) controls selected journal
  and conference publications.
- [`content/DOCUMENTATION.md`](content/DOCUMENTATION.md) controls application
  links, documentation, and editing guidance.

## Existing applications

- <https://github.com/AliAmeri75/pipeline-inspection-app>
- <https://github.com/AliAmeri75/pipeline-rl-planning>
- <https://github.com/AliAmeri75/pipeline_reliability_J2>
