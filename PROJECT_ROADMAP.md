# AM Dashboard Project Roadmap

This roadmap is written for a non-developer project owner who wants to learn the process while building a production-quality dashboard.

## Target Architecture

The dashboard should become the internal availability calculation and commercial review layer. It should not replace contractor systems. Contractors will continue to use an external event tracker, while asset managers use the AM Dashboard to import raw availability, review exclusion requests, calculate net availability, and understand commercial impact.

The target operating workflow is:

1. Raw availability figures are downloaded from the relevant SCADAs for each site.
2. Asset managers upload the raw availability files into the AM Dashboard.
3. Contractors submit exclusion requests in an external event tracker.
4. Asset managers import tracker exports into the AM Dashboard.
5. The dashboard shows exclusion requests by approval state.
6. Only approved requests flow into the exclusion register used for net availability.
7. Asset managers run the net availability calculation.
8. The dashboard reports availability, lost MWh, lost revenue, export packs, and audit trail outputs.

The intended data architecture remains:

1. Snowflake stores the governed source data.
2. A controlled sync step pulls the required dashboard data from Snowflake.
3. The sync step writes the final dashboard-ready dataset into a local SQLite repository.
4. The Streamlit user interface reads from SQLite only.
5. GitHub stores the project code, documentation, and deployment workflow.

During early development, manual CSV/XLSX uploads and SQLite are acceptable. Later, SCADA data and event tracker data can be automated through APIs, Snowflake ingestion, or governed file drops. This keeps the user interface simple and testable while allowing the operating model to mature.

## Phase 1: Local Foundation

Goal: make the dashboard easy to run on your laptop.

- Confirm Python and Visual Studio Code are installed.
- Confirm Git is available in PowerShell.
- Create a local virtual environment.
- Install the packages in `requirements.txt`.
- Run the dashboard with sample data.
- Keep secrets out of the codebase.

Beginner checkpoint:

- You can explain what a virtual environment is.
- You can run `streamlit run app.py`.
- You know where the project folder is on your machine.

## Phase 2: SQLite Repository

Goal: make SQLite the final data source for the interface.

- Create a SQLite schema for dashboard-ready availability data.
- Add a sync command that can populate SQLite with sample data.
- Update the Streamlit app to read from SQLite when the database exists.
- Add clear status messages so you know whether the UI is using SQLite or sample data.
- Keep the default local SQLite file outside OneDrive to avoid database locking issues.

Beginner checkpoint:

- You can run `python sync_sqlite_repository.py --source sample`.
- You understand that SQLite is the local database file used by the dashboard.
- You know the app should not read Snowflake directly during normal use.

## Phase 3: Snowflake Sync

Goal: replace sample data with the governed Snowflake data pull.

- Agree the exact Snowflake view or table name.
- Confirm required columns and data types.
- Install the Snowflake connector only in environments that need it.
- Store Snowflake credentials as environment variables or deployment secrets.
- Run the sync command with `--source snowflake`.
- Validate row counts, timestamp coverage, and availability calculations.

Beginner checkpoint:

- You can describe the difference between source data in Snowflake and dashboard-ready data in SQLite.
- You know why credentials are never committed to GitHub.

## Phase 4: Availability Workflow

Goal: support the internal raw-to-net availability workflow.

- Upload raw availability files from SCADA exports.
- Import event tracker exports from the external contractor tracker.
- Map tracker records to exclusion requests using event ID, site, affected device, start time, end time, reason, and status.
- Show request states such as `Pending`, `Approved`, `Rejected`, and `Needs clarification`.
- Apply only approved exclusions to the net availability calculation.
- Keep pending and rejected requests visible for workflow management and audit.
- Generate a gross-to-net availability bridge.
- Persist calculation runs and file lineage when the data model is ready.

Beginner checkpoint:

- You can explain why contractor requests are not automatically commercial exclusions.
- You know which approval statuses affect net availability.
- You can trace a final availability number back to raw availability files and approved tracker records.

## Phase 5: Commercial Impact

Goal: quantify the commercial consequences of availability loss.

- Calculate lost MWh by site and period.
- Calculate lost MWh by device and period when device-level data is available.
- Calculate lost revenue by site and period.
- Calculate lost revenue by device and period.
- Show pending exclusion exposure so asset managers can see the value still awaiting decision.
- Add export packs for commercial review, including gross-to-net bridge, exclusions, discrepancies, lost MWh, lost revenue, and audit trail.
- Agree the price source or price assumption used for lost revenue.

Beginner checkpoint:

- You can explain the difference between availability percentage, lost MWh, and lost revenue.
- You know which price assumption or revenue source is being used.
- You can identify whether a commercial impact number is final or still affected by pending exclusions.

## Phase 6: GitHub Workflow

Goal: make changes safely and keep a clean project history.

- Install Git if PowerShell cannot find it.
- Create or connect the GitHub repository.
- Use branches for changes.
- Commit small, understandable chunks of work.
- Push changes to GitHub.
- Use pull requests for review when others are involved.

Beginner checkpoint:

- You can run `git status`.
- You know the difference between commit and push.
- You understand that GitHub stores code, not passwords or local database files.

## Phase 7: Deployment

Goal: deploy the dashboard in a repeatable way.

- Decide the hosting target for the Streamlit app.
- Add deployment secrets for Snowflake if the host runs the sync step.
- Decide whether SQLite is generated during deployment or uploaded through a controlled process.
- Add basic automated checks.
- Document release steps.

Beginner checkpoint:

- You can rebuild the dashboard from GitHub instructions.
- You can identify where each secret is stored.
- You know how to roll back to a previous working version.

## Current Next Actions

1. Confirm the event tracker export format and required fields.
2. Add tracker import and approval-state handling to the Commercial / O&M module.
3. Change net availability so only approved exclusions are applied.
4. Add lost MWh calculations using MW capacity and interval duration.
5. Agree the first revenue price assumption or source for lost revenue.
6. Extend the export pack with tracker requests, approved exclusions, lost MWh, lost revenue, and audit lineage.
7. Confirm whether the dashboard will be hosted on Streamlit Community Cloud, an internal server, or another company-approved platform.
