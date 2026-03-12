---
name: review-doc
description: Review a Google Doc or Slides by emulating a senior leader's feedback style based on their past comments
user-invocable: true
---

# Review Doc Skill

Use this skill to get an AI-powered first-pass review of a Google Doc or Google Slides presentation, written in the style of a specific senior leader. It learns the leader's commenting style from their past feedback and posts comments directly to the target document.

## What This Skill Does

1. Checks that Google OAuth is configured and guides setup if not
2. Collects the target document URL and senior leader's email interactively
3. Checks for a cached style profile in `~/.review-doc/profiles/` — if found, offers to use it as-is, update it incrementally, or rebuild from scratch
4. Auto-discovers Google Docs/Slides where the leader has previously commented (skipped if using a cached profile as-is)
5. Analyses the leader's commenting style (focus areas, tone, depth, patterns) — or loads from cache
6. Saves the style profile to `~/.review-doc/profiles/` for reuse in future sessions
7. Reads the target document
8. Generates 5–15 review comments in the leader's style
9. Presents the comments for user approval before posting
10. Posts approved comments to the document, prefixed with `[Leader Name]: feedback`

## Prerequisites

None — the skill guides you through Google OAuth setup on first run.

## Usage

Invoke with `/review-doc`. The skill will ask for:
- The URL of the Google Doc or Slides to review
- The leader's email address
- The leader's display name (for comment prefixes)

## Available Scripts

All scripts live in `~/.claude/skills/review-doc/scripts/`. They require
`google-api-python-client`, `google-auth-oauthlib`, and `python-dotenv`
(already installed with the pm commands requirements).

| Script | Purpose |
|--------|---------|
| `fetch_comments.py` | Fetch comments from a single Doc/Slides, optionally filtered by author email |
| `find_commented_files.py` | Search Drive for recent Docs/Slides that have any comments |
| `add_comments.py` | Post comments to a Doc/Slides (supports `--dry-run`) |

Auth module: `scripts/auth/google.py` — self-contained OAuth with Drive scopes,
separate token cache at `~/.google-review-doc-token.json`.

## Comment Format

Each posted comment is formatted as:

```
[Leader Name]: Their feedback here
```

This makes AI-generated comments easy to identify and distinguish from the
leader's own comments if they later review the document themselves.
