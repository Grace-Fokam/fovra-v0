"""Check exported experiment provenance and reproducibility, excluding clocks."""

import json

import numpy as np
import pandas as pd

import benchmark_mpc


def test_repeats_preserve_behavior_and_export_all_comparators(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_mpc, "PROFILES", {"default": (20., 3.)})
    monkeypatch.setattr(benchmark_mpc, "SCENARIOS", ("Normal",))
    measurements, pairs = benchmark_mpc.run_benchmark(tmp_path, seeds=[20261020], repeats=2)
    assert set(measurements.controller) == {"Fovra", "Physics MPC", "Thermostat", "PI controller"}
    assert len(measurements) == 8
    assert len(pairs) == 1 and pairs.action_mismatches.item() == 0
    # Fresh controller state on each repeat must reproduce non-timing outcomes.
    fields = [column for column in measurements if not column.startswith("decision_")
              and column not in ("repeat", "run_position")]
    first = measurements[measurements.repeat == 0][fields].reset_index(drop=True)
    second = measurements[measurements.repeat == 1][fields].reset_index(drop=True)
    pd.testing.assert_frame_equal(first, second)
    persisted = pd.read_csv(tmp_path / "measurements.csv")
    np.testing.assert_allclose(persisted.energy_kwh, measurements.energy_kwh, rtol=1e-11)
    trajectory = pd.read_csv(tmp_path / "normal.csv")
    assert trajectory.baseline_type.eq("Physics MPC").all()
    assert trajectory.fovra_temperature_c.equals(trajectory.baseline_temperature_c)
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["seeds"] == [20261020] and metadata["repeats"] == 2
    assert "controllers.py" in metadata["source_sha256"]
    assert "scikit-learn" in metadata["versions"]
