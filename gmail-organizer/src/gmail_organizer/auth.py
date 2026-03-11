"""Gmail API authentication and credential management."""

import os
import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

DEFAULT_CREDENTIALS_PATH = Path("config/credentials.json")
DEFAULT_TOKEN_PATH = Path("config/token.json")


def get_gmail_service(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
):
    """Authenticate and return a Gmail API service instance.

    Args:
        credentials_path: Path to OAuth2 client credentials JSON file.
        token_path: Path to store/load the user's access token.

    Returns:
        A Gmail API service resource.
    """
    creds = _load_or_refresh_credentials(credentials_path, token_path)
    service = build("gmail", "v1", credentials=creds)
    logger.info("Gmail API service created successfully")
    return service


def _load_or_refresh_credentials(
    credentials_path: Path, token_path: Path
) -> Credentials:
    """Load existing credentials or run the OAuth2 flow."""
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        logger.debug("Loaded existing token from %s", token_path)

    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired credentials")
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth2 credentials file not found at {credentials_path}. "
                "Download it from the Google Cloud Console."
            )
        logger.info("Running OAuth2 authorization flow")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)

    # Save the token for future runs
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    logger.debug("Token saved to %s", token_path)

    return creds
