import datetime
from dataclasses import dataclass

from google_sheets import parse_date


@dataclass
class Assignment:
    name: str
    email: str
    is_replacement: bool
    reason: str


class NoOneAvailableError(Exception):
    pass


# --- Roster grid parsing ------------------------------------------------
# The Roster tab (inside your own Issues Scan Rotation sheet) is a grid:
# column A = weekday name, column B = date, columns C onward = one per
# person, and whichever person's cell for that row contains "Scan" is on
# duty that day. Confirmed from a real screenshot of "Castor Issues Scan
# Rotation" — column B holds dates like 9/4/2026.


def parse_roster_grid(
    grid_rows: list[list[str]],
    date_column_index: int = 1,
    date_format: str | None = None,
) -> dict[datetime.date, dict[str, str]]:
    """Returns {date: {person_name: cell_text}}."""
    if not grid_rows:
        return {}
    header = grid_rows[0]
    people_columns = [
        (i, name.strip())
        for i, name in enumerate(header)
        if i != date_column_index and name.strip()
    ]

    schedule: dict[datetime.date, dict[str, str]] = {}
    for row in grid_rows[1:]:
        if len(row) <= date_column_index or not row[date_column_index].strip():
            continue
        try:
            row_date = parse_date(row[date_column_index], date_format)
        except ValueError:
            continue
        schedule[row_date] = {
            person: (row[i].strip() if i < len(row) else "")
            for i, person in people_columns
        }
    return schedule


def find_primary(
    target_date: datetime.date,
    roster_schedule: dict[datetime.date, dict[str, str]],
    duty_keyword: str,
) -> str:
    day = roster_schedule.get(target_date)
    if day is None:
        raise ValueError(f"No roster row found for {target_date.isoformat()}")
    for person, cell in day.items():
        if duty_keyword.lower() in cell.lower():
            return person
    raise ValueError(
        f"No one is marked '{duty_keyword}' in the roster for {target_date.isoformat()}"
    )


# --- Leave sheet (separate, more up-to-date than the weekly roster) -----


def is_on_leave(
    name: str,
    target_date: datetime.date,
    leave_rows: list[dict],
    date_format: str | None = None,
) -> bool:
    for row in leave_rows:
        if row.get("Name", "").strip().lower() != name.strip().lower():
            continue
        start = parse_date(row["StartDate"], date_format)
        end = parse_date(row["EndDate"], date_format)
        if start <= target_date <= end:
            return True
    return False


# --- Assignment resolution ----------------------------------------------


def recent_backup_names(
    log_rows: list[dict],
    target_date: datetime.date,
    cooldown_days: int,
    date_format: str | None = None,
) -> set[str]:
    cutoff = target_date - datetime.timedelta(days=cooldown_days)
    names = set()
    for row in log_rows:
        if row.get("WasReplacement", "").strip().upper() != "TRUE":
            continue
        for_date = parse_date(row["ForDate"], date_format)
        if cutoff <= for_date < target_date:
            names.add(row["AssignedName"].strip().lower())
    return names


def already_sent(
    log_rows: list[dict], target_date: datetime.date, date_format: str | None = None
) -> bool:
    return any(
        parse_date(row["ForDate"], date_format) == target_date
        for row in log_rows
        if row.get("ForDate")
    )


def resolve_email(name: str, email_domain: str) -> str:
    return f"{name.strip().lower()}{email_domain}"


def pick_replacement(
    target_date: datetime.date,
    primary_name: str,
    roster_schedule: dict[datetime.date, dict[str, str]],
    leave_rows: list[dict],
    log_rows: list[dict],
    cooldown_days: int,
    date_format: str | None = None,
) -> str:
    # Anyone in the roster's column headers is a valid candidate — any
    # available (not on leave) teammate is fine, the only rule is no one
    # repeats as backup within `cooldown_days` (default 7: once/week).
    team_names = list(roster_schedule.get(target_date, {}).keys())
    candidates = [
        name
        for name in team_names
        if name.strip().lower() != primary_name.strip().lower()
        and not is_on_leave(name, target_date, leave_rows, date_format)
    ]
    if not candidates:
        raise NoOneAvailableError(f"Everyone is on leave for {target_date.isoformat()}")

    recently_used = recent_backup_names(log_rows, target_date, cooldown_days, date_format)

    for name in candidates:
        if name.strip().lower() not in recently_used:
            return name
    # Everyone eligible was used recently — fall back to the first one anyway.
    return candidates[0]


def resolve_assignment(
    target_date: datetime.date,
    roster_schedule: dict[datetime.date, dict[str, str]],
    leave_rows: list[dict],
    log_rows: list[dict],
    cooldown_days: int,
    duty_keyword: str,
    email_domain: str,
    date_format: str | None = None,
) -> Assignment:
    primary_name = find_primary(target_date, roster_schedule, duty_keyword)

    # The roster is filled in by hand ahead of time, so it can go stale —
    # cross-check against the live Leave sheet even for the scheduled person.
    if not is_on_leave(primary_name, target_date, leave_rows, date_format):
        return Assignment(
            name=primary_name,
            email=resolve_email(primary_name, email_domain),
            is_replacement=False,
            reason="scheduled on the roster",
        )

    replacement_name = pick_replacement(
        target_date, primary_name, roster_schedule, leave_rows, log_rows, cooldown_days, date_format
    )
    return Assignment(
        name=replacement_name,
        email=resolve_email(replacement_name, email_domain),
        is_replacement=True,
        reason=f"{primary_name} is on leave",
    )
