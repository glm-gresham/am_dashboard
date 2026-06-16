# AM Dashboard Project Roadmap

This roadmap is written for a non-developer project owner who wants to learn the process while building a production-quality dashboard.

## Target Architecture

The dashboard should use this data flow:

1. Snowflake stores the governed source data.
2. A controlled sync step pulls the required dashboard data from Snowflake.
3. The sync step writes the final dashboard-ready dataset into a local SQLite repository.
4. The Streamlit user interface reads from SQLite only.
5. GitHub stores the project code, documentation, and deployment workflow.

This keeps the user interface simple and testable. It also means the app can be run locally with sample data before any production credentials are involved.

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

## Phase 4: GitHub Workflow

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

## Phase 5: Deployment

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

1. Build and test the SQLite repository locally with sample data.
2. Confirm the real Snowflake table or view name.
3. Confirm whether the dashboard will be hosted on Streamlit Community Cloud, an internal server, or another company-approved platform.
4. Install Git so the project can be versioned and pushed to GitHub.
5. Move any local-only assets, such as logos, into a repo-safe `assets/` folder.
