## Applications and source code

| Research component | Live application | Source repository |
|---|---|---|
| Fixed inspection scheduling | [Open app](https://pipeline-inspection-appgit-qjifsvi4zeuyuchaueiuwm.streamlit.app/) | [GitHub](https://github.com/AliAmeri75/pipeline-inspection-app) |
| Dynamic RL planning | [Open app](https://pipeline-rl-planning.streamlit.app/) | [GitHub](https://github.com/AliAmeri75/pipeline-rl-planning) |
| Reliability and value of information | [Open app](https://pipeline-reliability-voi.streamlit.app/) | [GitHub](https://github.com/AliAmeri75/pipeline_reliability_J2) |
| Integrated research platform | [Open platform](https://pipeline-integrity-research.streamlit.app/) | [GitHub](https://github.com/AliAmeri75/pipeline-integrity-platform) |

## Editing the platform

The public-facing text is separated from the application code so it can be revised
directly on GitHub:

- `content/PLATFORM_ABSTRACT.md` controls the research overview on the home page.
- `content/PUBLICATIONS.md` controls the publication lists and links.
- `content/DOCUMENTATION.md` controls this documentation section.
- `home.py` controls the three research cards.
- `platform_ui.py` controls the ALIRIM and University of Alberta branding, styling, and team cards.

Each scientific application remains in its own repository and deployment. Fixed
Inspection Scheduling already has its preferred introduction in the standalone
application, so both the home-page card and sidebar link open that introduction
directly. The integrated platform retains its overview pages for Dynamic RL Planning
and Reliability and Value of Information. New tabs are required because Streamlit
Community Cloud runs the platform inside a protected browser frame that cannot load
another Streamlit application within itself.

## Data and privacy

The Journal 2 application can read approved `.npz` arrays from a public Google Drive
folder or accept a direct browser upload. Do not place confidential operator or ILI
records in a public folder. All three applications are research decision-support
prototypes and require appropriate engineering review.
