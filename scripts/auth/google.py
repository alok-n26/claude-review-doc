"""
Google OAuth authentication for the review-doc skill.

Self-contained module with its own scope list (includes Drive read/write for
comments API) and its own token cache, so it does not interfere with the
pm-commands readonly token.

Public functions:
  - check_auth_status(): returns dict describing current auth state
  - get_oauth_credentials(): returns valid Google credentials, triggering
    browser OAuth consent on first run
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".pm.env")
load_dotenv()

REVIEW_DOC_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
]

_DEFAULT_TOKEN_CACHE = str(Path.home() / ".google-review-doc-token.json")


def _get_paths() -> tuple[str, str]:
    secrets_file = os.environ.get("GOOGLE_CLIENT_SECRETS_FILE", "").strip()
    token_cache = os.environ.get(
        "REVIEW_DOC_TOKEN_CACHE_FILE",
        _DEFAULT_TOKEN_CACHE,
    ).strip()
    return secrets_file, token_cache


def check_auth_status() -> dict:
    """
    Return a dict describing the current auth setup state.

    Keys:
      client_secrets_ok (bool): client secrets file exists and is readable
      token_ok (bool):          token cache file exists
      secrets_path (str):       resolved path to client secrets file
      token_path (str):         resolved path to token cache file
      env_file_ok (bool):       ~/.pm.env exists and sets GOOGLE_CLIENT_SECRETS_FILE
    """
    secrets_file, token_cache = _get_paths()
    pm_env = Path.home() / ".pm.env"

    return {
        "client_secrets_ok": bool(secrets_file and Path(secrets_file).is_file()),
        "token_ok": Path(token_cache).is_file(),
        "secrets_path": secrets_file or "(not set)",
        "token_path": token_cache,
        "env_file_ok": pm_env.is_file() and bool(secrets_file),
    }


def get_oauth_credentials():
    """
    Return valid Google OAuth2 credentials for the review-doc skill.

    Uses a separate token cache (~/.google-review-doc-token.json) from the
    pm-commands token so that the Drive write scopes here do not invalidate
    the pm-commands readonly token.

    Opens a browser for the consent flow on first run only.
    """
    secrets_file, token_cache = _get_paths()

    if not secrets_file:
        print(
            "AUTH_FAILURE: GOOGLE_CLIENT_SECRETS_FILE is not set. "
            "Run /review-doc and follow the setup instructions.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not Path(secrets_file).is_file():
        print(
            f"AUTH_FAILURE: Client secrets file not found: {secrets_file}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        print(f"AUTH_FAILURE: Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    creds = None

    if Path(token_cache).is_file():
        try:
            with open(token_cache) as f:
                token_data = json.load(f)
            creds = Credentials.from_authorized_user_info(token_data, REVIEW_DOC_SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(
                    f"AUTH_FAILURE: Failed to refresh OAuth token: {e}. "
                    f"Delete {token_cache} and re-run to re-authenticate.",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(secrets_file, REVIEW_DOC_SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"AUTH_FAILURE: OAuth consent flow failed: {e}", file=sys.stderr)
                sys.exit(1)

        try:
            with open(token_cache, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"[warn] Could not write token cache to {token_cache}: {e}", file=sys.stderr)

    return creds
