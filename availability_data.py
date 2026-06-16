from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd


ASSET_FILTERS = ("om_provider", "pcs_oem", "ess_oem")


@dataclass(frozen=True)
class Asset:
    asset_id: str
    asset_name: str
    mw: float
    om_provider: str
    pcs_oem: str
    ess_oem: str


ASSETS = (
    Asset("BESS-001", "Arden", 49.9, "O&M A", "PCS OEM A", "ESS OEM A"),
    Asset("BESS-002", "Brock", 57.0, "O&M A", "PCS OEM B", "ESS OEM A"),
    Asset("BESS-003", "Calder", 99.0, "O&M B", "PCS OEM B", "ESS OEM B"),
    Asset("BESS-004", "Dane", 100.0, "O&M B", "PCS OEM C", "ESS OEM B"),
    Asset("BESS-005", "Eden", 49.5, "O&M C", "PCS OEM A", "ESS OEM C"),
    Asset("BESS-006", "Fosse", 75.0, "O&M C", "PCS OEM C", "ESS OEM C"),
    Asset("BESS-007", "Glen", 150.0, "O&M D", "PCS OEM D", "ESS OEM B"),
    Asset("BESS-008", "Haven", 200.0, "O&M D", "PCS OEM B", "ESS OEM D"),
)


EXPECTED_COLUMNS = (
    "timestamp",
    "asset_id",
    "asset_name",
    "availability_pct",
    "mw",
    "om_provider",
    "pcs_oem",
    "ess_oem",
)


def weighted_availability(df: pd.DataFrame) -> float:
    if df.empty:
        return float("nan")

    valid = df.dropna(subset=["availability_pct", "mw"])
    if valid.empty or valid["mw"].sum() == 0:
        return float("nan")

    return float(np.average(valid["availability_pct"], weights=valid["mw"]))


def aggregate_daily_availability(df: pd.DataFrame) -> pd.DataFrame:
    working = (
        df.dropna(subset=["availability_pct", "mw"])
        .assign(
            date=df["timestamp"].dt.floor("D"),
            weighted_availability=df["availability_pct"] * df["mw"],
        )
    )
    daily = (
        working.groupby("date", as_index=False)
        .agg(weighted_availability=("weighted_availability", "sum"), mw_weight=("mw", "sum"))
        .sort_values("date")
    )
    daily["availability_pct"] = daily["weighted_availability"] / daily["mw_weight"]
    daily = daily[["date", "availability_pct"]]
    daily["ma_10d"] = daily["availability_pct"].rolling(window=10, min_periods=1).mean()
    return daily


def aggregate_asset_availability(df: pd.DataFrame) -> pd.DataFrame:
    working = df.dropna(subset=["availability_pct", "mw"]).assign(
        weighted_availability=df["availability_pct"] * df["mw"]
    )
    summary = (
        working.groupby(["asset_id", "asset_name", "om_provider", "pcs_oem", "ess_oem"], as_index=False)
        .agg(
            weighted_availability=("weighted_availability", "sum"),
            mw_weight=("mw", "sum"),
            mw=("mw", "max"),
        )
    )
    summary["availability_pct"] = summary["weighted_availability"] / summary["mw_weight"]
    summary = summary.drop(columns=["weighted_availability", "mw_weight"]).sort_values("availability_pct")
    return summary


def load_availability_data() -> tuple[pd.DataFrame, str]:
    raw_data = _load_from_raw_excels_if_available()
    if raw_data is not None:
        return raw_data, "Raw Excel"

    sqlite_data = _load_from_sqlite_repository_if_available()
    if sqlite_data is not None:
        return sqlite_data, "SQLite repository"

    return generate_sample_availability_data(), "Sample data"


def _load_from_raw_excels_if_available() -> pd.DataFrame | None:
    from raw_availability_data import load_raw_bess_availability, raw_files_available

    if not raw_files_available():
        return None

    return _normalise_frame(load_raw_bess_availability())


def generate_sample_availability_data() -> pd.DataFrame:
    return _generate_sample_data()


def load_snowflake_availability_data() -> pd.DataFrame:
    snowflake_config = _snowflake_config_from_env()
    if not snowflake_config:
        raise RuntimeError(
            "Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD before syncing from Snowflake."
        )

    return _load_from_snowflake(snowflake_config)


def _load_from_sqlite_repository_if_available() -> pd.DataFrame | None:
    from sqlite_repository import default_sqlite_path, read_availability_from_sqlite

    database_path = default_sqlite_path()
    if not database_path.exists():
        return None

    return read_availability_from_sqlite(database_path)


def _snowflake_config_from_env() -> dict[str, Any]:
    required = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD")
    if not all(os.getenv(key) for key in required):
        return {}

    return {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "password": os.environ["SNOWFLAKE_PASSWORD"],
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
    }


def _load_from_snowflake(config: Mapping[str, Any]) -> pd.DataFrame:
    import snowflake.connector

    table_name = os.getenv("SNOWFLAKE_AVAILABILITY_TABLE", "ANALYTICS.ASSET_AVAILABILITY")
    query = f"""
        select
            timestamp,
            asset_id,
            asset_name,
            availability_pct,
            mw,
            om_provider,
            pcs_oem,
            ess_oem
        from {table_name}
        where timestamp >= dateadd(day, -45, current_timestamp())
    """

    connection = snowflake.connector.connect(**{k: v for k, v in config.items() if v})
    try:
        df = connection.cursor().execute(query).fetch_pandas_all()
    finally:
        connection.close()

    df.columns = [column.lower() for column in df.columns]
    return _normalise_frame(df)


def _normalise_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(EXPECTED_COLUMNS).difference(df.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Availability data is missing required columns: {missing_list}")

    normalised = df[list(EXPECTED_COLUMNS)].copy()
    normalised["timestamp"] = pd.to_datetime(normalised["timestamp"], utc=False)
    normalised["availability_pct"] = pd.to_numeric(normalised["availability_pct"], errors="coerce")
    normalised["mw"] = pd.to_numeric(normalised["mw"], errors="coerce")
    return normalised.sort_values(["timestamp", "asset_name"]).reset_index(drop=True)


def _generate_sample_data() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    timestamps = pd.date_range(end=end, periods=45 * 24, freq="h").tz_convert(None)

    rows = []
    for asset_index, asset in enumerate(ASSETS):
        base = 96.5 - asset_index * 0.22
        noise = rng.normal(0, 1.2, size=len(timestamps))
        daily_shape = np.sin(np.linspace(0, 10 * np.pi, len(timestamps))) * 0.65
        availability = base + noise + daily_shape

        outage_start = (asset_index * 37 + 83) % (len(timestamps) - 20)
        outage_length = 4 + asset_index % 5
        availability[outage_start : outage_start + outage_length] -= rng.uniform(8, 18)

        if asset_index in (2, 5):
            derate_start = len(timestamps) - (72 + asset_index * 3)
            availability[derate_start : derate_start + 18] -= rng.uniform(3.5, 6.5)

        for timestamp, value in zip(timestamps, availability):
            rows.append(
                {
                    "timestamp": timestamp,
                    "asset_id": asset.asset_id,
                    "asset_name": asset.asset_name,
                    "availability_pct": float(np.clip(value, 72, 100)),
                    "mw": asset.mw,
                    "om_provider": asset.om_provider,
                    "pcs_oem": asset.pcs_oem,
                    "ess_oem": asset.ess_oem,
                }
            )

    return pd.DataFrame(rows)
