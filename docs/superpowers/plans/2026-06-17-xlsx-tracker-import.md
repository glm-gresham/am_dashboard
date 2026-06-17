# XLSX Tracker Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Stage 1 import support for the current shared XLSX event tracker and make net availability apply only internally approved exclusions.

**Architecture:** Keep tracker parsing and exclusion conversion in `availability_domain.py`, next to the existing raw/exclusion upload functions. Keep Streamlit UI changes small by adding a tracker uploader to the existing Final Availability Workbench and showing tracker rows separately from approved exclusions.

**Tech Stack:** Python, pandas, openpyxl, Streamlit, standard-library `unittest`.

---

### Task 1: Tracker Parser And Exclusion Approval Rules

**Files:**
- Create: `tests/test_availability_domain.py`
- Modify: `availability_domain.py`

- [x] **Step 1: Write failing parser and approval tests**

Create tests that build an in-memory XLSX tracker with columns `event ID`, `site name`, `type1`, `type2`, `device type`, `device name`, `status`, `start date`, `end date`, `approval_status`, and verify:
- event IDs keep leading zeros
- tracker `status` maps to `tracker_status`
- blank end dates are allowed for tracker visibility
- only `approval_status == Approved` rows become applied exclusions
- rejected/open tracker rows remain visible but do not affect final availability

- [x] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_availability_domain -v`

Expected: tests fail because tracker parsing helpers do not exist and current final availability applies every exclusion row.

- [x] **Step 3: Implement tracker parsing**

Add:
- `TRACKER_COLUMN_ALIASES`
- `parse_uploaded_event_tracker(file, raw_availability)`
- `approved_exclusions_from_tracker(tracker_records)`
- helper functions for tracker dates and approval normalization

Parser output should include:
- `event_id`
- `asset_id`
- `asset_name`
- `event_type_1`
- `event_type_2`
- `device_granularity`
- `affected_device`
- `tracker_status`
- `start_timestamp`
- `end_timestamp`
- `approval_status`
- `exclusion_reason`

- [x] **Step 4: Implement approved-only availability application**

Update `calculate_final_availability` so it applies only exclusions whose `approval_status` is blank/missing or normalized to `Approved`. This preserves compatibility with the older manual exclusion register while allowing tracker imports to protect pending/rejected requests.

- [x] **Step 5: Run tests and verify GREEN**

Run: `python -m unittest tests.test_availability_domain -v`

Expected: all tests pass.

### Task 2: Streamlit Workbench Wiring

**Files:**
- Modify: `app.py`

- [x] **Step 1: Add tracker upload UI**

Import `parse_uploaded_event_tracker` and `approved_exclusions_from_tracker`. Add a file uploader labeled `Event tracker XLSX` in the Final Availability Workbench.

- [x] **Step 2: Merge approved tracker exclusions**

After raw availability is parsed, parse the tracker upload. Convert approved tracker rows into exclusions and concatenate them with any uploaded exclusions register.

- [x] **Step 3: Show tracker request table**

Show an `Event Tracker Requests` table with tracker lifecycle status and internal approval status. Do not hide pending/rejected rows.

- [x] **Step 4: Verify app import and workflow**

Run:
- `python -m unittest tests.test_availability_domain -v`
- `python -c "import app; print('app import ok')"`
- Streamlit health endpoint check

Expected: tests pass, app imports, health endpoint returns `ok`.

### Task 3: Documentation And Commit

**Files:**
- Modify: `PROJECT_ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-06-17-availability-commercial-workflow-design.md`

- [x] **Step 1: Mark tracker import as started**

Update the roadmap tracker to mark `XLSX event tracker import` as `Started`.

- [x] **Step 2: Verify and commit**

Run:
- `git diff --check`
- `git status --short`

Commit message: `Add XLSX event tracker import workflow`.
