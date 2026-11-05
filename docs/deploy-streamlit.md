# Deploy on Streamlit Community Cloud

The dashboard contains **simulated component design** and **data-center cooling** views. It opens the cold-plate explorer, with geometry controls, model diagnostics, comparisons and recorded search results. The separate cooling view compares illustrative dry and evaporative setups. Neither represents validated hardware or proven efficiency gains.

Creating a pull request does not deploy the app. Review and approve the interface before merging or deploying. These instructions are for an approved deployment.

## Create the app

First, connect [Streamlit Community Cloud](https://share.streamlit.io/) to the GitHub repo.

1. Check your Streamlit workspace for an existing app linked to `Grace-Fokam/fovra-v0` before creating a new one.
2. If there isn't one, click **Create app** and deploy from the repo.
3. Use these settings:

   | Setting | Value |
   | --- | --- |
   | Repository | `Grace-Fokam/fovra-v0` |
   | Branch | `main` |
   | Entry point | `app.py` |
   | Python | `3.12` |
   | Dependencies | Root `requirements.txt` |
   | Secrets | None |

4. Deploy and check the startup logs. If the app is public, open the URL in a signed-out browser to make sure it works. Don't share a URL you haven't checked.

## Check the dashboard

1. Open the app. It should go straight to **Component design**. Follow the [component explorer checks](component-explorer.md#review-checks), then choose **Data-center cooling** in the sidebar.
2. With the default hot-and-dry settings, the dry option should be flagged as failing the thermal checks. Look over the electricity, water, cost, emissions, and coolant-temperature outputs.
3. Set **Climate** to **Cool**. Both options should show zero makeup water.
4. Click **Run AI comparison**, review the search table, and download the summary and trial CSVs.
5. Change the IT load. The old search results should be marked out of date until you rerun.
6. Check the logs for errors, and confirm a signed-out browser can open the app without exposing credentials or private data.

GitHub Actions tests the dashboard and benchmarks, but passing tests don't prove the hosted app works.

## After the URL is verified

Add a **Live dashboard** link to the README with the exact working URL. A deployment that tracks `main` updates whenever you push to it.

Keep `.streamlit/secrets.toml`, credentials, private measurements, and customer information out of the repo.

For troubleshooting, see Streamlit's [deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [app logs](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app).
