# Deploy Fovra v0 on Streamlit Community Cloud

This app is a public-facing research demonstration. It uses a simulated hot-water tank, synthetic equipment configurations, and recorded comparison results. It is not validated on industrial equipment, does not establish real-world energy savings, and does not demonstrate an advantage unique to machine learning.

## Create the app

The repository owner must authorize Streamlit Community Cloud to access the GitHub repository. These steps require signing in to [Streamlit Community Cloud](https://share.streamlit.io/).

1. Check your Streamlit workspace for an app already connected to `Grace-Fokam/fovra-v0`. If one exists, open it and verify its URL instead of creating a duplicate.
2. Select **Create app** → **Yup, I have an app**.
3. Use these exact deployment values:

   | Setting | Value |
   | --- | --- |
   | GitHub repository | `Grace-Fokam/fovra-v0` |
   | Branch | `main` |
   | Main file path | `app.py` |
   | Python | `3.12` |
   | Dependencies | Root `requirements.txt` |
   | Secrets | None required |

4. Select a short custom subdomain if available, or accept the URL supplied by Streamlit. **Do not assume a proposed subdomain is live until it loads successfully.**
5. Click **Deploy**. Review the application and the deployment logs for import errors, incompatible packages, and startup failures.
6. In the app's sharing settings, confirm it is public if you want investors and design partners to open it without logging in. Test this in a signed-out browser.

## Verify both modes

Test the actual hosted app, not just the GitHub Actions tests.

- **Original simulation:** Open the dashboard. Confirm the temperature and energy charts render. Adjust room temperature to 15°C, production demand to 4.5 kW, scenario to **Production surge**, and baseline to **Physics MPC**. Click **Run**. Confirm the selected conditions appear, the energy and temperature metrics render, and no exception appears. Also test **Heater degradation** and return to **Normal**.
- **Adaptation experiment:** Use the **Dashboard view** selector to switch modes. Confirm the banner states there are **72 precomputed records across 18 matched cases**, a table with four controllers appears, and a metric chart renders. Under **Degraded** with all equipment and seeds selected, approximate mean tracking RMSE values should be 0.222°C for fixed learned MPC, 0.069°C for adaptive learned MPC, and 0.073°C for adaptive physics MPC. Fixed electricity use is about 161.611 kWh/day and adaptive electricity use about 162.500 kWh/day. These are **recorded synthetic results**, not a live industrial benchmark.
- Filter to one equipment configuration and seed 22. Expect four per-case records when all controllers remain selected. Change the metric, expand per-case results, and test the CSV download. Empty filter selections should display guidance. Return to **Original simulation**.
- Browsing the adaptation view must only read the committed `results/adaptation/summary.csv` file. It must **not** run `benchmark_adaptation.py` or rerun the 18 matched cases.
- Check app logs for runtime errors and unexpected dependency issues. Confirm the live URL opens anonymously without exposing application secrets, credentials, or internal tracebacks.

GitHub Actions already tests the two dashboard modes using Streamlit's headless testing runner. A green workflow is useful but does not replace the checks above on the hosted app.

## After the live URL is verified

Add a **Live dashboard** link near the top of `README.md` pointing to the *exact verified URL*. Do not commit a guessed or placeholder URL. Streamlit Community Cloud follows pushes to `main`, so subsequent changes will update the app automatically.

The code and experimental CSVs are public. Keep `.streamlit/secrets.toml`, credentials, personal data, and any unpublished operator measurements out of the repository. No API keys or credentials are needed for this demonstration. Maintain the statements about synthetic linear systems, competitive adaptive physics, and the absence of demonstrated industrial energy savings.

For troubleshooting, see [Streamlit's deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [cloud logs](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app).
