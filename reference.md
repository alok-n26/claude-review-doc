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
