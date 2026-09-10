# Daily Scan Reminder Automation

Two scheduled jobs, both reading the same company-wide Roster and Leave
sheets:

- **Daily reminder** ([send_reminder.py](send_reminder.py)) — emails
  whoever's actually on morning rotation tomorrow, 24 hours ahead.
  Automatically reassigns to an available teammate if there's a leave
  conflict (never repeating the same backup within a cooldown window),
  CCing the team lead so it's visible.
- **Weekly sheet update** ([update_scan_sheet.py](update_scan_sheet.py)) —
  once a week, resolves the whole upcoming Monday–Friday in one go and
  writes the results into your own Issues Scan Rotation sheet, so the
  whole week is visible in advance instead of finding out one day at a
  time. Safely re-runnable — if leave changes mid-week, running it again
  corrects the sheet rather than duplicating anything.

Both run via GitHub Actions — no server to maintain, no laptop that needs
to stay on.

## Three spreadsheets

| Sheet | What it's for | Access you already have |
|---|---|---|
| **Roster sheet** | company-wide shift/allocation roster | Viewer (read-only) |
| **Leave sheet** | company-wide leave plan | Viewer (read-only) |
| **Issues Scan Rotation sheet** | your team-owned sheet — `Log` tab (daily job) and the per-year grid tab (weekly job) | Editor |

No new sharing is required for any of these — the automation authenticates
as *your own* Google account (see setup step 1 below), reusing whatever
access you already have. This also sidesteps a wso2 Workspace policy that
blocks sharing files with external/service-account identities: since the
script logs in as you rather than a separate identity, it can read
anything you can already view, with no new grant needed.

Roster and Leave are both read-only, always — neither job ever writes to
either. The daily job's only write is appending a row to the Log tab; the
weekly job's only write is the per-year grid tab in your own Issues Scan
Rotation sheet (clearing/setting `"Scan"` markers for the upcoming week).

## How it decides who gets the email

0. **If tomorrow is a Saturday or Sunday, skip entirely** — nobody's
   scheduled to scan on weekends, so this is a normal no-op (no email, no
   Log write, no failure alert), not an error. Controlled by
   `SKIP_WEEKENDS` (default `true`).
1. **Check your own Issues Scan Rotation sheet first** — if tomorrow's row
   already has someone marked with `SCAN_SHEET_DUTY_MARKER` (default
   `"Scan"`), whether written by the weekly job or typed in by hand, that's
   who's primary. This is what makes a manual override in that sheet
   actually stick.
2. **Only if that sheet has no entry at all for tomorrow**, fall back to
   the company **Roster** sheet's team columns (found by matching the
   `ROSTER_TEAM_LABEL` secret) → whoever's cell **contains** `6-9am` or
   `6-9am-OC` (not necessarily an exact match) **and doesn't also contain
   `6-9pm`** is on morning rotation. A compound cell like `6-9pm/6-9am-oc`
   is excluded, not treated as duty — the evening shift takes priority (see
   `ROSTER_DUTY_EXCLUDE_CODES` below).
   - **If neither sheet has anyone explicitly marked, that's not an
     error** — it just means anyone available can do it, so the script
     picks from the same available pool used for replacements (step 4).
3. Whoever came out of step 1 or 2, **re-validate them daily against three
   things** regardless of which sheet named them — a Roster edit made
   *after* the weekly job already wrote the Issues Scan sheet is still
   caught this way:
   - the **Leave** sheet (leave taken after the Roster/Issues Scan sheet
     was filled in),
   - the `SCAN_SHEET_EXCLUDE_TAG` (default `"Skip"`) tag in the Issues Scan
     sheet, and
   - their own **current** Roster cell for that day — anything other than
     blank, an `ROSTER_AVAILABLE_CODES` code (e.g. `LK`), or one of the
     duty codes itself (still on duty per Roster, which is fine) counts as
     a conflict.
4. If there's a conflict (or nobody was explicitly marked in steps 1–2),
   pick from the team's Roster columns, skipping anyone who is:
   - on leave (Leave sheet), **or**
   - marked with anything other than blank/`LK` in their own Roster cell
     that day (their own allocation, evening shift, leave, etc. — see
     `ROSTER_AVAILABLE_CODES` below), **or**
   - manually excluded via the `Skip` tag, **or**
   - used as a pick (leave replacement, or picked via this same fallback)
     within the last `BACKUP_COOLDOWN_DAYS` days (so it doesn't always
     fall on the same person — this applies whether the pick was because
     of someone's leave *or* because nobody was explicitly on duty).
5. Send the reminder — includes an **"Add to Google Calendar" button**
   (a pre-filled event, `CALENDAR_EVENT_MINUTES` long starting at
   `SCAN_TIME_LOCAL`) that the recipient can click to save it to their own
   calendar; nothing is added automatically or shared, only the person who
   clicks it is affected — and log the decision to the **Log** tab (in
   your own Issues Scan Rotation sheet — the only sheet this automation
   ever writes to, and only this one tab).
6. If a reminder for that date was already logged (e.g. triggered twice),
   it skips — no duplicate emails.
7. If anything fails (bad data, everyone unavailable,
   API error), it emails `LEAD_ALERT_EMAIL` immediately instead of failing
   silently.

**Note:** the company Roster sheet is read-only for you, so nothing there
ever changes automatically — the Log tab is the full record of every real
outcome. The one sheet that *does* get written automatically is your own
Issues Scan Rotation sheet's per-year grid tab, via the separate weekly
job described next — and the daily job reads that same tab first, before
ever falling back to the Roster.

## Weekly Issues Scan sheet update

Runs once a week (before the work week starts) and, for the upcoming
Monday–Friday:

1. Resolves who's actually assigned each day — always Roster-first (Roster
   lookup, Leave cross-check, reassignment with the same allowlist and
   cooldown rules the daily job uses for its own fallback picks), since
   this job's whole purpose is to (re-)compute fresh from Roster+Leave
   rather than trust whatever's already written. The cooldown also
   accounts for picks made *earlier in the same weekly run*, so the same
   person doesn't end up covering two days in one week just because
   neither was logged yet.
2. For each day, clears every person's cell in that date's row in your
   Issues Scan Rotation sheet's per-year grid tab, then writes
   `SCAN_SHEET_DUTY_MARKER` (default `"Scan"`) into the resolved person's
   cell — same visual format as the sheet always had, just filled in
   automatically instead of by hand.
3. If a date's row doesn't exist yet in that tab, it's skipped with a
   warning rather than failing the whole run — add the row (or extend the
   sheet further into the year) if that happens.

The weekly job only edits the sheet, it never sends email — but the daily
job reads that sheet as its first source of "who's assigned" (see step 1
above), falling back to the Roster only when the weekly job (or a manual
edit) hasn't filled in that date yet. So the two aren't fully independent
by design: the weekly job's writes are what the daily job normally acts
on. Either can still run on its own without the other — the daily job just
falls back to computing fresh from Roster+Leave if the weekly job hasn't
run yet for that date.

## Filtering out people who've left the team

The company Roster sheet isn't yours to maintain, so it can go stale —
someone who's left the team might still have a column there. Both jobs
read your Issues Scan Rotation sheet's per-year grid tab **just for its
header row** and treat that as the authoritative "who's actually still
here" list — anyone in the Roster sheet whose name doesn't match one of
those headers (same fuzzy first-name-vs-initial matching used for the
Leave sheet) is dropped before picking a primary or a backup. So removing
someone from your own sheet's header row is enough to stop them ever being
selected, even if the company Roster sheet still lists them.

**Note:** hiding a column (vs. deleting it) doesn't work for this — hidden
columns are only a display setting, the Sheets API still returns their
data, so a hidden person would still be eligible. Delete the column, or at
minimum clear their header cell, to actually exclude them.

## Manually excluding someone for a specific date

Sometimes you know something the Roster/Leave sheets don't — type
`SCAN_SHEET_EXCLUDE_TAG` (default `"Skip"`) into that person's cell for a
specific date in your Issues Scan Rotation sheet, and they're excluded
from being picked for that date, whether as the scheduled person or as a
backup — same effect as being on leave, but controlled entirely by you in
your own sheet. The weekly job never overwrites a cell that already
contains this tag, so once typed in, it survives future weekly runs
instead of getting cleared.

## Required Google Sheet structure

**Roster sheet** — one tab per year (`2026`, ...). Column A = weekday,
column B = date. Each team gets a block of columns (one per person) under
a merged header with the team's name (confirmed from a real screenshot —
the exact text lives in the `ROSTER_TEAM_LABEL` secret, not shown here).
A few summary rows can sit above the header row; the script finds it by
searching, not by a fixed row number. Each person's cell holds a status
code for that date:

| | Date | PersonA | PersonB | PersonC |
|---|---|---|---|---|
| Mon | 9/7/2026 | LK | 6-9am | LK |
| Tue | 9/8/2026 | LL | LK | 6-9am |

- `ROSTER_DUTY_CODES` (default `6-9am,6-9am-OC`) — if a cell **contains**
  any of these (not necessarily an exact match), that person is on
  morning rotation and should do the scan — *unless* the cell also
  contains one of `ROSTER_DUTY_EXCLUDE_CODES` (default `6-9pm`), in which
  case it's excluded instead. So `6-9am-OC` alone counts as duty, but
  `6-9pm/6-9am-oc` doesn't — the evening shift marker overrides. If nobody
  in the team has a matching cell that day, that's not an error — the
  script falls back to picking anyone available (same rules as
  `ROSTER_AVAILABLE_CODES` below).
- `ROSTER_AVAILABLE_CODES` (default `LK`) — for anyone being considered as
  a **backup**, only these codes (or a blank cell) count as available.
  **Everything else excludes them** — `LL`, `AL`, `Allo-EXT`, `Allo-INT`,
  `Mig`, `IND`, `NLK`, `6-9pm`, or any code not yet seen. This is
  deliberately a safe allowlist rather than an exhaustive denylist, so an
  unrecognized future code can't accidentally let someone unavailable get
  picked.
- `ROSTER_TEAM_LABEL` (GitHub secret — no public default, since the real
  value identifies your team) is the exact header text the script
  searches for to find your team's columns.
- Unlike the other two sheets, this one's tab names **don't follow a
  predictable per-year pattern** — the current tab is `2026 - New`, but
  older ones are `ABT Roster Plan 2025`, `ABT Roster Plan 2024`, etc. Since
  there's nothing consistent to auto-detect, `ROSTER_TAB_OVERRIDE` is
  hardcoded to `2026 - New` in both workflow files and **needs manually
  updating once a year** when this sheet's owner creates the next tab —
  check what it's actually named rather than assuming a pattern.
- Email is derived from each column header, lowercased, plus
  `EMAIL_DOMAIN` (default `@wso2.com`) — e.g. `PersonA` → `persona@wso2.com`.
  This only works if that pattern matches real mailbox names for everyone;
  if it doesn't for someone, that needs revisiting rather than guessing.

**Leave sheet** — confirmed from real screenshots of "Integration ABT
Leave Plan". Also one tab per year (`Leave Plan 2026`, `Leave Plan 2025`,
...), shaped differently from Roster: column A holds dates *without a
year* (`19-Jan`, `20-Jan`, ...), and every team shares this one sheet —
each gets 3 columns under a merged header with the team's name, e.g.:

| Date | ... | (team label) | | | ... |
|---|---|---|---|---|---|
| | | Lead LL/AL | Member LL | Member AL | |
| 19-Jan | | | PersonA | PersonB | |
| 20-Jan | | | PersonB | PersonC | |

Whoever's on leave has their name typed into whichever of those 3 columns
matches their role/leave-type — any name in any of the 3 columns counts as
"on leave" that day, regardless of which specific column. `LEAVE_TEAM_LABEL`
(GitHub secret, same reasoning as `ROSTER_TEAM_LABEL`) — note this is a
**different label** than the Roster sheet's team label, since the two
sheets happen to name the team differently. `LEAVE_DATE_FORMAT` (default
`"%d-%b"`) matches the year-less date format — the missing year comes from
the tab name itself (`Leave Plan 2026` → 2026).

**Name matching is fuzzy on purpose**: the Leave sheet often uses first
names only (e.g. `Amal`), while Roster uses first-name+initial (e.g.
`AmalP`) — matching allows either to be a prefix of the other, so this
bridges automatically. If any name is ambiguous under this rule (two Roster
people share the same first-name prefix), that needs a closer look rather
than relying on this fallback.

**Issues Scan Rotation sheet** — `Log` tab (leave empty but for a header
row; the script appends to it):
| DateSent | ForDate | AssignedName | AssignedEmail | WasReplacement | Reason |
|---|---|---|---|---|---|

**`DATE_FORMAT` is set to `%m/%d/%Y`** (also used as `ROSTER_DATE_FORMAT`)
in [config.py](config.py) / the workflow, matching the confirmed
`9/4/2026`-style dates. Dates like this are ambiguous between day-first
and month-first — this is pinned explicitly rather than auto-detected, so
don't change it unless your sheets' actual format changes.

## One-time setup

### 1. Google Sheets access (OAuth as your own account)

A service account was the original plan, but wso2's Google Workspace policy
blocks sharing files with external/service-account identities. So instead,
the automation authenticates as *your own* Google account — you already
have view access to Roster and Leave, and edit access to the Scan
Rotation sheet, so no new sharing is needed at all.

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

### 2. Gmail access (two options)

**Option A — SMTP + app password** (default, `MAIL_PROVIDER=smtp`). No
admin needed — just the Gmail account you want reminders sent from (can
be a personal Gmail, or a shared/team address you control):

1. On that Gmail account, turn on **2-Step Verification**
   (myaccount.google.com/security) — app passwords only appear once this
   is on.
2. Go to myaccount.google.com/apppasswords → create one (name it e.g.
   "scan-reminder") → copy the 16-character password shown.
3. That's it — no Google Cloud project needed for this part.

**Note:** this is separate from the Google Sheets access in step 1 — that
one only reads the spreadsheets and writes the Log tab; this one only
sends mail. They can be different Google accounts if convenient.

**Option B — Gmail API via OAuth** (`MAIL_PROVIDER=gmail_api`). Try this
if App Passwords aren't available on the account you want to send from
(e.g. blocked by Workspace policy) — it reuses the same OAuth Client
ID/Secret from step 1, no new Google Cloud app or Microsoft Entra needed:

1. In the same Google Cloud project from step 1: **APIs & Services →
   Library** → search "Gmail API" → **Enable**.
2. On your own machine: `pip install google-auth-oauthlib`, then
   `python get_gmail_send_token.py`. It asks for the same Client ID/Secret
   from step 1, opens a browser for you to log into whichever account
   you want to send from, and approve sending mail on your behalf, then
   prints a refresh token.
3. There's no way to know in advance whether this will work for a given
   account — some Workspace setups provision Sheets/Drive but not Gmail
   itself for a given identity, in which case this fails for a different
   reason than the App Password block did. If it doesn't work, fall back
   to Option A.

### 3. GitHub repository secrets

Add these under **Settings → Secrets and variables → Actions → New
repository secret** on [veneerac/TicketScan](https://github.com/veneerac/TicketScan):

| Secret | Value |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | from step 1 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | from step 1 |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | printed by `get_refresh_token.py` in step 1 |
| `ROSTER_SPREADSHEET_ID` | ID from the company Roster sheet's URL (`.../d/<this part>/edit`) |
| `ROSTER_TEAM_LABEL` | the exact merged-header text for your team in the Roster sheet |
| `LEAVE_SPREADSHEET_ID` | ID from the Leave sheet's URL |
| `LEAVE_TEAM_LABEL` | the exact merged-header text for your team in the Leave sheet (may differ from `ROSTER_TEAM_LABEL`) |
| `SCAN_SPREADSHEET_ID` | ID from the Issues Scan Rotation sheet's URL (holds the Log tab) |
| `GMAIL_SENDER_ADDRESS` | the address reminders are sent from, from step 2 |
| `GMAIL_APP_PASSWORD` | the 16-character app password, from step 2 Option A (skip if using Option B) |
| `GMAIL_API_REFRESH_TOKEN` | printed by `get_gmail_send_token.py`, from step 2 Option B (skip if using Option A) |
| `LEAD_ALERT_EMAIL` | your email, for failure/leave-conflict alerts |

These are shared by both workflows — nothing extra to add for the weekly
job. To switch from Option A to Option B (or back), change `MAIL_PROVIDER`
in both workflow files (`"smtp"` or `"gmail_api"`) — it isn't a secret,
just a plain setting near the other env vars.

### 4. Adjust timing if needed

Daily reminder default assumes the scan happens at **09:00 Asia/Colombo**,
so it fires at 03:30 UTC (24h before) — update both the `cron` line and
`SCAN_TIME_LOCAL` in `.github/workflows/daily-reminder.yml` if different.

Weekly update default fires **Sunday 18:00 Asia/Colombo** (12:30 UTC) —
adjust the `cron` line in `.github/workflows/weekly-scan-sheet-update.yml`
if you want it earlier/later, as long as it's before Monday.

### 5. Test it safely

Both workflows' `Run workflow` forms have a **Test mode** checkbox —
**checked by default**, so a manual run is safe unless you explicitly
uncheck it:

- **Daily reminder, test mode ON**: still reads your real sheets and
  resolves a real assignment, but sends the preview only to
  `LEAD_ALERT_EMAIL` — never the real person — and skips the Log write.
- **Weekly update, test mode ON**: still resolves real assignments for the
  whole week, but only *prints* what it would write (visible in the run's
  log) instead of touching the Issues Scan sheet.
- **Test mode OFF** (either): the real action happens — real person
  emailed / Log row written, or the sheet actually updated. Only uncheck
  once a test-mode run looks right.

Both forms also have a **Target date** field (`YYYY-MM-DD`), normally left
blank:
- Daily reminder: treats that date as "tomorrow" — useful since weekends
  are skipped, so testing on a Friday would otherwise be a no-op.
- Weekly update: treats that date as the Monday to resolve the week from —
  useful to preview a future week without waiting for Sunday.

To test locally instead: `pip install -r requirements.txt`, export the
same env vars the workflow uses (including `TEST_MODE=true`), then
`python send_reminder.py`.

## Reliability notes

- **Idempotent**: re-running the same day won't double-send.
- **Self-alerting**: any failure (bad roster data, everyone unavailable,
  API errors) emails `LEAD_ALERT_EMAIL` immediately, and GitHub also marks
  the Actions run as failed (visible in the Actions tab, and GitHub emails
  repo watchers on scheduled-workflow failures by default).
- **GitHub Actions schedules are UTC and best-effort** — GitHub documents
  that scheduled runs can occasionally be delayed by a few minutes during
  high load. For a same-day reminder that's a non-issue; if you need
  guaranteed to-the-minute delivery, consider triggering this same script
  from your company's own scheduler instead (Azure Function timer, Power
  Automate, or a cron job on an internal server) — the script itself
  doesn't care what triggers it.
