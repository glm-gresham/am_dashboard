# Availability Commercial Workflow Design

## Purpose

The AM Dashboard should become the internal availability calculation and commercial review layer for BESS assets. It should not replace contractor systems. Contractors will continue to use an external event tracker, while asset managers use the dashboard to import raw availability, review exclusion requests, calculate net availability, and understand commercial impact.

## Operating Model

The future workflow is:

1. Raw availability figures are downloaded from the relevant SCADA for each site.
2. Asset managers upload the raw availability files into the AM Dashboard.
3. Contractors submit exclusion requests in an external event tracker. Today this is a shared XLSX file used by the owner and contractors.
4. Asset managers import tracker XLSX exports into the AM Dashboard.
5. The dashboard shows exclusion requests by approval state.
6. Only approved requests become exclusions for net availability.
7. Asset managers run the net availability calculation.
8. The dashboard reports availability, lost MWh, and audit outputs. Lost revenue is a Stage 2 output.

This keeps contractor access outside the AM Dashboard while making the internal commercial position traceable and repeatable.

## Source Systems

### Raw Availability

Raw availability comes from site SCADA exports. The current implementation supports manual upload of CSV and Excel files. In future, this can be automated through SCADA APIs, Snowflake ingestion, or a governed file drop.

Raw availability records should resolve to:

- `timestamp`
- `site_id` or `asset_id`
- `asset_name`
- `availability_pct`
- `affected_device` when available
- `device_granularity` when available
- `mw`
- static asset metadata such as O&M provider, PCS OEM, ESS OEM, and capacity

### External Event Tracker

The event tracker remains external because contractors should not access the AM Dashboard. The current source is a shared XLSX file used by the owner and contractors. The dashboard should consume that XLSX export first, then later consume records from the polished online event tracker when it is available.

The Stage 1 XLSX tracker columns are:

| XLSX column | Normalised field | Notes |
| --- | --- | --- |
| `event ID` | `event_id` | Treat as text so leading zeros are preserved. |
| `site name` | `asset_name` | Match to static asset metadata. |
| `type1` | `event_type_1` | Current high-level tracker category. |
| `type2` | `event_type_2` | Current subtype or event description. |
| `device type` | `device_granularity` | Examples include `PCS`, `batteries`, `transformer`, and `PCS-module`. |
| `device name` | `affected_device` | Preserve as text. |
| `status` | `tracker_status` | Event lifecycle status such as `open`, `ongoing`, or `closed`. This is not approval status. |
| `start date` | `start_timestamp` | Current format is day-month-year. |
| `end date` | `end_timestamp` | Can be blank for open or ongoing events. |

Stage 2 should add:

- `severity`
- `assigned_to`

These two fields belong to the related event tracker project and should be added to the AM Dashboard import once that tracker has them.

Tracker records should resolve to:

- `event_id`
- `site_id` or `asset_id`
- `asset_name`
- `event_type_1`
- `event_type_2`
- `affected_device`
- `device_granularity`
- `tracker_status`
- `start_timestamp`
- `end_timestamp`
- `request_reason`, derived from the type fields when no separate reason exists
- `contractor_comment`
- `requested_by`
- `request_timestamp`
- `approval_status`
- `approved_by`
- `approval_timestamp`
- `internal_comment`

## Approval Model

Not every contractor request becomes an exclusion.

Supported approval states should be:

- `Pending`
- `Approved`
- `Rejected`
- `Needs clarification`

Only `Approved` records flow into the exclusion register used by the net availability calculation. Pending, rejected, and clarification-needed records remain visible for workflow management and audit, but they do not change final availability. For the first implementation, asset managers should record approval decisions inside the AM Dashboard after importing the external tracker data.

The current XLSX `status` column should not be used as approval status. It describes the event lifecycle, such as open, ongoing, or closed. Imported tracker rows should default to an internal approval state such as `Pending` until the asset manager reviews them.

## Calculation Flow

The core calculation flow is:

```text
Raw availability -> approved exclusions -> net availability -> discrepancy events -> commercial impact
```

Gross availability is calculated from raw SCADA availability before exclusions. Net availability is calculated after removing intervals covered by approved exclusions. Future contract-specific methods can add more detailed adjustment rules if required. Each calculation run should retain enough lineage to show which raw files, tracker records, approvals, and calculation version produced the result.

## Outputs

The dashboard should provide:

- Gross vs net availability by site and period
- Gross vs net availability by device and period when device-level data is available
- Lost MWh by site and period
- Lost MWh by device and period
- Lost revenue by site and period as a Stage 2 feature
- Lost revenue by device and period as a Stage 2 feature
- Pending exclusion exposure, showing the impact still awaiting decision
- Exclusion register
- Discrepancy events
- Export pack for commercial review
- Audit trail for calculation runs

## Commercial Impact Method

Lost MWh should be calculated from the availability shortfall, asset or device MW capacity, and interval duration. Lost revenue should remain a Stage 2 feature. It should be added only after the lost MWh method is agreed and a price source or price assumption has been approved.

## Data Storage

The local SQLite repository should be extended to store:

- raw availability upload batches
- raw availability intervals
- event tracker imports
- exclusion requests
- approved exclusions
- tracker lifecycle status separately from internal approval status
- availability calculation runs
- gross and net availability outputs
- lost MWh outputs
- lost revenue outputs in Stage 2
- export packs
- audit trail records

Snowflake can later become the governed source for these tables, with SQLite remaining the local development and dashboard-ready repository.

## UI Shape

The Commercial / O&M Contract Management area should evolve into a workflow-oriented module:

- Upload raw availability files
- Import event tracker XLSX records
- Review request status and approval decisions
- Run net availability calculation
- Inspect gross-to-net bridge
- Inspect lost MWh
- Inspect lost revenue in Stage 2
- Download export pack

The Portfolio Availability and Asset Detail tabs should consume the calculated outputs once they are available, while keeping the current raw availability visuals for operational monitoring.

## Implementation Notes

The current manual upload workbench is a good first foundation. The next implementation should add current XLSX tracker import and approval-state handling before expanding the commercial impact views. The parser should preserve `event ID`, `site name`, `type1`, `type2`, `device type`, `device name`, `status`, `start date`, and `end date`. Applying every uploaded exclusion row should be replaced with explicit filtering so only approved requests affect net availability. Lost revenue should be left for Stage 2.

## Open Decisions

- Parser tolerance for the current XLSX tracker, including sheet name, blank rows, date formats, and optional columns.
- Stage 2 revenue price source for lost revenue calculations.
- Commercial baseline for lost MWh, such as shortfall from 100% technical availability or shortfall from a contractual threshold.
- Whether device-level capacity should come from SCADA exports, static metadata, or a new equipment register.
- Whether calculation outputs should be persisted immediately in SQLite or initially generated as session outputs.
- Exact timing for Stage 2 tracker fields `severity` and `assigned_to`, dependent on the event tracker project.
