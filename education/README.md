# ALIRIM educational tutorial

This folder contains the student-facing learning tutorial that connects the three
ALIRIM research applications. It includes two modules:

1. **Deterministic FPR:** select crack depth and length, calculate Failure
   Pressure Ratio (predicted failure pressure / operating pressure), view the
   FPR = 1 and FPR = 1.25 depth-length curves, and explore separate depth and
   length sensitivity plots.
2. **Probabilistic POF:** represent input uncertainty with student-selected
   distributions, estimate probability of failure with Monte Carlo simulation,
   interpret the result, and complete a short knowledge check.

The failure-pressure equations in `pof_model.py` are adapted from `CorlasP.py`
in the `AliAmeri75/pipeline-inspection-app` repository at commit
`b479e41116ad560465676b01a67e8e28aa9c1f85`.

The thresholds and actions shown in the tutorial are illustrative classroom
prompts, not engineering acceptance criteria.
