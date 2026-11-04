# Preliminary Analysis: replaceable threat models

All workspaces use the saved Data Exploration route, property segments and joint length. Selecting Crack or Corrosion filters the defect register without changing the pipeline or silently relabelling profiles. Dent geometry is stored in `dent_register`, separately from depth grids because dent displacement is not wall loss. No threat probabilities are combined into a physical interaction calculation.

## Crack

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

## Replacing models

Register pressure-resistance functions in `CORROSION_MODELS`. Their contract is (D_mm, t_mm, depth_mm, length_mm, UTS_psi) -> nominal pressure_psi; functions must validate their own domain. The common leakage classification, sizing checks and sampling domain also need review for a materially different model.

Register strain-demand functions in `DENT_MODELS`. Their contract is (D_mm, t_mm, displacement_mm, axial_length_mm, signed_R1_mm, signed_R2_mm) -> strain fraction. A fatigue/burst model needs a new event/output contract and uncertainty/loading inputs, not merely a new label. Update domain checks, references, deterministic benchmarks, Monte Carlo tests, interface descriptions and exported probability basis together.

Model changes need validation against independent test/field data before operational use. The tests supplied here verify equations and software behaviour; they do not establish asset-specific accuracy.
