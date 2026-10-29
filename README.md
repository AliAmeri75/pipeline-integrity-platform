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

## Preliminary Analysis

Under **Maintenance Planning (Cracks/Corrosion) → Preliminary Analysis**, switch
between **Deterministic Analysis**, **Risk & Reliability** and **Consequence Assessment**.
There is no separate Reliability Analysis sidebar entry.

The deterministic tab calculates resistance and FPR for each measured crack
without Monte Carlo, POF controls or probability outputs. FPR is unadjusted burst
resistance divided by operating pressure. Click a result-table row or FPR plot
point to select the defect and view its measured geometry on a 3D pipe, using
the same renderer as Data Exploration. A linked measured 2D/3D view is also
available. The lowest calculated FPR is summarized for each represented nominal
1 km section; this is not a segment reliability calculation or proof of safety.
No route endpoint is inferred from the profile workbook. Unsupported corrosion
resistance remains unavailable; corrosion geometry can still be visualized.

In the **Risk & Reliability** tab, calculate
feature Pf and map fixed 1 km sections with consequences and risk, without running any scheduling
study. The page includes a fictional 100 km Alberta route and crack CSV, route
drawing/GeoJSON upload, CSV defect input, and prepared profiles from Data Exploration.
Enter feature positions as km from the selected route's first point. Shared pipe
geometry and material inputs must match the entered profiles.

The crack-only CorLAS screening mode calculates Pf for the specified geometry and
loading condition. It is a snapshot, not an annual probability: it includes no
growth, initiation, repair, inspections, or cost optimization. The sidebar offers
collapsible Pipe Geometry, Operating Pressure, Material Properties, Resistance
Model Uncertainty, Crack Sizing and POF Simulation groups. Each parameter card
keeps distribution, mean and SD together; crack means come from each defect row.
Choose Deterministic, Normal, Lognormal or Gumbel distributions. Defaults mirror
the fixed-inspection model: diameter 20 in deterministic; WT 6.35/0.6 mm Normal;
pressure 936/20.0304 psi Gumbel; yield strength 57200/2002 psi Normal; ultimate
strength 73920/2587.2 psi Normal; E 210/8.4 GPa Normal; Charpy mean 85 and SD
`0.0223*85^1.46` Lognormal; model factor 1.27/0.21 Normal; crack depth/length SDs
0.74/15.6 mm Normal. These are research defaults, not calibration for your asset.

All entered means and SDs are arithmetic moments. Nonpositive random values are
resampled; this truncation can change realized moments. Lognormal/Gumbel moments
are transformed to their distribution parameters. Strength ordering and a positive
pipe bore are enforced by resampling incompatible joint draws. Pipe, material and
load samples are shared within each joint; crack dimensions are independent.
Joints remain independent in the section survival aggregation. Diameter can be
made uncertain, but its default SD remains zero because the scheduling model fixes
it. Export JSON settings for reproducibility; reset restores the reference values.
The active engine is `probabilistic_reliability_model.py`.

Leakage means sampled depth ≥ sampled
WT; burst applies to non-through-wall samples and compares pressure against
CorLAS resistance. Shared pipe/material/pressure draws capture dependence
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

### Consequence Assessment workspace

Open **Preliminary Analysis → Consequence Assessment** after selecting a route
in the Risk & Reliability tab.
Choose separate burst and leakage scenarios:

- **Natural-gas PIR**, burst only: `r_m = 0.3048 * 0.69 * nominal_diameter_in * sqrt(MAOP_psi)`.
  Source: [49 CFR 192.903](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-D/part-192/subpart-O/section-192.903).
  This is the US natural-gas rupture screening equation, not a leakage, fatality,
  full HCA designation or Canadian compliance calculation.
- **Point-source thermal radiation**: `r_m = sqrt(chi * Q_MW * 1000 / (4*pi*q_kW_m2))`.
  Source: McGrattan, Baum and Hamins (2000), [NISTIR 6546, Eq. 7](https://www.govinfo.gov/content/pkg/GOVPUB-C13-fa5a24c9e669a385816318793faac823/pdf/GOVPUB-C13-fa5a24c9e669a385816318793faac823.pdf).
  Atmospheric attenuation is neglected. Supply a credible fire heat-release
  rate and radiant fraction. This far-field approximation does not infer a
  pipeline release rate, flame geometry or transient jet-fire behaviour.
- **User-defined radius** from an independently assessed scenario.

CSV/Excel templates contain one row per section with local population density
(people/km²), asset value per m² and separate fixed burst/leak incident costs.
Optional mode-prefixed columns override numeric scenario inputs for each section.
Blank inputs are rejected. Defaults are illustrative, including costs and density.
No census or GIS population layer is automatically retrieved.

The section midpoint represents one release location. For a uniform local density,
people in its footprint equal `density * pi*r² / 1e6`. The conditional exposure
consequence multiplies this by a user-entered scenario/ignition probability.
This estimates exposure, not injuries or fatalities. Overlapping circles cannot
be summed as unique population; the midpoint is not the worst location in a section.

Direct economic screening is `fixed response cost + scenario probability * pi*r²
* asset value per m² * damage fraction`. Valuation and vulnerability fractions
are supplied assumptions, not a literature-calibrated economic-loss model.
There is no automatic value of life, environmental-loss or business-interruption
calculation. Do not add unrelated units or double-count shared losses.

Download full results with parameters, references and input source. Select a
measure, click **Use these consequences in Risk & Reliability**, return to that
tab and select **Use Consequence Assessment**. Exposure transfers in people
potentially exposed; economics transfers in the specified currency. Saved inputs
must match the route. Risk export metadata identifies the source scenario.

Heat-flux endpoint context: [EPA Appendix D](https://www.epa.gov/sites/default/files/2017-05/documents/oca-apds.pdf)
and [NOAA radiation levels of concern](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/resources/thermal-radiation-levels-concern.html).
Duration, shielding and scenario matter; the illustrative 5 kW/m² threshold is
not a fatality probability or validated evacuation radius.

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
