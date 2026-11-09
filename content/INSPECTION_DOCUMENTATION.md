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

1. Define the pipeline, cracks, pipe properties and uncertainties in **Data Exploration**, then save the shared dataset.
2. Select **Static Multiple Inspection and Excavation Planning** to view the introduction.
3. Click **Open Planning and VoI Simulation**, or select the **Planning & Results** tab.
4. Review the connected dataset and set the sample count, horizon and separate prior/ILI interval ranges.
5. Open the **Planning Settings** sections on the main page to edit safety class, growth, initiation, POD and sizing error, repair criteria, repair effectiveness and costs.
6. Run both optimizations and compare their schedules and lifecycle costs.
7. Review or download the VoI, prior-excavation, and ILI-informed results.

Your planning settings remain available when you return to the Introduction tab
or visit Data Exploration in the same session. Saved input changes still require
a new run before previous results can be used.

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
