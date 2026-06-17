import unittest
from io import BytesIO

import pandas as pd

from availability_domain import (
    approved_exclusions_from_tracker,
    calculate_final_availability,
    parse_uploaded_event_tracker,
)


class Upload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def workbook_upload(name: str, frame: pd.DataFrame) -> Upload:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
    return Upload(name, output.getvalue())


class EventTrackerImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_availability = pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-06-08 00:00"),
                    "asset_id": "COUPAR",
                    "asset_name": "Coupar",
                    "availability_pct": 90.0,
                    "mw": 40.0,
                    "source_file": "raw.csv",
                },
                {
                    "timestamp": pd.Timestamp("2026-06-09 00:00"),
                    "asset_id": "COUPAR",
                    "asset_name": "Coupar",
                    "availability_pct": 100.0,
                    "mw": 40.0,
                    "source_file": "raw.csv",
                },
            ]
        )

    def test_tracker_xlsx_import_preserves_stage_one_columns(self) -> None:
        tracker_upload = workbook_upload(
            "tracker.xlsx",
            pd.DataFrame(
                [
                    {
                        "event ID": "004",
                        "site name": "Coupar",
                        "type1": "fault",
                        "type2": "False Fire alarm tri",
                        "device type": "PCS",
                        "device name": "10 PCS",
                        "status": "closed",
                        "start date": "08-06-26",
                        "end date": "08-06-26",
                        "approval_status": "Approved",
                    },
                    {
                        "event ID": "011",
                        "site name": "Coupar",
                        "type1": "fault",
                        "type2": "False Fire alarm tri",
                        "device type": "PCS",
                        "device name": "10 PCS",
                        "status": "open",
                        "start date": "09-06-26",
                        "end date": "",
                        "approval_status": "Pending",
                    },
                ]
            ),
        )

        tracker, messages = parse_uploaded_event_tracker(tracker_upload, self.raw_availability)

        self.assertEqual(messages, [])
        self.assertEqual(tracker["event_id"].tolist(), ["004", "011"])
        self.assertEqual(tracker.loc[0, "tracker_status"], "closed")
        self.assertEqual(tracker.loc[1, "tracker_status"], "open")
        self.assertEqual(tracker.loc[0, "device_granularity"], "PCS")
        self.assertEqual(tracker.loc[0, "affected_device"], "10 PCS")
        self.assertEqual(tracker.loc[0, "approval_status"], "Approved")
        self.assertTrue(pd.isna(tracker.loc[1, "end_timestamp"]))

    def test_tracker_rows_without_internal_approval_default_to_pending(self) -> None:
        tracker_upload = workbook_upload(
            "tracker.xlsx",
            pd.DataFrame(
                [
                    {
                        "event ID": "005",
                        "site name": "Coupar",
                        "type1": "fault",
                        "type2": "unavailability",
                        "device type": "PCS",
                        "device name": "10 PCS",
                        "status": "closed",
                        "start date": "08-06-26",
                        "end date": "08-06-26",
                    },
                ]
            ),
        )

        tracker, messages = parse_uploaded_event_tracker(tracker_upload, self.raw_availability)

        self.assertEqual(messages, [])
        self.assertEqual(tracker.loc[0, "tracker_status"], "closed")
        self.assertEqual(tracker.loc[0, "approval_status"], "Pending")

    def test_only_approved_tracker_rows_affect_final_availability(self) -> None:
        tracker_upload = workbook_upload(
            "tracker.xlsx",
            pd.DataFrame(
                [
                    {
                        "event ID": "004",
                        "site name": "Coupar",
                        "type1": "fault",
                        "type2": "False Fire alarm tri",
                        "device type": "PCS",
                        "device name": "10 PCS",
                        "status": "closed",
                        "start date": "08-06-26",
                        "end date": "08-06-26",
                        "approval_status": "Approved",
                    },
                    {
                        "event ID": "011",
                        "site name": "Coupar",
                        "type1": "fault",
                        "type2": "False Fire alarm tri",
                        "device type": "PCS",
                        "device name": "10 PCS",
                        "status": "open",
                        "start date": "09-06-26",
                        "end date": "09-06-26",
                        "approval_status": "Rejected",
                    },
                ]
            ),
        )
        tracker, _ = parse_uploaded_event_tracker(tracker_upload, self.raw_availability)
        approved_exclusions = approved_exclusions_from_tracker(tracker)

        result = calculate_final_availability(self.raw_availability, approved_exclusions, 95.0)
        portfolio = result["contract_position"].query("asset_id == 'PORTFOLIO'").iloc[0]
        bridge = result["raw_to_net_bridge"].sort_values("timestamp")

        self.assertEqual(len(approved_exclusions), 1)
        self.assertEqual(approved_exclusions.loc[0, "event_id"], "004")
        self.assertEqual(int(portfolio.excluded_intervals), 1)
        self.assertEqual(float(portfolio.final_availability_pct), 100.0)
        self.assertEqual(bridge["excluded"].tolist(), [True, False])


if __name__ == "__main__":
    unittest.main()
