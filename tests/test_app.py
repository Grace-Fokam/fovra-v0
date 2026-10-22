"""Headless dashboard test using Streamlit's built-in AppTest runner.

Runs app.py without a browser, changes the sidebar controls, presses
"Run simulation", and checks that the page renders without exceptions and that
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
    assert _metric(at, "Fovra electricity") == f"{fovra['energy_kwh']:.1f} kWh"


@pytest.mark.parametrize("scenario", ["Normal", "Production surge", "Heater degradation"])
@pytest.mark.parametrize("baseline", ["Thermostat", "PI controller"])
def test_controls_rerun_simulation(scenario, baseline):
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.slider[0].set_value(15)      # surrounding temperature
    at.slider[1].set_value(4.5)     # production demand
    at.radio[0].set_value(scenario)
    at.selectbox[0].set_value(baseline)
    at.button[0].click().run()      # "Run simulation"
    assert not at.exception

    model, _ = train_world_model()
    _, _, fovra, base = compare(SimulationConfig(15.0, 4.5, scenario, baseline), model)
    assert _metric(at, "Fovra electricity") == f"{fovra['energy_kwh']:.1f} kWh"
    assert _metric(at, f"{baseline} electricity") == f"{base['energy_kwh']:.1f} kWh"
