# Review Doc — Reference

## Google Drive API v3: Comments

Base URL: `https://www.googleapis.com/drive/v3/files/{fileId}/comments`

### comments.list

```
GET https://www.googleapis.com/drive/v3/files/{fileId}/comments
```

Key parameters:
- `fields` — **required** to get full comment data (default response is sparse)
- `pageSize` — max 100 per page
- `includeDeleted` — set false to skip deleted comments
- `pageToken` — for pagination

Recommended `fields` value:
```
comments(commentId,content,author(displayName,emailAddress),
anchor,quotedFileContent,resolved,
replies(content,author(displayName,emailAddress),createdTime),
createdTime,modifiedTime),nextPageToken
```

### comments.create

```
POST https://www.googleapis.com/drive/v3/files/{fileId}/comments
```

Body fields:
- `content` (required) — comment text
- `quotedFileContent` — `{mimeType, value}` — best-effort anchor to matching text
- `anchor` — undocumented JSON string; format differs between Docs and Slides; avoid generating manually

### Rate limits

- 1000 queries / 100 seconds / user
- Use 0.5s delay between `comments.create` calls for safety

## OAuth Scopes

| Scope | Used for |
|-------|---------|
| `drive.readonly` | `files.list`, `comments.list` |
| `drive` | `comments.create` |
| `documents.readonly` | reading Doc content via Docs API |
| `presentations.readonly` | reading Slides content via Slides API |

Token cache: `~/.google-review-doc-token.json`
Client secrets env var: `GOOGLE_CLIENT_SECRETS_FILE` (set in `~/.pm.env`)

## URL Patterns for File ID Extraction

```python
# Google Docs
re.compile(r"https://docs\.google\.com/document/d/([a-zA-Z0-9_-]+)")

# Google Slides
re.compile(r"https://docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)")
```

## Comment Object Schema

```json
{
  "comment_id": "string",
  "content": "string",
  "author": {
    "display_name": "string",
    "email": "string"
  },
  "quoted_content": "string (text highlighted when comment was made)",
  "resolved": false,
  "created_time": "ISO 8601",
  "modified_time": "ISO 8601",
  "replies": [
    {
      "content": "string",
      "author": {"display_name": "string", "email": "string"},
      "created_time": "ISO 8601"
    }
  ]
}
```

## Style Analysis Prompt Template

When analysing a leader's comments, ask Claude to identify:

1. **Focus areas** — What topics does the leader most often comment on?
   Examples: data accuracy, clarity, structure, strategic alignment, grammar,
   missing information, audience fit, executive summary quality

2. **Tone** — How does the leader phrase feedback?
   Examples: direct/blunt, question-based ("Have you considered...?"),
   instructive ("You should..."), collaborative ("What if we..."),
   encouraging with caveats

3. **Detail level** — High-level strategic feedback vs granular line edits?

4. **Comment length** — Typical length: one sentence, a few sentences, paragraph?

5. **Recurring patterns** — Common phrases, pet peeves, things they always ask for

6. **Content they highlight** — What kinds of text do they anchor comments to?
   Examples: unsupported claims, vague language, section headings, data points

## Style Profile Persistence

### Storage location

Profiles are stored in `~/.review-doc/profiles/`, one file per leader.

### File naming

The filename is derived from the leader's email address:
1. Replace `@` with `_at_`
2. Replace every `.` with `_`
3. Append `.md`

Example: `jane.smith@company.com` → `jane_smith_at_company_com.md`

### Profile file schema

```markdown
---
leader_email: "jane.smith@company.com"
leader_name: "Jane Smith"
created: "2026-03-12T14:30:00Z"
last_updated: "2026-03-12T16:45:00Z"
comment_count: 27
source_document_count: 5
source_documents:
  - url: "https://docs.google.com/document/d/abc123/edit"
    name: "Q2 Strategy Review"
    comments_used: 8
  - url: "https://docs.google.com/presentation/d/def456/edit"
    name: "Board Deck March"
    comments_used: 6
incorporated_comment_ids:
  - "AAABOA2VNCA"
  - "AAABOA3XYZB"
user_corrections_applied: false
---

# Style Profile: Jane Smith

## Focus Areas
...

## Tone
...

## Detail Level
...

## Comment Length
...

## Recurring Patterns
...

## What They Anchor To
...
```

### Frontmatter fields

| Field | Type | Description |
|-------|------|-------------|
| `leader_email` | string | Leader's email address (matches `LEADER_EMAIL`) |
| `leader_name` | string | Leader's display name |
| `created` | ISO 8601 UTC | When the profile was first created |
| `last_updated` | ISO 8601 UTC | When the profile was last written |
| `comment_count` | integer | Total comments the current profile is based on |
| `source_document_count` | integer | Number of distinct source documents used |
| `source_documents` | list | Each entry has `url`, `name`, `comments_used` |
| `incorporated_comment_ids` | list | All `comment_id` values from comments used in the profile |
| `user_corrections_applied` | boolean | `true` if the user has manually corrected the profile |

### Incremental update algorithm

1. Read `incorporated_comment_ids` from the existing profile's frontmatter
2. Run the normal comment discovery flow (Steps 3a–3b)
3. Filter fetched comments: discard any whose `comment_id` is in `incorporated_comment_ids`
4. If no new comments remain, use the existing profile unchanged
5. If new comments exist, analyse them and merge insights into the existing profile body
6. Append the new `comment_id` values to `incorporated_comment_ids`
7. Increment `comment_count`, update `source_documents` list and `source_document_count`, update `last_updated`

### Dedup mechanism

The `comment_id` field from `fetch_comments.py` output maps directly to the Drive API `commentId` — a stable, immutable string assigned by Google when the comment is created. Using it as the dedup key means the same comment is never counted twice, even if a document is scanned in multiple sessions.

### User correction preservation

When `user_corrections_applied: true`, incremental updates must not overwrite corrected sections. New observations from new comments are appended or merged carefully; the user's edits to existing sections are left intact.

## Known Limitations

### Comment Anchoring
The Drive API anchor format is undocumented and differs between Docs and Slides.
The `quotedFileContent` approach is a best-effort alternative — if the quoted
text matches exactly, the API may anchor the comment to that text. If not, the
comment is created at document level. The comment text itself should always
reference the relevant section for clarity.

### Training Data Discovery
There is no Drive API query to find "all files commented on by person X".
`find_commented_files.py` scans recent files for any comments, then
`fetch_comments.py --author-email` filters to the specific leader. For leaders
who rarely comment, the user may need to provide specific document URLs.

### Author Matching Fallback
The Google Drive API occasionally omits `emailAddress` from comment author objects
while still returning `displayName`. When this happens, email-only filtering silently
drops legitimate comments from the target leader.

`fetch_comments.py` handles this with a two-step match:
1. **Email match (authoritative)** — if the API returns an email, it must equal `--author-email`
2. **Display name fallback** — if the email field is empty, the comment is included if
   `displayName` case-insensitively matches `--author-name`

Always pass both `--author-email` and `--author-name` when calling `fetch_comments.py`
to ensure comments are captured even when the API omits email addresses.

### Token Cache and Scopes
The review-doc token (`~/.google-review-doc-token.json`) uses different scopes
than the pm-commands token. If the token was created with the wrong scopes,
delete it and re-authenticate:

```bash
rm ~/.google-review-doc-token.json
# Re-run any review-doc script to trigger fresh OAuth consent
```
