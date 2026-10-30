"""Explore ground-movement observations along a pipeline route."""

from __future__ import annotations

from io import BytesIO
import json
import math

import altair as alt
import folium
from folium.plugins import Draw, HeatMap
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from map_presentation import readable_map_overlays
from platform_ui import render_project_hero
from profile_map import (
    EDMONTON_SAMPLE_ROUTE,
    haversine_distance_km,
    latest_route_from_drawings,
    point_at_chainage,
    route_length_km,
)


ROUTE_KEY = "data_exploration_map_route"
ROUTE_REVISION_KEY = "data_exploration_map_revision"
REQUIRED_COLUMNS = {
    "Latitude",
    "Longitude",
    "East displacement (mm)",
    "North displacement (mm)",
    "Vertical displacement (mm)",
}


@st.cache_data(show_spinner=False)
def sample_ground_movement_csv(
    route_coordinates: tuple[tuple[float, float], ...]
) -> bytes:
    """Return a synthetic survey near the currently shared demonstration route."""

    rng = np.random.default_rng(24)
    route = [list(point) for point in route_coordinates]
    length_km = route_length_km(route)
    records: list[dict[str, float | str]] = []
    for index, fraction in enumerate(np.linspace(0.0, 1.0, 90), start=1):
        latitude, longitude = point_at_chainage(route, fraction * length_km)
        latitude += rng.normal(0.0, 0.00045)
        longitude += rng.normal(0.0, 0.00065)
        hotspot_1 = 46.0 * math.exp(-((fraction - 0.43) / 0.085) ** 2)
        hotspot_2 = 27.0 * math.exp(-((fraction - 0.76) / 0.065) ** 2)
        background = 2.5 + 2.2 * math.sin(fraction * 4.0 * math.pi) ** 2
        magnitude = max(0.5, background + hotspot_1 + hotspot_2 + rng.normal(0, 1.2))
        direction = 0.6 + 1.2 * fraction
        east = magnitude * math.cos(direction)
        north = magnitude * math.sin(direction)
        vertical = 0.22 * magnitude * math.sin(fraction * 3.0 * math.pi)
        records.append(
            {
                "Survey point": f"GM-{index:03d}",
                "Latitude": round(latitude, 7),
                "Longitude": round(longitude, 7),
                "East displacement (mm)": round(east, 2),
                "North displacement (mm)": round(north, 2),
                "Vertical displacement (mm)": round(vertical, 2),
            }
        )
    return pd.DataFrame(records).to_csv(index=False).encode("utf-8")


def read_movement_data(content: bytes, filename: str) -> pd.DataFrame:
    """Read and validate a simple displacement table."""

    if filename.lower().endswith(".csv"):
        data = pd.read_csv(BytesIO(content))
    else:
        data = pd.read_excel(BytesIO(content))
    data.columns = [str(column).strip() for column in data.columns]
    missing = REQUIRED_COLUMNS.difference(data.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    if "Survey point" not in data.columns:
        data.insert(0, "Survey point", [f"GM-{index:03d}" for index in range(1, len(data) + 1)])
    numeric_columns = list(REQUIRED_COLUMNS)
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[numeric_columns].isna().any().any():
        raise ValueError("The required coordinate and displacement columns must contain numeric values.")
    if not data["Latitude"].between(-90, 90).all() or not data["Longitude"].between(-180, 180).all():
        raise ValueError("Latitude or longitude is outside its valid range.")
    data = data.copy()
    data["Horizontal displacement (mm)"] = np.hypot(
        data["East displacement (mm)"], data["North displacement (mm)"]
    )
    data["Ground displacement magnitude (mm)"] = np.sqrt(
        data["Horizontal displacement (mm)"] ** 2
        + data["Vertical displacement (mm)"] ** 2
    )
    return data


def route_samples(route: list[list[float]], count: int = 240) -> tuple[np.ndarray, np.ndarray]:
    """Return route sample coordinates and their chainages."""

    length_km = route_length_km(route)
    chainages = np.linspace(0.0, length_km, max(2, count))
    coordinates = np.asarray([point_at_chainage(route, value) for value in chainages])
    return coordinates, chainages


def add_pipeline_proximity(data: pd.DataFrame, route: list[list[float]]) -> pd.DataFrame:
    """Estimate nearest route chainage and offset for display, not structural analysis."""

    if len(route) < 2:
        return data
    coordinates, chainages = route_samples(route)
    route_latitude = np.radians(coordinates[:, 0])
    route_longitude = np.radians(coordinates[:, 1])
    output = data.copy()
    nearest_chainages: list[float] = []
    nearest_offsets: list[float] = []
    for latitude, longitude in output[["Latitude", "Longitude"]].itertuples(index=False, name=None):
        latitude_radians = math.radians(float(latitude))
        longitude_radians = math.radians(float(longitude))
        delta_latitude = route_latitude - latitude_radians
        delta_longitude = route_longitude - longitude_radians
        value = (
            np.sin(delta_latitude / 2.0) ** 2
            + math.cos(latitude_radians)
            * np.cos(route_latitude)
            * np.sin(delta_longitude / 2.0) ** 2
        )
        distances = 2.0 * 6371.0088 * np.arcsin(np.sqrt(np.clip(value, 0.0, 1.0)))
        nearest = int(np.argmin(distances))
        nearest_chainages.append(float(chainages[nearest]))
        nearest_offsets.append(float(distances[nearest] * 1000.0))
    output["Nearest pipeline chainage (km)"] = nearest_chainages
    output["Distance to pipeline (m)"] = nearest_offsets
    return output


def movement_colour(value: float, limits: tuple[float, float, float]) -> str:
    """Return a relative display colour based on this dataset's quantiles."""

    low, high, highest = limits
    if value >= highest:
        return "#8b1e3f"
    if value >= high:
        return "#d35400"
    if value >= low:
        return "#f1c40f"
    return "#2e8b57"


def render_ground_movement_map(data: pd.DataFrame, route: list[list[float]], influence_radius_m: float) -> None:
    """Render pipeline, relative ground movement and editable route."""

    display_data = data.nlargest(min(len(data), 1200), "Ground displacement magnitude (mm)").copy()
    values = display_data["Ground displacement magnitude (mm)"]
    limits = tuple(float(value) for value in values.quantile([0.50, 0.75, 0.90]).tolist())
    maximum = max(float(values.max()), 1e-9)
    if route:
        center = [
            sum(point[0] for point in route) / len(route),
            sum(point[1] for point in route) / len(route),
        ]
    else:
        center = [float(display_data["Latitude"].mean()), float(display_data["Longitude"].mean())]

    movement_map = folium.Map(location=center, zoom_start=11, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street map", control=True).add_to(movement_map)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        control=True,
    ).add_to(movement_map)

    heat_group = folium.FeatureGroup(name="Ground-movement heat map", show=True)
    HeatMap(
        [
            [float(row["Latitude"]), float(row["Longitude"]), float(row["Ground displacement magnitude (mm)"]) / maximum]
            for _, row in display_data.iterrows()
        ],
        min_opacity=0.20,
        radius=26,
        blur=20,
        gradient={0.15: "#2e8b57", 0.45: "#f1c40f", 0.72: "#d35400", 1.0: "#8b1e3f"},
    ).add_to(heat_group)
    heat_group.add_to(movement_map)

    point_group = folium.FeatureGroup(name="Survey observations", show=False)
    for _, row in display_data.iterrows():
        magnitude = float(row["Ground displacement magnitude (mm)"])
        folium.CircleMarker(
            [float(row["Latitude"]), float(row["Longitude"])],
            radius=5,
            color="white",
            weight=1,
            fill=True,
            fill_color=movement_colour(magnitude, limits),
            fill_opacity=0.90,
            tooltip=f"{row['Survey point']} · {magnitude:.1f} mm",
            popup=folium.Popup(
                f"<b>{row['Survey point']}</b><br>"
                f"Total displacement: {magnitude:.2f} mm<br>"
                f"East: {float(row['East displacement (mm)']):.2f} mm<br>"
                f"North: {float(row['North displacement (mm)']):.2f} mm<br>"
                f"Vertical: {float(row['Vertical displacement (mm)']):.2f} mm<br>"
                f"Nearest pipeline chainage: {float(row.get('Nearest pipeline chainage (km)', float('nan'))):.3f} km<br>"
                f"Offset from route: {float(row.get('Distance to pipeline (m)', float('nan'))):.1f} m",
                max_width=300,
            ),
        ).add_to(point_group)
    point_group.add_to(movement_map)

    if len(route) >= 2:
        coordinates, chainages = route_samples(route, count=70)
        pipeline_group = folium.FeatureGroup(name="Pipeline exposure screening", show=True)
        for start, end, start_chainage, end_chainage in zip(
            coordinates[:-1], coordinates[1:], chainages[:-1], chainages[1:]
        ):
            midpoint = [(start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0]
            nearby = display_data[
                display_data.apply(
                    lambda row: haversine_distance_km(
                        midpoint, [float(row["Latitude"]), float(row["Longitude"])]
                    )
                    * 1000.0
                    <= influence_radius_m,
                    axis=1,
                )
            ]
            if nearby.empty:
                colour = "#607d8b"
                label = "No nearby observation"
            else:
                segment_movement = float(nearby["Ground displacement magnitude (mm)"].max())
                colour = movement_colour(segment_movement, limits)
                label = f"Nearby observed movement: {segment_movement:.1f} mm"
            folium.PolyLine(
                [start.tolist(), end.tolist()],
                color=colour,
                weight=7,
                opacity=0.96,
                tooltip=(
                    f"Pipeline {start_chainage:.2f}–{end_chainage:.2f} km · {label}"
                ),
            ).add_to(pipeline_group)
        pipeline_group.add_to(movement_map)
        folium.Marker(route[0], tooltip="Pipeline route start", icon=folium.Icon(color="green")).add_to(movement_map)
        folium.Marker(route[-1], tooltip="Pipeline route end", icon=folium.Icon(color="blue")).add_to(movement_map)
        movement_map.fit_bounds(route, padding=(25, 25))

    Draw(
        export=False,
        draw_options={
            "polyline": {"shapeOptions": {"color": "#16a6a1", "weight": 6}},
            "marker": False,
            "polygon": False,
            "rectangle": False,
            "circle": False,
            "circlemarker": False,
        },
        edit_options={"edit": False, "remove": True},
    ).add_to(movement_map)
    folium.LayerControl(collapsed=False).add_to(movement_map)
    readable_map_overlays(movement_map)
    result = st_folium(
        movement_map,
        height=590,
        use_container_width=True,
        returned_objects=["all_drawings"],
        key=f"geohazard_movement_map_{st.session_state[ROUTE_REVISION_KEY]}",
    )
    new_route = latest_route_from_drawings(result.get("all_drawings") or [])
    if new_route and new_route != route:
        st.session_state[ROUTE_KEY] = new_route
        st.session_state[ROUTE_REVISION_KEY] += 1
        st.rerun()


render_project_hero(
    "Maintenance Planning (Geohazards)",
    "Data Exploration",
    "Explore a pipeline route together with ground-movement observations before pipe-response modelling.",
)

st.markdown(
    """
    <div class="notice"><strong>Purpose of this first-stage module.</strong> Compare a pipeline route with
    measured or processed ground displacement, identify areas that deserve closer review, and prepare data for
    a future pipe-response model. This page does not yet calculate pipe displacement, load, strain, or safety.</div>
    """,
    unsafe_allow_html=True,
)

if ROUTE_KEY not in st.session_state:
    st.session_state[ROUTE_KEY] = [point[:] for point in EDMONTON_SAMPLE_ROUTE]
if ROUTE_REVISION_KEY not in st.session_state:
    st.session_state[ROUTE_REVISION_KEY] = 0

st.subheader("1. Choose ground-movement data")
source = st.radio(
    "Ground-movement source",
    ["Sample ground-movement survey", "Upload processed displacement data"],
    horizontal=True,
    label_visibility="collapsed",
)
sample_route = st.session_state[ROUTE_KEY]
if len(sample_route) < 2:
    sample_route = EDMONTON_SAMPLE_ROUTE
sample_content = sample_ground_movement_csv(
    tuple((float(point[0]), float(point[1])) for point in sample_route)
)
if source == "Sample ground-movement survey":
    content = sample_content
    filename = "sample_ground_movement.csv"
    st.info(
        "Synthetic sample data for demonstrating the map. It does not represent an operating pipeline or a real LiDAR survey."
    )
    st.download_button(
        "Download sample ground-movement data",
        data=sample_content,
        file_name=filename,
        mime="text/csv",
    )
else:
    upload = st.file_uploader(
        "Upload CSV or Excel data",
        type=["csv", "xlsx"],
        help=(
            "Upload processed observations with latitude, longitude, and east, north, and vertical displacement in millimetres. "
            "Raw LiDAR point clouds require a separate preprocessing workflow."
        ),
    )
    if upload is None:
        st.caption("Download the sample file to see the required column names and format.")
        st.download_button(
            "Download upload template",
            data=sample_content,
            file_name="ground_movement_upload_template.csv",
            mime="text/csv",
        )
        st.stop()
    content = upload.getvalue()
    filename = upload.name

try:
    movement_data = read_movement_data(content, filename)
except (ValueError, pd.errors.ParserError) as error:
    st.error(f"The ground-movement file could not be used: {error}")
    st.stop()

st.subheader("2. Confirm the pipeline route")
route_actions = st.columns([1, 1, 2])
if route_actions[0].button("Load Edmonton sample route", use_container_width=True):
    st.session_state[ROUTE_KEY] = [point[:] for point in EDMONTON_SAMPLE_ROUTE]
    st.session_state[ROUTE_REVISION_KEY] += 1
    st.rerun()
if route_actions[1].button("Clear pipeline route", use_container_width=True):
    st.session_state[ROUTE_KEY] = []
    st.session_state[ROUTE_REVISION_KEY] += 1
    st.rerun()
route_actions[2].caption(
    "This is the same route stored by Crack/Corrosion Data Exploration. Drawing a new line here updates the shared route."
)

with st.expander("Upload a pipeline centreline (GeoJSON)", expanded=False):
    route_upload = st.file_uploader(
        "Route LineString or LineString Feature",
        type=["geojson", "json"],
        key="geohazard_route_upload",
    )
    if route_upload is not None and st.button("Apply uploaded geohazard centreline"):
        try:
            document = json.loads(route_upload.getvalue())
            geometry = document.get("geometry", document)
            if geometry["type"] != "LineString":
                raise ValueError("Use a single GeoJSON LineString.")
            uploaded_route = [[float(latitude), float(longitude)] for longitude, latitude in geometry["coordinates"]]
            if route_length_km(uploaded_route) <= 0:
                raise ValueError("The route must have positive length.")
            st.session_state[ROUTE_KEY] = uploaded_route
            st.session_state[ROUTE_REVISION_KEY] += 1
            st.rerun()
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            st.error(f"Route not applied: {error}")

route = st.session_state[ROUTE_KEY]
if len(route) >= 2:
    movement_data = add_pipeline_proximity(movement_data, route)

influence_radius_m = st.slider(
    "Display radius around the pipeline (m)",
    min_value=25,
    max_value=1000,
    value=250,
    step=25,
    help=(
        "A pipeline section is coloured using the largest displayed ground-movement observation within this distance. "
        "This is a screening visualization, not a soil–pipe interaction model."
    ),
)

st.subheader("3. Explore ground movement near the route")
st.caption(
    "Green, yellow, orange, and dark red are relative to this dataset's displacement distribution; they are not safety limits. "
    "Use the layer control to switch between the heat map, survey points, street map, and satellite image."
)
render_ground_movement_map(movement_data, route, float(influence_radius_m))

metrics = st.columns(4)
metrics[0].metric("Pipeline route", f"{route_length_km(route):.2f} km" if len(route) >= 2 else "Not defined")
metrics[1].metric("Movement observations", f"{len(movement_data):,}")
metrics[2].metric(
    "Largest observed movement",
    f"{movement_data['Ground displacement magnitude (mm)'].max():.1f} mm",
)
near_route = (
    int((movement_data["Distance to pipeline (m)"] <= influence_radius_m).sum())
    if "Distance to pipeline (m)" in movement_data.columns
    else 0
)
metrics[3].metric("Observations near route", f"{near_route:,}")

if "Nearest pipeline chainage (km)" in movement_data.columns:
    chart_data = movement_data[movement_data["Distance to pipeline (m)"] <= influence_radius_m]
    if not chart_data.empty:
        movement_chart = (
            alt.Chart(chart_data)
            .mark_circle(size=72, opacity=0.75)
            .encode(
                x=alt.X("Nearest pipeline chainage (km):Q", title="Nearest pipeline chainage (km)"),
                y=alt.Y("Ground displacement magnitude (mm):Q", title="Observed ground displacement (mm)"),
                color=alt.Color(
                    "Ground displacement magnitude (mm):Q",
                    scale=alt.Scale(scheme="yelloworangered"),
                    legend=alt.Legend(title="Movement (mm)"),
                ),
                tooltip=[
                    "Survey point:N",
                    alt.Tooltip("Nearest pipeline chainage (km):Q", format=".3f"),
                    alt.Tooltip("Distance to pipeline (m):Q", format=".1f"),
                    alt.Tooltip("Ground displacement magnitude (mm):Q", format=".2f"),
                ],
            )
            .properties(height=300, title="Ground movement near the pipeline route")
        )
        st.altair_chart(movement_chart, width="stretch")

st.markdown("#### Highest observed movement areas")
display_columns = [
    "Survey point",
    "Latitude",
    "Longitude",
    "Ground displacement magnitude (mm)",
]
for optional_column in ["Nearest pipeline chainage (km)", "Distance to pipeline (m)"]:
    if optional_column in movement_data.columns:
        display_columns.append(optional_column)
st.dataframe(
    movement_data.nlargest(min(15, len(movement_data)), "Ground displacement magnitude (mm)")[display_columns],
    width="stretch",
    hide_index=True,
)
st.download_button(
    "Download explored ground-movement table",
    data=movement_data.to_csv(index=False).encode("utf-8"),
    file_name="ground_movement_exploration.csv",
    mime="text/csv",
)

st.subheader("Future analysis stage")
st.markdown(
    """
    The next model can transform the ground-movement field into approximate pipe displacement and loading,
    divide the route into pipe segments, estimate strain in each segment, and identify critical locations.
    That stage will require pipe properties, burial and soil information, displacement direction, boundary
    conditions, and a validated soil–pipe interaction model.
    """
)
if st.button("Open Planning for Geohazards"):
    st.switch_page("geohazard_planning.py")
