from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


INCIDENTS_PATH = Path(r"C:\Users\g.mantinan\Downloads\metlen_sites_open_items_01.06.2026.xlsx")
INCIDENT_SHEET_NAME = "sheet1"
INCIDENT_COLUMNS = ("Site", "Equipment", "Corrective Plans", "Comments", "Long term plan")

ROOT_CAUSE_RULES = (
    ("Fire / safety", ("fire fault", "smoke", "burnt", "burned")),
    ("Thermal management", ("chiller", "temperature", "high temperature", "tms", "fan zone", "fan du", "lc filter fan")),
    ("Communications", ("comms", "communication", "moxa", "timeout")),
    (
        "Electrical / BoP",
        ("skid", " tx ", "transformer", "rmu", "earthing", "ground fault", "busbar", "relay", "phase fault", "oil leak"),
    ),
    (
        "Battery rack / system",
        ("battery rack", "battery  rack", "battery system", "rack", " bcu", "cell voltage", "module balancing", "catl", "fuse"),
    ),
    (
        "PCS / inverter",
        ("inverter", "pcs", "power electronics", "sma", " pe ", "fru", "desaturation", "ac breaker", "dc fuse", "ct board"),
    ),
    ("OEM / parts pending", ("spare", "parts", "replacement", "procured", "ordered", "quote")),
)


def load_incidents_data(path: Path = INCIDENTS_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Incidents workbook not found: {path}")

    incidents = pd.read_excel(path, sheet_name=INCIDENT_SHEET_NAME, engine="openpyxl")
    missing = set(INCIDENT_COLUMNS).difference(incidents.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Incidents workbook is missing required columns: {missing_list}")

    incidents = incidents[list(INCIDENT_COLUMNS)].copy()
    incidents = incidents.dropna(how="all")
    incidents["Site"] = incidents["Site"].ffill()
    incidents["Site"] = incidents["Site"].map(_clean_text)
    for column in INCIDENT_COLUMNS[1:]:
        incidents[column] = incidents[column].map(_clean_text)

    incidents = incidents[
        incidents[["Equipment", "Corrective Plans", "Comments", "Long term plan"]].ne("").any(axis=1)
    ].copy()
    incidents["site_key"] = incidents["Site"].map(normalize_site_name)
    incidents["Root cause"] = incidents.apply(_infer_root_cause, axis=1)
    incidents["Incident"] = range(1, len(incidents) + 1)

    return incidents[
        [
            "Incident",
            "Site",
            "site_key",
            "Equipment",
            "Root cause",
            "Corrective Plans",
            "Comments",
            "Long term plan",
        ]
    ].reset_index(drop=True)


def normalize_site_name(value: object) -> str:
    cleaned = _clean_text(value).lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _infer_root_cause(row: pd.Series) -> str:
    text = " ".join(_clean_text(row.get(column)) for column in INCIDENT_COLUMNS[1:]).lower()
    text = f" {re.sub(r'[^a-z0-9]+', ' ', text)} "

    for category, keywords in ROOT_CAUSE_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    return "Other / under investigation"


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
