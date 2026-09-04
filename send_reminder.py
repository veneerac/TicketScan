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
    now_local = datetime.datetime.now(ZoneInfo(config.TIMEZONE))
    return (now_local + datetime.timedelta(days=1)).date()


def build_email(assignment: scan_logic.Assignment, target_date: datetime.date) -> tuple[str, str]:
    subject = f"Reminder: Issue scan duty tomorrow ({target_date.isoformat()})"
    note = (
        f"(You're covering for {assignment.primary_name}, who is on leave.)"
        if assignment.is_replacement
        else ""
    )
    body = f"""
    <p>Hi {assignment.name},</p>
    <p>This is a reminder that <b>you're on morning issue-scan duty tomorrow,
    {target_date.strftime('%A, %d %B %Y')}</b> at {config.SCAN_TIME_LOCAL}
    ({config.TIMEZONE}).</p>
    <p>Please run the dashboard scan as usual. {note}</p>
    <p>Thanks!</p>
    """
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
        sheets = google_sheets.get_service(
            config.GOOGLE_OAUTH_CLIENT_ID,
            config.GOOGLE_OAUTH_CLIENT_SECRET,
            config.GOOGLE_OAUTH_REFRESH_TOKEN,
        )
        target_date = tomorrow_local()
        roster_tab = config.SCAN_ROSTER_TAB_OVERRIDE or str(target_date.year)
        leave_tab = config.LEAVE_TAB_OVERRIDE or f"{config.LEAVE_TAB_PREFIX}{target_date.year}"

        roster_grid = google_sheets.read_grid(sheets, config.SCAN_SPREADSHEET_ID, roster_tab)
        leave_grid = google_sheets.read_grid(sheets, config.LEAVE_SPREADSHEET_ID, leave_tab)
        log_rows = google_sheets.read_rows(sheets, config.SCAN_SPREADSHEET_ID, config.LOG_TAB)

        roster_schedule = scan_logic.parse_roster_grid(
            roster_grid, config.ROSTER_DATE_COLUMN_INDEX, config.DATE_FORMAT
        )
        leave_schedule = scan_logic.parse_leave_grid(
            leave_grid, config.LEAVE_TEAM_LABEL, target_date.year,
            config.LEAVE_DATE_COLUMN_INDEX, config.LEAVE_DATE_FORMAT,
        )

        if config.TEST_MODE:
            print("=== TEST_MODE is ON: no real email, no Log write, no roster write-back ===")
        elif scan_logic.already_sent(log_rows, target_date, config.DATE_FORMAT):
            print(f"Reminder for {target_date.isoformat()} already sent — skipping.")
            return 0

        assignment = scan_logic.resolve_assignment(
            target_date, roster_schedule, leave_schedule, log_rows,
            config.BACKUP_COOLDOWN_DAYS, config.ROSTER_DUTY_KEYWORD,
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
            cc_addresses=[config.LEAD_ALERT_EMAIL] if assignment.is_replacement else None,
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
                "TRUE" if assignment.is_replacement else "FALSE",
                assignment.reason,
            ],
        )
        print(f"Sent reminder to {assignment.name} <{assignment.email}> for {target_date}.")

        if assignment.is_replacement:
            try:
                old_cell = scan_logic.find_cell_ref(
                    roster_grid, target_date, assignment.primary_name,
                    config.ROSTER_DATE_COLUMN_INDEX, config.DATE_FORMAT,
                )
                new_cell = scan_logic.find_cell_ref(
                    roster_grid, target_date, assignment.name,
                    config.ROSTER_DATE_COLUMN_INDEX, config.DATE_FORMAT,
                )
                if old_cell and new_cell:
                    google_sheets.update_cell(sheets, config.SCAN_SPREADSHEET_ID, roster_tab, old_cell, "")
                    google_sheets.update_cell(
                        sheets, config.SCAN_SPREADSHEET_ID, roster_tab, new_cell, config.ROSTER_DUTY_KEYWORD
                    )
                    print(f"Updated roster: moved duty from {assignment.primary_name} to {assignment.name}.")
                else:
                    print("Could not locate roster cells to update — skipping write-back.", file=sys.stderr)
            except Exception:
                # Best-effort: the email already sent and the Log entry already
                # recorded the real outcome, so don't fail the run over this.
                traceback.print_exc()

        return 0

    except Exception:
        error_text = traceback.format_exc()
        print(error_text, file=sys.stderr)
        send_failure_alert(error_text)
        return 1


if __name__ == "__main__":
    sys.exit(main())
