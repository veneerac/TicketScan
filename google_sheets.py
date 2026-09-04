import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_service(client_id: str, client_secret: str, refresh_token: str):
    """Authenticates as your own Google account via a stored refresh token
    (obtained once via get_refresh_token.py), rather than a service account —
    needed because Workspace policy blocks sharing sheets with an external
    service-account identity."""
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_rows(service, spreadsheet_id: str, sheet_name: str) -> list[dict]:
    """Reads a sheet and returns rows as dicts keyed by the header row."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_name)
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []
    header, *rows = values
    out = []
    for row in rows:
        padded = row + [""] * (len(header) - len(row))
        out.append({header[i]: padded[i] for i in range(len(header))})
    return out


def read_grid(service, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
    """Reads a sheet as a raw grid (no header-keying) — for sheets shaped like
    the roster: header row = people's names, not field names."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_name)
        .execute()
    )
    return result.get("values", [])


def append_row(service, spreadsheet_id: str, sheet_name: str, row: list) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=sheet_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


# Dates like "9/4/2026" are ambiguous (day/month vs month/day) — guessing
# wrong silently picks the wrong person. DATE_FORMAT (config.py) should be
# set to whatever your sheets actually use; it's tried first. The fallback
# list below only exists for sheets with genuinely mixed formatting, and
# puts %m/%d/%Y ahead of %d/%m/%Y because that's the format the team's
# existing TicketScan script uses (strftime('%-m/%-d/%Y')).
_FALLBACK_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y")


def parse_date(value: str, preferred_format: str | None = None) -> datetime.date:
    value = value.strip()
    formats = ([preferred_format] if preferred_format else []) + [
        f for f in _FALLBACK_DATE_FORMATS if f != preferred_format
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r} (set DATE_FORMAT in config)")
