# Preliminary Analysis: replaceable threat models

All workspaces use the saved Data Exploration route, property segments and joint length. Selecting Crack or Corrosion filters the defect register without changing the pipeline or silently relabelling profiles. Dent geometry is stored in `dent_register`, separately from depth grids because dent displacement is not wall loss. No threat probabilities are combined into a physical interaction calculation.

## Sample and upload workflow

Data Exploration offers Sample crack profiles, Sample corrosion profiles, Sample dent data, Upload your workbook, and Upload dent CSV / Excel. Downloadable samples are synthetic, with distinct corrosion and dent IDs on the same fictional 10 km, 914.4 mm OD, 11.8 mm WT pipeline. Crack samples remain unchanged. Sources are alternative drafts, not automatically appended to the active dataset.

For corrosion, use the sample depth-grid workbook or upload a compatible profile workbook and choose the defect type. Review properties and uncertainties, then click **Save shared dataset for all analyses**. Open Preliminary Analysis to enter the matching threat workspace.

For dents, upload a CSV or `.xlsx` using the downloadable sample columns. Excel reads `Dents`, or the first sheet if that name is absent. Uploaded dent records start with the currently active route and segment properties; review these, replace the route if necessary, and save. A dent-only dataset has an empty crack/corrosion profile register—no dummy crack rows are required. The download includes all measured curvature columns and the combined-damage flag. False/True is parsed explicitly. Geometry, route bounds, unique IDs and booleans are validated at Save, so a new route can be adjusted after the draft is loaded.

The sample dent with the highest geometric strain exceeds the illustrative 6% strain criterion. This is synthetic screening behaviour, not a documented failure. Dent displacement can exceed WT because it is deformation, not missing wall material. The idealized Gaussian visual does not reconstruct the supplied curvature field.

## Crack workflow

Existing CorLAS deterministic and Monte Carlo workflows remain in place. Reliability inputs and calculation behaviour are unchanged. The workspace now receives only crack records from the shared register, so corrosion rows no longer block crack-only analysis. Outputs represent the crack contribution, not all threats.

## Corrosion

`corrosion_assessment_model.py` implements the nominal isolated longitudinal metal-loss pressure equation:

Q = sqrt(1 + 0.31 L²/(D t))

P = [2 t UTS/(D − t)] [(1 − d/t)/(1 − d/(t Q))]

Geometry is in mm; UTS and output pressure are psi. Differential operating pressure must use the same basis. The function accepts depth/WT up to 0.85. Known circumferentially wider-than-longer profiles are rejected. Applicability must be confirmed in the interface. There are no interaction rules, additional-load calculations, safety factors or regulatory acceptance rules.

The open equation and a regression example are documented by [Equinor NeqSim](https://equinor.github.io/neqsim/process/mechanical_design/dnv_rp_f101_corroded_pipeline). [DNV's publisher page](https://www.dnv.com/energy/standards-guidelines/dnv-rp-f101-corroded-pipelines/) describes the broader RP scope. This implementation is **not** certified or a full reproduction of the licensed standard. The example regression is not independent experimental validation.

Monte Carlo uses the shared generic pipe/load/UTS/sizing distributions only after explicit review. The defaults are not corrosion calibration. The CorLAS model-factor bias is deliberately replaced by 1.0 deterministic; users can enter a corrosion-specific factor distribution. Leakage is sampled depth ≥ WT. Burst is pressure ≥ factor × nominal resistance in non-through-wall draws. Non-through-wall draws beyond the model's depth domain abort the assessment rather than silently reducing the reported Pf.

Pipe/load draws are shared within each joint/property group, with sample-wise defect event unions; groups and sizing errors are assumed independent. Physical defect interactions are not simulated. Section risk is section burst-event Pf times its conditional burst consequence plus leakage-event Pf times its conditional leakage consequence. These are assessment-condition probabilities and losses, not annual rates. Unrecorded threats are unassessed. Missing consequences stay UNKNOWN.

## Dent

`dent_assessment_model.py` starts with the geometric strain equations in [PHMSA Mechanical Damage Final Report (2009), section 7.2.3, equations 2–6, PDF page 97](https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/docs/technical-resources/pipeline/gas-distribution-integrity-management/65991/mechanicaldamagefinalreport.pdf).

e1 = (t/2)(1/R0 − 1/R1), R0 = D/2

e2 = −t/(2 R2); e3 = 0.5 (d/L)²

inside strain = sqrt[e1² − e1(e2+e3) + (e2+e3)²]

outside strain = sqrt[e1² + e1(−e2+e3) + (−e2+e3)²]

Demand is the larger surface strain. Radii R1 and R2 must be measured signed curvature radii using the source's convention. They are not inferred from dent depth. Depth is inward displacement; WT is unchanged by denting. The optional Gaussian 3D illustration uses depth/length/width but **does not reconstruct or validate the entered curvature field**.

The selected criterion defaults to a historical 6% strain screening example; it is neither an automatically applicable acceptance limit nor an empirically calibrated failure strain. Reliability evaluates g = selected strain criterion − geometric strain demand. It reports strain-criterion exceedance probability, **not burst/leakage or annual failure probability**. All geometry uses a user-selected lognormal COV; criterion uncertainty uses a positive normal distribution. OD/WT and criterion draws are shared within joint/property groups. Associated crack/metal-loss dents are blocked pending an interaction model.

A separate optional conditional consequence can produce an expected **criterion-event consequence proxy**. Burst/leakage consequence tools remain available, but their results are not silently multiplied by the criterion probability. Actual dent rupture/fatigue risk requires a calibrated failure model, loading/pressure history and appropriate validation; that remains outstanding.

## Combined-defect research candidates

Combined-defect calculations are **not implemented**. The interface now identifies its current model for each threat and links the following research candidates:

- Dent–crack: [Okodi et al. (2020), Crack Propagation and Burst Pressure of Pipeline with Restrained and Unrestrained Concentric Dent-Crack Defects Using Extended Finite Element Method](https://www.mdpi.com/2076-3417/10/21/7554). This is an XFEM approach for the studied configurations, not a universally applicable closed-form pressure equation.
- Dent–corrosion: [Huang, Qin and Hu (2022), Failure pressure prediction by defect assessment and finite element modelling on pipelines containing a dent-corrosion defect](https://doi.org/10.1016/j.oceaneng.2022.112875).
- Adjacent dent–corrosion interaction: [Sun et al. (2021), Assessment of Interaction Between a Dent and an Adjacent Corrosion Feature on Pipelines and the Effect on Pipeline Failure Pressure by Finite-Element Modeling](https://doi.org/10.1061/(ASCE)PS.1949-1204.0000570).

Review full methods, material/calibration data, load cases and validation domains before implementation. Inputs may include paired defect IDs, axial and circumferential offsets, crack orientation, 3D dent and metal-loss geometry, stress–strain/fracture behaviour, restraint, indentation history and service pressure cycles. Which inputs are necessary depends on the selected model and failure mode. An offline validated FE surrogate could be wrapped by a replaceable web-app engine; it is not supplied by this change. No interaction reduction factor is invented.

Current isolated crack and corrosion engines are not combined by adding their probabilities, modifying nominal pressure with an arbitrary stress-concentration factor, or treating dent strain-criterion exceedance as rupture probability. A combined model needs its own leak/rupture event definitions and validation before those probabilities are used with release consequences.

[API's RP 1183 Addendum 1 notice](https://www.api.org/products-and-services/standards/important-standards-announcements/addendum-1-rp-1183) documents removal of first-edition Table 6 fatigue-screening guidance. The existing geometric strain implementation is separate from that table and must not be described as implementing the complete current API RP 1183.

## Engine replacement contracts

Register pressure-resistance functions in `CORROSION_MODELS`. Their contract is (D_mm, t_mm, depth_mm, length_mm, UTS_psi) -> nominal pressure_psi; functions must validate their own domain. The common leakage classification, sizing checks and sampling domain also need review for a materially different model.

Register strain-demand functions in `DENT_MODELS`. Their contract is (D_mm, t_mm, displacement_mm, axial_length_mm, signed_R1_mm, signed_R2_mm) -> strain fraction. A fatigue/burst model needs a new event/output contract and uncertainty/loading inputs, not merely a new label. Update domain checks, references, deterministic benchmarks, Monte Carlo tests, interface descriptions and exported probability basis together.

Model changes need validation against independent test/field data before operational use. The tests supplied here verify equations and software behaviour; they do not establish asset-specific accuracy.

## SCADA pressure cycles and dent fatigue (research implementation)

Preliminary Analysis → Dent → SCADA & Fatigue accepts the downloadable synthetic
7-day CSV or a user CSV/XLSX (first sheet). Users select one pipeline, timestamp,
pressure column and unit (MPa/bar/psi). Use local differential pressure at the dent;
no pressure interpolation along the route is inferred. Times without timezone
information are assumed UTC. Duplicate, reversed, invalid and irregular timestamps,
missing/negative pressures and mixed pipeline IDs are rejected. Records are treated
as interval-start observations; exposure is last-minus-first plus the median interval.
A continuous record is required; gaps are not silently interpolated. Users must
review source quality flags; the app does not infer vendor-specific quality codes.

`rainflow==3.2.0` extracts individual cycles and residual half cycles. A user-selected
minimum range (MPa) filters small cycles. Unbinned ranges, not the display histogram,
feed damage. Sampling resolution, sensor noise and range filtering affect results.
The synthetic file is illustrative only, not a model of an actual operator's hydraulics.

He & Zhou (2021), https://doi.org/10.1016/j.jpse.2021.08.004:
- Eq.15: K = 1 + 1.7169 (D/t)^0.8 (d/D)^0.7. Automatic calculation is restricted
  to 20 ≤ D/t ≤ 60 and 0.02 ≤ d/D ≤ 0.12. The existing demonstration pipe is
  outside this D/t range; it is deliberately not extrapolated. Users may instead
  supply an independently reviewed SCF with a required justification. The starting
  manual value 6 is explicitly illustrative, not calculated from the selected dent.
- Eq.10: N = exp[43.944 − 2.971 ln(145.033 Δσ_local / 2)], Δσ in MPa.
  Therefore m=2.971, A=exp(43.944)*(145.033/2)^(-m), about 3.61e13.
- Δσ_local = K Δp D/(2t). Annual damage at mean A is
  sum(count * Δσ_local^m)/(record_years * mean_A).
- Independent lognormal A and critical Miner damage have literature-example means
  3.61e13 and 1, COV 0.45 and 0.30 (editable COVs). With zero initial damage,
  cumulative Pf(T)=P(A*Dcrit ≤ T*annual_stress_power), evaluated analytically.
  This can resolve small tails without Monte Carlo sample-count limits.
- Fixed OD, WT, geometry, SCF and spectrum. No calibrated SCF error, geometry
  uncertainty, mean-stress correction, load sequence or re-rounding evolution.
- Users specify prior years under the same assumed pressure spectrum. Age zero
  assumes zero prior damage. Time extrapolation requires explicit acknowledgement
  of a stationary spectrum. One synthetic week does not establish actual annual loading.

Outputs are pressure history, rainflow spectrum/download, projected damage at mean
A, cumulative fatigue-limit probability, and unconditional interval probability
increments. A selected pressure history assesses one selected dent at a time.
Do not label these results as leakage or rupture Pf or attach release consequences
without an appropriate physical outcome model. This does not optimize inspections,
represent POD/measurement updating or evaluate dent–crack/corrosion/weld interaction.
It is not the withdrawn API RP1183 First Edition Table6 screening method.

Verification includes a hand stress/damage calculation, exact lognormal probability,
cycle-count benchmarks, source validation, monotonic time response and the rounded
He–Zhou Example1 discharge beta ≈4.82 at year5 for d/D=5%. Agreement with a paper
example verifies implementation, not predictive accuracy on operator data.
