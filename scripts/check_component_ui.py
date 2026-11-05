"""Browser smoke check and review screenshots; run with Playwright installed."""

import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ui-review"
URL = "http://127.0.0.1:8501"


def check_browser():
    OUTPUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1250}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL)
        page.get_by_text("41.386 °C", exact=True).wait_for()
        page.get_by_text("56.471 Pa", exact=True).wait_for()
        page.get_by_role("heading", name="Explore the geometry of cooling.").wait_for()
        page.locator(".st-key-cp_design_download").get_by_role("button").wait_for()
        page.screenshot(path=str(OUTPUT / "design-desktop.png"))

        with page.expect_download() as pending:
            page.get_by_role("button", name="Download current design JSON", exact=True).click()
        download = pending.value
        path = OUTPUT / "current-design.json"
        download.save_as(path)
        payload = json.loads(path.read_text())
        assert abs(payload["result"]["peak_base_c"] - 41.3861756818274) < 1e-10
        assert payload["result"]["feasible"] is True
        assert payload["case"]["heat_w"] == 100

        page.get_by_role("button", name="Pin current design", exact=True).click()
        page.get_by_role("button", name="Clear pinned designs", exact=True).wait_for(state="visible")
        page.get_by_text("Recorded search", exact=True).click()
        page.get_by_text("Check all seeds", exact=True).wait_for()
        page.get_by_text("Search the design space", exact=True).evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        page.screenshot(path=str(OUTPUT / "search-desktop.png"))
        page.get_by_text("Temperature & pressure tradeoffs", exact=True).evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        page.screenshot(path=str(OUTPUT / "tradeoffs-desktop.png"))
        assert page.locator("canvas").count() >= 2
        page.locator(".st-key-cp_budget").get_by_role("slider").press("Home")
        page.get_by_text("At 1 evaluations,", exact=False).wait_for()
        page.get_by_text("Model & evidence", exact=True).click()
        page.get_by_text("What the model can tell us", exact=True).wait_for()
        page.get_by_text("Data-center cooling", exact=True).click()
        page.get_by_role("heading", name="Cooling exploration", exact=True).wait_for()
        page.get_by_text("Component design", exact=True).click()
        page.get_by_text("Design studio", exact=True).click()
        page.get_by_role("button", name="Grid best", exact=True).click()
        page.get_by_text("41.386 °C", exact=True).wait_for()
        page.set_viewport_size({"width": 390, "height": 844})
        sidebar_close = page.get_by_test_id("stSidebarCollapseButton").get_by_role("button")
        if sidebar_close.is_visible():
            sidebar_close.click()
        page.get_by_role("heading", name="Explore the geometry of cooling.").evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        page.screenshot(path=str(OUTPUT / "design-mobile.png"))
        assert page.locator('[data-testid="stException"]').count() == 0
        assert not errors, errors
        browser.close()


def main():
    OUTPUT.mkdir(exist_ok=True)
    with (OUTPUT / "server.log").open("w") as log:
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
            "--server.address", "127.0.0.1", "--server.port", "8501", "--browser.gatherUsageStats", "false",
        ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Streamlit exited before becoming healthy")
                try:
                    with urlopen(URL + "/_stcore/health", timeout=1) as response:
                        if response.read().strip() == b"ok":
                            break
                except (URLError, TimeoutError):
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("Streamlit did not become healthy")
            check_browser()
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
