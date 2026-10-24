"""Conventional controllers and ML-model-based receding-horizon controller."""

from itertools import product

import numpy as np

from simulator import (
    HEAT_LOSS_KW_PER_C,
    MAX_HEATER_KW,
    MAX_SAFE_TEMP_C,
    MIN_SAFE_TEMP_C,
    STEP_HOURS,
    TARGET_TEMP_C,
    THERMAL_CAPACITY_KWH_PER_C,
)

BASELINES = ("Thermostat", "PI controller", "Physics MPC")
MPC_POWERS_KW = (0.0, 3.0, 6.0, 9.0, 12.0)
MPC_HORIZON_STEPS = 4


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


class ModelPredictiveController:
    """Shared finite-action MPC optimizer; subclasses only supply dynamics.

    Reads current temperature/ambient/demand, not hidden plant changes or the
    future disturbance schedule. Applies first action, observes actual plant,
    then plans again. The first prototype assumes ambient and demand stay at
    their current observed values within each 20-minute planning horizon.
    """

    def __init__(self):
        self.previous_kw = 0.0
        self.plans = np.asarray(
            list(product(MPC_POWERS_KW, repeat=MPC_HORIZON_STEPS)), dtype=float
        )
        self.plans.setflags(write=False)
        self.plan_count = len(self.plans)

    def predict_delta(self, temp_c, ambient_c, process_kw, heater_kw):
        raise NotImplementedError

    def predict_next_temperature(self, temp_c, ambient_c, process_kw, heater_kw):
        return np.asarray(temp_c) + self.predict_delta(
            temp_c, ambient_c, process_kw, heater_kw
        )

    def score_plans(self, temp_c: float, ambient_c: float, process_kw: float):
        """Score every plan without mutating controller state.

        Temperatures have soft penalties, not enforced hard constraints. Both
        controllers use the same costs, persistence forecast and plan ordering.
        """
        count = self.plan_count
        predicted_temperature = np.full(count, temp_c, dtype=float)
        objective = np.zeros(count, dtype=float)
        previous_kw = np.full(count, self.previous_kw, dtype=float)
        fixed_ambient = np.full(count, ambient_c, dtype=float)
        fixed_process = np.full(count, process_kw, dtype=float)

        for horizon_step in range(self.plans.shape[1]):
            candidate_kw = self.plans[:, horizon_step]
            predicted_temperature += self.predict_delta(
                predicted_temperature, fixed_ambient, fixed_process, candidate_kw
            )

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

        return objective

    def choose(self, temp_c: float, ambient_c: float, process_kw: float) -> float:
        # np.argmin selects the first minimum in the same ordered action grid.
        scores = self.score_plans(temp_c, ambient_c, process_kw)
        best_plan = self.plans[int(np.argmin(scores))]
        self.previous_kw = float(best_plan[0])
        return self.previous_kw


class LearnedMPC(ModelPredictiveController):
    """Shared MPC using the fitted scikit-learn temperature-change model."""

    name = "Fovra (learned MPC)"

    def __init__(self, model):
        super().__init__()
        self.model = model

    def predict_delta(self, temp_c, ambient_c, process_kw, heater_kw):
        x = np.column_stack(np.broadcast_arrays(temp_c, ambient_c, process_kw, heater_kw))
        return self.model.predict(x)


class PhysicsMPC(ModelPredictiveController):
    """Conventional nominal energy-balance MPC, with fixed efficiency = 1.

    Knows the design heat loss and capacity used to generate ML training data.
    Does not read the plant's actual efficiency, time, scenario or future data.
    This is a nominal baseline, not an oracle or an adaptive controller.
    """

    name = "Physics MPC"

    def predict_delta(self, temp_c, ambient_c, process_kw, heater_kw):
        temp_c, ambient_c, process_kw, heater_kw = np.broadcast_arrays(
            temp_c, ambient_c, process_kw, heater_kw
        )
        nominal_heat_kw = np.clip(heater_kw, 0.0, MAX_HEATER_KW)
        return (
            nominal_heat_kw - HEAT_LOSS_KW_PER_C * (temp_c - ambient_c) - process_kw
        ) * STEP_HOURS / THERMAL_CAPACITY_KWH_PER_C


def make_controller(baseline_name: str, model=None):
    if baseline_name == "Thermostat":
        return Thermostat()
    if baseline_name == "PI controller":
        return PIController()
    if baseline_name == "Physics MPC":
        return PhysicsMPC()
    if baseline_name == "Fovra":
        if model is None:
            raise ValueError("Fovra controller requires a trained world model")
        return LearnedMPC(model)
    raise ValueError(f"Unknown controller: {baseline_name}")
