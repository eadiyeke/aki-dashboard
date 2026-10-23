"""Load the study content (cases and AI recommendations) from the CSV files in ./csv.

Same CSV format as the original aki-dashboard app, so cases are authored exactly as before.
Participants are NOT read from CSV here: logins live in Streamlit secrets (see README).
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

SERIES_UNITS = {
    "creatinine": "mg/dL",
    "bun": "mg/dL",
    "urine_output": "mL/hr",
    "lactate": "mmol/L",
    "map": "mmHg",
    "hr": "bpm",
    "cvp": "mmHg",
    "iv_fluids": "mL/4hr",
    "vasopressors": "mcg/kg/min",
    "egfr": "mL/min/1.73 m²",
}
SERIES_NAMES = {
    "creatinine": "Creatinine",
    "bun": "BUN",
    "urine_output": "Urine output",
    "lactate": "Lactate",
    "map": "Mean arterial pressure",
    "hr": "Heart rate",
    "cvp": "CVP",
    "iv_fluids": "IV fluids",
    "vasopressors": "Vasopressors",
    "egfr": "eGFR",
}
LAB_KEYS = ["creatinine", "bun", "urine_output", "lactate"]
VITAL_KEYS = ["map", "hr", "cvp"]
OTHER_KEYS = ["iv_fluids", "vasopressors", "egfr"]


class ContentError(Exception):
    pass


def _read(csv_dir, name):
    path = os.path.join(csv_dir, name)
    if not os.path.exists(path):
        raise ContentError(f"missing required CSV: {path}")
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _num(value, where):
    value = (value or "").strip()
    if value == "":
        raise ContentError(f"{where}: empty numeric value")
    try:
        f = float(value)
    except ValueError:
        raise ContentError(f"{where}: '{value}' is not a number")
    return int(f) if f.is_integer() else f


def _s(r, key):
    return (r.get(key) or "").strip()


def _split(value, sep=";"):
    return [v.strip() for v in (value or "").split(sep) if v.strip()]


def load_cases(csv_dir):
    meta = _read(csv_dir, "cases_meta.csv")
    ts_by = defaultdict(list)
    for r in _read(csv_dir, "cases_timeseries.csv"):
        ts_by[_s(r, "case_id")].append(r)

    cases, seen = [], set()
    for m in meta:
        cid = _s(m, "case_id")
        if not cid:
            raise ContentError(f"cases_meta.csv: row missing case_id -> {m}")
        if cid in seen:
            raise ContentError(f"cases_meta.csv: duplicate case_id '{cid}'")
        seen.add(cid)
        rows = ts_by.get(cid)
        if not rows:
            raise ContentError(f"{cid}: no rows in cases_timeseries.csv")
        series = {
            k: [_num(r.get(k), f"{cid} {k} @ {r.get('time_label')}") for r in rows]
            for k in LAB_KEYS + VITAL_KEYS + OTHER_KEYS
        }
        cases.append({
            "id": cid,
            "patient": {
                "name": _s(m, "name"),
                "age": _num(m.get("age"), f"{cid} age"),
                "sex": _s(m, "sex"),
                "weight_kg": _num(m.get("weight_kg"), f"{cid} weight_kg"),
                "bmi": _num(m.get("bmi"), f"{cid} bmi"),
                "admission_diagnosis": _s(m, "admission_diagnosis"),
                "comorbidities": _split(m.get("comorbidities")),
                "charlson_index": _num(m.get("charlson_index"), f"{cid} charlson_index"),
            },
            "aki": {
                "stage": _num(m.get("aki_stage"), f"{cid} aki_stage"),
                "criteria": _s(m, "aki_criteria"),
                "baseline_creatinine": _num(m.get("baseline_creatinine"), f"{cid} baseline_creatinine"),
            },
            "labels": [_s(r, "time_label") for r in rows],
            "aki_stage_labels": [_s(r, "aki_stage_label") for r in rows],
            "series": series,
        })
    if not cases:
        raise ContentError("cases_meta.csv: no cases found")
    return cases


def load_recommendations(csv_dir, case_ids):
    def group(name, label_col, val_col, label_key, val_key):
        out = defaultdict(list)
        for r in _read(csv_dir, name):
            out[_s(r, "case_id")].append({
                label_key: _s(r, label_col),
                val_key: _num(r.get(val_col), f"{name} {r.get('case_id')}"),
            })
        return out

    feats = group("rec_features.csv", "feature_label", "value", "label", "value")
    alts = group("rec_alternatives.csv", "alt_label", "score", "label", "score")
    peers = group("rec_peer_options.csv", "option_label", "pct", "label", "pct")

    recs = {}
    for r in _read(csv_dir, "recommendations.csv"):
        cid = _s(r, "case_id")
        recs[cid] = {
            "vasopressor": _s(r, "rec_vasopressor"),
            "iv_fluid": _s(r, "rec_iv_fluid"),
            "cohort_n": _num(r.get("cohort_n"), f"{cid} cohort_n"),
            "match_pct": _num(r.get("match_pct"), f"{cid} match_pct"),
            "note": _s(r, "note"),
            "features": feats.get(cid, []),
            "alternatives": alts.get(cid, []),
            "peers": peers.get(cid, []),
        }
    missing = set(case_ids) - set(recs)
    if missing:
        raise ContentError(f"cases without a recommendation row: {sorted(missing)}")
    return recs


def load_all(csv_dir="csv"):
    cases = load_cases(csv_dir)
    recs = load_recommendations(csv_dir, [c["id"] for c in cases])
    return cases, recs
