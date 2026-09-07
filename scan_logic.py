import datetime
from dataclasses import dataclass

from google_sheets import parse_date


@dataclass
class Assignment:
    name: str
    email: str
    is_replacement: bool  # specifically: covering for someone who's on leave
    from_pool: bool  # picked via the available-candidates pool, for any reason
    # (leave replacement OR no one explicitly on duty) — this, not
    # is_replacement, is what should drive cooldown/no-repeat tracking,
    # since both cases are "the script chose someone" rather than the
    # roster explicitly naming them.
    reason: str
    primary_name: str  # who the roster originally scheduled, even if reassigned


class NoOneAvailableError(Exception):
    pass


# --- Company Roster grid parsing -----------------------------------------
# The company-wide Roster sheet is a grid: column A/B = weekday/date, and
# each team gets a variable-width block of columns (one per person) under
# a merged header with the team's name. Each person's cell holds a status
# code for that day — a duty code (e.g.
# other codes (LL, AL, Allo-EXT, Mig, 6-9pm, ...) mean unavailable. Unlike
# the Leave sheet, the team's header row isn't fixed at row 1 — several
# summary rows can precede it — so the header row itself is located by
# search, not assumed to be the first row.


def parse_roster_grid(
    grid_rows: list[list[str]],
    team_label: str,
    date_column_index: int = 1,
    date_format: str | None = None,
) -> dict[datetime.date, dict[str, str]]:
    """Returns {date: {person_name: status_code}}."""
    header_row_idx = next(
        (i for i, row in enumerate(grid_rows) if team_label in [c.strip() for c in row]),
        None,
    )
    if header_row_idx is None:
        raise ValueError(f"Team {team_label!r} not found in the Roster sheet")
    header_row = grid_rows[header_row_idx]
    start_col = next(i for i, v in enumerate(header_row) if v.strip() == team_label)
    end_col = len(header_row)
    for i in range(start_col + 1, len(header_row)):
        if header_row[i].strip():
            end_col = i
            break

    person_row = grid_rows[header_row_idx + 1] if header_row_idx + 1 < len(grid_rows) else []
    people_columns = [
        (i, person_row[i].strip())
        for i in range(start_col, end_col)
        if i < len(person_row) and person_row[i].strip()
    ]
    if not people_columns:
        raise ValueError(f"No person columns found under {team_label!r} in the Roster sheet")

    schedule: dict[datetime.date, dict[str, str]] = {}
    for row in grid_rows[header_row_idx + 2:]:
        if date_column_index >= len(row) or not row[date_column_index].strip():
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
    duty_codes: list[str],
    exclude_codes: list[str] = (),
) -> str | None:
    """Returns whoever's cell contains a duty code that day, or None if
    nobody's explicitly marked (not an error — just means anyone available
    can be assigned; see resolve_assignment). Matches by the code appearing
    anywhere in the cell, not an exact match — but a cell containing an
    exclude_codes marker (e.g. "6-9pm") never counts as duty even if a duty
    code also appears in it, e.g. "6-9pm/6-9am-OC" is excluded, not duty."""
    day = roster_schedule.get(target_date)
    if day is None:
        raise ValueError(f"No roster row found for {target_date.isoformat()}")
    duty_codes_lower = [c.strip().lower() for c in duty_codes]
    exclude_codes_lower = [c.strip().lower() for c in exclude_codes]
    for person, cell in day.items():
        cell_lower = cell.strip().lower()
        if any(ex in cell_lower for ex in exclude_codes_lower):
            continue
        if any(code in cell_lower for code in duty_codes_lower):
            return person
    return None


def is_available_in_roster(
    name: str,
    target_date: datetime.date,
    roster_schedule: dict[datetime.date, dict[str, str]],
    available_codes: list[str],
) -> bool:
    """Safe-by-default: blank or an explicitly-listed code (e.g. "LK") means
    available; any other code (recognized or not) means unavailable."""
    cell = roster_schedule.get(target_date, {}).get(name, "")
    if not cell.strip():
        return True
    available_lower = {c.strip().lower() for c in available_codes}
    return cell.strip().lower() in available_lower


def active_team_names(
    scan_grid: list[list[str]], date_column_index: int = 1
) -> list[str]:
    """The Issues Scan Rotation sheet's header row is treated as the
    authoritative list of who's currently on the team — used to filter
    departed people who are still listed as columns in the company Roster
    sheet (which you don't control and can go stale)."""
    if not scan_grid:
        return []
    header = scan_grid[0]
    return [
        name.strip()
        for i, name in enumerate(header)
        if i != date_column_index and name.strip()
    ]


def filter_active_roster(
    roster_schedule: dict[datetime.date, dict[str, str]],
    active_names: list[str],
) -> dict[datetime.date, dict[str, str]]:
    """Drops any person from the roster schedule who doesn't match one of
    active_names (same fuzzy prefix matching used for the Leave sheet,
    since the two sheets don't always use identical name spellings)."""
    return {
        date: {
            person: cell
            for person, cell in day.items()
            if any(_names_match(person, active) for active in active_names)
        }
        for date, day in roster_schedule.items()
    }


# --- Leave sheet (separate, more up-to-date than the weekly roster) -----
# Real structure (confirmed from screenshots of "Integration ABT Leave
# Plan"): one tab per year ("Leave Plan 2026", ...), column A = date
# *without a year* (e.g. "1-Jan"), and each team gets 3 columns under a
# merged header matching the team's name (LEAVE_TEAM_LABEL):
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
    "Amal"), while the Roster uses first-name+initial (e.g. "AmalP")."""
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


def pick_available(
    target_date: datetime.date,
    roster_schedule: dict[datetime.date, dict[str, str]],
    available_codes: list[str],
    leave_schedule: dict[datetime.date, list[str]],
    log_rows: list[dict],
    cooldown_days: int,
    date_format: str | None = None,
    exclude_name: str | None = None,
) -> str:
    # A candidate is eligible only if they're not on leave AND their own
    # Roster status that day is blank/"LK" — any other code (their own
    # allocation, leave, evening shift, etc.) rules them out too.
    team_names = list(roster_schedule.get(target_date, {}).keys())
    candidates = [
        name
        for name in team_names
        if (exclude_name is None or name.strip().lower() != exclude_name.strip().lower())
        and not is_on_leave(name, target_date, leave_schedule)
        and is_available_in_roster(name, target_date, roster_schedule, available_codes)
    ]
    if not candidates:
        raise NoOneAvailableError(f"Everyone is on leave/allocated for {target_date.isoformat()}")

    recently_used = recent_backup_names(log_rows, target_date, cooldown_days, date_format)

    for name in candidates:
        if name.strip().lower() not in recently_used:
            return name
    # Everyone eligible was used recently — fall back to the first one anyway.
    return candidates[0]


def resolve_assignment(
    target_date: datetime.date,
    roster_schedule: dict[datetime.date, dict[str, str]],
    duty_codes: list[str],
    duty_exclude_codes: list[str],
    available_codes: list[str],
    leave_schedule: dict[datetime.date, list[str]],
    log_rows: list[dict],
    cooldown_days: int,
    email_domain: str,
    date_format: str | None = None,
) -> Assignment:
    primary_name = find_primary(target_date, roster_schedule, duty_codes, duty_exclude_codes)

    if primary_name is None:
        # Nobody's explicitly marked with a duty code that day — not an
        # error, just pick anyone available from the team.
        assignee = pick_available(
            target_date, roster_schedule, available_codes, leave_schedule,
            log_rows, cooldown_days, date_format,
        )
        return Assignment(
            name=assignee,
            email=resolve_email(assignee, email_domain),
            is_replacement=False,
            from_pool=True,
            reason="no one explicitly on duty — assigned from available team members",
            primary_name=assignee,
        )

    # The roster is filled in ahead of time, so it can go stale — cross-check
    # against the live Leave sheet even for the scheduled person.
    if not is_on_leave(primary_name, target_date, leave_schedule):
        return Assignment(
            name=primary_name,
            email=resolve_email(primary_name, email_domain),
            is_replacement=False,
            from_pool=False,
            reason="scheduled on the roster",
            primary_name=primary_name,
        )

    replacement_name = pick_available(
        target_date, roster_schedule, available_codes, leave_schedule,
        log_rows, cooldown_days, date_format, exclude_name=primary_name,
    )
    return Assignment(
        name=replacement_name,
        email=resolve_email(replacement_name, email_domain),
        is_replacement=True,
        from_pool=True,
        reason=f"{primary_name} is on leave",
        primary_name=primary_name,
    )


# --- Issues Scan sheet write-back (weekly look-ahead) --------------------
# Your own Issues Scan Rotation sheet's per-year tab is a simple grid:
# column A = weekday, column B = date, one column per person, header row
# is row 1. The weekly job writes the resolved person's name into this
# grid (as "Scan") so the upcoming week is visible in advance.


def parse_scan_sheet_grid(
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


def _column_letter(index: int) -> str:
    n = index + 1  # convert 0-based to 1-based
    letters = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def find_scan_sheet_cell_ref(
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


def scan_sheet_row_people(
    grid_rows: list[list[str]],
    target_date: datetime.date,
    date_column_index: int = 1,
    date_format: str | None = None,
) -> list[tuple[str, str]]:
    """Returns [(person_name, cell_ref)] for every person column on
    target_date's row — used to clear stale markers before writing a fresh
    one, so re-running the weekly job is always safe."""
    if not grid_rows:
        return []
    header = grid_rows[0]
    people_columns = [
        (i, name.strip())
        for i, name in enumerate(header)
        if i != date_column_index and name.strip()
    ]
    for sheet_row_number, row in enumerate(grid_rows[1:], start=2):
        if len(row) <= date_column_index or not row[date_column_index].strip():
            continue
        try:
            row_date = parse_date(row[date_column_index], date_format)
        except ValueError:
            continue
        if row_date == target_date:
            return [
                (person, f"{_column_letter(i)}{sheet_row_number}")
                for i, person in people_columns
            ]
    return []
