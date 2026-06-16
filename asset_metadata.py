from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ASSET_METADATA_PATH = Path(r"C:\Users\g.mantinan\Downloads\the_shop_glm_sites_04.06.2026.xlsx")
ASSET_METADATA_SHEET_NAME = "sheet1"

REQUIRED_ASSET_METADATA_COLUMNS = {
    "site name": "asset_name",
    "capacity\n(MW)": "mw",
}

OPTIONAL_ASSET_METADATA_COLUMNS = {
    "capacity (MWh)": "mwh",
    "duration\n(h)": "duration_h",
    "status": "status",
    "O&M": "om_provider",
    "optimizer": "optimizer",
    "PCS_OEM": "pcs_oem",
    "ESS_OEM": "ess_oem",
    "SCADA": "scada",
    "PCS_model": "pcs_model",
    "ESS_model": "ess_model",
    "PCS_Vnom": "pcs_vnom",
}

ASSET_METADATA_COLUMNS = REQUIRED_ASSET_METADATA_COLUMNS | OPTIONAL_ASSET_METADATA_COLUMNS


def load_asset_metadata(path: Path = ASSET_METADATA_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Asset metadata workbook not found: {path}")

    metadata = pd.read_excel(path, sheet_name=ASSET_METADATA_SHEET_NAME, engine="openpyxl")
    missing = set(REQUIRED_ASSET_METADATA_COLUMNS).difference(metadata.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Asset metadata workbook is missing required columns: {missing_list}")

    available_columns = [column for column in ASSET_METADATA_COLUMNS if column in metadata.columns]
    metadata = metadata[available_columns].rename(columns=ASSET_METADATA_COLUMNS).copy()
    for column in OPTIONAL_ASSET_METADATA_COLUMNS.values():
        if column not in metadata.columns:
            metadata[column] = pd.NA

    metadata["asset_name"] = metadata["asset_name"].map(_clean_text)
    metadata = metadata[metadata["asset_name"] != ""].copy()
    metadata["site_key"] = metadata["asset_name"].map(normalize_site_name)
    metadata["mw"] = pd.to_numeric(metadata["mw"], errors="coerce")
    metadata["mwh"] = pd.to_numeric(metadata["mwh"], errors="coerce")
    metadata["duration_h"] = pd.to_numeric(metadata["duration_h"], errors="coerce")
    metadata["pcs_vnom"] = pd.to_numeric(metadata["pcs_vnom"], errors="coerce")

    for column in ["status", "om_provider", "optimizer", "pcs_oem", "ess_oem", "scada", "pcs_model", "ess_model"]:
        metadata[column] = metadata[column].map(_clean_text).replace("", "Unknown")

    return metadata[
        [
            "site_key",
            "asset_name",
            "mw",
            "mwh",
            "duration_h",
            "status",
            "om_provider",
            "optimizer",
            "pcs_oem",
            "ess_oem",
            "scada",
            "pcs_model",
            "ess_model",
            "pcs_vnom",
        ]
    ].drop_duplicates("site_key", keep="first")


def enrich_availability_with_asset_metadata(availability: pd.DataFrame) -> pd.DataFrame:
    enriched = availability.copy()
    enriched["site_key"] = enriched["asset_name"].map(normalize_site_name)

    try:
        metadata = load_asset_metadata()
    except (FileNotFoundError, ValueError):
        metadata = pd.DataFrame(
            columns=["site_key", "asset_name", "mw", "om_provider", "pcs_oem", "ess_oem"]
        )

    enriched = enriched.merge(
        metadata[["site_key", "asset_name", "mw", "om_provider", "pcs_oem", "ess_oem"]],
        on="site_key",
        how="left",
        suffixes=("", "_metadata"),
    )
    enriched["asset_name"] = enriched["asset_name_metadata"].combine_first(enriched["asset_name"])
    enriched["mw"] = enriched["mw"].fillna(1.0)
    enriched["om_provider"] = enriched["om_provider"].replace("", pd.NA).fillna("Unknown")
    enriched["pcs_oem"] = enriched["pcs_oem"].replace("", pd.NA).fillna("Unknown")
    enriched["ess_oem"] = enriched["ess_oem"].replace("", pd.NA).fillna("Unknown")

    return enriched.drop(columns=["site_key", "asset_name_metadata"])


def normalize_site_name(value: object) -> str:
    cleaned = _clean_text(value).lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
