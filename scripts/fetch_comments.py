#!/usr/bin/env python3
"""
fetch_comments.py — fetch comments from a Google Doc or Google Slides file.

Uses the Google Drive API v3 comments.list() endpoint. Optionally filters
by author email to isolate a specific person's comments.

Usage:
    python fetch_comments.py --url <google-doc-or-slides-url> \
        [--author-email <email>] \
        [--author-name <name>] \
        [--include-resolved] \
        [-o/--output <file.json>]

On success: JSON to stdout (or --output file), exit code 0.
On failure: ERROR_CODE: message to stderr, exit code 1.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".pm.env")
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from auth.google import get_oauth_credentials

_DOC_ID_RE = re.compile(r"https://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)")
_SLIDES_ID_RE = re.compile(r"https://docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)")

_FIELDS = (
    "comments(id,content,author(displayName,emailAddress),"
    "anchor,quotedFileContent,resolved,replies(content,"
    "author(displayName,emailAddress),createdTime),createdTime,modifiedTime),"
    "nextPageToken"
)


def extract_file_id(url: str) -> str:
    for pattern in (_DOC_ID_RE, _SLIDES_ID_RE):
        m = pattern.search(url)
        if m:
            return m.group(1)
    print(
        f"PARSE_ERROR: Could not extract file ID from URL: {url}. "
        "Expected a Google Docs or Google Slides URL.",
        file=sys.stderr,
    )
    sys.exit(1)


def fetch_all_comments(service, file_id: str, include_resolved: bool) -> list[dict]:
    comments = []
    page_token = None

    while True:
        kwargs = dict(
            fileId=file_id,
            fields=_FIELDS,
            pageSize=100,
            includeDeleted=False,
        )
        if page_token:
            kwargs["pageToken"] = page_token

        try:
            result = service.comments().list(**kwargs).execute()
        except Exception as e:
            _handle_api_error(e)

        for comment in result.get("comments", []):
            if not include_resolved and comment.get("resolved", False):
                continue
            comments.append(comment)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return comments


def _handle_api_error(e):
    try:
        from googleapiclient.errors import HttpError
        if isinstance(e, HttpError):
            status = e.resp.status
            if status == 404:
                print("NOT_FOUND: File not found. Check the URL and sharing permissions.", file=sys.stderr)
            elif status == 403:
                print(
                    "AUTH_FAILURE: Access denied. Either the file is not shared with your "
                    "Google account, or the OAuth token is missing Drive scopes. "
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


def normalise_comment(c: dict) -> dict:
    quoted = c.get("quotedFileContent", {})
    return {
        "comment_id": c.get("id", ""),
        "content": c.get("content", ""),
        "author": {
            "display_name": c.get("author", {}).get("displayName", ""),
            "email": c.get("author", {}).get("emailAddress", ""),
        },
        "quoted_content": quoted.get("value", "") if quoted else "",
        "resolved": c.get("resolved", False),
        "created_time": c.get("createdTime", ""),
        "modified_time": c.get("modifiedTime", ""),
        "replies": [
            {
                "content": r.get("content", ""),
                "author": {
                    "display_name": r.get("author", {}).get("displayName", ""),
                    "email": r.get("author", {}).get("emailAddress", ""),
                },
                "created_time": r.get("createdTime", ""),
            }
            for r in c.get("replies", [])
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch comments from a Google Doc or Slides.")
    parser.add_argument("--url", required=True, help="Google Doc or Slides URL.")
    parser.add_argument("--author-email", default=None, help="Filter comments by author email.")
    parser.add_argument("--author-name", default=None, help="Filter by author display name (fallback when email missing).")
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        default=False,
        help="Include resolved comments (default: open only).",
    )
    parser.add_argument("-o", "--output", default=None, help="Write JSON output to this file.")
    args = parser.parse_args()

    file_id = extract_file_id(args.url)

    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        print(f"AUTH_FAILURE: Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    creds = get_oauth_credentials()
    service = build("drive", "v3", credentials=creds)

    raw_comments = fetch_all_comments(service, file_id, args.include_resolved)

    comments = [normalise_comment(c) for c in raw_comments]

    if args.author_email:
        email_lower = args.author_email.lower()
        name_lower = args.author_name.lower() if args.author_name else None

        def matches_author(c):
            author_email = c["author"]["email"]
            if author_email:
                return author_email.lower() == email_lower
            if name_lower:
                return c["author"]["display_name"].lower() == name_lower
            return False

        comments = [c for c in comments if matches_author(c)]

    output = {
        "file_id": file_id,
        "file_url": args.url,
        "total_comments": len(comments),
        "author_filter": args.author_email,
        "author_name_filter": args.author_name,
        "comments": comments,
    }

    result = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(result)
        print(f"Wrote {len(comments)} comment(s) to {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
