import os


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Google Sheets — authenticated as your own Google account (not a service
# account: wso2's Workspace policy blocks sharing with external/service
# identities). Get these three by running get_refresh_token.py once locally.
GOOGLE_OAUTH_CLIENT_ID = _require("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = _require("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_OAUTH_REFRESH_TOKEN = _require("GOOGLE_OAUTH_REFRESH_TOKEN")

# Issues Scan Rotation sheet — owned by the team, you/teammates can edit it.
# Used for the Log tab (daily job writes every real outcome here) and for
# the per-year grid tab (weekly job writes the upcoming week's resolved
# assignments here — column A weekday, column B date, one column per
# person, "Scan" marks who's on duty).
SCAN_SPREADSHEET_ID = _require("SCAN_SPREADSHEET_ID")
LOG_TAB = os.environ.get("LOG_TAB", "Log")
SCAN_SHEET_TAB_OVERRIDE = os.environ.get("SCAN_SHEET_TAB_OVERRIDE") or None  # default: str(year)
SCAN_SHEET_DATE_COLUMN_INDEX = int(os.environ.get("SCAN_SHEET_DATE_COLUMN_INDEX", "1"))  # 0-based; 1 = column B
SCAN_SHEET_DUTY_MARKER = os.environ.get("SCAN_SHEET_DUTY_MARKER", "Scan")
# Manual override: typing this into a person's cell for a date excludes
# them from scan duty that day — takes priority over the Roster/Leave
# sheets, same effect as being on leave. The weekly job preserves any
# cell containing this tag rather than clearing it, so it survives future
# sheet updates once you type it in.
SCAN_SHEET_EXCLUDE_TAG = os.environ.get("SCAN_SHEET_EXCLUDE_TAG", "Skip")

# Company-wide Roster sheet — read-only for you, but readable via your own
# OAuth login (no sharing needed for reading something you can already
# view). One tab per year; a variable-width block of columns per team
# under a merged header (your team's exact header text — see
# ROSTER_TEAM_LABEL); each person's cell holds a status code for that
# date. A duty code (ROSTER_DUTY_CODES) means they're on morning rotation
# and should do the scan; anything not in ROSTER_AVAILABLE_CODES (and not
# blank) means unavailable, whether as primary or as a backup candidate.
ROSTER_SPREADSHEET_ID = _require("ROSTER_SPREADSHEET_ID")
# Falls back to str(year) if unset, but this sheet's tab names don't
# actually follow a predictable per-year pattern (current tab is literally
# "2026 - New", older ones are "ABT Roster Plan 2025", etc.) — so this is
# set explicitly in both workflow files and needs manual updating once a
# year when a new tab appears, rather than relying on auto-detection.
ROSTER_TAB_OVERRIDE = os.environ.get("ROSTER_TAB_OVERRIDE") or None
# A secret, not a plain default — the real value identifies your team and
# shouldn't sit in the public repo.
ROSTER_TEAM_LABEL = _require("ROSTER_TEAM_LABEL")
ROSTER_DATE_COLUMN_INDEX = int(os.environ.get("ROSTER_DATE_COLUMN_INDEX", "1"))  # 0-based; 1 = column B
ROSTER_DATE_FORMAT = os.environ.get("ROSTER_DATE_FORMAT", "%m/%d/%Y")
ROSTER_DUTY_CODES = [
    c.strip() for c in os.environ.get("ROSTER_DUTY_CODES", "6-9am,6-9am-OC").split(",") if c.strip()
]
# A cell containing any of these never counts as duty, even if a duty code
# also appears in it — e.g. "6-9pm/6-9am-OC" is excluded (evening shift
# takes priority), not treated as morning duty.
ROSTER_DUTY_EXCLUDE_CODES = [
    c.strip() for c in os.environ.get("ROSTER_DUTY_EXCLUDE_CODES", "6-9pm,Allo-INT").split(",") if c.strip()
]
ROSTER_AVAILABLE_CODES = [
    c.strip() for c in os.environ.get("ROSTER_AVAILABLE_CODES", "LK").split(",") if c.strip()
]

# Leave sheet — owned by someone else, but shareable. Checked separately
# from the roster because the roster is only updated weekly and can go
# stale if someone takes leave after that week's roster was filled in.
# Real structure: one tab per year ("Leave Plan 2026", ...), and each team
# gets 3 columns (Lead LL/AL | Member LL | Member AL) under a merged
# header matching LEAVE_TEAM_LABEL. Column A holds dates *without* a year
# (e.g. "1-Jan") — LEAVE_DATE_FORMAT describes that, separate from the
# full-date DATE_FORMAT used elsewhere.
LEAVE_SPREADSHEET_ID = _require("LEAVE_SPREADSHEET_ID")
LEAVE_TAB_OVERRIDE = os.environ.get("LEAVE_TAB_OVERRIDE") or None
LEAVE_TAB_PREFIX = os.environ.get("LEAVE_TAB_PREFIX", "Leave Plan ")
# A secret, not a plain default — see ROSTER_TEAM_LABEL above. Not
# necessarily the same text as ROSTER_TEAM_LABEL — the two sheets can
# label the same team differently.
LEAVE_TEAM_LABEL = _require("LEAVE_TEAM_LABEL")
LEAVE_DATE_COLUMN_INDEX = int(os.environ.get("LEAVE_DATE_COLUMN_INDEX", "0"))  # 0-based; 0 = column A
LEAVE_DATE_FORMAT = os.environ.get("LEAVE_DATE_FORMAT", "%d-%b")

# Email is derived directly from the roster's column header, lowercased
# plus this domain — e.g. "PersonA" -> "persona@wso2.com". Only works if
# that pattern actually matches real mailbox names; if it doesn't for some
# people, this needs revisiting (e.g. a lookup table) rather than guessing.
EMAIL_DOMAIN = os.environ.get("EMAIL_DOMAIN", "@wso2.com")

# Exact date format used across your sheets (Python strptime codes), e.g.
# "%m/%d/%Y" for 9/4/2026, "%Y-%m-%d" for 2026-09-04. Set this once you
# know your real sheets' format — pin it down instead of relying on the
# ambiguous auto-guess fallback in google_sheets.parse_date.
DATE_FORMAT = os.environ.get("DATE_FORMAT") or None

# Mail sending — "smtp" (default: Gmail SMTP + app password), "gmail_api"
# (Gmail API via OAuth, reusing the same Google OAuth client already used
# for Sheets access), or "graph" (Microsoft Graph via OAuth, sends as your
# own wso2.com account with delegated Mail.Send — no admin-consented
# application permission needed).
MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER", "smtp").strip().lower()

GMAIL_SENDER_ADDRESS = _require("GMAIL_SENDER_ADDRESS")

GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_API_REFRESH_TOKEN = os.environ.get("GMAIL_API_REFRESH_TOKEN", "")
MS_OAUTH_CLIENT_ID = os.environ.get("MS_OAUTH_CLIENT_ID", "")
MS_OAUTH_TENANT_ID = os.environ.get("MS_OAUTH_TENANT_ID", "")
MS_OAUTH_REFRESH_TOKEN = os.environ.get("MS_OAUTH_REFRESH_TOKEN", "")

if MAIL_PROVIDER == "gmail_api":
    GMAIL_API_REFRESH_TOKEN = _require("GMAIL_API_REFRESH_TOKEN")
elif MAIL_PROVIDER == "graph":
    MS_OAUTH_CLIENT_ID = _require("MS_OAUTH_CLIENT_ID")
    MS_OAUTH_TENANT_ID = _require("MS_OAUTH_TENANT_ID")
    MS_OAUTH_REFRESH_TOKEN = _require("MS_OAUTH_REFRESH_TOKEN")
else:
    GMAIL_APP_PASSWORD = _require("GMAIL_APP_PASSWORD")

# Who gets notified if the automation itself fails or nobody is available
LEAD_ALERT_EMAIL = _require("LEAD_ALERT_EMAIL")

# Scheduling
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Colombo")
SCAN_TIME_LOCAL = os.environ.get("SCAN_TIME_LOCAL", "09:00")

# Length of the "Add to Google Calendar" event block in the reminder email.
CALENDAR_EVENT_MINUTES = int(os.environ.get("CALENDAR_EVENT_MINUTES", "60"))

# Wording only — the team name shown in the reminder email itself.
TEAM_DISPLAY_NAME = os.environ.get("TEAM_DISPLAY_NAME", "Castor Team")

# How many days to look back in the Log before allowing the same person
# to be picked again as a leave-day replacement. Default 7 = won't repeat
# as backup within the same week.
BACKUP_COOLDOWN_DAYS = int(os.environ.get("BACKUP_COOLDOWN_DAYS", "7"))

# Shared by both scripts. Daily job (send_reminder.py): still reads real
# sheets and resolves a real assignment, but emails only LEAD_ALERT_EMAIL
# and skips the Log write. Weekly job (update_scan_sheet.py): still
# resolves real assignments but only prints what it would write, without
# touching the sheet.
TEST_MODE = os.environ.get("TEST_MODE", "false").strip().lower() == "true"

# Nobody's scheduled to scan on weekends (roster cells are blank Sat/Sun),
# so treat that as a normal no-op rather than an error worth alerting on.
SKIP_WEEKENDS = os.environ.get("SKIP_WEEKENDS", "true").strip().lower() == "true"

# Testing aid: override which date is used as the anchor (format
# YYYY-MM-DD), so you can verify the real assignment logic against any
# date on demand instead of waiting for the calendar. send_reminder.py
# treats this as "tomorrow"; update_scan_sheet.py treats it as the Monday
# to start the resolved week from. Leave unset for normal operation.
TARGET_DATE_OVERRIDE = os.environ.get("TARGET_DATE_OVERRIDE") or None
