## What the application does

The scheduling page evaluates a user-defined set of **equidistant inspection
intervals** over a selected analysis horizon. Each candidate interval is run
with the same random seed so the economic and reliability results can be
compared consistently.

The model can represent:

- multiple individual pipe joints or groups of statistically identical joints;
- one or more initial cracks per joint, as well as initially crack-free joints;
- uncertain crack growth and future crack initiation;
- inspection probability of detection and crack-sizing error;
- two repair criteria and configurable repair effectiveness; and
- inspection, repair, leak, and burst costs with economic discounting.

## Typical workflow

1. Select **Fixed inspection scheduling** from the integrated platform.
2. Use **Open the Inspection Scheduling Simulation** to launch the model.
3. Enter the Monte Carlo sample size, analysis horizon, and candidate interval range.
4. Upload a joint/crack CSV or edit the example table directly.
5. Review growth, cost, repair, uncertainty, and safety assumptions in the sidebar.
6. Run the optimization, compare the schedules, and download the results table.

## Main outputs

The application reports the preferred candidate interval, expected present
life-cycle cost, inspection/repair/failure cost components, expected number of
repairs, and whether the leak and burst safety criteria are satisfied. It also
plots the cost comparison and annual leak/burst probabilities for the selected
schedule.

## Scope and limitations

The current optimization compares only the candidate fixed intervals supplied
by the user. Results depend on the selected physical, probabilistic, inspection,
repair, consequence, and economic assumptions. A production integrity decision
should include data-quality review, model validation, sensitivity analysis, and
assessment by qualified pipeline-integrity professionals.
