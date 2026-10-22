"""Headless dashboard test using Streamlit's built-in AppTest runner.

Runs app.py without a browser, changes the sidebar controls, presses
"Run", and checks that the page renders without exceptions and that
the displayed metrics come from the real simulator. Skipped if Streamlit is
not installed.
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from evaluation import SimulationConfig, compare  # noqa: E402
from train_model import train_world_model  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_default_page_renders():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    model, _ = train_world_model()
    _, _, fovra, _ = compare(SimulationConfig(), model)
    assert _metric(at, "Fovra energy") == f"{fovra['energy_kwh']:.1f} kWh"


@pytest.mark.parametrize("scenario", ["Normal", "Production surge", "Heater degradation"])
@pytest.mark.parametrize("baseline", ["Thermostat", "PI controller", "Physics MPC"])
def test_controls_rerun_simulation(scenario, baseline):
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.slider[0].set_value(15)      # room temperature
    at.slider[1].set_value(4.5)     # production demand
    at.radio[0].set_value(scenario)
    at.selectbox[0].set_value(baseline)
    at.button[0].click().run()      # "Run"
    assert not at.exception

    model, _ = train_world_model()
    _, _, fovra, base = compare(SimulationConfig(15.0, 4.5, scenario, baseline), model)
    assert _metric(at, "Fovra energy") == f"{fovra['energy_kwh']:.1f} kWh"
    assert _metric(at, f"{baseline} energy") == f"{base['energy_kwh']:.1f} kWh"
    table = at.dataframe[0].value.set_index("Metric")
    assert table.loc["Typical miss from 60°C (°C)", baseline] == f"{base['target_rmse_c']:.3f}"
    assert table.loc["Heater changes", baseline] == str(base["heater_adjustments"])
    more = at.dataframe[1].value.set_index("Metric")
    assert float(more.loc["Time to decide, average (ms)", baseline]) >= 0
    records = at.dataframe[2].value
    assert f"{baseline} temp (°C)" in records.columns
    if baseline == "Physics MPC":
        assert records[f"{baseline} predicted temp (°C)"].notna().all()
