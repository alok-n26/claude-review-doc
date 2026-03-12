#!/usr/bin/env python3
"""
add_comments.py — post AI-generated comments to a Google Doc or Google Slides.

Uses the Google Drive API v3 comments.create() endpoint. Each comment is
prefixed with the reviewer's name in the format "[Name]: feedback" as required.

Usage:
    python add_comments.py --url <google-doc-or-slides-url> \
        --comments-file <comments.json> \
        [--dry-run]

Input JSON format (comments-file):
    {
      "reviewer_name": "Jane Leader",
      "comments": [
        {
          "content": "Feedback text..."
        }
      ]
    }

On success: summary to stdout, exit code 0.
On failure: ERROR_CODE: message to stderr, exit code 1.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".pm.env")
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from auth.google import get_oauth_credentials

_DOC_ID_RE = re.compile(r"https://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)")
_SLIDES_ID_RE = re.compile(r"https://docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)")


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


def load_comments(path: str) -> tuple[str, list[dict]]:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        print(f"PARSE_ERROR: Comments file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"PARSE_ERROR: Invalid JSON in comments file: {e}", file=sys.stderr)
        sys.exit(1)

    reviewer_name = data.get("reviewer_name", "Reviewer")
    comments = data.get("comments", [])
    if not comments:
        print("PARSE_ERROR: No comments found in comments file.", file=sys.stderr)
        sys.exit(1)
    return reviewer_name, comments


def build_comment_body(reviewer_name: str, comment: dict) -> dict:
    content = f"[{reviewer_name}]: {comment.get('content', '')}"
    return {"content": content}


def post_comment(service, file_id: str, body: dict):
    try:
        return service.comments().create(
            fileId=file_id,
            fields="id,content,author,createdTime",
            body=body,
        ).execute()
    except Exception as e:
        try:
            from googleapiclient.errors import HttpError
            if isinstance(e, HttpError):
                status = e.resp.status
                if status == 403:
                    print(
                        "AUTH_FAILURE: Access denied when writing comments. "
                        "The OAuth token may be missing the Drive write scope. "
                        "Delete ~/.google-review-doc-token.json and re-authenticate.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                print(f"NETWORK_ERROR: Drive API error {status}: {e}", file=sys.stderr)
                return None
        except ImportError:
            pass
        print(f"NETWORK_ERROR: {e}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post AI-generated comments to a Google Doc or Slides."
    )
    parser.add_argument("--url", required=True, help="Google Doc or Slides URL.")
    parser.add_argument(
        "--comments-file", required=True, help="Path to JSON file with comments to post."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be posted without calling the API.",
    )
    args = parser.parse_args()

    file_id = extract_file_id(args.url)
    reviewer_name, comments = load_comments(args.comments_file)

    print(f"Preparing {len(comments)} comment(s) from [{reviewer_name}]...")

    if args.dry_run:
        print("\n--- DRY RUN (no comments will be posted) ---\n")
        for i, comment in enumerate(comments, 1):
            body = build_comment_body(reviewer_name, comment)
            print(f"Comment {i}:")
            print(f"  Text:   {body['content']}")
            print()
        print(f"--- Would post {len(comments)} comment(s) to {args.url} ---")
        return

    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        print(f"AUTH_FAILURE: Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)

    creds = get_oauth_credentials()
    service = build("drive", "v3", credentials=creds)

    succeeded = 0
    failed = 0

    for i, comment in enumerate(comments, 1):
        body = build_comment_body(reviewer_name, comment)
        result = post_comment(service, file_id, body)
        if result:
            succeeded += 1
            print(f"  Posted comment {i}/{len(comments)}: {result.get('commentId', '')}")
        else:
            failed += 1
            print(f"  Failed comment {i}/{len(comments)}", file=sys.stderr)

        if i < len(comments):
            time.sleep(0.5)

    print(f"\nDone. {succeeded} comment(s) posted, {failed} failed.")

    if succeeded == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
