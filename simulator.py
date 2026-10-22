"""Transparent, synthetic 24-hour thermal-system simulator for Fovra v0.

The parameters in this file are illustrative, not calibrated to real equipment.
A heater command represents electric input power (kW); degraded heater efficiency
reduces delivered heat, NOT electricity consumed.
"""

from dataclasses import dataclass
from math import pi, sin

STEP_MINUTES = 5
STEP_HOURS = STEP_MINUTES / 60.0
STEPS_PER_DAY = 24 * 60 // STEP_MINUTES
MAX_HEATER_KW = 12.0
MIN_SAFE_TEMP_C = 58.0
MAX_SAFE_TEMP_C = 62.0
TARGET_TEMP_C = 60.0
START_TEMP_C = 60.0
HEAT_LOSS_KW_PER_C = 0.08
THERMAL_CAPACITY_KWH_PER_C = 1.0
SCENARIOS = ("Normal", "Production surge", "Heater degradation")


@dataclass(frozen=True)
class Conditions:
    """Plant conditions; only ambient and demand are exposed to controllers."""

    ambient_c: float
    process_kw: float
    heater_efficiency: float


def next_step(
    temp_c: float,
    ambient_c: float,
    process_kw: float,
    heater_kw: float,
    heater_efficiency: float = 1.0,
) -> tuple[float, float]:
    """Return (next temperature in °C, electricity consumed in kWh).

    One five-minute step of a deliberately simple lumped thermal model.
    No hidden randomness is used in the physical update.
    """
    heater_kw = max(0.0, min(MAX_HEATER_KW, float(heater_kw)))
    heat_loss_kw = HEAT_LOSS_KW_PER_C * (temp_c - ambient_c)
    delivered_heat_kw = heater_kw * heater_efficiency
    net_heat_kw = delivered_heat_kw - heat_loss_kw - process_kw
    next_temp_c = temp_c + net_heat_kw * STEP_HOURS / THERMAL_CAPACITY_KWH_PER_C
    electricity_kwh = heater_kw * STEP_HOURS
    return next_temp_c, electricity_kwh


def operating_conditions(
    step: int,
    ambient_baseline_c: float = 20.0,
    process_baseline_kw: float = 3.0,
    scenario: str = "Normal",
) -> Conditions:
    """Deterministic scenario shared by all controllers (fair comparison).

    Controllers observe the CURRENT ambient temperature and process demand only.
    They are not passed the scenario, future disturbances, or heater efficiency.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")

    hour = step * STEP_HOURS
    ambient_c = ambient_baseline_c + 1.0 * sin(2 * pi * (hour - 6) / 24)
    process_kw = max(
        0.0,
        process_baseline_kw
        + 0.45 * sin(2 * pi * hour / 8)
        + 0.25 * sin(2 * pi * hour / 3),
    )

    if scenario == "Production surge" and 10 <= hour < 14:
        process_kw += 2.5

    efficiency = 1.0
    if scenario == "Heater degradation" and hour >= 10:
        efficiency = 0.65

    return Conditions(
        ambient_c=float(ambient_c),
        process_kw=float(process_kw),
        heater_efficiency=efficiency,
    )
