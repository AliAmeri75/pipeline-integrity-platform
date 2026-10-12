## What the application does

The scheduling page evaluates a user-defined set of **equidistant intervention
intervals** over a selected analysis horizon. Each candidate is evaluated with
the same model inputs for two methods: prior excavation without ILI and
pre-posterior scheduling informed by ILI detection and sizing.

The model can represent:

- multiple individual pipe joints or groups of statistically identical joints;
- one or more initial cracks per joint, as well as initially crack-free joints;
- uncertain crack growth and future crack initiation;
- ILI probability of detection and crack-sizing error;
- two repair criteria and configurable repair effectiveness; and
- inspection, repair, leak, and burst costs with economic discounting.

## Typical workflow

1. Select **Multiple Inspection and Excavation** from the platform.
2. Open the scheduling simulation.
3. Enter the Monte Carlo sample size, analysis horizon, and candidate interval range.
4. Upload a joint/crack CSV or edit the example table directly.
5. Review growth, cost, repair, uncertainty, and safety assumptions in the sidebar.
6. Run both optimizations and compare their schedules and lifecycle costs.
7. Review or download the VoI, prior-excavation, and ILI-informed results.

## Main outputs

The application reports the preferred safe candidate for each method, expected
present lifecycle cost, inspection/repair/failure components, expected
interventions, and whether the leak and burst criteria are satisfied. Net VoI
is calculated as **minimum prior excavation cost − minimum ILI-informed cost**;
the ILI-informed total already includes discounted ILI costs.

## Scope and limitations

The prior method follows the supplied regular-repair model and excavates only
joints represented with initial cracks. The optimization compares only the
candidate fixed intervals supplied by the user. Results depend on the selected
physical, probabilistic, inspection, repair, consequence, and economic
assumptions. A production integrity decision should include data-quality review,
model validation, sensitivity analysis, and assessment by qualified
pipeline-integrity professionals.
