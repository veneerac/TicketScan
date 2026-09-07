"""Run this once, locally, to authorize the automation as your own Google
account. Opens a browser for you to log in and grant Sheets access, then
prints a refresh token to save as the GOOGLE_OAUTH_REFRESH_TOKEN GitHub
secret. Requires: pip install google-auth-oauthlib

Not used by the daily automation itself — that reads the token from
GitHub Secrets instead of running this interactive flow.
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def main() -> None:
    client_id = input("OAuth Client ID: ").strip()
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

    print("\nLogin succeeded. Save these as GitHub repository secrets:\n")
    print(f"GOOGLE_OAUTH_CLIENT_ID = {client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET = {client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN = {creds.refresh_token}")
    print("\nTreat the refresh token like a password — don't paste it anywhere but GitHub Secrets.")


if __name__ == "__main__":
    main()
