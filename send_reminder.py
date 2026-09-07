import datetime
import html
import sys
import traceback

from zoneinfo import ZoneInfo

import config
import google_sheets
import gmail_mail
import scan_logic


def tomorrow_local() -> datetime.date:
    if config.TARGET_DATE_OVERRIDE:
        return datetime.datetime.strptime(config.TARGET_DATE_OVERRIDE, "%Y-%m-%d").date()
    now_local = datetime.datetime.now(ZoneInfo(config.TIMEZONE))
    return (now_local + datetime.timedelta(days=1)).date()


def build_email(assignment: scan_logic.Assignment, target_date: datetime.date) -> tuple[str, str]:
    subject = f"Ticket Scan Reminder Tomorrow ({target_date.isoformat()})"
    note = (
        f"<br>(You're covering for {assignment.primary_name}, who is on leave.)"
        if assignment.is_replacement
        else ""
    )
    body = (
        f"Hello,<br>"
        f"Kind reminder, you have been allocated to do the {config.TEAM_DISPLAY_NAME} "
        f"ticket scan for tomorrow, {target_date.strftime('%A, %d %B %Y')}.{note}"
        f"<br><br><i>This is an auto-generated email.</i>"
    )
    return subject, body


def send_failure_alert(error_text: str) -> None:
    try:
        # Escape before embedding in HTML — raw tracebacks often contain
        # "<...>"-shaped text (e.g. "<HttpError 400 ...>") that would
        # otherwise be swallowed as an invalid HTML tag by the email client,
        # silently truncating the visible error right where it starts.
        safe_error_text = html.escape(error_text)
        gmail_mail.send_mail(
            sender_address=config.GMAIL_SENDER_ADDRESS,
            app_password=config.GMAIL_APP_PASSWORD,
            to_addresses=[config.LEAD_ALERT_EMAIL],
            subject="[ACTION NEEDED] Scan reminder automation failed",
            body_html=f"<p>The daily scan-reminder job failed:</p><pre>{safe_error_text}</pre>"
            f"<p>No reminder may have been sent for tomorrow's scan — please check "
            f"and assign someone manually if needed.</p>",
        )
    except Exception:
        # Best-effort only — don't let a failed alert mask the original error.
        traceback.print_exc()


def main() -> int:
    try:
        target_date = tomorrow_local()

        if config.SKIP_WEEKENDS and target_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            print(f"{target_date.isoformat()} is a weekend — no scan duty, skipping.")
            return 0

        sheets = google_sheets.get_service(
            config.GOOGLE_OAUTH_CLIENT_ID,
            config.GOOGLE_OAUTH_CLIENT_SECRET,
            config.GOOGLE_OAUTH_REFRESH_TOKEN,
        )
        roster_tab = config.ROSTER_TAB_OVERRIDE or str(target_date.year)
        leave_tab = config.LEAVE_TAB_OVERRIDE or f"{config.LEAVE_TAB_PREFIX}{target_date.year}"
        scan_tab = config.SCAN_SHEET_TAB_OVERRIDE or str(target_date.year)

        roster_grid = google_sheets.read_grid(sheets, config.ROSTER_SPREADSHEET_ID, roster_tab)
        leave_grid = google_sheets.read_grid(sheets, config.LEAVE_SPREADSHEET_ID, leave_tab)
        scan_grid = google_sheets.read_grid(sheets, config.SCAN_SPREADSHEET_ID, scan_tab)
        log_rows = google_sheets.read_rows(sheets, config.SCAN_SPREADSHEET_ID, config.LOG_TAB)

        roster_schedule = scan_logic.parse_roster_grid(
            roster_grid, config.ROSTER_TEAM_LABEL,
            config.ROSTER_DATE_COLUMN_INDEX, config.ROSTER_DATE_FORMAT,
        )
        # Filter out anyone still listed in the company Roster sheet who's
        # no longer on the team — the Issues Scan sheet's own column
        # headers are the authoritative "who's actually here" list.
        active_names = scan_logic.active_team_names(scan_grid, config.SCAN_SHEET_DATE_COLUMN_INDEX)
        roster_schedule = scan_logic.filter_active_roster(roster_schedule, active_names)

        leave_schedule = scan_logic.parse_leave_grid(
            leave_grid, config.LEAVE_TEAM_LABEL, target_date.year,
            config.LEAVE_DATE_COLUMN_INDEX, config.LEAVE_DATE_FORMAT,
        )

        if config.TEST_MODE:
            print("=== TEST_MODE is ON: no real email, no Log write ===")
        elif scan_logic.already_sent(log_rows, target_date, config.DATE_FORMAT):
            print(f"Reminder for {target_date.isoformat()} already sent — skipping.")
            return 0

        assignment = scan_logic.resolve_assignment(
            target_date, roster_schedule, config.ROSTER_DUTY_CODES, config.ROSTER_DUTY_EXCLUDE_CODES,
            config.ROSTER_AVAILABLE_CODES, leave_schedule, log_rows, config.BACKUP_COOLDOWN_DAYS,
            config.EMAIL_DOMAIN, config.DATE_FORMAT,
        )

        subject, body = build_email(assignment, target_date)

        if config.TEST_MODE:
            gmail_mail.send_mail(
                sender_address=config.GMAIL_SENDER_ADDRESS,
                app_password=config.GMAIL_APP_PASSWORD,
                to_addresses=[config.LEAD_ALERT_EMAIL],
                cc_addresses=None,
                subject=f"[TEST MODE] {subject}",
                body_html=f"<p><b>Real recipient would have been: {assignment.name} "
                f"&lt;{assignment.email}&gt;</b></p><hr>{body}",
            )
            print(
                f"[TEST MODE] Would have assigned {assignment.name} <{assignment.email}> "
                f"for {target_date} ({assignment.reason}). Sent preview to {config.LEAD_ALERT_EMAIL} instead."
            )
            return 0

        gmail_mail.send_mail(
            sender_address=config.GMAIL_SENDER_ADDRESS,
            app_password=config.GMAIL_APP_PASSWORD,
            to_addresses=[assignment.email],
            cc_addresses=[config.LEAD_ALERT_EMAIL] if assignment.from_pool else None,
            subject=subject,
            body_html=body,
        )

        google_sheets.append_row(
            sheets,
            config.SCAN_SPREADSHEET_ID,
            config.LOG_TAB,
            [
                datetime.date.today().isoformat(),
                target_date.isoformat(),
                assignment.name,
                assignment.email,
                # This column drives the 7-day no-repeat cooldown, so it
                # records from_pool (any time the script had to choose
                # someone) rather than strictly "covering for leave."
                "TRUE" if assignment.from_pool else "FALSE",
                assignment.reason,
            ],
        )
        print(f"Sent reminder to {assignment.name} <{assignment.email}> for {target_date}.")
        return 0

    except Exception:
        error_text = traceback.format_exc()
        print(error_text, file=sys.stderr)
        send_failure_alert(error_text)
        return 1


if __name__ == "__main__":
    sys.exit(main())
