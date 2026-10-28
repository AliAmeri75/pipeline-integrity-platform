"""Interactive measured-profile views for Data Exploration."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


PLOTLY_CDN_URL = "https://cdn.plot.ly/plotly-3.3.0.min.js"


def measured_depth_grid(
    profile: pd.DataFrame,
    wall_thickness_mm: float | None,
) -> tuple[list[float], list[float], np.ndarray, str]:
    """Return the measured profile as sorted x, y, and depth arrays.

    Depth is reported in millimetres when wall thickness is available. Otherwise
    the original percentage-of-wall-thickness measurements are retained.
    """

    required = {
        "Axial offset (mm)",
        "Circumferential offset (mm)",
        "Depth (%WT)",
    }
    missing = required.difference(profile.columns)
    if missing:
        raise ValueError(
            "Profile data are missing required columns: "
            + ", ".join(sorted(missing))
        )
    if profile.empty:
        raise ValueError("The selected profile does not contain measured cells.")

    grid = (
        profile.pivot_table(
            index="Circumferential offset (mm)",
            columns="Axial offset (mm)",
            values="Depth (%WT)",
            aggfunc="mean",
        )
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    depth = grid.to_numpy(dtype=float)
    wall = None
    if wall_thickness_mm is not None:
        try:
            candidate = float(wall_thickness_mm)
        except (TypeError, ValueError):
            candidate = math.nan
        if math.isfinite(candidate) and candidate > 0:
            wall = candidate
    if wall is not None:
        depth = depth * wall / 100.0
        unit = "mm"
    else:
        unit = "%WT"
    return (
        [float(value) for value in grid.columns],
        [float(value) for value in grid.index],
        depth,
        unit,
    )


def measured_profile_figures(
    profile: pd.DataFrame,
    wall_thickness_mm: float | None,
    profile_id: str,
) -> tuple[go.Figure, go.Figure, list[float], list[float], np.ndarray, str]:
    """Create exact measured 2D and 3D profile figures."""

    x_values, y_values, depth, unit = measured_depth_grid(
        profile, wall_thickness_mm
    )
    if not np.isfinite(depth).any():
        raise ValueError("The selected profile has no finite depth measurements.")
    maximum_index = np.unravel_index(np.nanargmax(depth), depth.shape)
    initial_x = x_values[maximum_index[1]]
    initial_y = y_values[maximum_index[0]]
    initial_depth = float(depth[maximum_index])
    color_maximum = max(initial_depth, 0.01)

    heatmap = go.Figure(
        go.Heatmap(
            x=x_values,
            y=y_values,
            z=depth,
            colorscale="YlOrRd",
            zmin=0,
            zmax=color_maximum,
            colorbar={"title": f"Depth<br>({unit})"},
            hovertemplate=(
                "Axial: %{x:.1f} mm<br>Circumferential: %{y:.1f} mm<br>"
                f"Depth: %{{z:.3f}} {unit}<extra></extra>"
            ),
        )
    )
    heatmap.add_trace(
        go.Scatter(
            x=[initial_x],
            y=[initial_y],
            mode="markers",
            marker={
                "size": 12,
                "color": "#ffdb05",
                "line": {"color": "#14251c", "width": 2},
            },
            showlegend=False,
            hoverinfo="skip",
        )
    )
    heatmap.update_layout(
        title=f"Measured 2D profile · {profile_id}",
        xaxis_title="Axial distance from profile start (mm)",
        yaxis_title="Circumferential distance (mm)",
        height=440,
        margin={"l": 55, "r": 20, "t": 55, "b": 55},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#fbfdfc",
        font={"family": "Inter, Arial, sans-serif", "color": "#14251c"},
    )

    xx, yy = np.meshgrid(x_values, y_values)
    surface = go.Figure(
        go.Surface(
            x=xx,
            y=yy,
            z=-depth,
            surfacecolor=depth,
            colorscale="YlOrRd",
            cmin=0,
            cmax=color_maximum,
            colorbar={"title": f"Depth<br>({unit})"},
            hovertemplate=(
                "Axial: %{x:.1f} mm<br>Circumferential: %{y:.1f} mm<br>"
                f"Depth: %{{surfacecolor:.3f}} {unit}<extra></extra>"
            ),
        )
    )
    surface.add_trace(
        go.Scatter3d(
            x=[initial_x],
            y=[initial_y],
            z=[-initial_depth],
            mode="markers",
            marker={
                "size": 6,
                "color": "#ffdb05",
                "line": {"color": "#14251c", "width": 2},
            },
            showlegend=False,
            hoverinfo="skip",
        )
    )
    surface.update_layout(
        title=f"Measured 3D surface · {profile_id}",
        height=440,
        margin={"l": 0, "r": 0, "t": 55, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, Arial, sans-serif", "color": "#14251c"},
        scene={
            "xaxis_title": "Axial (mm)",
            "yaxis_title": "Circumferential (mm)",
            "zaxis_title": f"Surface depth ({unit})",
            "zaxis": {"autorange": "reversed"},
            "camera": {"eye": {"x": 1.5, "y": -1.6, "z": 0.9}},
            # Depth is usually much smaller than length. This aspect ratio makes
            # the shape visible while tooltips and colour retain exact values.
            "aspectratio": {"x": 1.5, "y": 1.0, "z": 0.6},
        },
    )
    return heatmap, surface, x_values, y_values, depth, unit


def linked_measured_profile_html(
    profile: pd.DataFrame,
    wall_thickness_mm: float | None,
    profile_id: str,
) -> str:
    """Return a linked 2D/3D explorer for the actual measured profile grid."""

    heatmap, surface, x_values, y_values, depth, unit = measured_profile_figures(
        profile, wall_thickness_mm, profile_id
    )
    maximum_index = np.unravel_index(np.nanargmax(depth), depth.shape)
    initial_x = x_values[maximum_index[1]]
    initial_y = y_values[maximum_index[0]]
    initial_depth = float(depth[maximum_index])
    depth_values = [
        [float(value) if math.isfinite(float(value)) else None for value in row]
        for row in depth
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="{PLOTLY_CDN_URL}"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; color:#14251c; background:transparent;
      font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    .shell {{ padding:10px; border:1px solid #d8e2da; border-radius:18px;
      background:#fff; box-shadow:0 12px 30px rgba(20,49,32,.08); }}
    .header {{ display:flex; justify-content:space-between; gap:12px;
      padding:2px 8px 8px; flex-wrap:wrap; }}
    .title {{ font-weight:850; color:#173d27; }}
    .hint {{ color:#5b6961; font-size:12px; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:8px; }}
    .panel {{ min-width:0; border:1px solid #e5ece7; border-radius:14px;
      overflow:hidden; background:#fbfdfc; }}
    .plot {{ width:100%; height:440px; }}
    #readout {{ margin:9px 8px 3px; padding:9px 12px; border-radius:10px;
      background:#f1f6f2; border-left:4px solid #ffdb05; font-size:13px; }}
    #error {{ display:none; margin:12px; padding:12px; color:#8b1a1a;
      background:#fff1f1; border-radius:10px; }}
    @media (max-width:720px) {{ .grid {{ grid-template-columns:1fr; }} .plot {{ height:390px; }} }}
  </style>
</head>
<body>
  <section class="shell" aria-label="Linked measured two-dimensional and three-dimensional defect views">
    <div class="header">
      <span class="title">Linked measured-profile explorer</span>
      <span class="hint">Move over either view—the gold point follows in both.</span>
    </div>
    <div id="error">The interactive figures could not be loaded. Please refresh the page.</div>
    <div class="grid">
      <div class="panel"><div id="profile-map" class="plot"></div></div>
      <div class="panel"><div id="profile-surface" class="plot"></div></div>
    </div>
    <div id="readout">Axial: {initial_x:.1f} mm • Circumferential: {initial_y:.1f} mm • Depth: {initial_depth:.3f} {unit}</div>
  </section>
  <script>
  (() => {{
    const errorBox = document.getElementById("error");
    if (typeof Plotly === "undefined") {{ errorBox.style.display = "block"; return; }}
    const mapFigure = {heatmap.to_json()};
    const surfaceFigure = {surface.to_json()};
    const xValues = {json.dumps(x_values)};
    const yValues = {json.dumps(y_values)};
    const depthValues = {json.dumps(depth_values)};
    const mapDiv = document.getElementById("profile-map");
    const surfaceDiv = document.getElementById("profile-surface");
    const readout = document.getElementById("readout");
    const config = {{ responsive:true, displaylogo:false,
      modeBarButtonsToRemove:["lasso2d","select2d"] }};
    const nearest = (values,target) => values.reduce((best,value,index) =>
      Math.abs(value-target) < Math.abs(values[best]-target) ? index : best, 0);
    let pending = null;
    let frame = null;
    const synchronize = (xTarget,yTarget) => {{
      const column = nearest(xValues,Number(xTarget));
      const row = nearest(yValues,Number(yTarget));
      const x = xValues[column]; const y = yValues[row]; const depth = depthValues[row][column];
      if (depth === null || !Number.isFinite(depth)) return;
      Plotly.restyle(mapDiv, {{x:[[x]],y:[[y]]}}, [1]);
      Plotly.restyle(surfaceDiv, {{x:[[x]],y:[[y]],z:[[-depth]]}}, [1]);
      readout.textContent = `Axial: ${{x.toFixed(1)}} mm • Circumferential: ${{y.toFixed(1)}} mm • Depth: ${{depth.toFixed(3)}} {unit}`;
    }};
    const schedule = point => {{
      if (!point || !Number.isFinite(Number(point.x)) || !Number.isFinite(Number(point.y))) return;
      pending = {{x:Number(point.x),y:Number(point.y)}};
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {{ synchronize(pending.x,pending.y); frame=null; }});
    }};
    Promise.all([
      Plotly.newPlot(mapDiv,mapFigure.data,mapFigure.layout,config),
      Plotly.newPlot(surfaceDiv,surfaceFigure.data,surfaceFigure.layout,config)
    ]).then(() => {{
      mapDiv.on("plotly_hover",event => schedule(event.points[0]));
      surfaceDiv.on("plotly_hover",event => schedule(event.points[0]));
    }}).catch(() => {{ errorBox.style.display="block"; }});
  }})();
  </script>
</body>
</html>"""


def measured_profile_on_pipe_figure(
    profile: pd.DataFrame,
    wall_thickness_mm: float | None,
    outside_diameter_mm: float | None,
    profile_id: str,
    defect_type: str,
) -> go.Figure:
    """Place the measured profile on a schematic cylindrical pipe surface."""

    x_values, y_values, depth, unit = measured_depth_grid(
        profile, wall_thickness_mm
    )
    if not np.isfinite(depth).any():
        raise ValueError("The selected profile has no finite depth measurements.")
    profile_length = max(x_values) - min(x_values) if len(x_values) > 1 else 20.0
    view_length = max(profile_length * 1.8, 100.0)
    x_center = 0.5 * (min(x_values) + max(x_values))
    base_x = np.linspace(x_center - view_length / 2, x_center + view_length / 2, 101)
    base_theta = np.linspace(-math.pi, math.pi, 81)
    base_xx, base_tt = np.meshgrid(base_x, base_theta)

    radius_mm = None
    if outside_diameter_mm is not None:
        try:
            diameter = float(outside_diameter_mm)
        except (TypeError, ValueError):
            diameter = math.nan
        if math.isfinite(diameter) and diameter > 0:
            radius_mm = diameter / 2.0
    if radius_mm is None:
        radius_mm = max(10.0, (max(y_values) - min(y_values)) * 3.0)

    figure = go.Figure()
    figure.add_trace(
        go.Surface(
            x=base_xx,
            y=np.cos(base_tt),
            z=np.sin(base_tt),
            surfacecolor=np.zeros_like(base_xx),
            colorscale=[[0, "#dce5df"], [1, "#dce5df"]],
            showscale=False,
            opacity=0.72,
            hoverinfo="skip",
            name="Pipe surface",
        )
    )

    patch_x, patch_y = np.meshgrid(x_values, y_values)
    circumferential_center = 0.5 * (min(y_values) + max(y_values))
    patch_theta = (patch_y - circumferential_center) / radius_mm
    wall = None
    if wall_thickness_mm is not None:
        try:
            wall_candidate = float(wall_thickness_mm)
        except (TypeError, ValueError):
            wall_candidate = math.nan
        if math.isfinite(wall_candidate) and wall_candidate > 0:
            wall = wall_candidate
    if wall is not None and unit == "mm":
        depth_fraction = np.clip(depth / wall, 0.0, 1.0)
    else:
        depth_fraction = np.clip(depth / 100.0, 0.0, 1.0)
    # The depression is enlarged for visibility. Colour and hover values keep
    # the measured depth, so the visual scaling cannot be mistaken for a value.
    display_radius = 1.006 - 0.22 * depth_fraction
    maximum_depth = max(float(np.nanmax(depth)), 0.01)
    figure.add_trace(
        go.Surface(
            x=patch_x,
            y=display_radius * np.cos(patch_theta),
            z=display_radius * np.sin(patch_theta),
            surfacecolor=depth,
            colorscale="YlOrRd",
            cmin=0,
            cmax=maximum_depth,
            colorbar={"title": f"Depth<br>({unit})"},
            hovertemplate=(
                "Axial: %{x:.1f} mm<br>"
                f"Measured depth: %{{surfacecolor:.3f}} {unit}<extra></extra>"
            ),
            name="Measured profile",
        )
    )
    figure.update_layout(
        title=f"{defect_type} profile on pipe · {profile_id}",
        height=500,
        margin={"l": 0, "r": 0, "t": 55, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, Arial, sans-serif", "color": "#14251c"},
        scene={
            "xaxis_title": "Pipe axis (mm)",
            "yaxis_title": "",
            "zaxis_title": "",
            "camera": {"eye": {"x": 1.45, "y": -1.65, "z": 0.85}},
            "aspectratio": {"x": 2.2, "y": 1.0, "z": 1.0},
        },
    )
    return figure


def render_linked_measured_profile(
    profile: pd.DataFrame,
    wall_thickness_mm: float | None,
    profile_id: str,
) -> None:
    """Render the linked measured-profile explorer in Streamlit."""

    st.iframe(
        linked_measured_profile_html(profile, wall_thickness_mm, profile_id),
        height=570,
        width="stretch",
    )
