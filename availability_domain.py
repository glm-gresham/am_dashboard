from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

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
