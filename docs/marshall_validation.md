# Marshall published-calculation comparison

Location: Research Resources → Validation Examples → Preliminary Analysis Validation
→ Marshall Burst Resistance (`/validation`). Planning Validation is a separate tab
and is currently under construction. Also linked from
Preliminary Analysis → Crack → Deterministic Analysis. This is an isolated benchmark;
it does not replace or write the user's shared route, defect profiles or planning inputs.

## Sources

NTSB DCA10MP007, Attachment I, Table I: fitness-for-service calculations prepared by
Enbridge at NTSB's request, published source:
https://data.ntsb.gov/Docket/Document/docBLOB?FileExtension=.PDF&FileName=IMP%20Attachment%20I%20-%20Table%20I%3A%20Fitness%20for%20service%20calculations%20performed%20by%20Enbridge%20at%20NTSB%27s%20request%20using%20Corrosion%2C%20crack%20and%20tool%20tolerance%20data-Master.PDF&ID=40369111

Final report NTSB/PAR-12/01:
https://www.ntsb.gov/investigations/AccidentReports/Reports/PAR1201.pdf

The final report printed p.1, footnote4 establishes X52 SMYS52,000psi. TableI gives
UTS66,000psi, flow59,000psi, OD30in, external rectangular flaw, Charpy20ft-lbf,
MOP624psi, reference1.25MOP780psi. Per-row WT, length, effective depth and reference
failure pressures are transcribed in `samples/validation/marshall_ntsb_table_i.csv`.

TableII, historical inspection observations, is linked as context only. Do not merge
its corrosion/crack estimates or apply later algorithms to claim pre-accident foresight.

## Implementation

`education.pof_model.corlas_failure_pressure` now has optional `flaw_shape` and
`flow_stress_psi` keyword arguments. Existing callers retain elliptical geometry and
the original mean-strength flow rule and Newton solver. The added rectangular branch
uses Aeff=L*d, effective depth=d, and a bracketed positive toughness root to avoid
negative stress iterates. This follows the existing original `CorlasP.py` rectangular
option; it does not create a new combined-defect failure model.

Comparison assumptions: model yield52,000psi (SMYS used as yield; not measured yield),
E30,000,000psi (not specified in TableI). Reference flow stress is explicitly59,000psi.
The source's Charpy ft-lbf convention is passed directly into Jc=round(12*CVN/.124).
Input lengths use exact25.4mm/in; wrapper's existing approximate inch conversion is
retained. Nominal pressure uses no1.27 model-bias adjustment and no safety-factor division.
Neither modulus nor yield is fitted to minimize comparison residuals. Sensitivity
controls display analyst choices; reference source values are never overwritten.

With defaults: max absolute pressure difference0.73461psi; max relative difference
0.173257%; all16 rows within1psi. This is numerical agreement with rounded published
outputs, not evidence that discrepancies are solely rounding. The legacy rectangular
routine independently gives results within0.001psi of this wrapper.

Source anomalies are retained: row8 numeric depth.178in contradicts its textual
.055+.071+.020 depth description. The numeric effective-depth column is used.
2007 run label12 occurs three times; unique scenario IDs use source ordinal, preserving
all labels. The16 scenarios are not16 independent physical defects or failures.

The default comparison tolerance1% is illustrative and user-selectable, not a regulator
or code requirement. Source649/572/etc are nominal model calculations, not measured
burst pressures. The MOP reference624psi is not the pressure at actual rupture.

## Scope of evidence

Agreement supports reproduction of these specific post-accident reconstruction
calculations under stated assumptions. It does not validate the general interaction
of crack/corrosion, ILI sizing accuracy, POF, crack growth, future inspection intervals,
repair policy, or historical accident prevention. Existing elliptical analyses are not
silently switched to rectangular geometry. Model applicability remains engineering work.
