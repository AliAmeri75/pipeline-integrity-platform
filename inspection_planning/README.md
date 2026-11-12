# Shared-project inspection engine

`engine.py`, `corlas.py`, and `normal.py` originate from the existing ALIRIM
`AliAmeri75/pipeline-inspection-app` repository at commit
`bb562e83c73ff64366f3ea606291ff29f22b8674` (optimized, vectorized joint engine).
The standalone app has not been changed by this integration. The independent
sampler in `sampling.py` retains its CDF/quantile transformation and legacy random
stream, adding explicit deterministic distributions and zero-SD handling.

This namespaced copy lets the main Streamlit application use the saved Data
Exploration project in the same session. No cross-site session transfer, secret
query parameters, temporary public upload or external data store is required.

The flexible joint API retains `name`, `count`, `cracks`, `properties` and
`birth_rate`. Optional shared-project fields are:

- `properties['OD']`: outside diameter distribution in inches; the original
  properties retain WT in mm, pressure/strength in psi and modulus in GPa.
- Each crack may include `length_distribution`, `length_std`,
  `depth_distribution`, `depth_std`, alongside its mean dimensions in mm.
- `use_nominal_repair=True` and `maop_psi`: evaluate the repair FPR criteria
  against this segment's nominal properties and MAOP. Without the flag the
  original research reference constants are retained.
- `costs`: optional joint-specific `Cf_leak`/`Cf_burst` overrides in the same
  monetary units as the common cost settings.
- `D_rep1_fraction`/`D_rep2_fraction` in simulation settings: depth criteria as
  fractions of each joint's nominal WT, instead of common absolute millimetres.

OD now reaches initial survival screening, subsequent CorLAS calls, repair
criteria, and the fatigue-growth diameter term. Multiple cracks remain in one
joint definition and share that joint's pipe draws and repair action. The model
does not add crack-interaction equations or corrosion/dent planning physics.

The original engine conditions its Monte Carlo population on survival at time
zero. `debug['requested_samples']` and `debug['retained_samples']` expose that
conditioning; all-failed populations raise an error. This is not a substitute
for acting on already-critical measured defects. Safety limits are applied to
the annual probability of at least one failure anywhere on the full route,
without dividing by route length. The map separately shows local sliding 1 km
windows.

The UI uses Plotly. Optional original CLI plotting functions import Matplotlib
only when invoked; Matplotlib is not needed to run the integrated UI.
