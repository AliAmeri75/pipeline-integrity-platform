# Pipeline Integrity Research Platform

A unified Streamlit gateway to three applications developed from the pipeline
integrity doctoral research of Mohammadali Ameri with Yong Li at the University
of Alberta.

## Research modules

1. **Fixed inspection scheduling** — links to the existing deployed application
   for multiple pipe joints (Journal Papers 3 and 5).
2. **Dynamic RL planning** — introduces and links to the maintenance-only and
   inspection-and-maintenance reinforcement-learning application (Journal Paper 4).
3. **Reliability and value of information** — runs the Journal 2 prior and
   pre-posterior analysis using approved NPZ datasets synchronized from a public
   Google Drive folder or uploaded directly by the user.

The first two repositories remain independent and operational. This platform
provides their common introduction and navigation without duplicating their
scientific code. The Journal 2 calculation is included directly because its
large data arrays are stored separately.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy

Deploy `streamlit_app.py` from the repository root on Streamlit Community Cloud.
No secret is required for a publicly readable Drive folder. The first Journal 2
run after an app restart must synchronize the required data.

## Journal 2 data

`Cost_parallel.py`, `journal2_engine.py`, and the user interface are stored in
this repository. Only data arrays are downloaded from Drive. See
[`docs/JOURNAL2_DATA_GUIDE.md`](docs/JOURNAL2_DATA_GUIDE.md) for access,
filenames, validation, privacy, and capacity guidance.

## Existing applications

- <https://github.com/AliAmeri75/pipeline-inspection-app>
- <https://github.com/AliAmeri75/pipeline-rl-planning>
- <https://github.com/AliAmeri75/pipeline_reliability_J2>
