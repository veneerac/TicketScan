"""Run this once, locally, to authorize sending mail via the Gmail API as
a specific Google account (e.g. your wso2.com one) instead of SMTP + app
password. Reuses the same OAuth Client ID/Secret already set up for
Google Sheets access — no new Google Cloud app needed, just enable the
Gmail API in that same project first. Prints a refresh token to save as
the GMAIL_API_REFRESH_TOKEN GitHub secret. Requires:
pip install google-auth-oauthlib

Not used by the daily automation itself — that reads the token from
GitHub Secrets instead of running this interactive flow.
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> None:
    client_id = input("OAuth Client ID (same one used for Sheets access): ").strip()
    client_secret = input("OAuth Client Secret: ").strip()

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=0)

    print("\nLogin succeeded. Save this as a GitHub repository secret:\n")
    print(f"GMAIL_API_REFRESH_TOKEN = {creds.refresh_token}")
    print(
        "\n(This reuses your existing GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET "
        "secrets — nothing new needed for those.)"
    )
    print("Treat the refresh token like a password — don't paste it anywhere but GitHub Secrets.")


if __name__ == "__main__":
    main()
