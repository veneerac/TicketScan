"""Run this once, locally, to authorize the automation to send mail as
your own wso2.com account via Microsoft Graph (delegated Mail.Send).
Prints a code + URL for you to approve in any browser, then prints a
refresh token to save as GitHub secrets. Requires: pip install msal

Not used by the daily automation itself — that reads the token from
GitHub Secrets instead of running this interactive flow.
"""

import msal

SCOPES = ["Mail.Send"]


def main() -> None:
    client_id = input("Application (client) ID: ").strip()
    tenant_id = input("Directory (tenant) ID: ").strip()

    app = msal.PublicClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant_id}"
    )
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")

    print(f"\n{flow['message']}\n")
    result = app.acquire_token_by_device_flow(flow)  # blocks until you complete sign-in

    if "access_token" not in result:
        raise RuntimeError(
            f"Login failed: {result.get('error')}: {result.get('error_description')}"
        )

    print("\nLogin succeeded. Save these as GitHub repository secrets:\n")
    print(f"MS_OAUTH_CLIENT_ID = {client_id}")
    print(f"MS_OAUTH_TENANT_ID = {tenant_id}")
    print(f"MS_OAUTH_REFRESH_TOKEN = {result['refresh_token']}")
    print("\nTreat the refresh token like a password — don't paste it anywhere but GitHub Secrets.")


if __name__ == "__main__":
    main()
