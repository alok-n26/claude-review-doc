# review-doc

A [Claude Code](https://claude.ai/code) skill that reviews a Google Doc or Slides presentation in the style of a specific senior leader, by learning from their past comments.

## What it does

1. Auto-discovers Google Docs/Slides where the leader has previously commented
2. Analyses their commenting style — focus areas, tone, depth, recurring patterns
3. Reads the target document
4. Generates 5–15 review comments written as the leader would write them
5. Presents comments for your approval before posting anything
6. Posts approved comments directly to the document, prefixed with `[Leader Name]: feedback`

## Installation

Copy the skill into your Claude skills directory:

```bash
git clone https://github.com/alok-n26/claude-review-doc ~/.claude/skills/review-doc
```

Register it in your Claude Code skills config (`~/.claude/CLAUDE.md` or your project's `CLAUDE.md`):

```markdown
## Skills
- review-doc: ~/.claude/skills/review-doc
```

Install Python dependencies (shared with other Google API tools):

```bash
pip install google-api-python-client google-auth-oauthlib python-dotenv
```

## Usage

```
/review-doc
```

The skill will ask for:
- The URL of the Google Doc or Slides to review
- The leader's email address
- The leader's display name (used to prefix comments)

Google OAuth setup is guided automatically on first run.

## Prerequisites

- Python 3.9+
- A Google Cloud project with the Drive API, Docs API, and Slides API enabled
- OAuth 2.0 credentials (Desktop app) saved to `~/.google-client-secrets.json`
- `GOOGLE_CLIENT_SECRETS_FILE` set in `~/.pm.env`

The skill walks you through all of this on first run if it's not already configured.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/fetch_comments.py` | Fetch comments from a Doc/Slides, filtered by author email and/or display name |
| `scripts/find_commented_files.py` | Scan Drive for recent files that have comments |
| `scripts/add_comments.py` | Post comments to a Doc/Slides (`--dry-run` supported) |

## Comment format

Posted comments are prefixed so they're easy to identify:

```
[Jane Smith]: This section needs a clearer success metric — what does good look like in 6 months?
```

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill metadata and summary |
| `prompt.md` | Step-by-step execution instructions for Claude |
| `reference.md` | Google Drive API reference, known limitations, and technical notes |
| `scripts/` | Python scripts called during execution |
