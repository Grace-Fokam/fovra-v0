"""Check exact replay of the seven committed cold-plate scientific outputs.

Timing and environment metadata are deliberately outside this allowlist. This
stdlib-only checker never writes to either directory or regenerates references.
"""

import argparse
import difflib
import hashlib
from itertools import islice
from pathlib import Path


SCIENTIFIC_OUTPUTS = (
    "grid.csv",
    "grid_winners.json",
    "paired_comparison.csv",
    "reference_design.csv",
    "search_summary.csv",
    "search_trials.csv",
    "sensitivity.csv",
)
DEFAULT_REFERENCE = Path(__file__).resolve().parent / "results" / "cold_plate"
MAX_DIFF_LINES = 80


def check_outputs(reference, actual):
    """Return success and a readable report, inspecting every required output."""
    reference, actual = Path(reference), Path(actual)
    if reference.resolve() == actual.resolve():
        return False, "FAIL: reference and generated directories must be different.\n"

    report = ["Cold-plate scientific replay: exact bytes, no numerical tolerance.",
              "Excluded from comparison: timings.csv and metadata.json."]
    failures = 0
    for name in SCIENTIFIC_OUTPUTS:
        contents = []
        for label, directory in (("reference", reference), ("generated", actual)):
            try:
                contents.append((directory / name).read_bytes())
            except OSError as exc:
                report.append(f"FAIL {name}: cannot read {label} {directory / name}: {exc}")
                contents.append(None)
        if None in contents:
            failures += 1
            continue
        expected, generated = contents
        if expected == generated:
            report.append(f"PASS {name}")
            continue

        failures += 1
        report.append(f"FAIL {name}: differs from committed reference")
        for label, data in (("reference", expected), ("generated", generated)):
            report.append(f"  {label}: {len(data)} bytes, sha256={hashlib.sha256(data).hexdigest()}")
        # Keep line endings visible as escapes, including a missing final newline.
        def lines(data):
            return [line.rstrip("\r\n") + repr(line[len(line.rstrip("\r\n")):])[1:-1]
                    for line in data.decode("utf-8", errors="backslashreplace").splitlines(keepends=True)]
        diff = difflib.unified_diff(lines(expected), lines(generated),
                                    fromfile=f"reference/{name}", tofile=f"generated/{name}",
                                    n=2, lineterm="")
        preview = list(islice(diff, MAX_DIFF_LINES + 1))
        report.extend(preview[:MAX_DIFF_LINES])
        if len(preview) > MAX_DIFF_LINES:
            report.append(f"  Diff truncated after {MAX_DIFF_LINES} lines. Compare the full generated artifact.")

    report.append(f"{len(SCIENTIFIC_OUTPUTS) - failures}/{len(SCIENTIFIC_OUTPUTS)} scientific outputs match.")
    if failures:
        report.append("Inspect dependency versions, source hashes, and the file diffs. "
                      "Do not overwrite historical references to make this check pass.")
    return failures == 0, "\n".join(report) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--actual", type=Path, required=True)
    args = parser.parse_args(argv)
    success, report = check_outputs(args.reference, args.actual)
    print(report, end="")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
