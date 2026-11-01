from pathlib import Path

from streamlit.testing.v1 import AppTest

from cooling import CoolingCase, compare_cooling

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def cooling_app():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.selectbox(key="dashboard_view").set_value("Cooling exploration").run()
    assert not at.exception
    return at


def test_cooling_controls_match_simulator_and_navigation():
    at = cooling_app()
    at.selectbox(key="cool_climate").set_value("Cool")
    at.slider(key="cool_load").set_value(100)
    at.checkbox(key="cool_surge").set_value(True).run()
    assert not at.exception
    summary, _ = compare_cooling(CoolingCase("Cool", 100, True))
    table = at.dataframe[0].value
    assert table["Cooling electricity (kWh)"].tolist() == summary.cooling_kwh.round(2).tolist()
    assert table["Makeup water (L)"].eq(0).all()
    assert len(at.get("download_button")) == 2
    at.selectbox(key="dashboard_view").set_value("Adaptation experiment").run()
    assert not at.exception
    at.selectbox(key="dashboard_view").set_value("Original simulation").run()
    assert not at.exception
    assert any(m.label == "Fovra energy" for m in at.metric)


def test_search_results_are_not_stale_after_conditions_change():
    at = cooling_app()
    at.selectbox(key="cool_search_budget").set_value(8)
    at.button(key="cool_search_run").click().run()
    assert not at.exception
    assert len(at.dataframe) == 2
    table = at.dataframe[1].value
    assert set(table.Method) == {"AI screening", "Random search"}
    assert table.Simulations.eq(8).all()
    assert len(at.get("download_button")) == 3
    at.slider(key="cool_load").set_value(90).run()
    assert not at.exception
    assert len(at.dataframe) == 1
    assert any("Conditions changed" in item.value for item in at.info)
    at.button(key="cool_search_run").click().run()
    assert not at.exception
    assert len(at.dataframe) == 2
