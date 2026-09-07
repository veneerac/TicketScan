import datetime
import sys
import traceback

from zoneinfo import ZoneInfo

import config
import google_sheets
import scan_logic
from send_reminder import send_failure_alert


def upcoming_week_weekdays() -> list[datetime.date]:
    if config.TARGET_DATE_OVERRIDE:
        given = datetime.datetime.strptime(config.TARGET_DATE_OVERRIDE, "%Y-%m-%d").date()
        monday = given - datetime.timedelta(days=given.weekday())  # snap to that week's Monday
    else:
        today = datetime.datetime.now(ZoneInfo(config.TIMEZONE)).date()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        monday = today + datetime.timedelta(days=days_until_monday)
    return [monday + datetime.timedelta(days=i) for i in range(5)]  # Mon..Fri


def main() -> int:
    try:
        sheets = google_sheets.get_service(
            config.GOOGLE_OAUTH_CLIENT_ID,
            config.GOOGLE_OAUTH_CLIENT_SECRET,
            config.GOOGLE_OAUTH_REFRESH_TOKEN,
        )
        week_dates = upcoming_week_weekdays()
        print(f"Resolving assignments for {week_dates[0]} through {week_dates[-1]}...")

        log_rows = google_sheets.read_rows(sheets, config.SCAN_SPREADSHEET_ID, config.LOG_TAB)
        pretend_log_rows: list[dict] = []  # this batch's own picks, so later days in
        # the same run don't repeat a backup already used earlier in the week.

        # Cache per-year sheet reads/parses — a week can span a year boundary.
        roster_schedules: dict[int, dict] = {}
        leave_schedules: dict[int, dict] = {}
        scan_grids: dict[int, list] = {}
        scan_schedules: dict[int, dict] = {}

        def ensure_year_loaded(year: int) -> None:
            if year in roster_schedules:
                return
            roster_tab = config.ROSTER_TAB_OVERRIDE or str(year)
            leave_tab = config.LEAVE_TAB_OVERRIDE or f"{config.LEAVE_TAB_PREFIX}{year}"
            scan_tab = config.SCAN_SHEET_TAB_OVERRIDE or str(year)

            roster_grid = google_sheets.read_grid(sheets, config.ROSTER_SPREADSHEET_ID, roster_tab)
            leave_grid = google_sheets.read_grid(sheets, config.LEAVE_SPREADSHEET_ID, leave_tab)
            scan_grid = google_sheets.read_grid(sheets, config.SCAN_SPREADSHEET_ID, scan_tab)

            roster_schedule = scan_logic.parse_roster_grid(
                roster_grid, config.ROSTER_TEAM_LABEL,
                config.ROSTER_DATE_COLUMN_INDEX, config.ROSTER_DATE_FORMAT,
            )
            # Filter out anyone still listed in the company Roster sheet
            # who's no longer on the team — the Issues Scan sheet's own
            # column headers are the authoritative "who's actually here" list.
            active_names = scan_logic.active_team_names(scan_grid, config.SCAN_SHEET_DATE_COLUMN_INDEX)
            roster_schedules[year] = scan_logic.filter_active_roster(roster_schedule, active_names)
            leave_schedules[year] = scan_logic.parse_leave_grid(
                leave_grid, config.LEAVE_TEAM_LABEL, year,
                config.LEAVE_DATE_COLUMN_INDEX, config.LEAVE_DATE_FORMAT,
            )
            scan_grids[year] = scan_grid
            scan_schedules[year] = scan_logic.parse_scan_sheet_grid(
                scan_grid, config.SCAN_SHEET_DATE_COLUMN_INDEX, config.DATE_FORMAT
            )

        writes_by_tab: dict[str, dict[str, str]] = {}

        for target_date in week_dates:
            year = target_date.year
            ensure_year_loaded(year)

            try:
                assignment = scan_logic.resolve_assignment(
                    target_date, roster_schedules[year], config.ROSTER_DUTY_CODES,
                    config.ROSTER_DUTY_EXCLUDE_CODES, config.ROSTER_AVAILABLE_CODES,
                    leave_schedules[year], log_rows + pretend_log_rows, config.BACKUP_COOLDOWN_DAYS,
                    config.EMAIL_DOMAIN, config.DATE_FORMAT,
                )
            except (ValueError, scan_logic.NoOneAvailableError) as exc:
                print(f"{target_date}: could not resolve — {exc}", file=sys.stderr)
                continue

            print(
                f"{target_date} ({target_date.strftime('%A')}): {assignment.name}"
                + (f" [{assignment.reason}]" if assignment.from_pool else "")
            )

            if assignment.from_pool:
                # Tracked regardless of *why* the script picked them (leave
                # replacement or nobody explicitly on duty) — either way,
                # this was a choice the cooldown rule should remember for
                # the rest of this batch, not something the real roster
                # dictated.
                pretend_log_rows.append({
                    "ForDate": target_date.isoformat(),
                    "AssignedName": assignment.name,
                    "WasReplacement": "TRUE",
                })

            row_people = scan_logic.scan_sheet_row_people(
                scan_grids[year], target_date,
                config.SCAN_SHEET_DATE_COLUMN_INDEX, config.DATE_FORMAT,
            )
            if not row_people:
                print(f"{target_date}: no matching row in the Issues Scan sheet — skipping write.", file=sys.stderr)
                continue

            scan_tab = config.SCAN_SHEET_TAB_OVERRIDE or str(year)
            tab_writes = writes_by_tab.setdefault(scan_tab, {})
            for person, cell_ref in row_people:
                tab_writes[cell_ref] = (
                    config.SCAN_SHEET_DUTY_MARKER
                    if person.strip().lower() == assignment.name.strip().lower()
                    else ""
                )

        if config.TEST_MODE:
            print("=== TEST_MODE is ON: not writing to the Issues Scan sheet ===")
            for tab, cells in writes_by_tab.items():
                print(f"Would write to {tab!r}: {cells}")
            return 0

        for tab, cells in writes_by_tab.items():
            google_sheets.batch_update_cells(sheets, config.SCAN_SPREADSHEET_ID, tab, cells)
        print("Issues Scan sheet updated for the upcoming week.")
        return 0

    except Exception:
        error_text = traceback.format_exc()
        print(error_text, file=sys.stderr)
        send_failure_alert(error_text)
        return 1


if __name__ == "__main__":
    sys.exit(main())
