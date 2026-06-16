# BESS Availability Dashboard

Streamlit prototype for a BESS fund manager availability dashboard. It is built for daily asset-manager use while keeping the first viewport useful for managers who only need the latest portfolio KPIs.

For a step-by-step beginner setup, start with `SETUP_GUIDE.md`. For the wider project plan, read `PROJECT_ROADMAP.md`.

The intended data flow is:

```text
Snowflake -> SQLite repository -> Streamlit dashboard
```

The dashboard reads from SQLite when the repository file exists. If that file has not been created yet, the app falls back to deterministic sample data so the interface can still be developed locally.

## What It Shows

- Availability cards for the last 3 hours, last 24 hours, and last month.
- Daily availability bars for the last 5 days with a 10-day moving average overlay.
- A top-right `Filter by` control for `O&M`, `PCS OEM`, and `ESS OEM`.
- Asset-level availability bubbles where vertical position is availability percentage and bubble size is installed MW.

## Run Locally

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.venvs"
python -m venv "$env:USERPROFILE\.venvs\am-dashboard"
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\Activate.ps1"
pip install -r requirements.txt
python sync_sqlite_repository.py --source sample
streamlit run app.py
```

If PowerShell blocks `Activate.ps1`, run the virtual environment Python directly:

```powershell
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\python.exe" sync_sqlite_repository.py --source sample
& "$env:USERPROFILE\.venvs\am-dashboard\Scripts\python.exe" -m streamlit run app.py
```

Streamlit will print a local URL that can be shared on the same network if the host allows it.

## SQLite Repository

The SQLite repository is the final dashboard-ready data source used by the interface. On Windows, the default location is outside OneDrive to avoid SQLite locking issues in synced folders.

Default location:

```text
%LOCALAPPDATA%\AM Dashboard\am_dashboard.sqlite
```

Refresh it with sample data:

```powershell
python sync_sqlite_repository.py --source sample
```

Use a different database path when needed:

```powershell
python sync_sqlite_repository.py --source sample --database "C:\path\to\am_dashboard.sqlite"
```

You can also set `AM_DASHBOARD_SQLITE_PATH` if the app should read from a non-default SQLite file. This is useful for deployment environments or controlled shared locations.

## Static Asset Metadata

The dashboard uses this workbook as the local source of static site metadata:

```text
C:\Users\g.mantinan\Downloads\the_shop_glm_sites_04.06.2026.xlsx
```

It is loaded by `asset_metadata.py` and enriches raw availability data with asset name, MW capacity, O&M provider, optimizer, PCS OEM, ESS OEM, and SCADA. It also keeps the newer static fields, including MWh capacity, duration, status, PCS model, ESS model, and PCS nominal voltage, available for future dashboard views. The Streamlit cache fingerprint includes this file, so changes to the workbook refresh the app data on the next run.

Bradford 37 and Bradford 50 YTD availability workbooks are registered as supplemental raw sources from Downloads in `raw_availability_data.py`. If those files are later moved into the main raw-data folder, the loader de-duplicates by filename.

## Snowflake Integration

Install the Snowflake connector only in environments that need to pull data from Snowflake:

```powershell
pip install -r requirements-snowflake.txt
```

```powershell
$env:SNOWFLAKE_ACCOUNT="your_account"
$env:SNOWFLAKE_USER="your_user"
$env:SNOWFLAKE_PASSWORD="your_password"
$env:SNOWFLAKE_WAREHOUSE="your_warehouse"
$env:SNOWFLAKE_DATABASE="your_database"
$env:SNOWFLAKE_SCHEMA="your_schema"
$env:SNOWFLAKE_ROLE="your_role"
$env:SNOWFLAKE_AVAILABILITY_TABLE="ANALYTICS.ASSET_AVAILABILITY"
```

Then refresh the SQLite repository from Snowflake:

```powershell
python sync_sqlite_repository.py --source snowflake
```

The Snowflake table or view should expose these columns:

| Column | Type | Notes |
| --- | --- | --- |
| `timestamp` | timestamp | Measurement interval timestamp. |
| `asset_id` | text | Stable asset identifier. |
| `asset_name` | text | Display name. |
| `availability_pct` | number | Availability percentage from 0 to 100. |
| `mw` | number | Asset capacity in MW. |
| `om_provider` | text | O&M provider filter value. |
| `pcs_oem` | text | PCS OEM filter value. |
| `ess_oem` | text | ESS OEM filter value. |

## Suggested Deployment Path

1. Read `PROJECT_ROADMAP.md` for the staged project plan.
2. Create the Snowflake availability view from the SCADA ingestion pipeline.
3. Store Snowflake credentials as deployment secrets rather than committing them.
4. Deploy the Streamlit app behind the organisation's preferred authentication layer.
5. Use GitHub Actions for linting/tests and deployment promotion once the production data contract is agreed.
