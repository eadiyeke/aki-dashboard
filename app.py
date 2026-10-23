"""AKI Management Dashboard: Streamlit host for the original dashboard layout.

The dashboard itself (header, patient sidebar, charts, time slider, AI panel) is the original
HTML/CSS/Chart.js design, shown inside the page. Streamlit handles login and the decision bar,
and saves each clinician's decisions to a Google Sheet:

  per case:  initial plan (before AI)  ->  AI recommendation appears  ->  final plan (after AI)
"""
from __future__ import annotations

import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone

import streamlit as st

import content
from storage import FINAL, INITIAL, GoogleSheetStore, LocalCsvStore

HERE = os.path.dirname(os.path.abspath(__file__))
st.set_page_config(page_title="AKI Management Dashboard", page_icon="🩺", layout="wide",
                   initial_sidebar_state="collapsed")

BASE_CSS = """
<style>
  [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stSidebar"],
  [data-testid="stSidebarCollapsedControl"], #MainMenu, footer {display: none !important;}
  .block-container, [data-testid="stMainBlockContainer"] {padding: 0 !important; max-width: 100% !important;}
  [data-testid="stAppViewContainer"] > .main, .stMain {padding: 0 !important;}
  iframe {border: none; display: block;}
  [data-testid="stVerticalBlock"] {gap: 0;}

  /* decision bar (same look as the original footer) */
  .st-key-decision {background: #fff; border-top: 1px solid #e2e8f0; padding: 10px 24px 16px 24px;}
  .st-key-decision [data-testid="stVerticalBlock"] {gap: .25rem;}
  .st-key-decision label p {font-size: 13px !important; font-weight: 600; color: #718096;}
  .st-key-decision [data-testid="stNumberInputContainer"] {background: #fef9ec; border: 1.5px solid #f5d9a5; border-radius: 8px;}
  .st-key-decision input {background: #fef9ec !important; font-size: 15px !important; font-weight: 600; color: #2d3748;}
  .dec-note {font-size: 12px; color: #718096; margin-top: 2px;}
  .chip {display: inline-block; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 10px;
         background: #fff4d6; color: #9a6b00; border: 1px solid #f0d28a; margin-top: 6px;}
  .chip.same {background: #eef7f5; color: #1a7a70; border-color: #c5e8e4;}
  .step-title {font-size: 13px; font-weight: 700; color: #2d3748; margin-top: 4px;}
  .step-sub {font-size: 11px; color: #718096;}
</style>
"""

LOGIN_CSS = """
<style>
  .stApp {background: #3b4452 !important;}
  .st-key-login {background: #fff; border-radius: 12px; padding: 30px 32px 22px 32px;
                 box-shadow: 0 10px 40px rgba(0,0,0,.25); margin-top: 16vh;}
  .st-key-login [data-testid="stVerticalBlock"] {gap: .6rem;}
  .login-title {font-size: 19px; font-weight: 700; color: #2a9d8f; margin-bottom: 4px;}
  .st-key-login label p {font-size: 11px !important; font-weight: 600; color: #718096;
                         text-transform: uppercase; letter-spacing: .06em;}
  .st-key-login [data-testid="stForm"] {border: none; padding: 0;}
  .login-sub {font-size: 12px; color: #718096; margin-bottom: 12px;}
</style>
"""

DONE_CSS = """
<style>
  .stApp {background: #f7f8f5 !important;}
  .done-card {background: #fff; border-radius: 12px; padding: 40px 48px; text-align: center;
              box-shadow: 0 10px 40px rgba(0,0,0,.12); margin: 22vh auto 0 auto; max-width: 440px;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;}
  .done-card h1 {font-size: 22px; color: #2a9d8f; margin-bottom: 8px;}
  .done-card p {color: #718096; font-size: 14px;}
</style>
"""


# ---------------------------------------------------------------- setup -----
def _secret(key, default=None):
    try:
        return st.secrets[key] if key in st.secrets else default
    except Exception:  # no secrets file at all
        return default


@st.cache_data(show_spinner=False)
def get_content():
    return content.load_all(os.path.join(HERE, "csv"))


@st.cache_resource(show_spinner="Connecting to response storage...")
def get_store():
    sa, sheet_id = _secret("gcp_service_account"), _secret("sheet_id")
    if _secret("gcp_json"):  # whole JSON key file pasted as one block (preferred)
        sa = json.loads(_secret("gcp_json"))
    if sa and sheet_id:
        sa = {k: (v.strip() if isinstance(v, str) and k != "private_key" else v) for k, v in dict(sa).items()}
        try:
            return GoogleSheetStore(sa, sheet_id, _secret("worksheet"))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"{e} | app is using client_email='{sa.get('client_email')}', "
                               f"project_id='{sa.get('project_id')}', sheet_id='{sheet_id}'") from e
    return LocalCsvStore(os.path.join(HERE, "data", "decisions.csv"))


@st.cache_data(show_spinner=False)
def dashboard_assets():
    def read(name):
        with open(os.path.join(HERE, "dashboard", name), encoding="utf-8") as fh:
            return fh.read()
    return read("template.html"), read("styles.css"), read("chart.umd.js"), read("charts.js")


def participants():
    raw = _secret("participants", {}) or {}
    return {str(u): dict(v) for u, v in raw.items()}


def now_iso():
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def save_decision(case_number, case_id, decision, fluid, vaso, changed=None, d_fluid=None,
                  d_vaso=None, seconds=None):
    ss = st.session_state
    rec = {
        "timestamp_utc": now_iso(),
        "participant_id": ss.user["id"],
        "participant_name": ss.user["display_name"],
        "case_number": case_number,
        "case_id": case_id,
        "decision": decision,
        "iv_fluid_ml_4h": fluid,
        "vasopressor_mcg_kg_min": vaso,
        "changed_after_ai": changed,
        "fluid_change": d_fluid,
        "vasopressor_change": d_vaso,
        "seconds_on_step": seconds,
        "session_id": ss.session_id,
    }
    try:
        get_store().append(rec)
        return True
    except Exception as e:  # noqa: BLE001
        st.error(f"Your decision could not be saved. Please try again in a moment. ({e})")
        return False


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def restore_progress(pid, cases):
    """Where this clinician is, rebuilt from their saved decisions (resume after refresh)."""
    rows = get_store().read_participant(pid)
    done = {r["case_id"] for r in rows if r["decision"] == FINAL}
    idx = 0
    while idx < len(cases) and cases[idx]["id"] in done:
        idx += 1
    pre = None
    if idx < len(cases):
        inits = [r for r in rows if r["decision"] == INITIAL and r["case_id"] == cases[idx]["id"]]
        if inits:
            pre = {"fluid": _num(inits[-1]["iv_fluid_ml_4h"]), "vaso": _num(inits[-1]["vasopressor_mcg_kg_min"])}
    return idx, pre


def open_case(idx, pre=None):
    ss = st.session_state
    ss.idx, ss.pre = idx, pre
    ss.step_started = time.time()


# ---------------------------------------------------------------- views -----
def login_view(cases):
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    users = participants()
    _, mid, _ = st.columns([1, 0.62, 1])
    with mid:
        with st.container(key="login"):
            st.markdown("<div class='login-title'>AKI Management Dashboard</div>"
                        "<div class='login-sub'>Please log in with the credentials provided to you.</div>",
                        unsafe_allow_html=True)
            if not users:
                st.error("No logins configured. Add [participants] to the app's Secrets (see README).")
                return
            with st.form("login_form", border=False):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                ok = st.form_submit_button("Log in", type="primary", width="stretch")
            if not ok:
                return
            u = users.get(username.strip())
            if not u or not hmac.compare_digest(str(u.get("password", "")), password):
                st.error("Invalid username or password.")
                return
            ss = st.session_state
            ss.user = {"id": str(u.get("id", username)), "display_name": str(u.get("display_name", username))}
            ss.session_id = "S" + uuid.uuid4().hex[:12]
            try:
                idx, pre = restore_progress(ss.user["id"], cases)
            except Exception as e:  # noqa: BLE001
                del ss["user"]
                st.error(f"Could not reach response storage. Please try again. ({e})")
                return
            open_case(idx, pre)
            st.rerun()


def dashboard_html(case, rec, case_number, total):
    template, css, chartjs, charts_js = dashboard_assets()
    series = case["series"]
    unit = content.SERIES_UNITS
    case_js = {
        "id": case["id"],
        "patient": case["patient"],
        "aki": case["aki"],
        "timeline": {"labels": case["labels"], "aki_stage_labels": case["aki_stage_labels"]},
        "series": {
            "labs": {k: {"unit": unit[k], "data": series[k]} for k in content.LAB_KEYS},
            "vitals": {k: {"unit": unit[k], "data": series[k]} for k in content.VITAL_KEYS},
            **{k: {"unit": unit[k], "data": series[k]} for k in content.OTHER_KEYS},
        },
    }
    data = {"case": case_js, "rec": rec, "caseNumber": case_number, "totalCases": total,
            "who": st.session_state.user["display_name"]}
    data_js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (template.replace("/*__STYLES__*/", css)
            .replace("/*__CHARTJS__*/", chartjs)
            .replace("/*__CHARTS_JS__*/", charts_js)
            .replace("/*__DATA__*/", data_js))


def case_view(cases, recs):
    ss = st.session_state
    case = cases[ss.idx]
    cid, n = case["id"], ss.idx + 1
    revealed = ss.pre is not None

    height = int(_secret("dashboard_height", 680))
    st.iframe(dashboard_html(case, recs[cid] if revealed else None, n, len(cases)), height=height)

    with st.container(key="decision"):
        c0, c1, c2, c3, c4 = st.columns([1.35, 1.2, 1.2, 1.25, 0.5], vertical_alignment="center")
        with c0:
            if not revealed:
                st.markdown("<div class='step-title'>Step 1 · Your initial plan</div>"
                            "<div class='step-sub'>Locked once submitted; then the AI recommendation "
                            "appears.</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='step-title'>Step 2 · Your final plan</div>"
                            "<div class='step-sub'>Keep or change your plan after reviewing the AI "
                            "recommendation.</div>", unsafe_allow_html=True)
        prefix = "post" if revealed else "pre"
        with c1:
            f = st.number_input("IV fluid over next 4 h (mL/4h)", min_value=0.0, step=10.0, format="%.1f",
                                value=ss.pre["fluid"] if revealed else None, key=f"{prefix}_fluid_{cid}")
            if revealed:
                st.markdown(f"<div class='dec-note'>initial: {ss.pre['fluid']:g}</div>", unsafe_allow_html=True)
        with c2:
            v = st.number_input("NE-equivalent vasopressor (mcg/kg/min)", min_value=0.0, step=0.01,
                                format="%.2f", value=ss.pre["vaso"] if revealed else None,
                                key=f"{prefix}_vaso_{cid}")
            if revealed:
                st.markdown(f"<div class='dec-note'>initial: {ss.pre['vaso']:g}</div>", unsafe_allow_html=True)
        with c3:
            changed = None
            if revealed and f is not None and v is not None:
                changed = round(f, 3) != round(ss.pre["fluid"], 3) or round(v, 3) != round(ss.pre["vaso"], 3)
            label = "Confirm final plan" if revealed else "Submit initial plan"
            clicked = st.button(label, type="primary", width="stretch", key=f"btn_{prefix}_{cid}")
            if changed is not None:
                st.markdown(f"<span class='chip{'' if changed else ' same'}'>"
                            f"{'Modified from your initial plan' if changed else 'Unchanged from initial plan'}"
                            f"</span>", unsafe_allow_html=True)
        with c4:
            if st.button("Log out", type="tertiary", key="logout"):
                for k in list(ss.keys()):
                    del ss[k]
                st.rerun()

        if clicked:
            if f is None or v is None:
                st.warning("Please enter both an IV fluid and a vasopressor value (0 is allowed).")
                return
            secs = round(time.time() - ss.step_started, 1)
            if not revealed:
                if save_decision(n, cid, INITIAL, f, v, seconds=secs):
                    ss.pre = {"fluid": f, "vaso": v}
                    ss.step_started = time.time()
                    st.rerun()
            else:
                if save_decision(n, cid, FINAL, f, v, changed=changed,
                                 d_fluid=round(f - ss.pre["fluid"], 3),
                                 d_vaso=round(v - ss.pre["vaso"], 3), seconds=secs):
                    open_case(ss.idx + 1)
                    st.toast(f"Case {n} saved.")
                    st.rerun()

    if isinstance(get_store(), LocalCsvStore):
        st.caption("⚠️ Test mode: decisions are saved to a local file, not the Google Sheet.")


def done_view():
    st.markdown(DONE_CSS, unsafe_allow_html=True)
    st.markdown("<div class='done-card'><h1>Thank you</h1>"
                "<p>Your decisions have been recorded. You may close this window.</p></div>",
                unsafe_allow_html=True)


# ----------------------------------------------------------------- main -----
def main():
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    try:
        cases, recs = get_content()
    except content.ContentError as e:
        st.error(f"Problem in the case CSV files: {e}")
        st.stop()
    ss = st.session_state
    if "user" not in ss:
        login_view(cases)
    elif ss.idx >= len(cases):
        done_view()
    else:
        case_view(cases, recs)


main()
