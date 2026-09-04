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
# Holds: one roster-grid tab per calendar year (literally named "2026",
# "2025", ... — column A weekday, column B date, one column per person,
# "Scan" marks who's on duty), and Log (the script writes here).
SCAN_SPREADSHEET_ID = _require("SCAN_SPREADSHEET_ID")
LOG_TAB = os.environ.get("LOG_TAB", "Log")
ROSTER_DATE_COLUMN_INDEX = int(os.environ.get("ROSTER_DATE_COLUMN_INDEX", "1"))  # 0-based; 1 = column B
ROSTER_DUTY_KEYWORD = os.environ.get("ROSTER_DUTY_KEYWORD", "Scan")
# Leave unset (the normal case) to auto-pick the tab matching the target
# date's year (e.g. "2026") — set only to override that, e.g. if a tab is
# ever named differently than its plain year.
SCAN_ROSTER_TAB_OVERRIDE = os.environ.get("SCAN_ROSTER_TAB_OVERRIDE") or None

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
LEAVE_TEAM_LABEL = os.environ.get("LEAVE_TEAM_LABEL", "Castor (Team 2)")
LEAVE_DATE_COLUMN_INDEX = int(os.environ.get("LEAVE_DATE_COLUMN_INDEX", "0"))  # 0-based; 0 = column A
LEAVE_DATE_FORMAT = os.environ.get("LEAVE_DATE_FORMAT", "%d-%b")

# Email is derived directly from the roster's column header, lowercased
# plus this domain — e.g. "DinukaC" -> "dinukac@wso2.com". Only works if
# that pattern actually matches real mailbox names; if it doesn't for some
# people, this needs revisiting (e.g. a lookup table) rather than guessing.
EMAIL_DOMAIN = os.environ.get("EMAIL_DOMAIN", "@wso2.com")

# Exact date format used across your sheets (Python strptime codes), e.g.
# "%m/%d/%Y" for 9/4/2026, "%Y-%m-%d" for 2026-09-04. Set this once you
# know your real sheets' format — pin it down instead of relying on the
# ambiguous auto-guess fallback in google_sheets.parse_date.
DATE_FORMAT = os.environ.get("DATE_FORMAT") or None

# Gmail (sending mail via SMTP + app password)
GMAIL_SENDER_ADDRESS = _require("GMAIL_SENDER_ADDRESS")
GMAIL_APP_PASSWORD = _require("GMAIL_APP_PASSWORD")

# Who gets notified if the automation itself fails or nobody is available
LEAD_ALERT_EMAIL = _require("LEAD_ALERT_EMAIL")

# Scheduling
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Colombo")
SCAN_TIME_LOCAL = os.environ.get("SCAN_TIME_LOCAL", "09:00")

# How many days to look back in the Log before allowing the same person
# to be picked again as a leave-day replacement. Default 7 = won't repeat
# as backup within the same week.
BACKUP_COOLDOWN_DAYS = int(os.environ.get("BACKUP_COOLDOWN_DAYS", "7"))

# When true: still reads real sheets and resolves a real assignment, but
# sends the email only to LEAD_ALERT_EMAIL (not the real person), and skips
# writing to the Log tab or the roster grid — so nothing real gets touched.
TEST_MODE = os.environ.get("TEST_MODE", "false").strip().lower() == "true"

# Nobody's scheduled to scan on weekends (roster cells are blank Sat/Sun),
# so treat that as a normal no-op rather than an error worth alerting on.
SKIP_WEEKENDS = os.environ.get("SKIP_WEEKENDS", "true").strip().lower() == "true"

# Testing aid: override which date is treated as "tomorrow" (format
# YYYY-MM-DD), so you can verify the real assignment logic against any
# weekday on demand instead of waiting for the calendar. Leave unset for
# normal operation — real runs always use the actual tomorrow.
TARGET_DATE_OVERRIDE = os.environ.get("TARGET_DATE_OVERRIDE") or None
