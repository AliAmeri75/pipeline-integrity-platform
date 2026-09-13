#!/usr/bin/env python3
"""Journal 2 prior and pre-posterior reliability/VoI interface."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from packaging.version import Version

from drive_data import (
    DEFAULT_DRIVE_FOLDER_URL,
    REQUIRED_FILES,
    download_required_drive_data,
    stage_uploaded_files,
    validate_data_directory,
)
from platform_ui import render_project_hero


APP_DIR = Path(__file__).resolve().parent

POLICY_LABELS = {"pi1": "π1", "pi2": "π2"}
with (APP_DIR / "crack_templates.json").open(encoding="utf-8") as template_file:
    TEMPLATE_CONFIG = json.load(template_file)["templates"]
TEMPLATE_BY_ID = {int(template["id"]): template for template in TEMPLATE_CONFIG}
TEMPLATE_IDS = list(TEMPLATE_BY_ID)
TEMPLATE_SOURCE_BY_ID = {
    template_id: int(template["source_index"])
    for template_id, template in TEMPLATE_BY_ID.items()
}
CRACK_TEMPLATE_LABELS = {
    template_id: (
        f"{template['label']} · {float(template['initial_depth_mm']):g} mm"
    )
    for template_id, template in TEMPLATE_BY_ID.items()
}
COLORS = {
    "navy": "#10243d",
    "teal": "#0f766e",
    "blue": "#2563a8",
    "amber": "#c87818",
    "coral": "#c94f3d",
    "violet": "#7556a6",
}
MODERN_CHART_WIDTH = Version(st.__version__) >= Version("1.51.0")


st.markdown(
    """
    <style>
    :root {
        --ink: #10243d;
        --teal: #0f766e;
        --paper: #f4f2ec;
        --line: #dfe3e3;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(244,242,236,.92); }
    [data-testid="stSidebar"] { background: #eef0ed; border-right: 1px solid #cdd4d4; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { font-family: Georgia, 'Times New Roman', serif; }
    .main-title {
        padding: 1.0rem 1.2rem 1.05rem;
        margin: -0.3rem 0 1rem;
        color: white;
        background: var(--ink);
        border-bottom: 4px solid var(--teal);
    }
    .main-title small {
        display: block; margin-bottom: .25rem; color: #8fd1c9;
        font-size: .68rem; font-weight: 800; letter-spacing: .14em;
        text-transform: uppercase;
    }
    .main-title h1 {
        margin: 0; color: white; font-family: Georgia, 'Times New Roman', serif;
        font-size: 2rem; font-weight: 500;
    }
    .main-title p { margin: .35rem 0 0; color: #d9e3ea; font-size: .82rem; }
    div[data-testid="stMetric"] {
        min-height: 118px; padding: 1rem; background: white;
        border: 1px solid var(--line); border-top: 3px solid var(--ink);
        box-shadow: 0 4px 14px rgba(16,36,61,.04);
    }
    div[data-testid="stMetricLabel"] { color: #62717d; font-weight: 700; }
    div[data-testid="stMetricValue"] {
        color: var(--ink); font-family: Georgia, 'Times New Roman', serif;
    }
    div[data-testid="stPlotlyChart"] {
        background: white; border: 1px solid var(--line); padding: .35rem;
    }
    .formula-note {
        margin: .75rem 0 1rem; padding: .8rem 1rem; color: #445564;
        background: #edf0ed; border-left: 3px solid var(--teal); font-size: .82rem;
    }
    .decision-good, .decision-bad {
        padding: .8rem 1rem; margin: .4rem 0 1rem; font-weight: 700;
        border-left: 4px solid;
    }
    .decision-good { color: #126044; background: #e7f4ee; border-color: #167152; }
    .decision-bad { color: #8f342e; background: #f8e9e6; border-color: #ae3f36; }
    .small-note { color: #687783; font-size: .78rem; }
    div[data-testid="stDataFrame"] { border: 1px solid var(--line); }
    .stButton > button[kind="primary"] { background: var(--teal); border-color: var(--teal); }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def load_engine(data_directory: str) -> ModuleType:
    """Load one calculation-engine instance for a staged Data_CC directory."""
    data_path = Path(data_directory).expanduser().resolve()
    os.environ["JOURNAL2_DATA_DIR"] = str(data_path)

    engine_path = APP_DIR / "journal2_engine.py"
    module_name = f"reliability_engine_{abs(hash(str(data_path)))}"
    specification = importlib.util.spec_from_file_location(module_name, engine_path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load the calculation engine: {engine_path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    specification.loader.exec_module(module)
    return module


def money(value: float) -> str:
    return f"${value:.4f}M"


def repair_label(year: int) -> str:
    return "No repair" if int(year) >= 20 else f"Year {int(year)}"


def base_figure(title: str, x_title: str, y_title: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title={"text": title, "font": {"family": "Georgia", "size": 19}},
        xaxis_title=x_title,
        yaxis_title=y_title,
        height=390,
        margin={"l": 55, "r": 25, "t": 65, "b": 50},
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.22, "x": 0.5, "xanchor": "center"},
        font={"family": "Arial", "color": COLORS["navy"]},
    )
    figure.update_xaxes(showgrid=True, gridcolor="#e8ebea", zeroline=False)
    figure.update_yaxes(showgrid=True, gridcolor="#e8ebea", zeroline=False)
    return figure


def show_figure(figure: go.Figure) -> None:
    """Use the correct chart-width parameter across supported Streamlit versions."""
    width_argument = (
        {"width": "stretch"}
        if MODERN_CHART_WIDTH
        else {"use_container_width": True}
    )
    st.plotly_chart(
        figure,
        config={"displaylogo": False},
        **width_argument,
    )


def hazard_figure(result: dict) -> go.Figure:
    hazard = result["prior"]["hazard"]
    figure = base_figure(
        f"Pipe-joint hazard rates · {result['meta']['cracks']} cracks",
        "Year",
        "Annual probability",
    )
    series = [
        ("Combined hazard", hazard["combined"], COLORS["navy"], None),
        ("Burst hazard", hazard["burst"], COLORS["coral"], None),
        ("Leak hazard", hazard["leak"], COLORS["blue"], None),
        (
            f"Pfc = {hazard['threshold']:.1e}",
            [hazard["threshold"]] * len(hazard["years"]),
            COLORS["amber"],
            "dash",
        ),
    ]
    for name, values, color, dash in series:
        figure.add_trace(
            go.Scatter(
                x=hazard["years"],
                y=values,
                name=name,
                mode="lines+markers" if dash is None else "lines",
                line={"color": color, "width": 2.5, "dash": dash},
                marker={"size": 5},
            )
        )
    figure.update_yaxes(type="log")
    return figure


def prior_cost_figure(result: dict) -> go.Figure:
    candidates = result["prior"]["system"]["pi1Candidates"]
    figure = base_figure(
        "System prior cost by repair time", "Repair year", "Expected cost ($M)"
    )
    figure.add_trace(
        go.Scatter(
            x=list(range(len(candidates))),
            y=candidates,
            name="Cprior",
            mode="lines+markers",
            line={"color": COLORS["teal"], "width": 2.7},
            marker={"size": 6},
        )
    )
    return figure


def preposterior_figure(
    result: dict, selected_policy: str, value_key: str, title: str, y_title: str
) -> go.Figure:
    figure = base_figure(title, "Inspection year", y_title)
    years = result["preposterior"]["inspectionTimes"]
    selected_policies = (
        ["pi1", "pi2"] if selected_policy == "Both" else [selected_policy]
    )
    colors = [COLORS["teal"], COLORS["coral"], COLORS["blue"], COLORS["violet"]]
    color_index = 0
    for mode, mode_result in result["preposterior"]["modes"].items():
        for policy in selected_policies:
            summary = mode_result[policy]
            label = f"{POLICY_LABELS[policy]} · {mode}"
            figure.add_trace(
                go.Scatter(
                    x=years,
                    y=summary[value_key],
                    name=label,
                    mode="lines+markers",
                    line={
                        "color": colors[color_index % len(colors)],
                        "width": 2.6,
                        "dash": "dash" if mode == "imperfect" else "solid",
                    },
                    marker={"size": 5},
                )
            )
            color_index += 1
    if value_key == "netVoi":
        figure.add_hline(y=0, line_dash="dot", line_color="#687783")
    return figure


def prior_table(result: dict) -> pd.DataFrame:
    rows = []
    for row in result["prior"]["rows"]:
        rows.append(
            {
                "Analysis level": row["label"],
                "π1 prior cost ($M)": round(row["pi1Cost"], 6),
                "π1 repair": repair_label(row["pi1Repair"]),
                "π2 prior cost ($M)": round(row["pi2Cost"], 6),
                "π2 repair": repair_label(row["pi2Repair"]),
            }
        )
    return pd.DataFrame(rows)


def decision_table(result: dict, selected_policy: str) -> pd.DataFrame:
    rows = []
    for row in result["preposterior"]["table"]:
        policy_key = "pi1" if row["policy"] == "π1" else "pi2"
        if selected_policy != "Both" and policy_key != selected_policy:
            continue
        rows.append(
            {
                "Updated POF case": row["measurement"],
                "Policy": row["policy"],
                "Prior cost ($M)": round(row["priorCost"], 6),
                "Optimal inspection": f"Year {row['optimalInspection']}",
                "Minimum total cost ($M)": round(row["minimumTotal"], 6),
                "Maximum net VoI ($M)": round(row["maxNetVoi"], 6),
                "Justifiable?": "Yes" if row["justifiable"] else "No",
            }
        )
    return pd.DataFrame(rows)


render_project_hero(
    "Journal Paper 2",
    "Reliability and Value-of-Information Planning",
    "Prior and pre-posterior lifecycle analysis for one pipe joint containing one to eight cracks.",
)

st.markdown("## Introduction")
st.markdown(
    """
This module compares reliability-based repair decisions before and after inspection
information becomes available. It evaluates perfect and imperfect updated POF cases,
policies π1 and π2, inspection timing, expected lifecycle cost, and the net value of
inspection information over a 20-year horizon.
"""
)

st.markdown("## Connect the POF datasets")
st.caption(
    "The calculation code is stored in GitHub. Only approved NPZ data arrays are read "
    "from Google Drive or a direct upload; the application never modifies Drive."
)

if "journal2_data_directory" not in st.session_state:
    st.session_state.journal2_data_directory = None
if "journal2_data_source" not in st.session_state:
    st.session_state.journal2_data_source = None

drive_url = st.text_input(
    "Public Google Drive folder",
    value=DEFAULT_DRIVE_FOLDER_URL,
    help="The folder must allow anyone with the link to view the required NPZ files.",
)
drive_col, sync_col = st.columns([1, 1.35])
with drive_col:
    drive_link = (
        drive_url
        if drive_url.startswith("https://drive.google.com/")
        else DEFAULT_DRIVE_FOLDER_URL
    )
    st.link_button(
        "Open Drive folder to upload/manage data",
        drive_link,
        width="stretch",
    )
with sync_col:
    synchronize = st.button(
        "Read the required files from Google Drive",
        type="primary",
        width="stretch",
    )

if synchronize:
    progress_bar = st.progress(0, text="Reading the Google Drive file list…")

    def update_progress(current: int, total: int, filename: str) -> None:
        progress_bar.progress(
            current / total,
            text=f"Preparing {filename} ({current}/{total})",
        )

    try:
        with st.spinner(
            "Downloading the 15 required files. The first connection may take several minutes."
        ):
            synchronized_dir = download_required_drive_data(
                drive_url,
                progress=update_progress,
            )
        st.session_state.journal2_data_directory = str(synchronized_dir)
        st.session_state.journal2_data_source = "Google Drive"
        st.session_state.analysis_result = None
        st.session_state.analysis_error = None
        progress_bar.progress(1.0, text="POF datasets are ready")
    except Exception as problem:
        progress_bar.empty()
        st.error(f"The Drive data could not be prepared: {problem}")

with st.expander("Direct upload fallback", expanded=False):
    st.markdown(
        "If Drive is unavailable or rate-limited, select all 15 required NPZ files. "
        "Files are validated before the model is enabled."
    )
    uploaded_files = st.file_uploader(
        "Upload Journal 2 NPZ files",
        type="npz",
        accept_multiple_files=True,
        help="Required filenames are listed below and in the repository data guide.",
    )
    if st.button(
        "Validate and use uploaded files",
        disabled=not uploaded_files,
        width="stretch",
    ):
        try:
            uploaded_dir = stage_uploaded_files(uploaded_files)
            st.session_state.journal2_data_directory = str(uploaded_dir)
            st.session_state.journal2_data_source = "Direct upload"
            st.session_state.analysis_result = None
            st.session_state.analysis_error = None
            st.success("The uploaded POF datasets passed validation.")
        except Exception as problem:
            st.error(str(problem))
    st.code("\n".join(REQUIRED_FILES), language=None)

data_directory = st.session_state.journal2_data_directory
if data_directory:
    data_problems = validate_data_directory(
        Path(data_directory),
        check_archives=False,
    )
    if data_problems:
        st.session_state.journal2_data_directory = None
        st.error("The prepared data are incomplete: " + "; ".join(data_problems))
        st.stop()
    st.success(
        f"Journal 2 data are ready from {st.session_state.journal2_data_source}. "
        "Configure the analysis in the left panel."
    )
else:
    st.info(
        "Connect the public Drive folder or upload the required NPZ files to enable the analysis."
    )
    st.stop()


with st.sidebar:
    st.header("Analysis inputs")
    number_of_cracks = st.slider(
        "Number of cracks in the pipe joint",
        min_value=1,
        max_value=8,
        value=3,
        step=1,
    )
    st.markdown("**Template assigned to each crack**")
    st.caption("Templates 1, 2, and 3 use the three currently available POF datasets.")
    crack_types = []
    template_columns = st.columns(2)
    for crack_index in range(number_of_cracks):
        with template_columns[crack_index % 2]:
            crack_types.append(
                st.selectbox(
                    f"Crack {crack_index + 1}",
                    TEMPLATE_IDS,
                    index=crack_index % len(TEMPLATE_IDS),
                    key=f"crack_template_{crack_index}",
                    format_func=lambda source: CRACK_TEMPLATE_LABELS[source],
                )
            )

    with st.form("analysis_inputs"):
        pof_source = st.radio(
            "POF source",
            ["Use pre-calculated POFs", "Calculate POFs"],
            horizontal=True,
        )
        selected_policy_label = st.radio(
            "Policies to display", ["Both", "π1", "π2"], index=0, horizontal=True
        )
        pfc = st.selectbox(
            "Policy π2 threshold, Pfc",
            [1e-3, 3e-4, 3e-5],
            format_func=lambda value: f"{value:.1e}",
        )
        custom_pfc = st.number_input(
            "Custom Pfc",
            min_value=0.0,
            value=float(pfc),
            step=0.00001,
            format="%.6f",
        )
        measurement_label = st.selectbox(
            "Updated POF set",
            ["Perfect and imperfect", "Perfect only", "Imperfect only"],
        )
        use_pod_model = st.toggle("Use probability-of-detection model", value=False)

        st.markdown("**Economic inputs — million dollars**")
        col_a, col_b = st.columns(2)
        with col_a:
            cf_leak = st.number_input("Cfleak", min_value=0.0, value=1.0, step=0.1)
            repair_cost = st.number_input("Cr", min_value=0.0, value=0.2, step=0.01)
            discount_rate = st.number_input(
                "Discount rate", min_value=0.0, value=0.04, step=0.01
            )
        with col_b:
            cf_burst = st.number_input(
                "Cfburst", min_value=0.000001, value=10.0, step=0.5
            )
            inspection_cost = st.number_input(
                "Cinsp", min_value=0.0, value=0.02, step=0.01
            )

        calculate_selected = pof_source == "Calculate POFs"
        run_clicked = st.form_submit_button(
            "Run analysis",
            type="primary",
            use_container_width=True,
            disabled=calculate_selected,
        )

    if calculate_selected:
        st.info(
            "The connection point is ready, but POF calculation and reliability "
            "updating are intentionally reserved for the next version."
        )
    st.caption("Current calculations use the loaded 10,000-sample updated POF files.")


measurement = {
    "Perfect and imperfect": "both",
    "Perfect only": "perfect",
    "Imperfect only": "imperfect",
}[measurement_label]
selected_policy = {
    "Both": "Both",
    "π1": "pi1",
    "π2": "pi2",
}[selected_policy_label]

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "analysis_error" not in st.session_state:
    st.session_state.analysis_error = None

if run_clicked:
    try:
        data_path = Path(data_directory).expanduser().resolve()
        data_problems = validate_data_directory(data_path, check_archives=False)
        if data_problems:
            raise FileNotFoundError("; ".join(data_problems))
        with st.spinner("Reading updated POFs and evaluating both policies…"):
            engine = load_engine(str(data_path))
            st.session_state.analysis_result = engine.calculate(
                {
                    "pofSource": "loaded",
                    "measurement": measurement,
                    "crackTypes": [
                        TEMPLATE_SOURCE_BY_ID[int(template_id)]
                        for template_id in crack_types
                    ],
                    "usePodModel": use_pod_model,
                    "cfLeak": cf_leak,
                    "cfBurst": cf_burst,
                    "repairCost": repair_cost,
                    "inspectionCost": inspection_cost,
                    "discountRate": discount_rate,
                    "pfc": custom_pfc,
                }
            )
        st.session_state.analysis_error = None
    except Exception as problem:  # Streamlit should present the useful message
        st.session_state.analysis_error = str(problem)


if st.session_state.analysis_error:
    st.error(st.session_state.analysis_error)

result = st.session_state.analysis_result
if result is None:
    st.info("Choose the inputs in the left panel and select **Run analysis**.")
    st.stop()


result_types = result["meta"]["crackTypes"]
result_crack_count = len(result_types)
summary_mode = result["preposterior"]["modes"].get("imperfect")
if summary_mode is None:
    summary_mode = result["preposterior"]["modes"].get("perfect")
summary_policy = "pi2" if selected_policy == "pi2" else "pi1"
summary = summary_mode[summary_policy]
prior_cost = result["prior"]["system"][f"{summary_policy}Cost"]
prior_repair = result["prior"]["system"][f"{summary_policy}Repair"]

if result_types != crack_types:
    st.warning(
        "The crack population controls have changed. Select **Run analysis** "
        "to update the plots and tables."
    )

st.caption(
    f"Displayed pipe joint: {result_crack_count} crack(s) · templates "
    + ", ".join(str(source) for source in result_types)
)

metric_columns = st.columns(4)
metric_columns[0].metric(
    f"{POLICY_LABELS[summary_policy]} joint prior cost · {result_crack_count} cracks",
    money(prior_cost),
    help="Expected cost without inspection information.",
)
metric_columns[1].metric(
    "Prior optimal repair",
    repair_label(prior_repair),
    help="The prior joint-level repair decision for the selected population and policy.",
)
metric_columns[2].metric(
    "Optimal inspection",
    f"Year {summary['optimalInspection']}",
    help="Minimizes Cpp plus the discounted inspection cost.",
)
metric_columns[3].metric(
    "Maximum net VoI",
    money(summary["maxNetVoi"]),
    delta="Justifiable" if summary["justifiable"] else "Not justifiable",
    delta_color="normal" if summary["justifiable"] else "inverse",
)


prior_tab, preposterior_tab = st.tabs(["Prior analysis", "Pre-posterior and VoI"])

with prior_tab:
    plot_col_a, plot_col_b = st.columns(2)
    with plot_col_a:
        show_figure(hazard_figure(result))
    with plot_col_b:
        show_figure(prior_cost_figure(result))

    st.markdown(
        """
        <div class="formula-note">
        <b>Policy π2:</b> Hf,comb = Hf,burst + Hf,leak × Cfleak / Cfburst.
        Year 20 in the calculation represents the no-repair alternative.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("Prior cost and optimal repair time under each policy")
    st.dataframe(prior_table(result), width="stretch", hide_index=True)

with preposterior_tab:
    decision_class = "decision-good" if summary["justifiable"] else "decision-bad"
    decision_text = (
        "Inspection is economically justifiable"
        if summary["justifiable"]
        else "Inspection is not economically justifiable"
    )
    st.markdown(
        f'<div class="{decision_class}">{decision_text} for the displayed '
        f'{POLICY_LABELS[summary_policy]} reference case.</div>',
        unsafe_allow_html=True,
    )

    plot_col_a, plot_col_b = st.columns(2)
    with plot_col_a:
        show_figure(
            preposterior_figure(
                result,
                selected_policy,
                "total",
                "Total expected cost by inspection year",
                "Cpp + discounted Cinsp ($M)",
            )
        )
    with plot_col_b:
        show_figure(
            preposterior_figure(
                result,
                selected_policy,
                "netVoi",
                "Net value of information by inspection year",
                "Net VoI ($M)",
            )
        )

    st.markdown(
        """
        <div class="formula-note">
        <b>Net VoI(T)</b> = Cprior − [Cpp(T) + Cinsp/(1+r)<sup>T</sup>].
        Inspection is justifiable when the maximum net VoI is positive.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("VoI, justifiability, and optimal inspection time")
    st.dataframe(
        decision_table(result, selected_policy),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "The updated component POFs are combined as an independent series system. "
        "One inspection cost and one joint-level repair action are used."
    )

with st.expander("Export this run"):
    st.download_button(
        "Download results as JSON",
        data=json.dumps(result, indent=2),
        file_name=f"reliability_results_{result_crack_count}_cracks.json",
        mime="application/json",
    )
