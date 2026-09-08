import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def send_mail(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    sender_address: str,
    to_addresses: list[str],
    subject: str,
    body_html: str,
    cc_addresses: list[str] | None = None,
) -> None:
    """Sends via the Gmail API (OAuth) as whichever account authorized
    refresh_token — an alternative to SMTP + app password, for accounts
    where App Passwords are blocked (e.g. by Workspace policy) but OAuth
    consent still works."""
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_address
    msg["To"] = ", ".join(to_addresses)
    if cc_addresses:
        msg["Cc"] = ", ".join(cc_addresses)
    msg.attach(MIMEText(body_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
