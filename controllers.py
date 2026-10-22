"""Conventional controllers and ML-model-based receding-horizon controller."""

from itertools import product

import numpy as np

from simulator import (
    MAX_HEATER_KW,
    MAX_SAFE_TEMP_C,
    MIN_SAFE_TEMP_C,
    STEP_HOURS,
    TARGET_TEMP_C,
)


class Thermostat:
    """Bang-bang heating with hysteresis: on below 59°C, off above 61°C."""

    name = "Thermostat"

    def __init__(self):
        self.power_kw = 0.0

    def choose(self, temp_c: float, ambient_c: float, process_kw: float) -> float:
        if temp_c < 59.0:
            self.power_kw = MAX_HEATER_KW
        elif temp_c > 61.0:
            self.power_kw = 0.0
        return self.power_kw


class PIController:
    """Proportional-integral baseline, a feedback-only controller.

    Intentionally simple. Its settings are illustrative, not site-optimized.
    """

    name = "PI controller"

    def __init__(self):
        self.integral = 0.0
        self.kp = 5.0
        self.ki = 4.0
        self.base_kw = 6.0

    def choose(self, temp_c: float, ambient_c: float, process_kw: float) -> float:
        error = TARGET_TEMP_C - temp_c
        proposed_integral = np.clip(self.integral + error * STEP_HOURS, -3.0, 3.0)
        requested = self.base_kw + self.kp * error + self.ki * proposed_integral
        # Basic integral anti-windup: do not continue accumulating error
        # when the actuator is saturated in the same direction.
        if not (requested > MAX_HEATER_KW and error > 0) and not (
            requested < 0 and error < 0
        ):
            self.integral = proposed_integral
        power = self.base_kw + self.kp * error + self.ki * self.integral
        return float(np.clip(power, 0.0, MAX_HEATER_KW))


class LearnedMPC:
    """Optimize 20-minute action sequences with a fitted ML dynamics model.

    Reads current temperature/ambient/demand, not true plant parameters or the
    future disturbance schedule. Applies first action, observes actual plant,
    then plans again. The first prototype assumes ambient and demand stay at
    their current observed values within each 20-minute planning horizon.
    """

    name = "Fovra (learned MPC)"

    def __init__(self, model):
        self.model = model
        self.previous_kw = 0.0
        candidate_powers = (0.0, 3.0, 6.0, 9.0, 12.0)
        self.plans = np.asarray(list(product(candidate_powers, repeat=4)), dtype=float)
        self.plan_count = len(self.plans)

    def choose(self, temp_c: float, ambient_c: float, process_kw: float) -> float:
        count = self.plan_count
        predicted_temperature = np.full(count, temp_c, dtype=float)
        objective = np.zeros(count, dtype=float)
        previous_kw = np.full(count, self.previous_kw, dtype=float)
        fixed_ambient = np.full(count, ambient_c, dtype=float)
        fixed_process = np.full(count, process_kw, dtype=float)

        for horizon_step in range(self.plans.shape[1]):
            candidate_kw = self.plans[:, horizon_step]
            x = np.column_stack(
                (predicted_temperature, fixed_ambient, fixed_process, candidate_kw)
            )
            # This is an actual scikit-learn-trained model prediction.
            predicted_temperature += self.model.predict(x)

            # Electricity input over the hypothetical five-minute step.
            objective += candidate_kw * STEP_HOURS

            # Prefer adequate temperature margin, not precarious proximity
            # to the lower safety limit.
            objective += 9.0 * (predicted_temperature - TARGET_TEMP_C) ** 2
            below = np.maximum(MIN_SAFE_TEMP_C - predicted_temperature, 0.0)
            above = np.maximum(predicted_temperature - MAX_SAFE_TEMP_C, 0.0)
            objective += 500.0 * (below**2 + above**2)

            # Reduce rapid changes in commanded electrical power.
            objective += 0.006 * (candidate_kw - previous_kw) ** 2
            previous_kw = candidate_kw

        best_plan = self.plans[int(np.argmin(objective))]
        self.previous_kw = float(best_plan[0])
        return self.previous_kw


def make_controller(baseline_name: str, model=None):
    if baseline_name == "Thermostat":
        return Thermostat()
    if baseline_name == "PI controller":
        return PIController()
    if baseline_name == "Fovra":
        if model is None:
            raise ValueError("Fovra controller requires a trained world model")
        return LearnedMPC(model)
    raise ValueError(f"Unknown controller: {baseline_name}")
