from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from availability_data import EXPECTED_COLUMNS, _normalise_frame


AVAILABILITY_TABLE = "availability_measurements"
METADATA_TABLE = "repository_metadata"
FALLBACK_DATABASE_PATH = Path("data/am_dashboard.sqlite")


SCHEMA_SQL = f"""
create table if not exists {AVAILABILITY_TABLE} (
    timestamp text not null,
    asset_id text not null,
    asset_name text not null,
    availability_pct real,
    mw real,
    om_provider text,
    pcs_oem text,
    ess_oem text,
    primary key (timestamp, asset_id)
);

create index if not exists idx_availability_timestamp
on {AVAILABILITY_TABLE} (timestamp);

create table if not exists {METADATA_TABLE} (
    key text primary key,
    value text not null
);
"""


def default_sqlite_path() -> Path:
    configured_path = os.getenv("AM_DASHBOARD_SQLITE_PATH")
    if configured_path:
        return Path(configured_path).expanduser()

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AM Dashboard" / "am_dashboard.sqlite"

    return FALLBACK_DATABASE_PATH


def initialise_repository(database_path: str | Path | None = None) -> Path:
    path = _resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)

    return path


def read_availability_from_sqlite(database_path: str | Path | None = None) -> pd.DataFrame:
    path = _resolve_database_path(database_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite repository does not exist: {path}")

    with sqlite3.connect(path) as connection:
        df = pd.read_sql_query(
            f"""
            select
                timestamp,
                asset_id,
                asset_name,
                availability_pct,
                mw,
                om_provider,
                pcs_oem,
                ess_oem
            from {AVAILABILITY_TABLE}
            order by timestamp, asset_name
            """,
            connection,
        )

    return _normalise_frame(df)


def replace_availability_data(
    df: pd.DataFrame,
    database_path: str | Path | None = None,
    *,
    source: str,
) -> Path:
    path = initialise_repository(database_path)
    normalised = _normalise_frame(df)
    to_write = normalised[list(EXPECTED_COLUMNS)].copy()
    to_write["timestamp"] = pd.to_datetime(to_write["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(path) as connection:
        connection.execute(f"delete from {AVAILABILITY_TABLE}")
        to_write.to_sql(AVAILABILITY_TABLE, connection, if_exists="append", index=False)
        _write_metadata(
            connection,
            {
                "last_sync_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "last_sync_source": source,
                "row_count": str(len(to_write)),
            },
        )

    return path


def repository_status(database_path: str | Path | None = None) -> dict[str, str]:
    path = _resolve_database_path(database_path)
    if not path.exists():
        return {"exists": "false", "path": str(path)}

    with sqlite3.connect(path) as connection:
        metadata = dict(connection.execute(f"select key, value from {METADATA_TABLE}").fetchall())
        row_count = connection.execute(f"select count(*) from {AVAILABILITY_TABLE}").fetchone()[0]

    return {
        "exists": "true",
        "path": str(path),
        "row_count": str(row_count),
        **metadata,
    }


def _write_metadata(connection: sqlite3.Connection, metadata: dict[str, str]) -> None:
    connection.executemany(
        f"""
        insert into {METADATA_TABLE} (key, value)
        values (?, ?)
        on conflict(key) do update set value = excluded.value
        """,
        metadata.items(),
    )


def _resolve_database_path(database_path: str | Path | None = None) -> Path:
    if database_path is None:
        return default_sqlite_path()

    return Path(database_path).expanduser()
