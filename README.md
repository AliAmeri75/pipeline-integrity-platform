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

## Unified Data Exploration → Preliminary Analysis

**Data Exploration is the single input workspace.** Define the centreline (draw
it or upload a GeoJSON LineString), defect chainages measured from the route
origin, property segments, nominal pipe/material/load values, distributions and
standard deviations. Click a map marker or select a feature to inspect the same
measured 2D/3D profile. Multiple defects in one nominal 12 m interval retain the
same joint ID; a property segment is a different concept from a physical joint.

Open **Define shared defects, pipe segments and uncertainties** to edit the
registers. Segment boundaries can have any positive length and arbitrary unique
positive integer IDs. They must cover the route continuously, without gaps or
overlaps. Each parameter has a distribution and absolute SD per segment;
pipe/material/load means come from the segment register, while defect-size means
come from measured feature dimensions. Choose Deterministic, Normal, Lognormal
or Gumbel. Synchronize uncertainty rows after adding or changing segment IDs.

Press **Save shared dataset for all analyses** before opening Preliminary
Analysis. Downstream pages do not request another route, defect upload or
independent set of pipe properties. Unsaved drafts are identified; analysis
signatures invalidate old results after saved input changes. Use in-app
navigation to retain the Streamlit session. Current storage is session-only;
download the registers and centreline for your records. External independent
planning applications are not silently synchronized across deployments.

### Common demonstration dataset

The fictional bent route near Edmonton is exactly 10 km, with the same measured
synthetic shapes SYN-001, SYN-002 and SYN-003 at 0.5, 4.5 and 8.5 km. The source
sample workbook uses these same chainages. Initial property segments are
non-overlapping 1 km intervals. All sample segments and profiles use the same
914.4 mm (36 in) outside diameter and 11.8 mm wall thickness. Custom assets
can still use different segment properties. Other properties, uncertainty settings and conditional
losses are illustrative inputs, not validated asset or geographical information.
SYN-003 retains its 360 mm length and 65% inspection-WT maximum depth; its
default FPR is approximately 1.079.

### Deterministic Analysis

The deterministic workflow uses each defect's assigned segment geometry,
material properties and nominal operating pressure. FPR is explicitly
**unadjusted CorLAS burst resistance / entered operating pressure**; it is not
automatically MAOP-based or a regulatory acceptance measure. It does not apply
the stochastic model factor θ. Select a result row or FPR plot point to view the
same feature in 3D. Segment summaries retain the saved arbitrary boundaries.

Red circles mark the user-selected screening rule **FPR < 1.1 OR depth > 0.5 WT**,
with a single “Severe → immediate action!” legend entry rather than repeated
point labels. Hover details, the table and exports retain each defect’s reason.
This user-configured screening label is not a code-compliance or approved
repair decision.

The selected crack shows measured-depth and CorLAS burst-pressure heatmaps.
Each valid measured depth uses the full profile length and the same assigned
segment inputs. This is a depth-sensitivity screening map, not a profile
interaction calculation or independent cell-sized cracks. Original measured
depths in mm are retained even if assessment WT differs from inspection WT;
display %WT grids are adapted on a copy, not by modifying the source profiles.
Minimum FPR and resistance cards appear immediately. Missing/negative,
through-wall or unsupported measurements do not receive fabricated FPR.
Corrosion geometry is supported, but requires a separately implemented and
validated corrosion resistance model before FPR or calculated Pf is available.

### Risk & Reliability

Only simulation settings and map screening thresholds are chosen here. All
asset and uncertainty inputs come from the saved shared register.
The active Monte Carlo engine is `probabilistic_reliability_model.py`, called by
`assessment_project.reliability_project`. It applies segment-specific parameter
specifications to each defect. Arithmetic means/SDs are converted for lognormal
and Gumbel draws; nonpositive draws and incompatible geometry/strength ordering
are resampled, which can alter realized moments.

Pipe/material/load draws are shared within each joint–segment group; defect-size
draws are independent. A property boundary through a nominal joint splits the
sampling group without creating a new physical joint ID. Different groups are
assumed independent. Section Pf uses `1 - product(1 - group Pf)`; defects are
assigned once by chainage to [start,end), with the route endpoint included in the
last segment. This assumption is explicit, not a calibrated spatial dependence
model.

Leakage is sampled depth ≥ sampled WT. Burst is pressure ≥ θ × CorLAS
resistance for a non-through-wall sample. These are **assessment-condition**
probabilities, not annual Pf: no time evolution, initiation, inspection, repair
or optimization is included. The former 100 km/independent defect-source example
is removed from the interface. Corrosion is not silently evaluated with CorLAS.

Consequences are conditional segment-event losses in one common unit, not
already probability-weighted losses. Risk = burst Pf × burst consequence +
leakage Pf × leakage consequence. Missing consequences remain UNKNOWN/NaN,
not zero; POF may still be assessed. This screening metric is not an expected
multiple-incident count, and loss definitions must avoid double counting.

POF, consequence and risk are plotted against the same saved segment boundaries.
The map switches between them. POF red corresponds to a user-selected screening
limit; consequence/risk scales are relative, and grey means unknown.
Defaults 0.001 burst / 0.01 leakage do not claim CSA compliance. Unlisted threats
are not modeled; no listed defects means zero modeled contribution, not proof of
safety. Zero observed failures do not demonstrate zero Pf; the approximate 95%
upper bound at zero failures is 3/N. Downloads retain the dataset signature and
probability basis.

Selected-threshold screening: burst Pf strictly above its selected limit OR
leakage Pf strictly above its limit flags **→ Immediate action!**. The POF chart
adds threshold lines and circles at flagged segment midpoints. The map adds red
segment outlines and white-backed action labels in every layer; individual
defects exceeding a threshold receive red rings. Segment and defect flags are
distinct: an aggregate segment can exceed a limit even when no individual
feature does. Tables and CSVs include status, reason and both selected limits.
Changing a screening limit reclassifies saved probabilities without another
simulation. These are user-configured review flags, not regulatory repair orders.

Assessment profile charts use a white paper/plot background, Times New Roman
(Times/serif fallback), black framed axes and light gridlines. POF uses a
logarithmic vertical axis; FPR, consequences and risk remain linear. Zero POF
estimates are omitted from the log plot, leaving gaps; tables and exports retain
the original zero values. No small positive surrogate is inserted. Threshold
labels have white backgrounds and additional plot margins retain action labels.

### Consequence Assessment workspace

Open **Preliminary Analysis → Consequence Assessment** after saving the shared
route and segment register in Data Exploration. MAOP and nominal diameter for
PIR screening come from that register; they are not re-entered in this tab.
The explicit transfer button writes assessed losses and their unit back to the
same shared segment register. Re-run Risk & Reliability after transferring them.
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
