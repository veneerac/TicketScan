# Daily Scan Reminder Automation

Sends each team member a reminder email 24 hours before their morning
dashboard issue-scan duty. If the scheduled person is on leave, it
automatically reassigns to an available teammate (never repeating the same
backup within a cooldown window) and CCs the team lead so it's visible.

Runs daily via GitHub Actions — no server to maintain, no laptop that needs
to stay on.

## Two spreadsheets

| Sheet | What it's for | Access you already have |
|---|---|---|
| **Issues Scan Rotation sheet** | your team-owned sheet — has `Log` and one roster-grid tab per year (`2026`, `2025`, ...) | Editor |
| **Leave sheet** | someone else's leave plan | Viewer (read-only) |

No new sharing is required for either — the automation authenticates as
*your own* Google account (see setup step 1 below), reusing whatever
access you already have. This also sidesteps a wso2 Workspace policy that
blocks sharing files with external/service-account identities.

The company-wide shift/allocation roster sheet turned out to be
inaccessible (read-only for you, and its owner isn't reachable to grant
sharing), so this automation doesn't read it. Instead, the day-by-day duty
plan lives in the per-year roster-grid tabs inside your own Issues Scan
Rotation sheet, which you maintain manually — including reflecting any
allocation conflict you become aware of from the company roster. The
automation still handles leave automatically by cross-checking the
separate Leave sheet.

Each spreadsheet has its own ID in [config.py](config.py) — see
`SCAN_SPREADSHEET_ID` and `LEAVE_SPREADSHEET_ID`.

## How it decides who gets the email

1. Look up tomorrow's date in the Issues Scan Rotation sheet's roster-grid
   tab for that year → gives the scheduled person.
2. Cross-check the **Leave** sheet for that person. This matters because
   you fill in the roster grid by hand — if someone goes on leave after you
   filled it in, the Leave sheet catches what the roster missed.
3. If there's a conflict, pick a replacement from the roster grid's own
   column headers (anyone else on the team), skipping anyone who is on
   leave or was used as a replacement within the last `BACKUP_COOLDOWN_DAYS`
   days (so it doesn't always fall on the same person).
4. Send the reminder, and log the decision to the **Log** tab.
5. If a reminder for that date was already logged (e.g. triggered twice),
   it skips — no duplicate emails.
6. If anything fails (bad data, nobody scheduled, everyone on leave, API
   error), it emails `LEAD_ALERT_EMAIL` immediately instead of failing
   silently.

## Required Google Sheet structure

**Issues Scan Rotation sheet** — one roster-grid tab per calendar year,
confirmed from real screenshots of "Castor Issues Scan Rotation": tabs are
literally named `2026`, `2025`, `2024`, `2023`, etc. Each is a grid — no
changes needed, this is what you already maintain: column A = weekday,
column B = date, one column per person, `"Scan"` marks who's on duty:

| | Date | PersonA | PersonB | PersonC |
|---|---|---|---|---|
| Friday | 9/4/2026 | | | Scan |
| Saturday | 9/5/2026 | | | |
| Monday | 9/7/2026 | Scan | | |

The script auto-picks the tab matching the target date's year (no
maintenance needed as years roll over) — set `SCAN_ROSTER_TAB_OVERRIDE`
only if a tab is ever named differently than its plain year.
`ROSTER_DATE_COLUMN_INDEX` (default `1`, i.e. column B) and
`ROSTER_DUTY_KEYWORD` (default `"Scan"`) are both configurable if either
ever changes.

No separate Team tab — email is derived straight from each column header:
lowercased, plus `EMAIL_DOMAIN` (default `@wso2.com`). So `DinukaC` →
`dinukac@wso2.com`. This only works if that pattern matches real mailbox
names for everyone; if any don't fit, that needs revisiting rather than
guessing. If the scheduled person is on leave, any other available
teammate from the same column headers is picked as backup — no
priority/ordering, the only rule being nobody repeats as backup within
`BACKUP_COOLDOWN_DAYS` (default `7`, i.e. once a week).

**Issues Scan Rotation sheet** — `Log` tab (new, leave empty but for a
header row; the script appends to it):
| DateSent | ForDate | AssignedName | AssignedEmail | WasReplacement | Reason |
|---|---|---|---|---|---|

**Leave sheet** — still needs confirming (the "Castor (Team 2)" sheet with
`Member AL` / `Member LL` / `Lead LL/AL` columns you described). One row
per leave period is the current guess:
| Name | StartDate | EndDate |
|---|---|---|
| PersonB | 9/5/2026 | 9/6/2026 |

If it's actually a grid like Roster (one row per date, names typed into
whichever leave-type column applies), that needs a different reader — send
a screenshot the same way you did for Roster and I'll match it exactly.

**`DATE_FORMAT` is set to `%m/%d/%Y`** in [config.py](config.py) / the
workflow, matching the confirmed `9/4/2026`-style dates in your real
sheets. Dates like this are ambiguous between day-first and month-first —
this is pinned explicitly rather than auto-detected, so don't change it
unless your sheets' actual format changes.

## One-time setup

### 1. Google Sheets access (OAuth as your own account)

A service account was the original plan, but wso2's Google Workspace policy
blocks sharing files with external/service-account identities. So instead,
the automation authenticates as *your own* Google account — you already
have edit access to the Scan Rotation sheet and view access to Leave, so
no new sharing is needed at all.

1. In Google Cloud Console, create/select a project → enable the
   **Google Sheets API**.
2. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**.
   - If prompted to configure the consent screen first: choose **External**
     (or **Internal** if your Cloud project is under wso2's Workspace org),
     fill in an app name (e.g. "Scan Reminder"), your email as support/dev
     contact, save through the remaining steps — you don't need to submit
     for verification for personal/internal use.
   - Application type: **Desktop app** → name it → **Create**.
   - Copy the **Client ID** and **Client Secret** shown.
3. On your own machine: `pip install google-auth-oauthlib`, then
   `python get_refresh_token.py` from this project folder. It'll ask for
   the Client ID/Secret, open a browser for you to log into your wso2
   Google account and approve access, then print a **refresh token**.
4. That refresh token, plus the Client ID and Secret, are the three
   credentials — never paste them anywhere but GitHub Secrets (step 3
   below). If this token ever leaks, revoke it at
   [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
   and re-run `get_refresh_token.py` for a new one.

### 2. Gmail access (send mail via SMTP + app password)

No admin needed — just the Gmail account you want reminders to be sent
from (can be a personal Gmail, or a shared/team Gmail address you control):

1. On that Gmail account, turn on **2-Step Verification**
   (myaccount.google.com/security) — app passwords only appear once this
   is on.
2. Go to myaccount.google.com/apppasswords → create one (name it e.g.
   "scan-reminder") → copy the 16-character password shown.
3. That's it — no Google Cloud project needed for this part (that's only
   for the Sheets API access in step 1).

**Note:** this is separate from the Google Sheets access in step 1 — that
one only reads/writes the spreadsheets; this one only sends mail. They can
be different Google accounts if convenient.

### 3. GitHub repository secrets

Add these under **Settings → Secrets and variables → Actions → New
repository secret** on [veneerac/TicketScan](https://github.com/veneerac/TicketScan):

| Secret | Value |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | from step 1 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | from step 1 |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | printed by `get_refresh_token.py` in step 1 |
| `SCAN_SPREADSHEET_ID` | ID from the Issues Scan Rotation sheet's URL (`.../d/<this part>/edit`) |
| `LEAVE_SPREADSHEET_ID` | ID from the Leave sheet's URL |
| `GMAIL_SENDER_ADDRESS` | the Gmail address reminders are sent from, from step 2 |
| `GMAIL_APP_PASSWORD` | the 16-character app password, from step 2 |
| `LEAD_ALERT_EMAIL` | your email, for failure/leave-conflict alerts |

### 4. Adjust timing if needed

Default assumes the scan happens at **09:00 Asia/Colombo**, so the reminder
fires at 03:30 UTC (24h before). If your scan time is different, update
both the `cron` line and the `SCAN_TIME_LOCAL` value in
`.github/workflows/daily-reminder.yml`.

### 5. Test it

- `Actions` tab → `Daily Scan Reminder` → `Run workflow` to trigger it
  manually anytime, without waiting for the schedule.
- To test locally: `pip install -r requirements.txt`, export the same
  env vars the workflow uses, then `python send_reminder.py`.

## Reliability notes

- **Idempotent**: re-running the same day won't double-send.
- **Self-alerting**: any failure (bad roster data, everyone on leave, API
  errors) emails `LEAD_ALERT_EMAIL` immediately, and GitHub also marks the
  Actions run as failed (visible in the Actions tab, and GitHub emails repo
  watchers on scheduled-workflow failures by default).
- **GitHub Actions schedules are UTC and best-effort** — GitHub documents
  that scheduled runs can occasionally be delayed by a few minutes during
  high load. For a same-day reminder that's a non-issue; if you need
  guaranteed to-the-minute delivery, consider triggering this same script
  from your company's own scheduler instead (Azure Function timer, Power
  Automate, or a cron job on an internal server) — the script itself
  doesn't care what triggers it.
