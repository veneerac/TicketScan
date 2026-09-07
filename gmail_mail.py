import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_mail(
    sender_address: str,
    app_password: str,
    to_addresses: list[str],
    subject: str,
    body_html: str,
    cc_addresses: list[str] | None = None,
    max_retries: int = 3,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_address
    msg["To"] = ", ".join(to_addresses)
    if cc_addresses:
        msg["Cc"] = ", ".join(cc_addresses)
    msg.attach(MIMEText(body_html, "html"))

    all_recipients = to_addresses + (cc_addresses or [])

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.login(sender_address, app_password)
                server.sendmail(sender_address, all_recipients, msg.as_string())
            return
        except smtplib.SMTPException as exc:
            last_error = str(exc)
            time.sleep(2 * attempt)
    raise RuntimeError(f"Gmail send failed after {max_retries} attempts: {last_error}")
