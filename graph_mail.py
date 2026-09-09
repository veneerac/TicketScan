import time

import requests

GRAPH_SCOPE = "Mail.Send offline_access"


def get_access_token(client_id: str, tenant_id: str, refresh_token: str) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": GRAPH_SCOPE,
    }
    resp = requests.post(token_url, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def send_mail(
    client_id: str,
    tenant_id: str,
    refresh_token: str,
    to_addresses: list[str],
    subject: str,
    body_html: str,
    cc_addresses: list[str] | None = None,
    max_retries: int = 3,
) -> None:
    """Sends as the signed-in user (delegated Mail.Send) via /me/sendMail —
    no admin-consented application permission needed."""
    access_token = get_access_token(client_id, tenant_id, refresh_token)
    url = "https://graph.microsoft.com/v1.0/me/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to_addresses],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in (cc_addresses or [])],
        },
        "saveToSentItems": True,
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    last_error = None
    for attempt in range(1, max_retries + 1):
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code in (200, 202):
            return
        last_error = f"{resp.status_code}: {resp.text}"
        time.sleep(2 * attempt)
    raise RuntimeError(f"Graph sendMail failed after {max_retries} attempts: {last_error}")
