from __future__ import annotations

from io import BytesIO
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from asset_metadata import normalize_site_name
from raw_availability_data import (
    BESS_COLUMN,
    RAW_SHEET_NAME,
    _component_columns,
    _site_availability_source_columns,
    _site_level_interval_availability,
)
from raw_availability_data import SITE_LEVEL
from sqlite_repository import default_sqlite_path


DEFAULT_CONTRACT_THRESHOLD_PCT = 95.0
SEED_ASSET_NAMES = ("Arbroath", "Coupar")

DOMAIN_TABLES = (
    ("availability_contracts", "Contracts"),
    ("contract_thresholds", "Thresholds"),
    ("source_documents", "Source documents"),
    ("availability_runs", "Availability runs"),
    ("daily_availability", "Daily availability"),
    ("monthly_availability", "Monthly availability"),
    ("availability_exclusions", "Exclusions"),
    ("discrepancy_events", "Discrepancy events"),
    ("export_packs", "Export packs"),
    ("audit_trail_entries", "Audit trail"),
)

EXPORT_PACK_TYPES = (
    "Contract Position",
    "Projection Scenarios",
    "Daily/Monthly Breakdown",
    "Raw-to-Net Bridge",
    "Discrepancy Events",
    "Exclusions Register",
    "Audit Trail",
)

RAW_UPLOAD_TEMPLATE_COLUMNS = (
    "timestamp",
    "asset_name",
    "availability_pct",
    "mw",
)
EXCLUSIONS_TEMPLATE_COLUMNS = (
    "asset_name",
    "start_timestamp",
    "end_timestamp",
    "category",
    "reason",
    "status",
)

RAW_COLUMN_ALIASES = {
    "timestamp": "timestamp",
    "time": "timestamp",
    "datetime": "timestamp",
    "date_time": "timestamp",
    "date/time": "timestamp",
    "asset": "asset_name",
    "asset_name": "asset_name",
    "asset name": "asset_name",
    "site": "asset_name",
    "site_name": "asset_name",
    "site name": "asset_name",
    "asset_id": "asset_id",
    "asset id": "asset_id",
    "site_id": "asset_id",
    "site id": "asset_id",
    "availability": "availability_pct",
    "availability_pct": "availability_pct",
    "availability pct": "availability_pct",
    "availability_%": "availability_pct",
    "availability (%)": "availability_pct",
    "bess availability (%) [bess]": "availability_pct",
    "mw": "mw",
    "capacity_mw": "mw",
    "capacity mw": "mw",
    "capacity\n(mw)": "mw",
}

EXCLUSION_COLUMN_ALIASES = {
    "asset": "asset_name",
    "asset_name": "asset_name",
    "asset name": "asset_name",
    "site": "asset_name",
    "site_name": "asset_name",
    "site name": "asset_name",
    "asset_id": "asset_id",
    "asset id": "asset_id",
    "site_id": "asset_id",
    "site id": "asset_id",
    "start": "start_timestamp",
    "start_timestamp": "start_timestamp",
    "start timestamp": "start_timestamp",
    "start_time": "start_timestamp",
    "start time": "start_timestamp",
    "start_date": "start_timestamp",
    "start date": "start_timestamp",
    "end": "end_timestamp",
    "end_timestamp": "end_timestamp",
    "end timestamp": "end_timestamp",
    "end_time": "end_timestamp",
    "end time": "end_timestamp",
    "end_date": "end_timestamp",
    "end date": "end_timestamp",
    "category": "category",
    "reason": "reason",
    "description": "reason",
    "status": "status",
    "approval_status": "approval_status",
    "approval status": "approval_status",
}

TRACKER_COLUMN_ALIASES = {
    "event id": "event_id",
    "event_id": "event_id",
    "eventid": "event_id",
    "site name": "asset_name",
    "site_name": "asset_name",
    "site": "asset_name",
    "asset name": "asset_name",
    "asset_name": "asset_name",
    "type1": "event_type_1",
    "type 1": "event_type_1",
    "type_1": "event_type_1",
    "type2": "event_type_2",
    "type 2": "event_type_2",
    "type_2": "event_type_2",
    "device type": "device_granularity",
    "device_type": "device_granularity",
    "device name": "affected_device",
    "device_name": "affected_device",
    "affected device": "affected_device",
    "affected_device": "affected_device",
    "status": "tracker_status",
    "tracker status": "tracker_status",
    "tracker_status": "tracker_status",
    "start date": "start_timestamp",
    "start_date": "start_timestamp",
    "start": "start_timestamp",
    "end date": "end_timestamp",
    "end_date": "end_timestamp",
    "end": "end_timestamp",
    "approval_status": "approval_status",
    "approval status": "approval_status",
    "approval": "approval_status",
    "severity": "severity",
    "assigned_to": "assigned_to",
    "assigned to": "assigned_to",
}

AVAILABILITY_DOMAIN_SCHEMA_SQL = """
create table if not exists availability_contracts (
    contract_id text primary key,
    asset_id text not null,
    asset_name text not null,
    counterparty text,
    om_provider text,
    contract_year integer,
    availability_threshold_pct real not null default 95.0,
    ld_clause_summary text,
    status text not null default 'draft',
    effective_from text,
    effective_to text,
    created_at text not null default current_timestamp
);

create table if not exists contract_thresholds (
    threshold_id text primary key,
    contract_id text not null,
    threshold_name text not null,
    threshold_pct real not null,
    calculation_basis text not null,
    consequence text,
    source_reference text,
    foreign key (contract_id) references availability_contracts(contract_id)
);

create table if not exists source_documents (
    document_id text primary key,
    asset_id text,
    document_type text not null,
    file_name text not null,
    source_path text,
    source_hash text,
    extracted_at text,
    status text not null default 'pending'
);

create table if not exists availability_runs (
    run_id text primary key,
    asset_id text not null,
    source_document_id text,
    run_type text not null,
    period_start text not null,
    period_end text not null,
    calculation_version text not null,
    status text not null default 'draft',
    created_at text not null default current_timestamp,
    foreign key (source_document_id) references source_documents(document_id)
);

create table if not exists daily_availability (
    daily_availability_id text primary key,
    run_id text not null,
    asset_id text not null,
    date text not null,
    gross_availability_pct real,
    net_availability_pct real,
    excluded_mwh real default 0,
    source_row_count integer,
    unique (run_id, asset_id, date),
    foreign key (run_id) references availability_runs(run_id)
);

create table if not exists monthly_availability (
    monthly_availability_id text primary key,
    run_id text not null,
    asset_id text not null,
    month text not null,
    gross_availability_pct real,
    net_availability_pct real,
    excluded_mwh real default 0,
    source_day_count integer,
    unique (run_id, asset_id, month),
    foreign key (run_id) references availability_runs(run_id)
);

create table if not exists availability_exclusions (
    exclusion_id text primary key,
    run_id text,
    asset_id text not null,
    start_timestamp text not null,
    end_timestamp text not null,
    category text,
    reason text,
    availability_impact_pct real,
    source_reference text,
    status text not null default 'draft',
    foreign key (run_id) references availability_runs(run_id)
);

create table if not exists discrepancy_events (
    discrepancy_event_id text primary key,
    run_id text,
    asset_id text not null,
    event_start text not null,
    event_end text not null,
    threshold_pct real not null,
    observed_availability_pct real,
    availability_impact_mw_days real,
    status text not null default 'open',
    notes text,
    foreign key (run_id) references availability_runs(run_id)
);

create table if not exists export_packs (
    export_pack_id text primary key,
    run_id text,
    asset_id text,
    pack_type text not null,
    generated_at text,
    file_path text,
    status text not null default 'draft',
    foreign key (run_id) references availability_runs(run_id)
);

create table if not exists audit_trail_entries (
    audit_id text primary key,
    entity_type text not null,
    entity_id text not null,
    action text not null,
    actor text,
    occurred_at text not null default current_timestamp,
    details text
);
"""


def ensure_availability_domain_schema(database_path: str | Path | None = None) -> Path:
    path = _resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.executescript(AVAILABILITY_DOMAIN_SCHEMA_SQL)

    return path


def availability_domain_schema_inventory() -> pd.DataFrame:
    return pd.DataFrame(
        {"entity": entity, "table_name": table_name, "status": "Defined", "rows": pd.NA}
        for table_name, entity in DOMAIN_TABLES
    )


def availability_domain_table_inventory(
    database_path: str | Path | None = None,
    *,
    initialise: bool = False,
) -> pd.DataFrame:
    path = ensure_availability_domain_schema(database_path) if initialise else _resolve_database_path(database_path)
    if not path.exists():
        return availability_domain_schema_inventory()

    rows: list[dict[str, object]] = []

    try:
        with sqlite3.connect(path) as connection:
            for table_name, entity in DOMAIN_TABLES:
                exists = connection.execute(
                    "select 1 from sqlite_master where type = 'table' and name = ?",
                    (table_name,),
                ).fetchone()
                count = connection.execute(f"select count(*) from {table_name}").fetchone()[0] if exists else pd.NA
                rows.append(
                    {
                        "entity": entity,
                        "table_name": table_name,
                        "status": "Ready" if exists else "Defined",
                        "rows": count,
                    }
                )
    except sqlite3.Error:
        return availability_domain_schema_inventory()

    return pd.DataFrame(rows)


def raw_upload_template() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": "2026-03-01 00:10",
                "asset_name": "Coupar",
                "availability_pct": 99.7,
                "mw": 40,
            }
        ],
        columns=RAW_UPLOAD_TEMPLATE_COLUMNS,
    )


def exclusions_template() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_name": "Coupar",
                "start_timestamp": "2026-03-05 00:00",
                "end_timestamp": "2026-03-05 23:59",
                "category": "Contractual exclusion",
                "reason": "Example accepted outage exclusion",
                "status": "Approved",
            }
        ],
        columns=EXCLUSIONS_TEMPLATE_COLUMNS,
    )


def template_csv_bytes(template: pd.DataFrame) -> bytes:
    return template.to_csv(index=False).encode("utf-8")


def parse_uploaded_raw_availability(files: list[object], asset_reference: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    messages: list[str] = []

    for file in files:
        file_name = getattr(file, "name", "uploaded_availability")
        file_bytes = _uploaded_file_bytes(file)
        try:
            parsed = _parse_single_raw_upload(file_name, file_bytes, asset_reference)
        except Exception as exc:  # noqa: BLE001 - convert parser failures into user-facing validation messages.
            messages.append(f"{file_name}: {exc}")
            continue

        if parsed.empty:
            messages.append(f"{file_name}: no usable availability rows found.")
            continue
        parsed["source_file"] = file_name
        frames.append(parsed)

    if not frames:
        return _empty_raw_upload_frame(), messages

    raw = pd.concat(frames, ignore_index=True)
    raw = raw.dropna(subset=["timestamp", "availability_pct"])
    raw["availability_pct"] = raw["availability_pct"].clip(lower=0, upper=100)
    return _enrich_uploaded_raw(raw, asset_reference).sort_values(["timestamp", "asset_name"]), messages


def parse_uploaded_exclusions(file: object | None, raw_availability: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if file is None:
        return _empty_exclusions_frame(), []

    file_name = getattr(file, "name", "uploaded_exclusions")
    messages: list[str] = []
    try:
        table = _read_uploaded_table(file_name, _uploaded_file_bytes(file))
    except Exception as exc:  # noqa: BLE001
        return _empty_exclusions_frame(), [f"{file_name}: {exc}"]

    table = _standardise_columns(table, EXCLUSION_COLUMN_ALIASES)
    required = {"start_timestamp", "end_timestamp"}
    missing = required.difference(table.columns)
    if missing:
        return _empty_exclusions_frame(), [f"{file_name}: missing required columns: {', '.join(sorted(missing))}."]

    if "asset_id" not in table.columns:
        table["asset_id"] = pd.NA
    if "asset_name" not in table.columns:
        table["asset_name"] = pd.NA
    for column in ["category", "reason", "status"]:
        if column not in table.columns:
            table[column] = "Uploaded"

    exclusions = table[["asset_id", "asset_name", "start_timestamp", "end_timestamp", "category", "reason", "status"]].copy()
    exclusions["start_timestamp"] = pd.to_datetime(exclusions["start_timestamp"], errors="coerce")
    exclusions["end_timestamp"] = exclusions["end_timestamp"].map(_inclusive_end_timestamp)
    exclusions["asset_id"] = exclusions["asset_id"].map(_clean_optional_text)
    exclusions["asset_name"] = exclusions["asset_name"].map(_clean_optional_text)
    exclusions["category"] = exclusions["category"].map(_clean_optional_text).replace("", "Uploaded exclusion")
    exclusions["reason"] = exclusions["reason"].map(_clean_optional_text).replace("", "No reason supplied")
    exclusions["status"] = exclusions["status"].map(_clean_optional_text).replace("", "Uploaded")
    exclusions = exclusions.dropna(subset=["start_timestamp", "end_timestamp"])
    exclusions = exclusions[exclusions["end_timestamp"] >= exclusions["start_timestamp"]].copy()

    if exclusions.empty:
        messages.append(f"{file_name}: no valid exclusion windows found.")
        return _empty_exclusions_frame(), messages

    exclusions = _enrich_uploaded_exclusions(exclusions, raw_availability)
    exclusions["exclusion_id"] = [
        f"EXC-{index + 1:04d}" for index in range(len(exclusions))
    ]
    return exclusions[_empty_exclusions_frame().columns], messages


def parse_uploaded_event_tracker(file: object | None, raw_availability: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if file is None:
        return _empty_tracker_frame(), []

    file_name = getattr(file, "name", "uploaded_event_tracker")
    try:
        table = _read_uploaded_table(file_name, _uploaded_file_bytes(file))
    except Exception as exc:  # noqa: BLE001
        return _empty_tracker_frame(), [f"{file_name}: {exc}"]

    table = _standardise_columns(table, TRACKER_COLUMN_ALIASES)
    required = {"event_id", "asset_name", "start_timestamp"}
    missing = required.difference(table.columns)
    if missing:
        return _empty_tracker_frame(), [f"{file_name}: missing required columns: {', '.join(sorted(missing))}."]

    for column in _empty_tracker_frame().columns:
        if column not in table.columns:
            table[column] = pd.NA

    tracker = table[_empty_tracker_frame().columns].copy()
    tracker["event_id"] = tracker["event_id"].map(_format_event_id)
    tracker["asset_id"] = tracker["asset_id"].map(_clean_optional_text)
    tracker["asset_name"] = tracker["asset_name"].map(_clean_optional_text)
    tracker["event_type_1"] = tracker["event_type_1"].map(_clean_optional_text)
    tracker["event_type_2"] = tracker["event_type_2"].map(_clean_optional_text)
    tracker["device_granularity"] = tracker["device_granularity"].map(_clean_optional_text)
    tracker["affected_device"] = tracker["affected_device"].map(_clean_optional_text)
    tracker["tracker_status"] = tracker["tracker_status"].map(_clean_optional_text)
    tracker["approval_status"] = tracker["approval_status"].map(_normalise_approval_status).replace("", "Pending")
    tracker["severity"] = tracker["severity"].map(_clean_optional_text)
    tracker["assigned_to"] = tracker["assigned_to"].map(_clean_optional_text)
    tracker["start_timestamp"] = tracker["start_timestamp"].map(_parse_tracker_start_timestamp)
    tracker["end_timestamp"] = tracker["end_timestamp"].map(_parse_tracker_end_timestamp)
    tracker["source_file"] = file_name
    tracker["exclusion_reason"] = tracker.apply(_tracker_exclusion_reason, axis=1)
    tracker = tracker.dropna(subset=["event_id", "asset_name", "start_timestamp"])

    if tracker.empty:
        return _empty_tracker_frame(), [f"{file_name}: no valid tracker rows found."]

    tracker = _enrich_uploaded_exclusions(tracker, raw_availability)
    return tracker[_empty_tracker_frame().columns], []


def approved_exclusions_from_tracker(
    tracker_records: pd.DataFrame,
    raw_availability: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "exclusion_id",
        "event_id",
        "asset_id",
        "asset_name",
        "affected_device",
        "device_granularity",
        "tracker_status",
        "approval_status",
        "start_timestamp",
        "end_timestamp",
        "category",
        "reason",
        "status",
    ]
    if tracker_records is None or tracker_records.empty:
        return pd.DataFrame(columns=columns)

    tracker = tracker_records.copy()
    tracker["approval_status"] = tracker.get("approval_status", pd.Series(index=tracker.index, dtype="object")).map(
        _normalise_approval_status
    )
    approved = tracker[tracker["approval_status"].eq("Approved")].copy()
    if approved.empty:
        return pd.DataFrame(columns=columns)

    approved["end_timestamp"] = _fill_open_tracker_end_dates(approved, raw_availability)
    approved = approved.dropna(subset=["start_timestamp", "end_timestamp"])
    approved = approved[approved["end_timestamp"] >= approved["start_timestamp"]].copy()
    if approved.empty:
        return pd.DataFrame(columns=columns)

    approved["exclusion_id"] = approved["event_id"].map(lambda value: f"TRK-{value}")
    approved["category"] = approved["event_type_1"].replace("", "Tracker event")
    approved["reason"] = approved["exclusion_reason"].replace("", "Approved tracker exclusion")
    approved["status"] = approved["approval_status"]
    return approved[columns].reset_index(drop=True)


def calculate_final_availability(
    raw_availability: pd.DataFrame,
    exclusions: pd.DataFrame,
    threshold_pct: float = DEFAULT_CONTRACT_THRESHOLD_PCT,
) -> dict[str, pd.DataFrame]:
    raw = raw_availability.copy()
    if raw.empty:
        return _empty_final_availability_result(threshold_pct)

    raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce")
    raw["availability_pct"] = pd.to_numeric(raw["availability_pct"], errors="coerce")
    raw["mw"] = pd.to_numeric(raw["mw"], errors="coerce")
    raw = raw.dropna(subset=["timestamp", "availability_pct"])
    raw["excluded"] = False
    raw["exclusion_reason"] = ""
    raw["exclusion_category"] = ""

    exclusions = exclusions.copy() if exclusions is not None else _empty_exclusions_frame()
    if not exclusions.empty:
        exclusions["start_timestamp"] = pd.to_datetime(exclusions["start_timestamp"], errors="coerce")
        exclusions["end_timestamp"] = pd.to_datetime(exclusions["end_timestamp"], errors="coerce")
        exclusions = exclusions.dropna(subset=["start_timestamp", "end_timestamp"])
        if "approval_status" in exclusions.columns:
            approval_status = exclusions["approval_status"].map(_normalise_approval_status)
            exclusions = exclusions[approval_status.eq("Approved") | approval_status.eq("")].copy()
        for exclusion in exclusions.itertuples(index=False):
            mask = _exclusion_mask(raw, exclusion)
            raw.loc[mask, "excluded"] = True
            raw.loc[mask, "exclusion_reason"] = getattr(exclusion, "reason", "")
            raw.loc[mask, "exclusion_category"] = getattr(exclusion, "category", "")

    raw["date"] = raw["timestamp"].dt.floor("D")
    raw["month"] = raw["timestamp"].dt.to_period("M").astype(str)
    raw["retained_availability_pct"] = raw["availability_pct"].where(~raw["excluded"])

    daily = _availability_breakdown(raw, ["asset_id", "asset_name", "date"])
    monthly = _availability_breakdown(raw, ["asset_id", "asset_name", "month"])
    contract_position = _contract_position(raw)
    discrepancy_events = _final_discrepancy_events(daily, threshold_pct)
    audit_trail = _final_availability_audit(raw, exclusions, threshold_pct)

    return {
        "contract_position": contract_position,
        "daily_breakdown": daily,
        "monthly_breakdown": monthly,
        "raw_to_net_bridge": raw[
            [
                "timestamp",
                "asset_id",
                "asset_name",
                "availability_pct",
                "retained_availability_pct",
                "excluded",
                "exclusion_category",
                "exclusion_reason",
                "source_file",
            ]
        ].rename(
            columns={
                "availability_pct": "gross_availability_pct",
                "retained_availability_pct": "net_availability_pct",
            }
        ),
        "exclusions_register": exclusions,
        "discrepancy_events": discrepancy_events,
        "audit_trail": audit_trail,
    }


def export_final_availability_pack(result: dict[str, pd.DataFrame]) -> bytes:
    sheet_order = [
        ("Contract Position", "contract_position"),
        ("Projection Scenarios", "projection_scenarios"),
        ("Daily Breakdown", "daily_breakdown"),
        ("Monthly Breakdown", "monthly_breakdown"),
        ("Raw To Net Bridge", "raw_to_net_bridge"),
        ("Tracker Requests", "tracker_requests"),
        ("Discrepancy Events", "discrepancy_events"),
        ("Exclusions Register", "exclusions_register"),
        ("Audit Trail", "audit_trail"),
    ]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, key in sheet_order:
            frame = result.get(key, pd.DataFrame())
            if key == "projection_scenarios" and (frame is None or frame.empty):
                frame = _projection_scenarios(result.get("contract_position", pd.DataFrame()))
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            worksheet = writer.sheets[sheet_name[:31]]
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 42)
    output.seek(0)
    return output.getvalue()


def build_contract_seed_view(availability: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "asset_name",
        "mw",
        "om_provider",
        "pcs_oem",
        "ess_oem",
        "contract_year",
        "availability_threshold_pct",
        "status",
    ]
    if availability.empty:
        return pd.DataFrame(columns=columns)

    contracts = (
        availability.dropna(subset=["asset_id", "asset_name"])
        .groupby(["asset_id", "asset_name"], as_index=False)
        .agg(
            mw=("mw", "max"),
            om_provider=("om_provider", _first_non_empty),
            pcs_oem=("pcs_oem", _first_non_empty),
            ess_oem=("ess_oem", _first_non_empty),
        )
        .sort_values("asset_name")
    )
    contracts = _prefer_seed_assets(contracts)
    contracts["contract_year"] = 2026
    contracts["availability_threshold_pct"] = DEFAULT_CONTRACT_THRESHOLD_PCT
    contracts["status"] = "Seeded from availability data"
    return contracts[columns]


def build_monthly_availability_seed(component_daily: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    daily = _site_level_seed_daily(component_daily, availability)
    if daily.empty:
        return pd.DataFrame(
            columns=["asset_name", "month", "availability_pct", "lowest_day_pct", "observed_days", "mw"]
        )

    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    monthly = (
        daily.groupby(["asset_id", "asset_name", "month"], as_index=False)
        .agg(
            availability_pct=("availability_pct", "mean"),
            lowest_day_pct=("availability_pct", "min"),
            observed_days=("date", "nunique"),
            mw=("mw", "max"),
        )
        .sort_values(["asset_name", "month"])
    )
    return monthly[["asset_name", "month", "availability_pct", "lowest_day_pct", "observed_days", "mw"]]


def build_discrepancy_events(
    component_daily: pd.DataFrame,
    availability: pd.DataFrame,
    threshold_pct: float = DEFAULT_CONTRACT_THRESHOLD_PCT,
) -> pd.DataFrame:
    columns = [
        "event_id",
        "asset_name",
        "start_date",
        "end_date",
        "duration_days",
        "threshold_pct",
        "mean_availability_pct",
        "lowest_availability_pct",
        "availability_impact_mw_days",
        "status",
    ]
    daily = _site_level_seed_daily(component_daily, availability)
    if daily.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for (asset_id, asset_name), series in daily.groupby(["asset_id", "asset_name"], sort=False):
        series = series.sort_values("date").reset_index(drop=True)
        below_threshold = series["availability_pct"] < threshold_pct
        start_index: int | None = None

        for index, is_below in enumerate(below_threshold.tolist() + [False]):
            if is_below and start_index is None:
                start_index = index
                continue

            if not is_below and start_index is not None:
                outage = series.iloc[start_index:index].copy()
                start_date = outage["date"].min()
                end_date = outage["date"].max()
                mw = float(outage["mw"].max()) if pd.notna(outage["mw"].max()) else 0.0
                impact = (((threshold_pct - outage["availability_pct"]).clip(lower=0) / 100.0) * mw).sum()
                rows.append(
                    {
                        "event_id": f"{asset_id}-{start_date:%Y%m%d}-{end_date:%Y%m%d}",
                        "asset_name": asset_name,
                        "start_date": start_date.date(),
                        "end_date": end_date.date(),
                        "duration_days": int(outage["date"].nunique()),
                        "threshold_pct": threshold_pct,
                        "mean_availability_pct": float(outage["availability_pct"].mean()),
                        "lowest_availability_pct": float(outage["availability_pct"].min()),
                        "availability_impact_mw_days": float(impact),
                        "status": "Review",
                    }
                )
                start_index = None

    return pd.DataFrame(rows, columns=columns).sort_values(
        ["availability_impact_mw_days", "duration_days"],
        ascending=[False, False],
        ignore_index=True,
    )


def build_export_pack_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pack_type": EXPORT_PACK_TYPES,
            "status": ["Skeleton"] * len(EXPORT_PACK_TYPES),
        }
    )


def _site_level_seed_daily(component_daily: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    columns = ["date", "asset_id", "asset_name", "availability_pct", "mw"]
    if component_daily.empty or availability.empty:
        return pd.DataFrame(columns=columns)

    site_daily = component_daily[component_daily["level"] == SITE_LEVEL].copy()
    if site_daily.empty:
        return pd.DataFrame(columns=columns)

    site_daily = _prefer_seed_assets(site_daily)
    available_assets = set(availability["asset_name"].dropna().astype(str))
    if available_assets:
        site_daily = site_daily[site_daily["asset_name"].isin(available_assets)]
    if "asset_id" not in site_daily.columns and "site_id" in site_daily.columns:
        site_daily["asset_id"] = site_daily["site_id"]
    mw_lookup = availability.groupby("asset_name")["mw"].max()
    site_daily["mw"] = site_daily["asset_name"].map(mw_lookup)
    site_daily["date"] = pd.to_datetime(site_daily["date"], errors="coerce")
    site_daily["availability_pct"] = pd.to_numeric(site_daily["availability_pct"], errors="coerce")
    site_daily = site_daily.dropna(subset=["date", "availability_pct"])
    return site_daily[columns].sort_values(["asset_name", "date"]).reset_index(drop=True)


def _parse_single_raw_upload(file_name: str, file_bytes: bytes, asset_reference: pd.DataFrame) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        table = pd.read_csv(BytesIO(file_bytes))
        return _normalise_simple_raw_upload(table, file_name)

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        excel = pd.ExcelFile(BytesIO(file_bytes))
        if RAW_SHEET_NAME in excel.sheet_names:
            return _parse_scada_workbook_upload(file_name, file_bytes)
        table = pd.read_excel(BytesIO(file_bytes), sheet_name=excel.sheet_names[0])
        return _normalise_simple_raw_upload(table, file_name)

    raise ValueError("unsupported file type. Upload CSV or XLSX files.")


def _empty_tracker_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_id",
            "asset_id",
            "asset_name",
            "event_type_1",
            "event_type_2",
            "device_granularity",
            "affected_device",
            "tracker_status",
            "start_timestamp",
            "end_timestamp",
            "approval_status",
            "severity",
            "assigned_to",
            "source_file",
            "exclusion_reason",
        ]
    )


def _format_event_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value)).zfill(3)
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value)).zfill(3)
    text = _clean_optional_text(value)
    if re.fullmatch(r"\d+", text):
        return text.zfill(3)
    return text


def _parse_tracker_start_timestamp(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", dayfirst=True)


def _parse_tracker_end_timestamp(value: object) -> pd.Timestamp:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return pd.NaT
    timestamp = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(timestamp):
        return pd.NaT
    raw_value = str(value).strip()
    if raw_value and not any(separator in raw_value for separator in [":", "T"]):
        return timestamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return timestamp


def _normalise_approval_status(value: object) -> str:
    text = _clean_optional_text(value)
    if text == "":
        return ""
    key = normalize_site_name(text)
    mapping = {
        "approved": "Approved",
        "approve": "Approved",
        "accepted": "Approved",
        "pending": "Pending",
        "open": "Pending",
        "rejected": "Rejected",
        "reject": "Rejected",
        "declined": "Rejected",
        "needs clarification": "Needs clarification",
        "needsclarification": "Needs clarification",
        "clarification": "Needs clarification",
    }
    return mapping.get(key, text[:1].upper() + text[1:])


def _tracker_exclusion_reason(row: pd.Series) -> str:
    parts = [
        _clean_optional_text(row.get("event_type_1", "")),
        _clean_optional_text(row.get("event_type_2", "")),
    ]
    reason = " - ".join(part for part in parts if part)
    affected_device = _clean_optional_text(row.get("affected_device", ""))
    if affected_device:
        return f"{reason} ({affected_device})" if reason else affected_device
    return reason


def _fill_open_tracker_end_dates(
    approved: pd.DataFrame,
    raw_availability: pd.DataFrame | None,
) -> pd.Series:
    ends = pd.to_datetime(approved["end_timestamp"], errors="coerce")
    if ends.notna().all():
        return ends

    if raw_availability is not None and not raw_availability.empty:
        max_raw_timestamp = pd.to_datetime(raw_availability["timestamp"], errors="coerce").max()
    else:
        max_raw_timestamp = pd.NaT

    fallback = approved["start_timestamp"].map(lambda value: pd.Timestamp(value).ceil("D") - pd.Timedelta(nanoseconds=1))
    if pd.notna(max_raw_timestamp):
        fallback = fallback.map(lambda value: max(value, max_raw_timestamp))
    return ends.fillna(fallback)


def _parse_scada_workbook_upload(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    site_id, asset_name = _uploaded_asset_from_file_name(file_name)
    header = pd.read_excel(BytesIO(file_bytes), sheet_name=RAW_SHEET_NAME, nrows=0, engine="openpyxl")
    component_columns = _component_columns(header.columns, site_id, asset_name)
    site_source_columns = _site_availability_source_columns(component_columns)

    if site_source_columns:
        wide = pd.read_excel(
            BytesIO(file_bytes),
            sheet_name=RAW_SHEET_NAME,
            usecols=["Timestamp", *site_source_columns],
            engine="openpyxl",
        )
        availability = _site_level_interval_availability(wide, component_columns)
        parsed = pd.DataFrame({"timestamp": wide["Timestamp"], "availability_pct": availability})
    elif BESS_COLUMN in header.columns:
        parsed = pd.read_excel(
            BytesIO(file_bytes),
            sheet_name=RAW_SHEET_NAME,
            usecols=["Timestamp", BESS_COLUMN],
            engine="openpyxl",
        ).rename(columns={"Timestamp": "timestamp", BESS_COLUMN: "availability_pct"})
    else:
        raise ValueError("could not find site-level, PCS/battery, or BESS availability columns.")

    parsed["asset_id"] = site_id
    parsed["asset_name"] = asset_name
    return parsed


def _normalise_simple_raw_upload(table: pd.DataFrame, file_name: str) -> pd.DataFrame:
    table = _standardise_columns(table, RAW_COLUMN_ALIASES)
    missing = {"timestamp", "availability_pct"}.difference(table.columns)
    if missing:
        raise ValueError(f"missing required columns: {', '.join(sorted(missing))}.")

    if "asset_id" not in table.columns:
        table["asset_id"] = pd.NA
    if "asset_name" not in table.columns:
        _, inferred_name = _uploaded_asset_from_file_name(file_name)
        table["asset_name"] = inferred_name
    if "mw" not in table.columns:
        table["mw"] = pd.NA

    parsed = table[["timestamp", "asset_id", "asset_name", "availability_pct", "mw"]].copy()
    parsed["timestamp"] = pd.to_datetime(parsed["timestamp"], errors="coerce")
    parsed["asset_id"] = parsed["asset_id"].map(_clean_optional_text)
    parsed["asset_name"] = parsed["asset_name"].map(_clean_optional_text)
    parsed["availability_pct"] = pd.to_numeric(parsed["availability_pct"], errors="coerce")
    parsed["mw"] = pd.to_numeric(parsed["mw"], errors="coerce")
    return parsed.dropna(subset=["timestamp", "availability_pct"])


def _read_uploaded_table(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(BytesIO(file_bytes))
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(BytesIO(file_bytes))
    raise ValueError("unsupported file type. Upload CSV or XLSX files.")


def _standardise_columns(table: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    rename: dict[object, str] = {}
    seen: set[str] = set()
    for column in table.columns:
        key = str(column).strip().lower().replace("-", "_")
        target = aliases.get(key, aliases.get(key.replace("_", " ")))
        if target and target not in seen:
            rename[column] = target
            seen.add(target)
    return table.rename(columns=rename)


def _enrich_uploaded_raw(raw: pd.DataFrame, asset_reference: pd.DataFrame) -> pd.DataFrame:
    enriched = raw.copy()
    reference = _asset_reference(asset_reference)
    if reference.empty:
        for column, default in [
            ("asset_id", ""),
            ("asset_name", "Uploaded asset"),
            ("mw", 1.0),
            ("om_provider", "Unknown"),
            ("pcs_oem", "Unknown"),
            ("ess_oem", "Unknown"),
        ]:
            if column not in enriched.columns:
                enriched[column] = default
        return enriched

    enriched["asset_id"] = enriched.get("asset_id", pd.Series(index=enriched.index, dtype="object")).map(_clean_optional_text)
    enriched["asset_name"] = enriched.get("asset_name", pd.Series(index=enriched.index, dtype="object")).map(_clean_optional_text)
    enriched["site_key"] = enriched["asset_name"].map(normalize_site_name)
    reference_by_id = reference.set_index("asset_id")
    reference_by_key = reference.set_index("site_key")

    for index, row in enriched.iterrows():
        match = None
        asset_id = row.get("asset_id", "")
        site_key = row.get("site_key", "")
        if asset_id and asset_id in reference_by_id.index:
            match = reference_by_id.loc[asset_id]
        elif site_key and site_key in reference_by_key.index:
            match = reference_by_key.loc[site_key]

        if match is not None:
            for column in ["asset_id", "asset_name", "mw", "om_provider", "pcs_oem", "ess_oem"]:
                if column not in enriched.columns or pd.isna(enriched.at[index, column]) or enriched.at[index, column] == "":
                    enriched.at[index, column] = match[column]

    fallback_names = (
        enriched["source_file"].map(lambda name: _uploaded_asset_from_file_name(str(name))[1])
        if "source_file" in enriched.columns
        else pd.Series(["Uploaded asset"] * len(enriched), index=enriched.index)
    )
    enriched["asset_name"] = enriched["asset_name"].replace("", pd.NA).fillna(fallback_names)
    enriched["asset_id"] = enriched["asset_id"].replace("", pd.NA).fillna(enriched["asset_name"].map(_asset_id_from_name))
    enriched["mw"] = pd.to_numeric(enriched.get("mw", 1.0), errors="coerce").fillna(1.0)
    for column in ["om_provider", "pcs_oem", "ess_oem"]:
        if column not in enriched.columns:
            enriched[column] = "Unknown"
        enriched[column] = enriched[column].replace("", pd.NA).fillna("Unknown")

    return enriched.drop(columns=["site_key"], errors="ignore")[
        [
            "timestamp",
            "asset_id",
            "asset_name",
            "availability_pct",
            "mw",
            "om_provider",
            "pcs_oem",
            "ess_oem",
            "source_file",
        ]
    ]


def _enrich_uploaded_exclusions(exclusions: pd.DataFrame, raw_availability: pd.DataFrame) -> pd.DataFrame:
    enriched = exclusions.copy()
    if raw_availability.empty:
        return enriched

    assets = raw_availability[["asset_id", "asset_name"]].drop_duplicates()
    assets["site_key"] = assets["asset_name"].map(normalize_site_name)
    by_id = assets.set_index("asset_id")
    by_key = assets.set_index("site_key")
    enriched["site_key"] = enriched["asset_name"].map(normalize_site_name)

    for index, row in enriched.iterrows():
        match = None
        if row.asset_id and row.asset_id in by_id.index:
            match = by_id.loc[row.asset_id]
        elif row.site_key and row.site_key in by_key.index:
            match = by_key.loc[row.site_key]
        if match is not None:
            enriched.at[index, "asset_id"] = match["asset_id"]
            enriched.at[index, "asset_name"] = match["asset_name"]

    return enriched.drop(columns=["site_key"], errors="ignore")


def _asset_reference(asset_reference: pd.DataFrame) -> pd.DataFrame:
    columns = ["asset_id", "asset_name", "mw", "om_provider", "pcs_oem", "ess_oem"]
    if asset_reference.empty or not set(["asset_id", "asset_name"]).issubset(asset_reference.columns):
        return pd.DataFrame(columns=[*columns, "site_key"])
    reference = asset_reference.copy()
    for column in columns:
        if column not in reference.columns:
            reference[column] = "Unknown" if column.endswith("oem") or column == "om_provider" else pd.NA
    reference = reference[columns].dropna(subset=["asset_id", "asset_name"]).drop_duplicates("asset_id")
    reference["site_key"] = reference["asset_name"].map(normalize_site_name)
    return reference


def _availability_breakdown(raw: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    breakdown = (
        raw.groupby(group_columns, dropna=False)
        .agg(
            gross_availability_pct=("availability_pct", "mean"),
            final_availability_pct=("retained_availability_pct", "mean"),
            observed_intervals=("availability_pct", "size"),
            excluded_intervals=("excluded", "sum"),
            mw=("mw", "max"),
        )
        .reset_index()
    )
    breakdown["retained_intervals"] = breakdown["observed_intervals"] - breakdown["excluded_intervals"]
    breakdown["excluded_days"] = np.nan
    breakdown["availability_delta_pct"] = breakdown["final_availability_pct"] - breakdown["gross_availability_pct"]
    return breakdown


def _contract_position(raw: pd.DataFrame) -> pd.DataFrame:
    summary = _availability_breakdown(raw, ["asset_id", "asset_name"])
    summary["period_start"] = raw.groupby(["asset_id", "asset_name"])["timestamp"].min().values
    summary["period_end"] = raw.groupby(["asset_id", "asset_name"])["timestamp"].max().values
    excluded_days = raw[raw["excluded"]].groupby(["asset_id", "asset_name"])["date"].nunique()
    summary["excluded_days"] = [
        int(excluded_days.get((row.asset_id, row.asset_name), 0)) for row in summary.itertuples(index=False)
    ]
    portfolio = _portfolio_contract_position(summary)
    return pd.concat([summary, portfolio], ignore_index=True) if not portfolio.empty else summary


def _portfolio_contract_position(summary: pd.DataFrame) -> pd.DataFrame:
    valid = summary.dropna(subset=["mw"])
    if valid.empty or valid["mw"].sum() == 0:
        return pd.DataFrame(columns=summary.columns)
    row = {
        "asset_id": "PORTFOLIO",
        "asset_name": "Portfolio",
        "gross_availability_pct": np.average(valid["gross_availability_pct"], weights=valid["mw"]),
        "final_availability_pct": np.average(valid["final_availability_pct"].fillna(valid["gross_availability_pct"]), weights=valid["mw"]),
        "observed_intervals": valid["observed_intervals"].sum(),
        "excluded_intervals": valid["excluded_intervals"].sum(),
        "mw": valid["mw"].sum(),
        "retained_intervals": valid["retained_intervals"].sum(),
        "excluded_days": valid["excluded_days"].sum(),
        "availability_delta_pct": np.average(valid["availability_delta_pct"].fillna(0), weights=valid["mw"]),
        "period_start": valid["period_start"].min(),
        "period_end": valid["period_end"].max(),
    }
    return pd.DataFrame([row], columns=summary.columns)


def _final_discrepancy_events(daily: pd.DataFrame, threshold_pct: float) -> pd.DataFrame:
    columns = [
        "event_id",
        "asset_id",
        "asset_name",
        "start_date",
        "end_date",
        "duration_days",
        "threshold_pct",
        "mean_final_availability_pct",
        "lowest_final_availability_pct",
        "availability_impact_mw_days",
        "status",
    ]
    if daily.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for (asset_id, asset_name), series in daily.groupby(["asset_id", "asset_name"], sort=False):
        if asset_id == "PORTFOLIO":
            continue
        series = series.sort_values("date").reset_index(drop=True)
        values = series["final_availability_pct"].fillna(series["gross_availability_pct"])
        below_threshold = values < threshold_pct
        start_index: int | None = None
        for index, is_below in enumerate(below_threshold.tolist() + [False]):
            if is_below and start_index is None:
                start_index = index
                continue
            if not is_below and start_index is not None:
                event = series.iloc[start_index:index].copy()
                event_values = values.iloc[start_index:index]
                impact = (((threshold_pct - event_values).clip(lower=0) / 100.0) * event["mw"].fillna(0)).sum()
                start_date = pd.Timestamp(event["date"].min())
                end_date = pd.Timestamp(event["date"].max())
                rows.append(
                    {
                        "event_id": f"{asset_id}-{start_date:%Y%m%d}-{end_date:%Y%m%d}",
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "start_date": start_date.date(),
                        "end_date": end_date.date(),
                        "duration_days": int(event["date"].nunique()),
                        "threshold_pct": threshold_pct,
                        "mean_final_availability_pct": float(event_values.mean()),
                        "lowest_final_availability_pct": float(event_values.min()),
                        "availability_impact_mw_days": float(impact),
                        "status": "Review",
                    }
                )
                start_index = None
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["availability_impact_mw_days", "duration_days"],
        ascending=[False, False],
        ignore_index=True,
    )


def _final_availability_audit(raw: pd.DataFrame, exclusions: pd.DataFrame, threshold_pct: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"item": "calculation_version", "value": "manual-upload-gross-to-net-v1"},
            {"item": "threshold_pct", "value": threshold_pct},
            {"item": "raw_rows", "value": len(raw)},
            {"item": "excluded_rows", "value": int(raw["excluded"].sum())},
            {"item": "exclusion_windows", "value": len(exclusions)},
            {"item": "period_start", "value": raw["timestamp"].min()},
            {"item": "period_end", "value": raw["timestamp"].max()},
        ]
    )


def _projection_scenarios(contract_position: pd.DataFrame) -> pd.DataFrame:
    if contract_position.empty:
        return pd.DataFrame(columns=["asset_name", "scenario", "future_availability_pct", "illustrative_final_pct"])
    rows: list[dict[str, object]] = []
    for row in contract_position.itertuples(index=False):
        for scenario in (99.0, 97.0, 95.0):
            final_value = row.final_availability_pct if pd.notna(row.final_availability_pct) else row.gross_availability_pct
            rows.append(
                {
                    "asset_name": row.asset_name,
                    "scenario": f"Future {scenario:.0f}%",
                    "future_availability_pct": scenario,
                    "illustrative_final_pct": final_value,
                }
            )
    return pd.DataFrame(rows)


def _exclusion_mask(raw: pd.DataFrame, exclusion: object) -> pd.Series:
    mask = (raw["timestamp"] >= exclusion.start_timestamp) & (raw["timestamp"] <= exclusion.end_timestamp)
    asset_id = getattr(exclusion, "asset_id", "")
    asset_name = getattr(exclusion, "asset_name", "")
    if asset_id:
        return mask & raw["asset_id"].eq(asset_id)
    if asset_name:
        return mask & raw["asset_name"].map(normalize_site_name).eq(normalize_site_name(asset_name))
    return mask


def _inclusive_end_timestamp(value: object) -> pd.Timestamp:
    raw_value = "" if value is None or pd.isna(value) else str(value).strip()
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return pd.NaT
    if raw_value and not any(separator in raw_value for separator in [":", "T"]):
        return timestamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return timestamp


def _uploaded_file_bytes(file: object) -> bytes:
    if hasattr(file, "getvalue"):
        return file.getvalue()
    if hasattr(file, "read"):
        data = file.read()
        if hasattr(file, "seek"):
            file.seek(0)
        return data
    raise ValueError("could not read uploaded file bytes.")


def _uploaded_asset_from_file_name(file_name: str) -> tuple[str, str]:
    stem = Path(file_name).stem
    lower = stem.lower()
    for suffix in ["_all_devices_availability", "_availability", "_raw_availability"]:
        if suffix in lower:
            stem = stem[: lower.index(suffix)]
            break
    stem = re.sub(r"[_-]+", " ", stem).strip() or "Uploaded asset"
    asset_name = stem.title()
    return _asset_id_from_name(asset_name), asset_name


def _asset_id_from_name(asset_name: object) -> str:
    cleaned = normalize_site_name(asset_name).upper()
    return re.sub(r"[^A-Z0-9]+", "_", cleaned).strip("_") or "UPLOADED_ASSET"


def _clean_optional_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _empty_raw_upload_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "timestamp",
            "asset_id",
            "asset_name",
            "availability_pct",
            "mw",
            "om_provider",
            "pcs_oem",
            "ess_oem",
            "source_file",
        ]
    )


def _empty_exclusions_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "exclusion_id",
            "asset_id",
            "asset_name",
            "start_timestamp",
            "end_timestamp",
            "category",
            "reason",
            "status",
        ]
    )


def _empty_final_availability_result(threshold_pct: float) -> dict[str, pd.DataFrame]:
    empty_position = pd.DataFrame(
        columns=[
            "asset_id",
            "asset_name",
            "gross_availability_pct",
            "final_availability_pct",
            "observed_intervals",
            "excluded_intervals",
            "retained_intervals",
            "excluded_days",
            "availability_delta_pct",
            "mw",
            "period_start",
            "period_end",
        ]
    )
    return {
        "contract_position": empty_position,
        "daily_breakdown": pd.DataFrame(),
        "monthly_breakdown": pd.DataFrame(),
        "raw_to_net_bridge": pd.DataFrame(),
        "exclusions_register": _empty_exclusions_frame(),
        "discrepancy_events": pd.DataFrame(),
        "audit_trail": pd.DataFrame([{"item": "threshold_pct", "value": threshold_pct}]),
    }


def _prefer_seed_assets(df: pd.DataFrame) -> pd.DataFrame:
    if "asset_name" not in df.columns:
        return df

    seed = df[df["asset_name"].isin(SEED_ASSET_NAMES)].copy()
    if seed.empty:
        return df.copy()
    return seed


def _first_non_empty(series: pd.Series) -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    return values.iloc[0] if not values.empty else "Unknown"


def _resolve_database_path(database_path: str | Path | None = None) -> Path:
    if database_path is None:
        return default_sqlite_path()
    return Path(database_path).expanduser()
