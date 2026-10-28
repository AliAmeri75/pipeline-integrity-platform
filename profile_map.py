"""Map profile chainages onto a user-defined pipeline centreline."""

from __future__ import annotations

import copy
import math
from typing import Iterable, Mapping, Sequence

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium


EARTH_RADIUS_KM = 6371.0088
EDMONTON_SAMPLE_ROUTE = [
    [53.5350, -113.5850],
    [53.5480, -113.5350],
    [53.5570, -113.4800],
    [53.5670, -113.4300],
]


def _point(point: Sequence[float]) -> tuple[float, float]:
    if len(point) != 2:
        raise ValueError("Each route point must contain latitude and longitude.")
    latitude, longitude = float(point[0]), float(point[1])
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Route coordinates must be valid latitude/longitude values.")
    return latitude, longitude


def haversine_distance_km(
    point_1: Sequence[float], point_2: Sequence[float]
) -> float:
    """Return the great-circle distance between two latitude/longitude points."""

    latitude_1, longitude_1 = _point(point_1)
    latitude_2, longitude_2 = _point(point_2)
    lat_1 = math.radians(latitude_1)
    lat_2 = math.radians(latitude_2)
    delta_lat = lat_2 - lat_1
    delta_lon = math.radians(longitude_2 - longitude_1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(value))


def route_length_km(route: Sequence[Sequence[float]]) -> float:
    """Return the total geodesic length of a route polyline."""

    if len(route) < 2:
        return 0.0
    points = [_point(point) for point in route]
    return sum(
        haversine_distance_km(start, end)
        for start, end in zip(points[:-1], points[1:])
    )


def point_at_chainage(
    route: Sequence[Sequence[float]], chainage_km: float
) -> tuple[float, float]:
    """Return the latitude/longitude at a distance along the route."""

    if len(route) < 2:
        raise ValueError("Draw a pipeline route with at least two points first.")
    points = [_point(point) for point in route]
    total_length = route_length_km(points)
    if total_length <= 0:
        raise ValueError("The pipeline route cannot contain only repeated points.")
    if not math.isfinite(chainage_km) or not 0 <= chainage_km <= total_length:
        raise ValueError(
            f"Distance from route start must be between 0 and {total_length:.3f} km."
        )

    remaining = chainage_km
    for start, end in zip(points[:-1], points[1:]):
        segment_length = haversine_distance_km(start, end)
        if segment_length == 0:
            continue
        if remaining <= segment_length:
            fraction = remaining / segment_length
            return (
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            )
        remaining -= segment_length
    return points[-1]


def latest_route_from_drawings(
    drawings: Iterable[Mapping[str, object]] | None,
) -> list[list[float]] | None:
    """Return the most recently drawn GeoJSON line as [latitude, longitude]."""

    for drawing in reversed(list(drawings or [])):
        geometry = drawing.get("geometry", {})
        if not isinstance(geometry, Mapping) or geometry.get("type") != "LineString":
            continue
        coordinates = geometry.get("coordinates", [])
        return [
            [float(latitude), float(longitude)]
            for longitude, latitude in coordinates
        ]
    return None


def locate_profiles_on_route(
    summary: pd.DataFrame,
    route: Sequence[Sequence[float]],
    *,
    route_start_chainage_m: float,
    joint_length_m: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int]]:
    """Place profile locations on a route and assign physical pipe joints.

    Profile locations are treated as pipeline chainages. Two or more features
    within the same joint-length interval receive the same joint ID.
    """

    required = {
        "Profile ID",
        "Feature ID",
        "Defect type",
        "Feature location (m)",
        "Maximum depth (%WT)",
        "Maximum depth (mm)",
        "Profile length (mm)",
    }
    missing = required.difference(summary.columns)
    if missing:
        raise ValueError(
            "Profile summary is missing required columns: "
            + ", ".join(sorted(missing))
        )
    if joint_length_m <= 0:
        raise ValueError("Nominal pipe-joint length must be positive.")
    route_length = route_length_km(route)
    if route_length <= 0:
        raise ValueError("Draw a pipeline route with a positive length first.")
    if not math.isfinite(float(route_start_chainage_m)):
        raise ValueError("Route start chainage must be finite.")

    route_length_m = route_length * 1000.0
    total_joints = max(1, math.ceil(route_length_m / joint_length_m))
    mapped_records: list[dict[str, object]] = []
    outside_records: list[dict[str, object]] = []
    for row_number, (_, feature) in enumerate(summary.iterrows(), start=1):
        try:
            feature_chainage = float(feature["Feature location (m)"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Profile row {row_number} has a non-numeric feature location."
            ) from error
        relative_m = feature_chainage - float(route_start_chainage_m)
        base_record = feature.to_dict()
        base_record["Distance from mapped route start (m)"] = relative_m
        if not math.isfinite(relative_m) or relative_m < 0 or relative_m > route_length_m:
            base_record["Map status"] = "Outside mapped route"
            outside_records.append(base_record)
            continue

        latitude, longitude = point_at_chainage(route, relative_m / 1000.0)
        joint_number = min(
            math.floor(relative_m / joint_length_m) + 1,
            total_joints,
        )
        base_record.update(
            {
                "Latitude": latitude,
                "Longitude": longitude,
                "Joint number": joint_number,
                "Joint ID": f"Joint {joint_number:05d}",
                "Map status": "Mapped",
            }
        )
        mapped_records.append(base_record)

    mapped = pd.DataFrame(mapped_records)
    outside = pd.DataFrame(outside_records)
    if not mapped.empty:
        counts = mapped.groupby("Joint ID")["Profile ID"].transform("count")
        mapped["Features in joint"] = counts.astype(int)
    metadata: dict[str, float | int] = {
        "route_length_km": route_length,
        "route_start_chainage_m": float(route_start_chainage_m),
        "route_end_chainage_m": float(route_start_chainage_m) + route_length_m,
        "joint_length_m": float(joint_length_m),
        "total_joints": total_joints,
        "mapped_features": len(mapped),
        "unmapped_features": len(outside),
        "defect_containing_joints": (
            int(mapped["Joint ID"].nunique()) if not mapped.empty else 0
        ),
    }
    return mapped, outside, metadata


def render_profile_location_map(
    summary: pd.DataFrame,
    selected_profile_id: str,
) -> pd.DataFrame:
    """Render an editable pipeline route with profile locations and joint IDs."""

    route_key = "data_exploration_map_route"
    revision_key = "data_exploration_map_revision"
    if route_key not in st.session_state:
        st.session_state[route_key] = copy.deepcopy(EDMONTON_SAMPLE_ROUTE)
    if revision_key not in st.session_state:
        st.session_state[revision_key] = 0

    st.markdown(
        """
        <div class="notice"><strong>How to use the map.</strong><br>
        <strong>1.</strong> Draw or replace the pipeline centreline with the line tool.<br>
        <strong>2.</strong> Enter the chainage represented by the start of the drawn line.<br>
        <strong>3.</strong> The app places every uploaded profile at its recorded chainage
        and groups profiles within the same nominal joint length.</div>
        """,
        unsafe_allow_html=True,
    )

    action_1, action_2, action_3 = st.columns([1, 1, 2])
    if action_1.button("Load Edmonton sample route", use_container_width=True):
        st.session_state[route_key] = copy.deepcopy(EDMONTON_SAMPLE_ROUTE)
        st.session_state[revision_key] += 1
        st.rerun()
    if action_2.button("Clear pipeline route", use_container_width=True):
        st.session_state[route_key] = []
        st.session_state[revision_key] += 1
        st.rerun()
    action_3.caption(
        "The Edmonton route is synthetic and does not represent an operating pipeline."
    )

    setting_1, setting_2 = st.columns(2)
    with setting_1:
        route_start_chainage_m = st.number_input(
            "Chainage at the start of the drawn route (m)",
            value=0.0,
            step=100.0,
            help=(
                "Use 0 when the drawn line begins at the pipeline origin. If the map "
                "shows only a segment, enter that segment's starting chainage."
            ),
        )
    with setting_2:
        joint_length_m = st.number_input(
            "Nominal pipe-joint length (m)",
            min_value=1.0,
            max_value=100.0,
            value=12.0,
            step=1.0,
            help=(
                "Profiles within the same interval receive the same joint ID. "
                "Use construction records when the real joint boundaries are available."
            ),
        )

    route = st.session_state[route_key]
    mapped = pd.DataFrame()
    outside = pd.DataFrame()
    metadata: dict[str, float | int] | None = None
    mapping_error = None
    if len(route) >= 2:
        try:
            mapped, outside, metadata = locate_profiles_on_route(
                summary,
                route,
                route_start_chainage_m=float(route_start_chainage_m),
                joint_length_m=float(joint_length_m),
            )
        except ValueError as error:
            mapping_error = str(error)

    if route:
        map_center = [
            sum(point[0] for point in route) / len(route),
            sum(point[1] for point in route) / len(route),
        ]
    else:
        map_center = [53.5461, -113.4938]
    pipeline_map = folium.Map(
        location=map_center,
        zoom_start=11,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer("OpenStreetMap", name="Street map", control=True).add_to(
        pipeline_map
    )
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri World Imagery",
        name="Satellite",
        control=True,
    ).add_to(pipeline_map)

    if len(route) >= 2:
        folium.PolyLine(
            route,
            color="#16a6a1",
            weight=6,
            opacity=0.95,
            tooltip="Pipeline centreline",
        ).add_to(pipeline_map)
        folium.Marker(
            route[0],
            tooltip=f"Route start — chainage {float(route_start_chainage_m):,.1f} m",
            icon=folium.Icon(color="green"),
        ).add_to(pipeline_map)
        route_end = (
            float(route_start_chainage_m) + route_length_km(route) * 1000.0
        )
        folium.Marker(
            route[-1],
            tooltip=f"Route end — chainage {route_end:,.1f} m",
            icon=folium.Icon(color="blue"),
        ).add_to(pipeline_map)
        pipeline_map.fit_bounds(route, padding=(25, 25))

    if not mapped.empty:
        for _, feature_record in mapped.iterrows():
            selected = str(feature_record["Profile ID"]) == str(selected_profile_id)
            defect_type = str(feature_record["Defect type"])
            marker_color = "#155987" if selected else (
                "#c62828" if defect_type == "Crack" else "#d98b22"
            )
            maximum_depth_mm = feature_record.get("Maximum depth (mm)")
            maximum_depth_text = (
                "Unavailable"
                if pd.isna(maximum_depth_mm)
                else f"{float(maximum_depth_mm):.3f} mm"
            )
            folium.CircleMarker(
                location=[
                    float(feature_record["Latitude"]),
                    float(feature_record["Longitude"]),
                ],
                radius=11 if selected else 8,
                color="white",
                weight=3 if selected else 2,
                fill=True,
                fill_color=marker_color,
                fill_opacity=0.95,
                tooltip=(
                    f"Profile {feature_record['Profile ID']} — "
                    f"{feature_record['Joint ID']}"
                ),
                popup=folium.Popup(
                    (
                        f"<b>Profile {feature_record['Profile ID']}</b><br>"
                        f"Feature: {feature_record['Feature ID']}<br>"
                        f"Type: {feature_record['Defect type']}<br>"
                        f"Chainage: {float(feature_record['Feature location (m)']):,.3f} m<br>"
                        f"{feature_record['Joint ID']} "
                        f"({int(feature_record['Features in joint'])} feature(s))<br>"
                        f"Maximum depth: {maximum_depth_text}<br>"
                        f"Profile length: {float(feature_record['Profile length (mm)']):,.1f} mm"
                    ),
                    max_width=280,
                ),
            ).add_to(pipeline_map)

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
    ).add_to(pipeline_map)
    folium.LayerControl(collapsed=False).add_to(pipeline_map)
    map_result = st_folium(
        pipeline_map,
        height=560,
        use_container_width=True,
        returned_objects=["all_drawings"],
        key=f"data_exploration_pipeline_map_{st.session_state[revision_key]}",
    )
    new_route = latest_route_from_drawings(map_result.get("all_drawings") or [])
    if new_route and new_route != route:
        st.session_state[route_key] = new_route
        st.session_state[revision_key] += 1
        st.rerun()

    if mapping_error:
        st.error(mapping_error)
        return mapped
    if metadata is None:
        st.info("Draw a pipeline centreline to place the uploaded profiles on the map.")
        return mapped

    metrics = st.columns(4)
    metrics[0].metric("Mapped route", f"{metadata['route_length_km']:.2f} km")
    metrics[1].metric("Physical joints", f"{metadata['total_joints']:,}")
    metrics[2].metric("Mapped profiles", f"{metadata['mapped_features']:,}")
    metrics[3].metric(
        "Defect-containing joints", f"{metadata['defect_containing_joints']:,}"
    )
    if not outside.empty:
        st.warning(
            f"{len(outside)} profile(s) fall outside the mapped chainage range "
            f"{metadata['route_start_chainage_m']:,.1f}–"
            f"{metadata['route_end_chainage_m']:,.1f} m. Adjust the route or its "
            "starting chainage to display them."
        )
    if not mapped.empty:
        st.caption(
            "The blue marker is the profile selected above. Red markers are cracks; "
            "orange markers are corrosion/metal loss. Click a marker for details."
        )
        map_columns = [
            "Profile ID",
            "Feature ID",
            "Defect type",
            "Feature location (m)",
            "Joint ID",
            "Features in joint",
            "Maximum depth (mm)",
            "Profile length (mm)",
        ]
        st.dataframe(mapped[map_columns], width="stretch", hide_index=True)
        st.session_state["prepared_profile_map"] = mapped
        st.session_state["prepared_profile_route"] = route
    return mapped
