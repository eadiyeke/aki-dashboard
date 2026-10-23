"""Where clinicians' decisions are saved: one row per decision.

- GoogleSheetStore: used when the Streamlit secrets contain [gcp_service_account] and sheet_id.
  Use this on Streamlit Community Cloud (its own disk is wiped on every restart).
- LocalCsvStore: fallback for testing on your own computer (writes data/decisions.csv).
"""
from __future__ import annotations

import csv
import os
import threading
import time

COLUMNS = ["timestamp_utc", "participant_id", "participant_name", "case_number", "case_id",
           "decision", "iv_fluid_ml_4h", "vasopressor_mcg_kg_min", "changed_after_ai",
           "fluid_change", "vasopressor_change", "seconds_on_step", "session_id"]

INITIAL = "initial (before AI)"
FINAL = "final (after AI)"


def to_row(rec):
    return [("" if rec.get(c) is None else rec.get(c)) for c in COLUMNS]


def from_row(row):
    return dict(zip(COLUMNS, list(row) + [""] * (len(COLUMNS) - len(row))))


class LocalCsvStore:
    name = "local file"

    def __init__(self, path="data/decisions.csv"):
        self.path = path
        self._lock = threading.Lock()
        self._ensure()

    def _ensure(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(COLUMNS)

    def append(self, rec):
        with self._lock:
            self._ensure()
            with open(self.path, "a", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(to_row(rec))
                fh.flush()
                os.fsync(fh.fileno())

    def read_participant(self, pid):
        with self._lock:
            self._ensure()
            with open(self.path, newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))[1:]
        return [from_row(r) for r in rows if len(r) > 1 and r[1] == pid]


class GoogleSheetStore:
    name = "Google Sheet"

    def __init__(self, service_account_info, sheet_id, worksheet=None):
        import gspread

        self._gspread = gspread
        gc = gspread.service_account_from_dict(dict(service_account_info))
        book = gc.open_by_key(sheet_id)
        self.ws = book.worksheet(worksheet) if worksheet else book.sheet1
        first = self.ws.row_values(1)
        if not first:
            self.ws.append_row(COLUMNS, value_input_option="RAW")
        elif first[: len(COLUMNS)] != COLUMNS:
            raise RuntimeError("Row 1 of the Google Sheet doesn't match the expected columns. "
                               "Start with an empty sheet; the app writes the header itself.")

    def _retry(self, fn):
        delay = 1.0
        for attempt in range(5):
            try:
                return fn()
            except self._gspread.exceptions.APIError as e:
                code = getattr(getattr(e, "response", None), "status_code", 0)
                if code in (429, 500, 502, 503) and attempt < 4:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise

    def append(self, rec):
        self._retry(lambda: self.ws.append_row(to_row(rec), value_input_option="RAW",
                                               insert_data_option="INSERT_ROWS"))

    def read_participant(self, pid):
        rows = self._retry(lambda: self.ws.get_all_values())[1:]
        return [from_row(r) for r in rows if len(r) > 1 and r[1] == pid]
