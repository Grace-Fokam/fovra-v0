"""Optional: run numerical experiments without launching the Streamlit browser UI.

Usage: python run_example.py
Saves three CSV comparison records under examples/.
"""
from pathlib import Path
import pandas as pd

from evaluation import SimulationConfig, compare, merge_for_download
from simulator import SCENARIOS
from train_model import train_world_model

model, heldout_mae = train_world_model()
output = Path(__file__).resolve().parent / "examples"
output.mkdir(exist_ok=True)
summary_rows = []
print(f"Held-out nominal prediction MAE: {heldout_mae:.8f} °C")
for scenario in SCENARIOS:
    config = SimulationConfig(20, 3, scenario, "Thermostat")
    fovra, baseline, fovra_stats, baseline_stats = compare(config, model)
    filename = scenario.lower().replace(" ", "_") + ".csv"
    merge_for_download(fovra, baseline, "Thermostat").to_csv(output / filename, index=False)
    row = {
        "scenario": scenario,
        "ambient_baseline_c": 20,
        "production_baseline_kw": 3,
        "fovra_energy_kwh": round(fovra_stats["energy_kwh"], 2),
        "thermostat_energy_kwh": round(baseline_stats["energy_kwh"], 2),
        "fovra_minutes_outside": fovra_stats["minutes_outside"],
        "thermostat_minutes_outside": baseline_stats["minutes_outside"],
        "fovra_model_one_step_mae_c": round(fovra_stats["one_step_prediction_mae_c"], 4),
    }
    summary_rows.append(row)

pd.DataFrame(summary_rows).to_csv(output / "summary.csv", index=False)
print(pd.DataFrame(summary_rows).to_string(index=False))
print(f"CSVs saved in {output}")
