# Shared Data Exploration → Inspection Planning

The `/inspection` page runs inside the main ALIRIM Streamlit session. It reads
`project_editor.get_project()` and converts a validated private copy with
`planning_project.planning_handoff()`. The saved dataset and measured profile grids
are never modified by planning. A fresh browser session starts with the explicitly
labelled synthetic sample; no persistent operator database is provided.

The page opens with the restored Introduction, team, abstract and documentation.
**Open Planning and VoI Simulation** selects **Planning & Results**. The planning
controls are in main-page expanders under **Planning Settings**, rather than in
the collapsible app sidebar. Both tabs render their controls consistently, and
`settings.py` keeps a separate copy of planning choices so a visit to Data
Exploration does not reset them. This is session storage, not durable storage.
The Data Exploration Continue button opens Planning & Results directly.

## Entering and editing asset data

Data Exploration opens on **Enter / edit defects**, starting from the saved
dataset. Its **Defect register** table has dynamic rows and editable IDs, types,
chainages, depths and lengths (plus width for corrosion). Rows can be added or
deleted. The quick-entry controls add a defect at a distance, or supply the size
for the map's pin tool. Pins within 100 m of the route are projected to the
nearest centreline leg. Existing coloured markers select a defect for viewing.

**Upload crack / corrosion data (CSV or Excel)** reads a `Defects` worksheet or
the first sheet. Columns are `defect_id`, `chainage_m`, `depth_mm`, `length_mm`,
and optionally `defect_type` and `width_mm`. `chainage_km` is also accepted.
The previous standalone planner's mapped CSV format (`crack_id`, `latitude`,
`longitude`, `depth_mm`, `length_mm`) is accepted; the preview reports GPS
projection offsets before the user replaces the register. Location references
are measured from the current route origin. Importing replaces the defect
register without replacing the route or pipe-property settings.

Route inputs accept manual ordered latitude/longitude rows, CSV, Excel (`Route`
worksheet or first sheet), or one GeoJSON LineString/Feature/FeatureCollection.
Applying a new route retains property zones, trims those beyond its end and
extends the final zone if needed. This reuse is explained in the UI and remains
a draft assumption to review. Defect chainages stay unchanged; saving rejects
locations outside the new route. Use the existing segment editor to change
properties or repartition the route explicitly.

The original sample grids and measured-profile workbook upload remain available.
Unchanged measured grids are preserved, including when only chainage is edited.
New or resized defects have an **illustrative** shape derived from entered
dimensions, marked both in exploration and the analysis views. The original
workbook bytes are not changed. Analyses use the same entered maximum depth and
length; the illustrative shape does not provide measured interaction geometry.
Incomplete edits cannot be saved over the last valid analysis dataset. Empty
tables remain editable, but saving still requires a defect or a dent record.

## Input contract

- Joint number = floor(chainage / joint length) + 1; the route endpoint belongs to
  the final partial joint. Multiple cracks retain one physical joint and all IDs.
- Geometry = measured maximum depth and full profile length. Profile shape is
  retained for exploration, but the planning model uses equivalent elliptical cracks.
- Pipe properties and uncertainty distributions map by section: diameter_in→OD,
  wall_thickness_mm→WT, pressure→Pservice, yield→SMYS, ultimate→SMTS,
  modulus→E, Charpy→CVN, model_factor→err. Units remain inches/mm/psi/GPa and
  the existing model's Charpy units. Crack depth/length retain their per-section
  uncertainty distribution and absolute SD.
- Segment boundaries that cut a physical joint with different planning inputs are
  rejected. A joint is never split or assigned averaged properties. Identical
  adjacent populations can cross a bookkeeping segment boundary. Initially clean
  joints use the segment containing their midpoint; for an accepted straddling
  joint both populations are equivalent.
- Growth, births, ILI detection/error, repair, safety, intervals and costs are
  planning assumptions. No values for these are inferred from a profile image.
- Repair criteria use saved nominal pipe/material properties, saved MAOP as the
  pressure reference, and user-entered depth fractions of that joint's nominal WT.
- Optional saved consequence override converts loss/1e6. It is off by default:
  the UI requires an explicit choice to interpret a segment loss as the loss for
  **each joint failure event**. UNKNOWN losses use visible planning fallbacks.
- Corrosion or dents in the saved register block crack planning; no records are
  silently filtered out. Preliminary Analysis retains its separate threat models.

## Calculations and provenance

`inspection_planning/engine.py`, `corlas.py`, `normal.py`, and `comparison.py` are
adapted from the user's `AliAmeri75/pipeline-inspection-app` repository at commit
`bb562e83c73ff64366f3ea606291ff29f22b8674`. The original standalone repository is
unchanged. The integrated package has namespaced imports, independent-distribution
sampling, per-joint OD in CorLAS/initial survival/growth, per-crack sizing
uncertainties and segment nominal repair references. Defaults are retained for
legacy callers. It uses the optimized fixed-interval engine, not the separate
streaming implementation. Only equidistant planning is exposed in the main UI.

The simulation retains the original conditioning on survival at time zero.
Requested and retained sample counts must be interpreted with the future
conditional failure results. Joint-group probability/count approximations and
independence assumptions remain those of the original planning model. A successful
data handoff does not establish accuracy of those scientific assumptions.

The UI fingerprints the dataset, all model inputs and both interval grids. Old
recommendations disappear after any changed input. Comparison/prior/ILI CSVs carry
the full dataset hash. Separate prior and ILI candidate intervals, safe/cost-optimal
recommendations, selected-point cost components and net VoI are retained.

## Larger studies and resource limits

The integrated page uses `inspection_planning/execution.py` to call the same
fixed-interval physical engine in smaller batches. There is no 10,000-sample
entry ceiling or workload-based disabled Run button. The default batch size is
250, reduced automatically when a conservative array estimate would exceed a
32 MiB target. This estimate excludes other server/application overhead.

Only sufficient statistics remain after each batch. Failure counts for each
representative joint are pooled using retained-sample weights before system POF,
annual POF and safety are recomputed. Costs are weighted by the same retained
population. System probabilities or Safe/Unsafe flags are never averaged across
batches. The existing group-count approximation and initial-survival conditioning
remain in place. Threshold scheduling is not batched.

The same seed and batch size reproduce a study. Changing batch size changes the
Monte Carlo realizations, so it invalidates the results and restarts the study.
A small accumulator retains completed batches and intervals in the current
Streamlit session. After an interruption, Resume skips completed work. A server
restart, a lost session, or changing inputs invalidates that checkpoint. Partial
interval tables are downloadable, but no final optimum is selected from an
unfinished candidate grid.

Batching reduces peak memory; it does not add CPU capacity or bypass Community
Cloud quotas. For a larger study, run the same app locally or deploy to a server
with sufficient resources. The local workflow is:

```sh
cd pipeline-integrity-platform
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Open the address printed by Streamlit, upload/save the pipeline dataset, and run
Planning & Results. Computations then use that computer's resources.
