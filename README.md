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
│   ├── Try sample crack profile data or upload a TCAT/Psqr profile workbook
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

## Standalone Reliability Analysis

Under **Maintenance Planning (Cracks/Corrosion) → Reliability Analysis**, calculate
feature Pf and map fixed 1 km sections with consequences and risk, without running any scheduling
study. The page includes a fictional 100 km Alberta route and crack CSV, route
drawing/GeoJSON upload, CSV defect input, and prepared profiles from Data Exploration.
Enter feature positions as km from the selected route's first point. Shared pipe
geometry and material inputs must match the entered profiles.

The crack-only CorLAS screening mode calculates Pf for the specified geometry and
loading condition. It is a snapshot, not an annual probability: it includes no
growth, initiation, repair, inspections, or cost optimization. Positive truncated
normal sampling is used for crack depth/length, wall thickness, pressure and model
factor. Other material inputs are fixed. Leakage means sampled depth ≥ sampled
WT; burst applies to non-through-wall samples and compares pressure against
CorLAS resistance. Shared WT, pressure and model-factor draws capture dependence
between cracks in one joint; their failures are combined sample by sample.

For corrosion, or annual probabilities from another model, use **Import
crack/corrosion Pf** with `feature_id`, `defect_type` (Crack/Corrosion),
`chainage_km`, `burst_pf`, and `leak_pf`. State the probability basis and period.
No corrosion failure model is assumed. Imported feature events are assumed
independent, including within a joint; use caution if your source model includes
dependence. Do not mix periods or probability definitions in one upload.

Sections are fixed from the route start: [0,1), [1,2), and onward. The last
section can be shorter; a feature at the route endpoint belongs to the final
section. Each feature belongs to exactly one section by chainage. When a joint
crosses a section boundary, only that section's feature failure samples contribute
to its Pf. This retains within-joint dependence without duplicating a defect.
Joint events within each section use the independent series combination
`1 - product(1 - joint Pf)`.

Download a route-specific consequence CSV template or upload CSV/Excel containing
`section_id`, `burst_consequence`, `leak_consequence`; optional `start_km`/`end_km`
must match the current route. Every section must have exactly one row. Values must
be finite and nonnegative; zero explicitly means no consequence in the selected
metric, while missing values are rejected. Enter conditional section-level loss
if a mode occurs, not probability-weighted cost. Both modes must share a common
unit (e.g. CAD) and a consistent valuation basis. Sample costs are invented for
demonstration and are not location-specific estimates.

`burst_risk = burst_pf * burst_consequence`, likewise for leakage, and total risk
is their sum. Consequences must be additive without double counting common losses.
Risk is expected loss over the stated probability basis: CAD/year only for
imported annual Pf, otherwise CAD per stated assessment. No annual claim is made
for the snapshot crack model.

Three step plots display POF, consequence and risk against route distance.
The map selector switches POF/consequence/risk and burst/leakage (or total risk).
A numeric green-yellow-red legend scales from zero to the selected Pf limit for
POF, and to the displayed maximum for consequences/risk. The latter are relative
colours, not regulatory risk categories. The separate `pof_category`
column uses the selected burst/leakage screening limits. Default limits of
0.001/0.01 do not claim CSA compliance. Unknown defects are not included; green
does not establish overall safety. Monte Carlo zeros are not proof of zero Pf.
Downloads carry units, probability basis and period. Input changes invalidate
saved results; display switches retain them without rerunning Monte Carlo.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy

Deploy `streamlit_app.py` from the repository root on Streamlit Community Cloud.

## Configure the ALIRIM Assistant

The assistant uses the OpenAI Responses API. A ChatGPT subscription does not
automatically provide API access; configure a separate OpenAI project API key.

1. Create a dedicated project and API key in the OpenAI Platform.
2. Set a conservative project budget and usage limits before making the chatbot public.
3. In Streamlit Community Cloud, open **Manage app → Settings → Secrets**.
4. Copy the fields from `.streamlit/secrets.example.toml` and replace only the API-key placeholder.
5. Save the secrets and reboot the Streamlit app.
6. Open **ALIRIM Assistant** from the app navigation and test a concept and a navigation question.

Never commit `.streamlit/secrets.toml` or a real API key. The public assistant also
limits prompt length, response length, and the number of questions per browser session.
The core gateway and research launch pages do not require a secret or a large
scientific dataset; only the optional ALIRIM Assistant requires the OpenAI API
secret described above. Each launch page opens the corresponding independently
deployed research application in a new tab, avoiding Streamlit's cross-origin
frame restriction.

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
