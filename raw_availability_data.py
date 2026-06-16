from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from asset_metadata import enrich_availability_with_asset_metadata


RAW_DATA_DIR = Path(r"C:\Users\g.mantinan\OneDrive - Gresham House\Documents\09. raw data")
ADDITIONAL_RAW_DATA_FILES = (
    Path(r"C:\Users\g.mantinan\Downloads\Bradford_37_all_devices_availability_YTD26_v1-20260101T000000.xlsx"),
    Path(r"C:\Users\g.mantinan\Downloads\Bradford_50_all_devices_availability_YTD26_v1-20260101T000000.xlsx"),
)
RAW_SHEET_NAME = "msrc10m"
BESS_COLUMN = "BESS availability (%) [BESS]"

SITE_LEVEL = "Site level"
GRANULARITY_OPTIONS = ("PCS", "Battery system", "PCS-module", "Battery rack")

SITE_FILE_RE = re.compile(
    r"^(.+)_all_devices_availability_(?:\d{2}(?:-\d{2})?\.\d{4}|YTD\d{2}_v\d+-\d{8}T\d{6})\.xlsx$",
    re.IGNORECASE,
)
PCS_RE = re.compile(r"^Availability \(\%\) \[Battery Inverter (?:PCS)?([A-Z0-9-]+)\]$")
BATTERY_SYSTEM_INVERTER_RE = re.compile(r"^Batteries availability \(\%\) \[Battery Inverter (PCS\d{2})\]$")
BATTERY_SYSTEM_RE = re.compile(r"^Batteries availability \(\%\) \[Battery system ([A-Z0-9&-]+)\]$")
PCS_MODULE_RE = re.compile(r"^Inverter Availability \(\%\) \[Battery Inverter module (?:PCS)?([A-Z0-9-]+)\]$")
BATTERY_RACK_RE = re.compile(r"^Battery availability \(\%\) \[Battery rack ((\d{2})-(\d{2})a?-\d{2})\]$")


@dataclass(frozen=True)
class ComponentColumn:
    source_column: str
    site_id: str
    asset_name: str
    level: str
    component_id: str
    component_label: str
    parent_id: str
    drill_level: str | None


def raw_files(raw_dir: Path = RAW_DATA_DIR) -> list[Path]:
    candidates = [
        *raw_dir.glob("*_all_devices_availability_*.xlsx"),
        *ADDITIONAL_RAW_DATA_FILES,
    ]
    files_by_name: dict[str, Path] = {}
    for path in candidates:
        if not path.exists() or not _site_from_path(path):
            continue
        files_by_name.setdefault(path.name.lower(), path)
    return sorted(files_by_name.values(), key=lambda path: path.name.lower())


def raw_files_available(raw_dir: Path = RAW_DATA_DIR) -> bool:
    return bool(raw_files(raw_dir))


def load_raw_bess_availability(raw_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for path in raw_files(raw_dir):
        site_id, asset_name = _site_from_path(path)
        header = pd.read_excel(path, sheet_name=RAW_SHEET_NAME, nrows=0, engine="openpyxl")
        component_columns = _component_columns(header.columns, site_id, asset_name)
        site_source_columns = _site_availability_source_columns(component_columns)

        if site_source_columns:
            df = pd.read_excel(
                path,
                sheet_name=RAW_SHEET_NAME,
                usecols=["Timestamp", *site_source_columns],
                engine="openpyxl",
            )
            df = pd.DataFrame(
                {
                    "timestamp": df["Timestamp"],
                    "availability_pct": _site_level_interval_availability(df, component_columns),
                }
            )
        elif BESS_COLUMN in header.columns:
            df = pd.read_excel(
                path,
                sheet_name=RAW_SHEET_NAME,
                usecols=["Timestamp", BESS_COLUMN],
                engine="openpyxl",
            )
            df = df.rename(columns={"Timestamp": "timestamp", BESS_COLUMN: "availability_pct"})
        else:
            continue

        df["asset_id"] = site_id
        df["asset_name"] = asset_name
        frames.append(df)

    if not frames:
        raise FileNotFoundError(f"No raw availability workbooks found in {raw_dir}")

    availability = pd.concat(frames, ignore_index=True)
    availability["timestamp"] = pd.to_datetime(availability["timestamp"], errors="coerce")
    availability["availability_pct"] = pd.to_numeric(availability["availability_pct"], errors="coerce")
    availability = availability.dropna(subset=["timestamp", "availability_pct"])
    availability = enrich_availability_with_asset_metadata(availability)

    return availability[
        [
            "timestamp",
            "asset_id",
            "asset_name",
            "availability_pct",
            "mw",
            "om_provider",
            "pcs_oem",
            "ess_oem",
        ]
    ].sort_values(["timestamp", "asset_name"])


def load_daily_component_availability(raw_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    monthly_frames: list[pd.DataFrame] = []

    for path in raw_files(raw_dir):
        site_id, asset_name = _site_from_path(path)
        header = pd.read_excel(path, sheet_name=RAW_SHEET_NAME, nrows=0, engine="openpyxl")
        component_columns = _component_columns(header.columns, site_id, asset_name)
        source_columns = [column.source_column for column in component_columns]
        usecols = ["Timestamp", *source_columns]
        if BESS_COLUMN in header.columns:
            usecols.append(BESS_COLUMN)

        wide = pd.read_excel(path, sheet_name=RAW_SHEET_NAME, usecols=usecols, engine="openpyxl")
        dates = pd.to_datetime(wide.pop("Timestamp"), errors="coerce").dt.floor("D")
        wide = wide.copy()
        wide.insert(0, "date", dates)
        wide = wide.dropna(subset=["date"])

        site_monthly = _site_level_daily_availability(wide, component_columns, site_id, asset_name)
        if not site_monthly.empty:
            monthly_frames.append(site_monthly)

        numeric_values = wide[source_columns].apply(pd.to_numeric, errors="coerce")
        component_daily_wide = pd.concat([wide["date"], numeric_values], axis=1)
        component_daily_wide = component_daily_wide.groupby("date", as_index=False)[source_columns].mean()

        metadata = pd.DataFrame([column.__dict__ for column in component_columns])
        monthly = component_daily_wide.melt(
            id_vars=["date"],
            value_vars=source_columns,
            var_name="source_column",
            value_name="availability_pct",
        )
        monthly = monthly.dropna(subset=["availability_pct"])
        monthly = monthly.merge(metadata, on="source_column", how="inner")
        monthly_frames.append(monthly)

    if not monthly_frames:
        raise FileNotFoundError(f"No raw availability workbooks found in {raw_dir}")

    daily = pd.concat(monthly_frames, ignore_index=True)
    return (
        daily.groupby(
            [
                "date",
                "site_id",
                "asset_name",
                "level",
                "component_id",
                "component_label",
                "parent_id",
                "drill_level",
            ],
            dropna=False,
            as_index=False,
        )["availability_pct"]
        .mean()
        .sort_values(["date", "asset_name", "level", "component_id"])
        .reset_index(drop=True)
    )


def _site_level_daily_availability(
    wide: pd.DataFrame,
    component_columns: list[ComponentColumn],
    site_id: str,
    asset_name: str,
) -> pd.DataFrame:
    site_availability = _site_level_interval_availability(wide, component_columns)
    if site_availability.isna().all() and BESS_COLUMN not in wide.columns:
        return pd.DataFrame()

    site_values = pd.DataFrame(
        {
            "date": wide["date"],
            "availability_pct": site_availability,
        }
    )

    site_values["availability_pct"] = pd.to_numeric(site_values["availability_pct"], errors="coerce")
    site_values = site_values.dropna(subset=["availability_pct"])
    if site_values.empty:
        return pd.DataFrame()

    daily = site_values.groupby("date", as_index=False)["availability_pct"].mean()
    daily = daily.assign(
        site_id=site_id,
        asset_name=asset_name,
        level=SITE_LEVEL,
        component_id=site_id,
        component_label=asset_name,
        parent_id="PORTFOLIO",
        drill_level=None,
    )
    return daily[
        [
            "date",
            "site_id",
            "asset_name",
            "level",
            "component_id",
            "component_label",
            "parent_id",
            "drill_level",
            "availability_pct",
        ]
    ]


def _site_availability_source_columns(component_columns: list[ComponentColumn]) -> list[str]:
    columns = [
        column.source_column
        for column in component_columns
        if column.level in {"PCS", "Battery system"}
    ]
    return list(dict.fromkeys(columns))


def _site_level_interval_availability(wide: pd.DataFrame, component_columns: list[ComponentColumn]) -> pd.Series:
    pcs_columns = _level_source_columns(component_columns, "PCS", wide.columns)
    battery_columns = _level_source_columns(component_columns, "Battery system", wide.columns)

    level_availability: list[pd.Series] = []
    if pcs_columns:
        level_availability.append(wide[pcs_columns].apply(pd.to_numeric, errors="coerce").mean(axis=1))
    if battery_columns:
        level_availability.append(wide[battery_columns].apply(pd.to_numeric, errors="coerce").mean(axis=1))

    if len(level_availability) >= 2:
        return pd.concat(level_availability, axis=1).min(axis=1)
    if level_availability:
        return level_availability[0]
    if BESS_COLUMN in wide.columns:
        return pd.to_numeric(wide[BESS_COLUMN], errors="coerce")
    return pd.Series(pd.NA, index=wide.index, dtype="float64")


def _level_source_columns(component_columns: list[ComponentColumn], level: str, available_columns: pd.Index) -> list[str]:
    available = set(available_columns)
    return [
        column.source_column
        for column in component_columns
        if column.level == level and column.source_column in available
    ]


def _component_columns(columns: pd.Index, site_id: str, asset_name: str) -> list[ComponentColumn]:
    parsed: list[ComponentColumn] = []
    battery_system_ids = _battery_system_ids(columns)
    rack_parent_ids = _rack_parent_ids(columns, battery_system_ids)

    for column in columns:
        if not isinstance(column, str):
            continue

        if match := PCS_RE.match(column):
            component_id = _pcs_id(match.group(1))
            parsed.append(
                ComponentColumn(
                    source_column=column,
                    site_id=site_id,
                    asset_name=asset_name,
                    level="PCS",
                    component_id=component_id,
                    component_label=component_id,
                    parent_id="BESS",
                    drill_level="PCS-module",
                )
            )
            continue

        if match := BATTERY_SYSTEM_INVERTER_RE.match(column):
            pcs_id = match.group(1)
            component_id = f"BATTERY-{pcs_id}"
            parsed.append(
                ComponentColumn(
                    source_column=column,
                    site_id=site_id,
                    asset_name=asset_name,
                    level="Battery system",
                    component_id=component_id,
                    component_label=f"Battery system {pcs_id}",
                    parent_id="BESS",
                    drill_level="Battery rack" if component_id in rack_parent_ids else None,
                )
            )
            continue

        if match := BATTERY_SYSTEM_RE.match(column):
            battery_system_id = match.group(1)
            component_id = f"BATTERY-{battery_system_id}"
            parsed.append(
                ComponentColumn(
                    source_column=column,
                    site_id=site_id,
                    asset_name=asset_name,
                    level="Battery system",
                    component_id=component_id,
                    component_label=f"Battery system {battery_system_id}",
                    parent_id="BESS",
                    drill_level="Battery rack" if component_id in rack_parent_ids else None,
                )
            )
            continue

        if match := PCS_MODULE_RE.match(column):
            component_id = _pcs_id(match.group(1))
            parent_id = _module_parent_id(component_id)
            parsed.append(
                ComponentColumn(
                    source_column=column,
                    site_id=site_id,
                    asset_name=asset_name,
                    level="PCS-module",
                    component_id=component_id,
                    component_label=component_id,
                    parent_id=parent_id,
                    drill_level=None,
                )
            )
            continue

        if match := BATTERY_RACK_RE.match(column):
            rack_id = match.group(1)
            pcs_number = match.group(2)
            battery_system_number = match.group(3)
            parsed.append(
                ComponentColumn(
                    source_column=column,
                    site_id=site_id,
                    asset_name=asset_name,
                    level="Battery rack",
                    component_id=rack_id,
                    component_label=f"Rack {rack_id}",
                    parent_id=_battery_rack_parent_id(pcs_number, battery_system_number, battery_system_ids),
                    drill_level=None,
                )
            )

    return parsed


def _battery_system_ids(columns: pd.Index) -> set[str]:
    ids: set[str] = set()
    for column in columns:
        if not isinstance(column, str):
            continue
        if match := BATTERY_SYSTEM_INVERTER_RE.match(column):
            ids.add(f"BATTERY-{match.group(1)}")
        elif match := BATTERY_SYSTEM_RE.match(column):
            ids.add(f"BATTERY-{match.group(1)}")
    return ids


def _rack_parent_ids(columns: pd.Index, battery_system_ids: set[str]) -> set[str]:
    parent_ids: set[str] = set()
    for column in columns:
        if not isinstance(column, str):
            continue
        if match := BATTERY_RACK_RE.match(column):
            parent_ids.add(_battery_rack_parent_id(match.group(2), match.group(3), battery_system_ids))
    return parent_ids


def _battery_rack_parent_id(pcs_number: str, battery_system_number: str, battery_system_ids: set[str]) -> str:
    battery_system_id = f"BATTERY-{pcs_number}-{battery_system_number}"
    inverter_id = f"BATTERY-PCS{pcs_number}"

    if battery_system_id in battery_system_ids:
        return battery_system_id
    if inverter_id in battery_system_ids:
        return inverter_id
    return battery_system_id


def _site_from_path(path: Path) -> tuple[str, str] | None:
    match = SITE_FILE_RE.match(path.name)
    if not match:
        return None

    slug = match.group(1).lower()
    site_id = slug.upper().replace("-", "_")
    asset_name = slug.replace("_", " ").replace("-", " ").title()
    return site_id, asset_name


def _pcs_id(raw_id: str) -> str:
    return raw_id if raw_id.startswith("PCS") else f"PCS{raw_id}"


def _module_parent_id(component_id: str) -> str:
    parts = component_id.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:2])
    return parts[0]
