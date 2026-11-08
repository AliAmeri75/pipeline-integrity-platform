# Shared Data Exploration → Inspection Planning

The `/inspection` page runs inside the main ALIRIM Streamlit session. It reads
`project_editor.get_project()` and converts a validated private copy with
`planning_project.planning_handoff()`. The saved dataset and measured profile grids
are never modified by planning. A fresh browser session starts with the explicitly
labelled synthetic sample; no persistent operator database is provided.

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
