#!/usr/bin/env python3
"""Calculation engine for the Journal 2 reliability and VoI interface.

The engine reads staged POF arrays and calls the repository-owned
``Cost_parallel.py`` implementation. Large data arrays may be synchronized from
Google Drive or uploaded by the user, but executable Python code is never loaded
from Drive.
"""

from __future__ import annotations

import argparse
import json
import os
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import norm


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("JOURNAL2_DATA_DIR", APP_DIR / "Data_CC"))
TL = 20
YEARS = np.arange(TL + 1, dtype=int)
INSPECTION_TIMES = np.arange(1, TL, dtype=int)
MEAN_WT = 6.35
STD_WT = 0.6
POD_TD = 1.0
POD_Q = 0.5
TEMPLATE_CONFIG_PATH = Path(__file__).resolve().with_name("crack_templates.json")

with TEMPLATE_CONFIG_PATH.open(encoding="utf-8") as template_file:
    TEMPLATE_CONFIG = json.load(template_file)["templates"]
TEMPLATE_BY_SOURCE = {
    int(template["source_index"]): template for template in TEMPLATE_CONFIG
}
AVAILABLE_TEMPLATE_SOURCES = tuple(sorted(TEMPLATE_BY_SOURCE))


def _template_id(source: int) -> int:
    return int(TEMPLATE_BY_SOURCE[source]["id"])


def _template_label(source: int) -> str:
    template = TEMPLATE_BY_SOURCE[source]
    return f"{template['label']} · {float(template['initial_depth_mm']):g} mm"

try:
    from Cost_parallel import build_true_cost_cache, cp_pi1_batch, cp_pi2_batch
except ImportError as exc:  # pragma: no cover - produces a clearer UI error
    raise RuntimeError(
        f"Could not import Cost_parallel.py from the application repository: {APP_DIR}"
    ) from exc


def _float(value: Any, name: str, minimum: float | None = None) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _hazard(pof: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.diff(pof) / (1.0 - pof[:-1])
    return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=0.0)


def _combine_independent(component_pofs: np.ndarray) -> np.ndarray:
    return 1.0 - np.prod(1.0 - component_pofs, axis=0)


def _check_pof(pof: np.ndarray, label: str) -> np.ndarray:
    array = np.asarray(pof, dtype=float)[: TL + 1]
    if array.shape != (TL + 1,):
        raise ValueError(f"{label} must contain {TL + 1} annual values")
    if not np.all(np.isfinite(array)) or np.any((array < 0) | (array > 1)):
        raise ValueError(f"{label} values must be finite and between 0 and 1")
    if np.any(np.diff(array) < -1e-12):
        raise ValueError(f"{label} must be cumulative and nondecreasing")
    return array


@lru_cache(maxsize=None)
def _load_prior_pof(source_index: int) -> tuple[np.ndarray, np.ndarray]:
    choices = [
        DATA_DIR / f"prior_pof_crack_{source_index}.npz",
        DATA_DIR / f"prior_analysis{source_index}.npz",
        DATA_DIR / f"\\prior_analysis{source_index}.npz",
    ]
    source = next((path for path in choices if path.exists()), None)
    if source is None:
        raise FileNotFoundError(
            f"No prior POF file was found for template {_template_id(source_index)}"
        )
    with np.load(source) as data:
        leak = _check_pof(data["Pf_T_leak"], "Leak POF")
        burst = _check_pof(data["Pf2_T_burst"], "Burst POF")
    return leak, burst


def _prior_for_path(
    leak: np.ndarray,
    burst: np.ndarray,
    costs: dict[str, float],
    pfc: float,
) -> dict[str, Any]:
    leak_2d = leak[None, :]
    burst_2d = burst[None, :]
    cache = build_true_cost_cache(
        leak_2d,
        burst_2d,
        costs["cf_leak"],
        costs["cf_burst"],
        costs["rate"],
        TL,
    )
    pod = np.ones(1)
    pi1_cost, _, pi1_repair = cp_pi1_batch(
        pod,
        cache,
        leak_2d,
        burst_2d,
        costs["cf_leak"],
        costs["cf_burst"],
        costs["repair"],
        0,
        return_details=True,
    )
    pi2_cost, _, pi2_repair = cp_pi2_batch(
        pod,
        cache,
        leak_2d,
        burst_2d,
        costs["cf_leak"],
        costs["cf_burst"],
        costs["repair"],
        0,
        np.asarray([pfc]),
        return_details=True,
    )
    pi1_candidates = np.r_[
        cache.prefix[0, :TL]
        + costs["repair"] * cache.discount[:TL],
        cache.no_repair[0],
    ]
    return {
        "pi1Cost": float(pi1_cost),
        "pi1Repair": int(pi1_repair[0]),
        "pi2Cost": float(pi2_cost[0]),
        "pi2Repair": int(pi2_repair[0, 0]),
        "pi1Candidates": pi1_candidates.tolist(),
    }


def _compute_prior(
    costs: dict[str, float],
    pfc: float,
    crack_types: list[int],
) -> dict[str, Any]:
    """Prior analysis for 1–8 instances selected from available templates."""
    component_paths = [_load_prior_pof(source) for source in crack_types]
    component_leak = np.asarray([paths[0] for paths in component_paths])
    component_burst = np.asarray([paths[1] for paths in component_paths])
    system_leak = _combine_independent(component_leak)
    system_burst = _combine_independent(component_burst)

    rows = []
    path_results: list[dict[str, Any]] = []
    for crack_number, (source, leak, burst) in enumerate(
        zip(crack_types, component_leak, component_burst), start=1
    ):
        result = _prior_for_path(leak, burst, costs, pfc)
        path_results.append(result)
        rows.append(
            {
                "label": f"Crack {crack_number} ({_template_label(source)})",
                "crackNumber": crack_number,
                "template": _template_id(source),
                **result,
            }
        )

    system_result = _prior_for_path(system_leak, system_burst, costs, pfc)
    system_label = f"Pipe-joint system ({len(crack_types)} crack{'s' if len(crack_types) != 1 else ''})"
    rows.append({"label": system_label, **system_result})

    leak_hazard = _hazard(system_leak)
    burst_hazard = _hazard(system_burst)
    combined_hazard = burst_hazard + leak_hazard * (
        costs["cf_leak"] / costs["cf_burst"]
    )

    return {
        "crackTypes": [_template_id(source) for source in crack_types],
        "rows": rows,
        "component": path_results,
        "system": system_result,
        "hazard": {
            "years": YEARS[1:].tolist(),
            "leak": leak_hazard.tolist(),
            "burst": burst_hazard.tolist(),
            "combined": combined_hazard.tolist(),
            "threshold": pfc,
        },
        "systemPof": {
            "years": YEARS.tolist(),
            "leak": system_leak.tolist(),
            "burst": system_burst.tolist(),
        },
    }


def _load_cpp_inputs(crack_id: int) -> dict[str, np.ndarray]:
    """Load one crack template without retaining its large arrays globally."""
    sample_path = DATA_DIR / f"Samples_HPC{crack_id}_.npz"
    true_burst_path = DATA_DIR / f"name_Pfx_burst_leak{crack_id}.npz"
    perfect_path = DATA_DIR / f"name_Pfx3_burst_leak{crack_id}.npz"
    imperfect_path = DATA_DIR / f"name_Pfy3_burst_leak{crack_id}_e1.npz"

    required = [sample_path, true_burst_path, perfect_path, imperfect_path]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing updated POF file(s): " + ", ".join(missing))

    with np.load(sample_path) as data:
        samples = np.asarray(data["OriginSamples0"], dtype=float)
    with np.load(true_burst_path) as data:
        true_burst = np.asarray(data["Pfx_burst_read"], dtype=float)
    with np.load(perfect_path) as data:
        perfect_leak = np.asarray(data["Pfx3_leak_read"], dtype=float)
        perfect_burst = np.asarray(data["Pfx3_burst_read"], dtype=float)
    with np.load(imperfect_path) as data:
        imperfect_leak = np.asarray(data["Pfy3_leak_read"], dtype=float)
        imperfect_burst = np.asarray(data["Pfy3_burst_read"], dtype=float)

    sample_count = min(
        10000,
        samples.shape[0],
        true_burst.shape[0],
        perfect_leak.shape[1],
        perfect_burst.shape[1],
        imperfect_leak.shape[1],
        imperfect_burst.shape[1],
    )
    samples = samples[:sample_count]
    true_burst = true_burst[:sample_count, : TL + 1]
    perfect_leak = perfect_leak[: TL - 1, :sample_count, : TL + 1]
    perfect_burst = perfect_burst[: TL - 1, :sample_count, : TL + 1]
    imperfect_leak = imperfect_leak[: TL - 1, :sample_count, : TL + 1]
    imperfect_burst = imperfect_burst[: TL - 1, :sample_count, : TL + 1]

    depth = samples[:, 1]
    growth = samples[:, 2]
    depth_by_year = depth[:, None] + growth[:, None] * YEARS[None, :]
    true_leak = norm.cdf(depth_by_year, loc=MEAN_WT, scale=STD_WT)
    pod_model = np.where(
        depth_by_year > POD_TD,
        1.0 - np.exp(-POD_Q * (depth_by_year - POD_TD)),
        0.0,
    )

    return {
        "true_leak": true_leak,
        "true_burst": true_burst,
        "perfect_leak": perfect_leak,
        "perfect_burst": perfect_burst,
        "imperfect_leak": imperfect_leak,
        "imperfect_burst": imperfect_burst,
        "pod_model": pod_model,
    }


def _build_population_inputs(crack_types: list[int]) -> dict[str, np.ndarray]:
    """Assemble sample-level joint POFs for the selected crack population.

    The combination follows the earlier crack-count sensitivity analysis. Each
    failure mode is a conditionally independent series system. When a template
    is repeated, independently permuted outer-sample rows avoid treating the
    repeated cracks as identical Monte Carlo trajectories.
    """

    population: dict[str, np.ndarray] | None = None
    type_counts = {source: crack_types.count(source) for source in set(crack_types)}

    for source in sorted(type_counts):
        loaded = _load_cpp_inputs(source)
        if population is None:
            population = {
                "true_leak_survival": np.ones_like(loaded["true_leak"]),
                "true_burst_survival": np.ones_like(loaded["true_burst"]),
                "perfect_leak_survival": np.ones_like(loaded["perfect_leak"]),
                "perfect_burst_survival": np.ones_like(loaded["perfect_burst"]),
                "imperfect_leak_survival": np.ones_like(loaded["imperfect_leak"]),
                "imperfect_burst_survival": np.ones_like(loaded["imperfect_burst"]),
                "pod_survival": np.ones_like(loaded["pod_model"]),
            }

        sample_count = loaded["true_leak"].shape[0]
        generator = np.random.default_rng(20260819 + 1009 * source)
        for occurrence in range(type_counts[source]):
            rows = (
                np.arange(sample_count)
                if occurrence == 0
                else generator.permutation(sample_count)
            )
            population["true_leak_survival"] *= 1.0 - loaded["true_leak"][rows]
            population["true_burst_survival"] *= 1.0 - loaded["true_burst"][rows]
            population["perfect_leak_survival"] *= 1.0 - loaded["perfect_leak"][:, rows, :]
            population["perfect_burst_survival"] *= 1.0 - loaded["perfect_burst"][:, rows, :]
            population["imperfect_leak_survival"] *= 1.0 - loaded["imperfect_leak"][:, rows, :]
            population["imperfect_burst_survival"] *= 1.0 - loaded["imperfect_burst"][:, rows, :]
            population["pod_survival"] *= 1.0 - loaded["pod_model"][rows]
        del loaded

    if population is None:
        raise ValueError("At least one crack is required")

    return {
        "true_leak": 1.0 - population["true_leak_survival"],
        "true_burst": 1.0 - population["true_burst_survival"],
        "perfect_leak": 1.0 - population["perfect_leak_survival"],
        "perfect_burst": 1.0 - population["perfect_burst_survival"],
        "imperfect_leak": 1.0 - population["imperfect_leak_survival"],
        "imperfect_burst": 1.0 - population["imperfect_burst_survival"],
        "pod_model": 1.0 - population["pod_survival"],
    }


def _compute_cpp_mode(
    loaded: dict[str, np.ndarray],
    mode: str,
    costs: dict[str, float],
    pfc: float,
    use_pod_model: bool,
) -> dict[str, Any]:
    true_leak = loaded["true_leak"]
    true_burst = loaded["true_burst"]
    cache = build_true_cost_cache(
        true_leak,
        true_burst,
        costs["cf_leak"],
        costs["cf_burst"],
        costs["rate"],
        TL,
    )
    updated_leak = loaded[f"{mode}_leak"]
    updated_burst = loaded[f"{mode}_burst"]
    pod_by_year = loaded["pod_model"] if use_pod_model else np.ones_like(true_leak)

    pi1 = np.empty(len(INSPECTION_TIMES), dtype=float)
    pi2 = np.empty(len(INSPECTION_TIMES), dtype=float)
    for column, inspection_time in enumerate(INSPECTION_TIMES):
        pod = pod_by_year[:, inspection_time]
        pi1[column] = cp_pi1_batch(
            pod,
            cache,
            updated_leak[column],
            updated_burst[column],
            costs["cf_leak"],
            costs["cf_burst"],
            costs["repair"],
            int(inspection_time),
        )
        pi2[column] = cp_pi2_batch(
            pod,
            cache,
            updated_leak[column],
            updated_burst[column],
            costs["cf_leak"],
            costs["cf_burst"],
            costs["repair"],
            int(inspection_time),
            np.asarray([pfc]),
        )[0]
    return {"pi1": pi1, "pi2": pi2}


def _decision_summary(
    cpp: np.ndarray,
    prior_cost: float,
    costs: dict[str, float],
) -> dict[str, Any]:
    inspection_cost = costs["inspection"] * np.power(
        1.0 + costs["rate"], -INSPECTION_TIMES
    )
    total = cpp + inspection_cost
    gross_voi = prior_cost - cpp
    net_voi = prior_cost - total
    best_index = int(np.argmin(total))
    return {
        "cpp": cpp.tolist(),
        "total": total.tolist(),
        "grossVoi": gross_voi.tolist(),
        "netVoi": net_voi.tolist(),
        "optimalInspection": int(INSPECTION_TIMES[best_index]),
        "minimumTotal": float(total[best_index]),
        "maxNetVoi": float(net_voi[best_index]),
        "justifiable": bool(net_voi[best_index] > 0),
    }


def _compute_preposterior(
    crack_types: list[int],
    prior: dict[str, Any],
    costs: dict[str, float],
    pfc: float,
    measurement: str,
    use_pod_model: bool,
) -> dict[str, Any]:
    loaded = _build_population_inputs(crack_types)
    modes = ["perfect", "imperfect"] if measurement == "both" else [measurement]
    mode_results: dict[str, Any] = {}
    table = []
    selected_prior = prior["system"]

    for mode in modes:
        cpp = _compute_cpp_mode(loaded, mode, costs, pfc, use_pod_model)
        pi1 = _decision_summary(cpp["pi1"], selected_prior["pi1Cost"], costs)
        pi2 = _decision_summary(cpp["pi2"], selected_prior["pi2Cost"], costs)
        mode_results[mode] = {"pi1": pi1, "pi2": pi2}
        for policy, summary in (("π1", pi1), ("π2", pi2)):
            table.append(
                {
                    "measurement": "Perfect update" if mode == "perfect" else "Imperfect update",
                    "policy": policy,
                    "priorCost": selected_prior["pi1Cost"] if policy == "π1" else selected_prior["pi2Cost"],
                    **summary,
                }
            )

    return {
        "cracks": len(crack_types),
        "crackTypes": [_template_id(source) for source in crack_types],
        "inspectionTimes": INSPECTION_TIMES.tolist(),
        "modes": mode_results,
        "table": table,
    }


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("pofSource", "loaded") != "loaded":
        raise ValueError(
            "POF calculation is reserved for the next version. "
            "Select 'Use pre-calculated POFs' for this interface."
        )

    costs = {
        "cf_leak": _float(payload.get("cfLeak", 1.0), "Leak failure cost", 0.0),
        "cf_burst": _float(payload.get("cfBurst", 10.0), "Burst failure cost", 1e-12),
        "repair": _float(payload.get("repairCost", 0.2), "Repair cost", 0.0),
        "inspection": _float(payload.get("inspectionCost", 0.02), "Inspection cost", 0.0),
        "rate": _float(payload.get("discountRate", 0.04), "Discount rate", 0.0),
    }
    pfc = _float(payload.get("pfc", 1e-3), "Pfc", 0.0)
    requested_types = payload.get("crackTypes")
    if requested_types is None:
        # Backward compatibility for the first browser interface: its prior
        # analysis used all three cracks while Cpp used one selected crack.
        legacy_crack = int(payload.get("crack", 0))
        if legacy_crack not in AVAILABLE_TEMPLATE_SOURCES:
            raise ValueError("Crack must be 1, 2, or 3")
        prior_types = list(AVAILABLE_TEMPLATE_SOURCES)
        preposterior_types = [legacy_crack]
    else:
        preposterior_types = [int(source) for source in requested_types]
        if not 1 <= len(preposterior_types) <= 8:
            raise ValueError("Select between 1 and 8 cracks")
        if any(source not in AVAILABLE_TEMPLATE_SOURCES for source in preposterior_types):
            available = ", ".join(
                str(_template_id(source)) for source in AVAILABLE_TEMPLATE_SOURCES
            )
            raise ValueError(f"Each crack must use an available template: {available}")
        prior_types = preposterior_types
    measurement = str(payload.get("measurement", "both"))
    if measurement not in {"perfect", "imperfect", "both"}:
        raise ValueError("Measurement must be perfect, imperfect, or both")

    prior = _compute_prior(costs, pfc, prior_types)
    preposterior = _compute_preposterior(
        preposterior_types,
        prior,
        costs,
        pfc,
        measurement,
        bool(payload.get("usePodModel", False)),
    )
    return {
        "ok": True,
        "meta": {
            "cracks": len(prior_types),
            "crackTypes": [_template_id(source) for source in prior_types],
            "horizon": TL,
            "pfc": pfc,
            "costUnit": "million dollars",
            "pofSource": "Pre-calculated POF files",
            "hazardFormula": "Hf_burst + Hf_leak × Cf_leak / Cf_burst",
        },
        "prior": prior,
        "preposterior": preposterior,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Cannot serialize {type(value)!r}")


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ReliabilityDashboard/1.0"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "codeDirectory": str(APP_DIR),
                    "dataDirectory": str(DATA_DIR),
                },
            )
            return
        self._send_json(
            HTTPStatus.NOT_FOUND,
            {"ok": False, "error": "Use the dashboard to run the analysis."},
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/analyze":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send_json(HTTPStatus.OK, calculate(payload))
        except Exception as exc:  # return a useful message in the UI
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": str(exc)},
            )

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[dashboard] {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reliability dashboard calculation API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Lifecycle data directory does not exist: {DATA_DIR}")
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Calculation service ready at http://{args.host}:{args.port}")
    print(f"Using lifecycle code from {APP_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
