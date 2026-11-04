"""Illustrative warm-water cooling loop. No equipment calibration or chip model.

See docs/cooling-experiment.md for equations, boundaries, and assumptions.
"""

from dataclasses import asdict, dataclass
from math import exp, isfinite, pi, sin

import numpy as np
import pandas as pd

STEP_HOURS = 5 / 60
STEPS = 288
TARGET_C = 32.0
LIMIT_C = 35.0  # Illustrative bulk-coolant limit, not an equipment standard.
CAPACITY_KWH_PER_C = 5.0
BASE_UA_KW_PER_C = 12.0
PUMP_KW = 1.5
SPRAY_PUMP_KW = 0.4
FAN_RATED_KW = 4.0
WET_APPROACH_C = 3.0
LATENT_KWH_PER_L = 0.68
CYCLES_OF_CONCENTRATION = 4.0
CLIMATES = {
    "Cool": (15.0, 10.0),
    "Hot and dry": (34.0, 19.0),
    "Hot and humid": (32.0, 27.0),
}
MODES = ("Dry cooler", "Evaporative assist")


@dataclass(frozen=True)
class CoolingCase:
    climate: str = "Hot and dry"
    load_kw: float = 80.0
    surge: bool = False
    carbon_kg_per_kwh: float = 0.4
    electricity_per_kwh: float = 0.12
    water_per_m3: float = 2.0

    def __post_init__(self):
        if self.climate not in CLIMATES:
            raise ValueError("Unknown climate")
        values = (self.load_kw, self.carbon_kg_per_kwh,
                  self.electricity_per_kwh, self.water_per_m3)
        if not all(isfinite(v) and v >= 0 for v in values) or self.load_kw > 200:
            raise ValueError("Use finite nonnegative inputs and a load up to 200 kW")


@dataclass(frozen=True)
class CoolingDesign:
    mode: str = "Dry cooler"
    size: float = 1.0
    wet_trigger: float = 1.0

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError("Unknown heat rejection mode")
        if not isfinite(self.size) or not 0.5 <= self.size <= 2.0:
            raise ValueError("Cooler size must be between 0.5 and 2.0")
        if not isfinite(self.wet_trigger) or not 0 < self.wet_trigger <= 1:
            raise ValueError("Wet trigger must be in (0, 1]")

    @property
    def name(self):
        return f"{self.mode} | size {self.size:g} | trigger {self.wet_trigger:g}"


def make_conditions(case):
    """Paired synthetic weather and IT load. No location or weather-feed claims."""
    dry, wet = CLIMATES[case.climate]
    rows = []
    for step in range(STEPS):
        hour = step * STEP_HOURS
        wave = sin(2 * pi * (hour - 9) / 24)
        load = case.load_kw * (1 + 0.10 * sin(2 * pi * (hour - 6) / 24))
        if case.surge and 10 <= hour < 14:
            load *= 1.35
        rows.append((hour, dry + 4 * wave, wet + 2 * wave, load))
    return pd.DataFrame(rows, columns=["time_h", "dry_bulb_c", "wet_bulb_c", "it_kw"])


def advance_temperature(temp, sink, heat_kw, ua, hours=STEP_HOURS):
    """Exact integration with fixed inputs and a bypass preventing reverse flow.

    Returns end temperature and interval-average rejected heat (thermal kW).
    Below the sink, load first warms the loop without heat rejection.
    """
    if not all(isfinite(v) for v in (temp, sink, heat_kw, ua, hours)):
        raise ValueError("Thermal inputs must be finite")
    if heat_kw < 0 or ua < 0 or hours <= 0:
        raise ValueError("Heat and UA must be nonnegative, timestep positive")
    if ua == 0 or (temp <= sink and heat_kw == 0):
        return temp + heat_kw * hours / CAPACITY_KWH_PER_C, 0.0
    active_hours = hours
    active_temp = temp
    if temp < sink:
        warmup = (sink - temp) * CAPACITY_KWH_PER_C / heat_kw
        if warmup >= hours:
            return temp + heat_kw * hours / CAPACITY_KWH_PER_C, 0.0
        active_hours -= warmup
        active_temp = sink
    equilibrium = sink + heat_kw / ua
    end = equilibrium + (active_temp - equilibrium) * exp(
        -ua * active_hours / CAPACITY_KWH_PER_C
    )
    rejected = heat_kw - CAPACITY_KWH_PER_C * (end - temp) / hours
    return end, max(0.0, rejected)


def required_fan(temp, sink, heat, design):
    """Smallest fan fraction reaching the target at interval end, or full power."""
    def end_at(speed):
        return advance_temperature(temp, sink, heat, BASE_UA_KW_PER_C * design.size * speed)[0]

    if end_at(0.0) <= TARGET_C:
        return 0.0
    if end_at(1.0) > TARGET_C:
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(18):
        mid = (low + high) / 2
        if end_at(mid) > TARGET_C:
            low = mid
        else:
            high = mid
    return high


def simulate_cooling(case, design):
    """One matched 24-hour day, from 32°C, with no IT load reduction or backup."""
    temp = TARGET_C
    rows = []
    for hour, dry, wet, it_kw in make_conditions(case).itertuples(index=False, name=None):
        dry_fan = required_fan(temp, dry, it_kw + PUMP_KW, design)
        wet_sink = wet + WET_APPROACH_C
        dry_end = advance_temperature(
            temp, dry, it_kw + PUMP_KW, BASE_UA_KW_PER_C * design.size * dry_fan
        )[0]
        use_wet = (design.mode == "Evaporative assist" and wet_sink < dry
                   and (dry_fan > design.wet_trigger or dry_end > TARGET_C + 1e-6))
        sink = wet_sink if use_wet else dry
        pump = PUMP_KW + (SPRAY_PUMP_KW if use_wet else 0.0)
        fan = required_fan(temp, sink, it_kw + pump, design) if use_wet else dry_fan
        after, rejected = advance_temperature(
            temp, sink, it_kw + pump, BASE_UA_KW_PER_C * design.size * fan
        )
        fan_kw = FAN_RATED_KW * design.size * fan ** 3
        cooling_kw = pump + fan_kw
        # Idealized all-latent wet heat rejection. Blowdown is withdrawal,
        # not evaporation. Recirculating coolant is not counted as consumed.
        evaporated_l = rejected * STEP_HOURS / LATENT_KWH_PER_L if use_wet else 0.0
        blowdown_l = evaporated_l / (CYCLES_OF_CONCENTRATION - 1)
        rows.append({
            "time_h": hour + STEP_HOURS,
            "dry_bulb_c": dry, "wet_bulb_c": wet, "it_kw": it_kw,
            "temperature_before_c": temp, "coolant_c": after,
            "wet_active": use_wet, "fan_fraction": fan,
            "fan_kw": fan_kw, "pump_kw": pump, "cooling_kw": cooling_kw,
            "heat_rejected_kw": rejected,
            "cooling_kwh": cooling_kw * STEP_HOURS,
            "evaporated_l": evaporated_l, "blowdown_l": blowdown_l,
            "makeup_l": evaporated_l + blowdown_l,
        })
        temp = after
    frame = pd.DataFrame(rows)
    frame["cumulative_cooling_kwh"] = frame.cooling_kwh.cumsum()
    frame["cumulative_makeup_l"] = frame.makeup_l.cumsum()
    return frame


def summarize_cooling(frame, case, design):
    energy = float(frame.cooling_kwh.sum())
    makeup = float(frame.makeup_l.sum())
    # Conservative interval flag: either endpoint above the illustrative limit.
    over = frame[["temperature_before_c", "coolant_c"]].max(axis=1) > LIMIT_C + 1e-8
    peak = float(frame[["temperature_before_c", "coolant_c"]].max().max())
    stored = CAPACITY_KWH_PER_C * (float(frame.coolant_c.iloc[-1]) - TARGET_C)
    return {
        **asdict(case), **asdict(design), "design": design.name,
        "it_kwh": float(frame.it_kw.sum() * STEP_HOURS),
        "cooling_kwh": energy,
        "evaporated_l": float(frame.evaporated_l.sum()),
        "blowdown_l": float(frame.blowdown_l.sum()), "makeup_l": makeup,
        "cooling_carbon_kg": energy * case.carbon_kg_per_kwh,
        "cooling_utility_cost": energy * case.electricity_per_kwh + makeup / 1000 * case.water_per_m3,
        "peak_coolant_c": peak, "end_coolant_c": float(frame.coolant_c.iloc[-1]),
        "over_limit_minutes": int(round(over.sum() * STEP_HOURS * 60)),
        "stored_heat_kwh": stored,
        # A design cannot win by leaving appreciable heat in the loop.
        "thermal_ok": bool(not over.any() and stored <= 0.5 + 1e-8),
    }


def evaluate_design(case, design):
    return summarize_cooling(simulate_cooling(case, design), case, design)


def compare_cooling(case, size=1.0, wet_trigger=1.0):
    traces, summaries = [], []
    for mode in MODES:
        design = CoolingDesign(mode, size, wet_trigger)
        frame = simulate_cooling(case, design)
        summaries.append(summarize_cooling(frame, case, design))
        traces.append(frame.assign(mode=mode))
    return pd.DataFrame(summaries), pd.concat(traces, ignore_index=True)


def pareto_mask(frame):
    """Nondominated electricity/makeup-water points among thermally valid runs."""
    values = frame[["cooling_kwh", "makeup_l"]].to_numpy()
    valid = frame.thermal_ok.to_numpy(dtype=bool)
    result = np.zeros(len(frame), dtype=bool)
    for i, point in enumerate(values):
        if valid[i]:
            dominates = valid & (values <= point).all(axis=1) & (values < point).any(axis=1)
            result[i] = not dominates.any()
    return result
