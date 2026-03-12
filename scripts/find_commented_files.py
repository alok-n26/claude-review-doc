#!/usr/bin/env python3
"""
find_commented_files.py — search Google Drive for recent Docs/Slides with comments.

Uses the Drive API v3 files.list() to find recently modified Google Docs and
Slides, then checks each for the presence of any comments. Returns a list of
files that have at least one comment.

This is used during the learning phase of the review-doc skill to auto-discover
documents where the senior leader may have left comments.

Usage:
    python find_commented_files.py [--limit <N>] [-o/--output <file.json>]

On success: JSON to stdout (or --output file), exit code 0.
On failure: ERROR_CODE: message to stderr, exit code 1.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".pm.env")
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from auth.google import get_oauth_credentials

_GDOC_MIME = "application/vnd.google-apps.document"
_GSLIDES_MIME = "application/vnd.google-apps.presentation"

_URL_TEMPLATES = {
    _GDOC_MIME: "https://docs.google.com/document/d/{id}/edit",
    _GSLIDES_MIME: "https://docs.google.com/presentation/d/{id}/edit",
}


def list_recent_files(service, limit: int) -> list[dict]:
    """Return up to `limit` recently modified Docs and Slides."""
    query = (
        f"(mimeType='{_GDOC_MIME}' or mimeType='{_GSLIDES_MIME}') "
        "and trashed=false"
    )
    files = []
    page_token = None

    while len(files) < limit:
        batch = min(100, limit - len(files))
        kwargs = dict(
            q=query,
            orderBy="modifiedTime desc",
            pageSize=batch,
            fields="files(id,name,mimeType),nextPageToken",
        )
        if page_token:
            kwargs["pageToken"] = page_token

        try:
            result = service.files().list(**kwargs).execute()
        except Exception as e:
            _handle_api_error(e)

        files.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return files[:limit]


def has_comments(service, file_id: str) -> bool:
    """Return True if the file has at least one comment."""
    try:
        result = service.comments().list(
            fileId=file_id,
            fields="comments(commentId)",
            pageSize=1,
            includeDeleted=False,
        ).execute()
        return len(result.get("comments", [])) > 0
    except Exception:
        return False


def _handle_api_error(e):
    try:
        from googleapiclient.errors import HttpError
        if isinstance(e, HttpError):
            status = e.resp.status
            if status == 403:
                print(
                    "AUTH_FAILURE: Access denied. The OAuth token may be missing Drive scopes. "
                    "Delete ~/.google-review-doc-token.json and re-authenticate.",
                    file=sys.stderr,
                )
            else:
                print(f"NETWORK_ERROR: Drive API error {status}: {e}", file=sys.stderr)
            sys.exit(1)
    except ImportError:
        pass
    print(f"NETWORK_ERROR: {e}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find recent Google Docs/Slides that have comments."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of recent files to scan (default: 20).",
    )
    parser.add_argument("-o", "--output", default=None, help="Write JSON output to this file.")
    args = parser.parse_args()

    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        print(f"AUTH_FAILURE: Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    creds = get_oauth_credentials()
    service = build("drive", "v3", credentials=creds)

    print(f"Scanning up to {args.limit} recent files...", file=sys.stderr)
    files = list_recent_files(service, args.limit)
    print(f"Found {len(files)} file(s). Checking for comments...", file=sys.stderr)

    results = []
    for f in files:
        file_id = f["id"]
        mime = f["mimeType"]
        url = _URL_TEMPLATES.get(mime, "").format(id=file_id)
        commented = has_comments(service, file_id)
        results.append({
            "file_id": file_id,
            "name": f.get("name", ""),
            "url": url,
            "mime_type": mime,
            "has_comments": commented,
        })

    commented_count = sum(1 for r in results if r["has_comments"])
    print(f"{commented_count} file(s) have comments.", file=sys.stderr)

    output = {"files": results}
    result_json = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(result_json)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(result_json)


if __name__ == "__main__":
    main()
