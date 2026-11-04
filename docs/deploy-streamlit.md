# Deploy Fovra v0 on Streamlit Community Cloud

The dashboard is a public research demonstration of **simulated data-center cooling**. It compares illustrative dry and evaporative cooling configurations, electricity use, makeup water, and modeled thermal limits. The equipment curves and weather are synthetic. This is not validated industrial equipment or demonstrated energy savings.

## Create the app

The repository owner must authorize [Streamlit Community Cloud](https://share.streamlit.io/) to access the GitHub repository.

1. Check your Streamlit workspace for an existing app connected to `Grace-Fokam/fovra-v0`. Verify its address rather than creating a duplicate.
2. If none exists, select **Create app** and choose a repository-based deployment.
3. Use these settings:

   | Setting | Value |
   | --- | --- |
   | Repository | `Grace-Fokam/fovra-v0` |
   | Branch | `main` |
   | Entry point | `app.py` |
   | Python | `3.12` |
   | Dependencies | Root `requirements.txt` |
   | Secrets | None required |

4. Deploy and review startup logs. Test the public URL in a signed-out browser if the app is intended for external viewers. Do not publish an unverified URL.

## Verify the cooling dashboard

1. Open the app. It should display **Cooling exploration** directly, without a dashboard-mode selector.
2. At the default hot-and-dry settings, verify the dry option is flagged as failing the modeled thermal checks. Check the electricity, water, cost, emissions, and coolant-temperature outputs.
3. Change **Climate** to **Cool** and confirm both options report zero makeup water under the modeled assumptions.
4. Run **AI comparison**, review the search table, and download the summary and trial CSVs.
5. Change the IT load. Previous search results should be marked stale until the comparison is rerun.
6. Inspect the hosted logs for exceptions. Confirm a signed-out browser can access the app and no credentials or private data are exposed.

GitHub Actions exercises the remaining dashboard controls and research benchmarks, but local tests do not prove a hosted deployment is working.

## Once the live URL is verified

Add a **Live dashboard** link to the README using the exact working URL. A Streamlit deployment tracking `main` will update after pushes to that branch.

Keep `.streamlit/secrets.toml`, credentials, private measurements, and unpublished customer information out of the repository.

See [Streamlit's deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [cloud logs](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app) for troubleshooting.
