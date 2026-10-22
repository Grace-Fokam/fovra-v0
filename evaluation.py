"""Run matched controller experiments and compute *actual simulated* metrics."""

from dataclasses import dataclass
from time import perf_counter_ns

import numpy as np
import pandas as pd

from controllers import ModelPredictiveController, make_controller
from simulator import (
    MAX_SAFE_TEMP_C,
    MIN_SAFE_TEMP_C,
    START_TEMP_C,
    STEP_HOURS,
    STEP_MINUTES,
    STEPS_PER_DAY,
    TARGET_TEMP_C,
    next_step,
    operating_conditions,
)


@dataclass(frozen=True)
class SimulationConfig:
    ambient_c: float = 20.0
    process_kw: float = 3.0
    scenario: str = "Normal"
    baseline: str = "Thermostat"


def run_controller(name: str, config: SimulationConfig, model=None) -> pd.DataFrame:
    controller = make_controller(name, model)
    temp_c = START_TEMP_C
    cumulative_energy = 0.0
    measurements = []

    for step in range(STEPS_PER_DAY):
        condition = operating_conditions(
            step, config.ambient_c, config.process_kw, config.scenario
        )
        start_ns = perf_counter_ns()
        command_kw = controller.choose(
            temp_c, condition.ambient_c, condition.process_kw
        )
        decision_ms = (perf_counter_ns() - start_ns) / 1e6
        # Diagnostics are outside the timed decision. Neither MPC gets hidden
        # efficiency, time, scenario identity, or future disturbances.
        pred_next = (
            float(np.asarray(controller.predict_next_temperature(
                temp_c, condition.ambient_c, condition.process_kw, command_kw
            )).item())
            if isinstance(controller, ModelPredictiveController)
            else float("nan")
        )
        next_temp_c, energy_kwh = next_step(
            temp_c,
            condition.ambient_c,
            condition.process_kw,
            command_kw,
            condition.heater_efficiency,
        )
        cumulative_energy += energy_kwh
        measurements.append(
            {
                "time_h": (step + 1) * STEP_HOURS,
                "temperature_before_c": temp_c,
                "temperature_c": next_temp_c,
                "heater_kw": command_kw,
                "decision_ms": decision_ms,
                "interval_energy_kwh": energy_kwh,
                "cumulative_energy_kwh": cumulative_energy,
                "ambient_c": condition.ambient_c,
                "process_kw": condition.process_kw,
                "heater_efficiency": condition.heater_efficiency,
                "predicted_next_c": pred_next,
                "prediction_error_c": next_temp_c - pred_next,
            }
        )
        temp_c = next_temp_c

    return pd.DataFrame(measurements)


def summarize(frame: pd.DataFrame) -> dict:
    temperatures = frame["temperature_c"].to_numpy(dtype=float)
    powers = frame["heater_kw"].to_numpy(dtype=float)
    outside = (temperatures < MIN_SAFE_TEMP_C) | (temperatures > MAX_SAFE_TEMP_C)
    predicted_err = frame["prediction_error_c"].to_numpy(dtype=float)
    deviations = temperatures - TARGET_TEMP_C
    violation = np.maximum(MIN_SAFE_TEMP_C - temperatures, 0.0) + np.maximum(
        temperatures - MAX_SAFE_TEMP_C, 0.0
    )
    # Keep support for older saved frames that predate decision timing.
    timing = (
        frame["decision_ms"].to_numpy(dtype=float)
        if "decision_ms" in frame else np.array([np.nan])
    )

    return {
        "energy_kwh": float(frame["interval_energy_kwh"].sum()),
        "minutes_outside": int(np.sum(outside) * STEP_MINUTES),
        "target_rmse_c": float(np.sqrt(np.mean(deviations**2))),
        "temperature_std_c": float(np.std(temperatures)),
        "worst_target_deviation_c": float(np.max(np.abs(deviations))),
        "max_violation_c": float(np.max(violation)),
        "violation_degree_minutes": float(np.sum(violation) * STEP_MINUTES),
        "min_temperature_c": float(np.min(temperatures)),
        "max_temperature_c": float(np.max(temperatures)),
        "heater_adjustments": int(np.sum(np.abs(np.diff(powers)) > 0.01)),
        "heater_total_variation_kw": float(np.sum(np.abs(np.diff(powers)))),
        "decision_mean_ms": float(np.mean(timing)),
        "decision_p95_ms": float(np.percentile(timing, 95)),
        "decision_total_ms": float(np.sum(timing)),
        "one_step_prediction_mae_c": float(np.nanmean(np.abs(predicted_err)))
        if np.any(np.isfinite(predicted_err))
        else float("nan"),
    }


def compare(config: SimulationConfig, model) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    fovra = run_controller("Fovra", config, model)
    baseline = run_controller(config.baseline, config, model)
    return fovra, baseline, summarize(fovra), summarize(baseline)


def merge_for_download(fovra: pd.DataFrame, baseline: pd.DataFrame, baseline_name: str) -> pd.DataFrame:
    """One tidy table; every displayed trajectory comes from this comparison."""
    return pd.DataFrame(
        {
            "time_hours": fovra["time_h"],
            "ambient_c": fovra["ambient_c"],
            "process_heat_demand_kw": fovra["process_kw"],
            "actual_heater_efficiency": fovra["heater_efficiency"],
            "fovra_temperature_c": fovra["temperature_c"],
            "baseline_temperature_c": baseline["temperature_c"],
            "fovra_heater_kw": fovra["heater_kw"],
            "baseline_heater_kw": baseline["heater_kw"],
            "fovra_cumulative_kwh": fovra["cumulative_energy_kwh"],
            "baseline_cumulative_kwh": baseline["cumulative_energy_kwh"],
            "fovra_predicted_next_temperature_c": fovra["predicted_next_c"],
            "baseline_predicted_next_temperature_c": baseline["predicted_next_c"],
            "fovra_prediction_error_c": fovra["prediction_error_c"],
            "baseline_prediction_error_c": baseline["prediction_error_c"],
            "fovra_decision_ms": fovra["decision_ms"],
            "baseline_decision_ms": baseline["decision_ms"],
            "baseline_type": baseline_name,
        }
    )
