# AKI Management Dashboard — Streamlit version

The original dashboard (same header, patient sidebar, Chart.js charts, time slider and AI panel),
hosted on **Streamlit Community Cloud**, with each clinician's decisions saved to a **Google Sheet**.

**Per case**

1. The clinician reviews the patient. The AI panel is hidden.
2. They enter an **initial plan** (IV fluid mL/4h + NE-equivalent vasopressor mcg/kg/min) and click
   **Submit initial plan**. It is saved immediately and can't be changed.
3. The **AI recommendation** panel appears (recommendation, feature explanation, alternatives,
   clinician decisions in similar states).
4. They keep or change the values and click **Confirm final plan**. It is saved, and the next case opens.

After the last case they see a thank-you page. If someone closes the browser, logging back in continues
at the right case (and, if the initial plan was already submitted, with the AI panel open).

No questionnaires and no interaction tracking: only the decisions are recorded.

---

## What gets saved

One row per decision in the Google Sheet:

| Column | Meaning |
|---|---|
| `timestamp_utc` | When it was saved (UTC) |
| `participant_id`, `participant_name` | Who (from the login list) |
| `case_number`, `case_id` | Which case |
| `decision` | `initial (before AI)` or `final (after AI)` |
| `iv_fluid_ml_4h`, `vasopressor_mcg_kg_min` | The values entered |
| `changed_after_ai` | Final rows only: `TRUE` if the final plan differs from the initial plan |
| `fluid_change`, `vasopressor_change` | Final rows only: final minus initial |
| `seconds_on_step` | Time from opening the case (initial) or from the AI appearing (final) to clicking submit |
| `session_id` | Distinguishes separate logins by the same person |

So each clinician × case has exactly two rows.

---

## Folder contents

| File | What it is |
|---|---|
| `app.py` | The app: login, decision bar, saving, resume |
| `dashboard/` | The original dashboard design: `styles.css`, `charts.js`, `chart.umd.js` (Chart.js), plus `template.html` |
| `content.py` | Reads the case CSVs |
| `storage.py` | Saves decisions to Google Sheets (or `data/decisions.csv` when testing locally) |
| `csv/` | Cases, time series and AI recommendations (same format as the original app) |
| `requirements.txt` | Python packages for Streamlit Cloud |
| `.streamlit/config.toml` | Colours |
| `.streamlit/secrets.toml.example` | Template for logins + Google key. The real secrets go into Streamlit Cloud, never into GitHub. |

---

## Deploy, step by step (about 30–40 minutes the first time)

You need a **GitHub** account and a **Google** account. A personal Gmail is easiest; university
Google accounts often block step 2d. Everything is free.

### Step 1 — Put the code on GitHub

1. github.com → **New repository** → name it `aki-dashboard` → **Create repository**.
   Public or private both work; no passwords are in the code.
2. On the new repo page click **uploading an existing file**, then drag in everything from this folder:
   `app.py`, `content.py`, `storage.py`, `requirements.txt`, `README.md`, and the `csv`, `dashboard`
   and `.streamlit` folders → **Commit changes**.
   - On a Mac, `.streamlit` is hidden in Finder: press **Cmd + Shift + .** to show it. If it doesn't
     upload, the app still works.
   - Never upload a file called `secrets.toml`.

### Step 2 — Google Sheet + a "robot" account that can write to it

a. **console.cloud.google.com** → project dropdown (top) → **New project** → name `aki-study` →
   **Create**, and make sure it's selected.

b. Search bar → **Google Sheets API** → **Enable**.

c. Left menu **APIs & Services → Credentials** → **Create credentials → Service account** →
   name `aki-app` → **Create and continue** → **Done**.

d. Click the new service account → **Keys** tab → **Add key → Create new key → JSON → Create**.
   A `.json` file downloads. Keep it private.

e. Copy the service account's email (like `aki-app@aki-study.iam.gserviceaccount.com`).

f. Go to **sheets.new** to create an **empty** Google Sheet named `AKI decisions`.

g. **Share** → paste the service-account email → **Editor** → untick "Notify" → **Share**.

h. Copy the sheet ID from the address bar:
   `https://docs.google.com/spreadsheets/d/`**`THIS_LONG_PART`**`/edit`

### Step 3 — Deploy on Streamlit Community Cloud

1. **share.streamlit.io** → **Continue with GitHub**.
2. **Create app → Deploy a public app from GitHub**. Only people with a login get past the first page.
3. Repository `your-name/aki-dashboard` · Branch `main` · Main file path `app.py`.
4. Optional: pick an address, e.g. `aki-dashboard` → `aki-dashboard.streamlit.app`.
5. **Advanced settings** → Python version **3.12** → **Secrets**: paste the contents of
   `.streamlit/secrets.toml.example` and fill it in:
   - **`[participants.<username>]`**: one block per clinician with `id`, `password`, `display_name`.
     Use a different strong password for each.
   - **`sheet_id`**: from step 2h.
   - **`[gcp_service_account]`**: open the downloaded `.json` key in a text editor and copy each value
     into the matching line. Copy `private_key` exactly, including the `\n` characters, inside quotes.
6. **Save → Deploy** (first start takes 2–3 minutes).

### Step 4 — Test

1. Open the link, log in, submit an initial plan, then a final plan.
2. Open the Google Sheet. You should see a header row plus two rows for that case.
   - If the page shows **"⚠️ Test mode: decisions are saved to a local file"** under the decision bar,
     the Google part of the Secrets is missing or misnamed. Fix it under App → **Settings → Secrets**.
     Local files on Streamlit Cloud are deleted on every restart.
3. Submit an initial plan, close the browser, log back in: you should be on the same case with the AI
   panel open.
4. Have 2–3 colleagues try it at the same time with **different** logins.

### Step 5 — Before the real study

- Delete all test rows in the Google Sheet **except row 1** (the header).
- Give each clinician the link and their **own** username and password. Two people sharing a login are
  treated as one participant.
- Free Streamlit apps go to sleep after a period with no visitors. Open the link yourself shortly before
  a session; a sleeping app shows a "wake up" button and takes ~30 seconds. Saved decisions are not
  affected.

---

## Getting the data

Open the sheet anytime. When done: **File → Download → Comma-separated values (.csv)**.

```r
library(dplyr); library(tidyr)

d <- read.csv("AKI decisions - Sheet1.csv", stringsAsFactors = FALSE)

# One row per clinician x case: initial vs final plan
wide <- d |>
  mutate(when = ifelse(grepl("^initial", decision), "initial", "final")) |>
  group_by(participant_id, case_id, when) |> slice_tail(n = 1) |> ungroup() |>
  select(participant_id, case_id, when, iv_fluid_ml_4h, vasopressor_mcg_kg_min) |>
  pivot_wider(names_from = when, values_from = c(iv_fluid_ml_4h, vasopressor_mcg_kg_min))

# How often clinicians changed their plan after seeing the AI
d |> filter(grepl("^final", decision)) |>
  summarise(n = n(), changed = sum(changed_after_ai %in% c("TRUE", "True", TRUE)),
            pct_changed = 100 * changed / n)
```

---

## Changing things later

- **Cases / AI recommendations:** edit the CSVs in `csv/` on GitHub (open file → pencil icon → edit →
  **Commit**). The app updates in about a minute. If a CSV has a mistake, the app shows exactly what's
  wrong.
- **Clinicians:** App → **Settings → Secrets** → edit the `[participants...]` blocks → **Save**.
- **Dashboard height:** if the bottom of the dashboard is cut off or there's too much empty space on
  your screens, add `dashboard_height = 760` (or another number) to Secrets. The default is 680.

## Test on your own computer (optional)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # keep only the [participants] blocks
streamlit run app.py
```

Without the Google settings, decisions go to `data/decisions.csv`.
