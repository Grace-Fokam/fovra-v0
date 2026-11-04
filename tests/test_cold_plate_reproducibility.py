"""The replay check should catch any changed result, not just changed totals."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from check_cold_plate_reproducibility import (
    DEFAULT_REFERENCE, SCIENTIFIC_OUTPUTS, check_outputs,
)


@pytest.fixture
def replay(tmp_path):
    actual = tmp_path / "generated"
    actual.mkdir()
    for name in SCIENTIFIC_OUTPUTS:
        shutil.copyfile(DEFAULT_REFERENCE / name, actual / name)
    return actual


def test_recorded_outputs_pass_without_timing_or_metadata(replay):
    success, report = check_outputs(DEFAULT_REFERENCE, replay)
    assert success
    assert "7/7 scientific outputs match" in report
    # Timing and metadata can differ without affecting the result.
    (replay / "timings.csv").write_text("elapsed_s\n999999\n")
    (replay / "metadata.json").write_text('{"python": "another environment"}')
    assert check_outputs(DEFAULT_REFERENCE, replay) == (success, report)


@pytest.mark.parametrize("name", SCIENTIFIC_OUTPUTS)
def test_every_scientific_output_is_required_and_checked(replay, name):
    path = replay / name
    original = path.read_text()
    if name.endswith(".json"):
        data = json.loads(original)
        data[0]["result"]["peak_base_c"] += 1
        path.write_text(json.dumps(data, indent=2) + "\n")
    else:
        # Change one data row and leave everything else alone.
        lines = original.splitlines(keepends=True)
        lines[1] = "999," + lines[1].split(",", 1)[1]
        path.write_text("".join(lines))
    success, report = check_outputs(DEFAULT_REFERENCE, replay)
    assert not success
    assert f"FAIL {name}" in report
    assert f"--- reference/{name}" in report and f"+++ generated/{name}" in report
    assert "6/7 scientific outputs match" in report
    if name == "search_trials.csv":
        assert (replay / "paired_comparison.csv").read_bytes() == (DEFAULT_REFERENCE / "paired_comparison.csv").read_bytes()
    path.unlink()
    success, report = check_outputs(DEFAULT_REFERENCE, replay)
    assert not success
    assert f"FAIL {name}: cannot read generated" in report


def test_missing_reference_and_multiple_failures_are_reported(replay, tmp_path):
    reference = tmp_path / "reference"
    shutil.copytree(replay, reference)
    (reference / "grid.csv").unlink()
    (replay / "search_summary.csv").unlink()
    success, report = check_outputs(reference, replay)
    assert not success
    assert "FAIL grid.csv: cannot read reference" in report
    assert "FAIL search_summary.csv: cannot read generated" in report
    assert "5/7 scientific outputs match" in report


def test_rejects_self_comparison(replay):
    success, report = check_outputs(replay, replay / ".")
    assert not success and "must be different" in report


def test_tiny_numeric_drift_and_serialization_changes_are_not_silently_tolerated(replay):
    path = replay / "grid_winners.json"
    data = json.loads(path.read_text())
    data[0]["result"]["peak_base_c"] += 1e-12
    path.write_text(json.dumps(data, indent=2) + "\n")
    assert not check_outputs(DEFAULT_REFERENCE, replay)[0]
    shutil.copyfile(DEFAULT_REFERENCE / path.name, path)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    success, report = check_outputs(DEFAULT_REFERENCE, replay)
    assert not success
    assert "-]\\n\n+]" in report


def test_cli_exit_status_diagnostics_and_no_reference_mutation(replay):
    checker = Path(__file__).resolve().parents[1] / "check_cold_plate_reproducibility.py"
    before = {name: (DEFAULT_REFERENCE / name).read_bytes() for name in SCIENTIFIC_OUTPUTS}
    command = [sys.executable, str(checker), "--actual", str(replay)]
    good = subprocess.run(command, cwd=replay, capture_output=True, text=True)
    assert good.returncode == 0 and "7/7" in good.stdout
    (replay / "search_trials.csv").write_text("changed\n" * 100)
    bad = subprocess.run(command, cwd=replay, capture_output=True, text=True)
    assert bad.returncode == 1
    assert "FAIL search_trials.csv" in bad.stdout
    assert "Diff truncated" in bad.stdout
    assert "PASS sensitivity.csv" in bad.stdout
    assert before == {name: (DEFAULT_REFERENCE / name).read_bytes() for name in SCIENTIFIC_OUTPUTS}
