from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from adaptation_view import CONTROLLERS, load_results, select_results

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_recorded_degraded_means():
    frame = load_results()
    assert len(frame) == 72
    means = frame[frame.degradation].groupby("controller").mean(numeric_only=True)
    assert means.loc["adaptive_learned", "target_rmse_c"] == pytest.approx(.069011, abs=1e-6)
    assert means.loc["adaptive_physics", "energy_kwh"] == pytest.approx(162.5)
    assert means.violation_minutes.eq(0).all()


def test_reject_incomplete_and_duplicate_data(tmp_path):
    frame = load_results()
    for bad in (frame.iloc[:-1], pd.concat([frame, frame.iloc[:1]])):
        path = tmp_path / "summary.csv"
        bad.to_csv(path, index=False)
        with pytest.raises(ValueError):
            load_results(path)


def test_adaptation_filters_and_original_navigation(monkeypatch):
    import benchmark_adaptation
    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded view must not run benchmark")
    monkeypatch.setattr(benchmark_adaptation, "run_case", forbidden)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.selectbox(key="dashboard_view").set_value("Adaptation experiment").run()
    assert not at.exception
    assert len(at.dataframe[1].value) == 36
    for condition in ("Unchanged", "Degraded"):
        for equipment in ("nominal", "unseen_small", "unseen_large"):
            at.multiselect[0].set_value([equipment])
            at.multiselect[1].set_value([22])
            at.radio[0].set_value(condition).run()
            expected = select_results(load_results(), [equipment], condition == "Degraded", [22], list(CONTROLLERS))
            pd.testing.assert_frame_equal(at.dataframe[1].value.reset_index(drop=True), expected.reset_index(drop=True))
            assert not at.exception
    at.multiselect[2].set_value(["adaptive_physics"]).run()
    assert len(at.dataframe[0].value) == 1
    at.multiselect[0].set_value([]).run()
    assert not at.exception
    assert any("Select at least" in i.value for i in at.info)
    at.selectbox(key="dashboard_view").set_value("Original simulation").run()
    assert not at.exception
    assert any(m.label == "Fovra energy" for m in at.metric)
