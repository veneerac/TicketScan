import datetime
from dataclasses import dataclass

from google_sheets import parse_date


@dataclass
class Assignment:
    name: str
    email: str
    is_replacement: bool
    reason: str
    primary_name: str  # who the roster originally scheduled, even if reassigned


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
# Real structure (confirmed from screenshots of "Integration ABT Leave
# Plan"): one tab per year ("Leave Plan 2026", ...), column A = date
# *without a year* (e.g. "1-Jan"), and each team gets 3 columns under a
# merged header matching the team's name (e.g. "Castor (Team 2)"):
# Lead LL/AL | Member LL | Member AL. Whoever's on leave has their name
# typed into whichever of those 3 columns matches their role/leave-type —
# row 1 = team headers, row 2 = the 3 sub-headers, data starts row 3.


def parse_leave_grid(
    grid_rows: list[list[str]],
    team_label: str,
    year: int,
    date_column_index: int = 0,
    leave_date_format: str = "%d-%b",
) -> dict[datetime.date, list[str]]:
    """Returns {date: [names on leave that day for this team]}."""
    if len(grid_rows) < 3:
        return {}
    header_row = grid_rows[0]
    start_col = next(
        (i for i, v in enumerate(header_row) if v.strip() == team_label), None
    )
    if start_col is None:
        raise ValueError(f"Team {team_label!r} not found in the Leave sheet's header row")
    leave_cols = [start_col, start_col + 1, start_col + 2]

    schedule: dict[datetime.date, list[str]] = {}
    for row in grid_rows[2:]:
        if date_column_index >= len(row) or not row[date_column_index].strip():
            continue
        raw_date = row[date_column_index].strip()
        try:
            row_date = datetime.datetime.strptime(
                f"{raw_date}-{year}", f"{leave_date_format}-%Y"
            ).date()
        except ValueError:
            continue
        names = [row[c].strip() for c in leave_cols if c < len(row) and row[c].strip()]
        schedule[row_date] = names
    return schedule


def _names_match(a: str, b: str) -> bool:
    """Case-insensitive match, allowing one name to be a short-form prefix
    of the other — the Leave sheet often uses first names only (e.g.
    "Kavindu"), while the Roster uses first-name+initial (e.g. "KavinduN")."""
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a) and bool(b) and (a == b or a.startswith(b) or b.startswith(a))


def is_on_leave(
    name: str,
    target_date: datetime.date,
    leave_schedule: dict[datetime.date, list[str]],
) -> bool:
    return any(_names_match(name, n) for n in leave_schedule.get(target_date, []))


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
    leave_schedule: dict[datetime.date, list[str]],
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
        and not is_on_leave(name, target_date, leave_schedule)
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
    leave_schedule: dict[datetime.date, list[str]],
    log_rows: list[dict],
    cooldown_days: int,
    duty_keyword: str,
    email_domain: str,
    date_format: str | None = None,
) -> Assignment:
    primary_name = find_primary(target_date, roster_schedule, duty_keyword)

    # The roster is filled in by hand ahead of time, so it can go stale —
    # cross-check against the live Leave sheet even for the scheduled person.
    if not is_on_leave(primary_name, target_date, leave_schedule):
        return Assignment(
            name=primary_name,
            email=resolve_email(primary_name, email_domain),
            is_replacement=False,
            reason="scheduled on the roster",
            primary_name=primary_name,
        )

    replacement_name = pick_replacement(
        target_date, primary_name, roster_schedule, leave_schedule, log_rows, cooldown_days, date_format
    )
    return Assignment(
        name=replacement_name,
        email=resolve_email(replacement_name, email_domain),
        is_replacement=True,
        reason=f"{primary_name} is on leave",
        primary_name=primary_name,
    )


# --- Roster write-back ---------------------------------------------------
# When a replacement is picked, move the duty marker in the actual sheet
# from the on-leave person's cell to the replacement's cell, so the roster
# always reflects who's really doing it, not just the original plan.


def _column_letter(index: int) -> str:
    n = index + 1  # convert 0-based to 1-based
    letters = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def find_cell_ref(
    grid_rows: list[list[str]],
    target_date: datetime.date,
    person_name: str,
    date_column_index: int = 1,
    date_format: str | None = None,
) -> str | None:
    """Returns the A1 cell reference (e.g. "E244") for person_name's column
    on target_date's row, or None if either can't be found."""
    if not grid_rows:
        return None
    header = grid_rows[0]
    col_index = next(
        (i for i, name in enumerate(header) if name.strip().lower() == person_name.strip().lower()),
        None,
    )
    if col_index is None:
        return None

    for sheet_row_number, row in enumerate(grid_rows[1:], start=2):
        if len(row) <= date_column_index or not row[date_column_index].strip():
            continue
        try:
            row_date = parse_date(row[date_column_index], date_format)
        except ValueError:
            continue
        if row_date == target_date:
            return f"{_column_letter(col_index)}{sheet_row_number}"
    return None
