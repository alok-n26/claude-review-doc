# Review Doc — Execution Instructions

When this skill is invoked via `/review-doc`, follow these steps.

---

## Step 1: Check Auth & Guide Setup

Run the following to check auth status:

```bash
python -c "
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / '.pm.env')
sys.path.insert(0, str(Path.home() / '.claude/skills/review-doc/scripts'))
from auth.google import check_auth_status
import json
print(json.dumps(check_auth_status(), indent=2))
"
```

**If `client_secrets_ok` is false:**

Tell the user:

> "Google OAuth is not yet set up. I'll guide you through the one-time setup."

Then guide them step by step:

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Library** and enable:
   - **Google Drive API**
   - **Google Docs API**
   - **Google Slides API**
4. Go to **APIs & Services → OAuth consent screen**:
   - Choose **External** user type
   - Fill in app name (e.g. "review-doc"), support email
   - Under **Scopes**, add: `drive`, `documents.readonly`, `presentations.readonly`
   - Under **Test users**, add your own Google email
5. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Download the JSON file
6. Save the downloaded file to `~/.google-client-secrets.json`
7. Add this line to `~/.pm.env` (create the file if it doesn't exist):
   ```
   GOOGLE_CLIENT_SECRETS_FILE=/Users/<your-username>/.google-client-secrets.json
   ```
   Replace `<your-username>` with the output of `whoami`.

Once done, tell the user to re-run `/review-doc`. The next run will proceed to the OAuth browser consent flow.

**If `client_secrets_ok` is true but `token_ok` is false:**

Tell the user:

> "Google credentials are configured. The first run will open your browser for a one-time OAuth consent — this grants access to read your Drive files and post comments. Proceed?"

On confirmation, continue to Step 2 (the first script call will trigger the browser flow automatically).

**If a script exits with `AUTH_FAILURE` containing "missing Drive scopes" or similar:**

Tell the user to delete the stale token and re-authenticate:

```bash
rm ~/.google-review-doc-token.json
```

Then re-run the failed step.

**If everything is configured:** proceed directly to Step 2.

---

## Step 2: Collect & Validate Inputs (Interactive)

Ask the user the following questions one at a time:

1. **"What's the URL of the Google Doc or Slides you'd like reviewed?"**
   - Validate it matches `docs.google.com/document/d/` or `docs.google.com/presentation/d/`
   - If it doesn't match, explain the expected format and ask again

2. **"What's the email address of the senior leader whose review style to emulate?"**
   - Validate it looks like an email address (contains `@`)

3. **"What's the leader's display name?"** (e.g. "Jane Smith")
   - This is used to prefix comments: `[Jane Smith]: feedback`

Store these as:
- `TARGET_URL` — the document to review
- `LEADER_EMAIL` — the leader's email
- `LEADER_NAME` — the leader's display name

---

## Step 2b: Check for Existing Style Profile

Derive the profile filename from `LEADER_EMAIL`:
- Replace `@` with `_at_`
- Replace every `.` with `_`
- Append `.md`

Example: `jane.smith@company.com` → `jane_smith_at_company_com.md`

Store as `PROFILE_PATH` = `~/.review-doc/profiles/<sanitized_email>.md`

**If the profile file exists**, read it and present its metadata to the user:

> "I found an existing style profile for [LEADER_NAME]:
> - Created: [created date]
> - Last updated: [last_updated date]
> - Based on [comment_count] comments across [source_document_count] document(s)
>
> How would you like to proceed?
> **(a) Use as-is** — skip style analysis, go straight to reviewing the document
> **(b) Update** — fetch new comments and refresh the profile
> **(c) Rebuild from scratch** — re-analyse all comments and overwrite the profile
> **(d) View profile** — show the full profile, then choose a/b/c"

Handle each response:
- **(a) Use as-is** → load the profile body, skip Steps 3–4, go to Step 5
- **(b) Update** → proceed to Step 3 in **incremental mode** (see below)
- **(c) Rebuild from scratch** → proceed to Step 3 as normal (full rebuild)
- **(d) View profile** → display the full profile file contents, then re-ask a/b/c

**If the profile file does not exist**, proceed directly to Step 3 (backward compatible — same as today).

**If the profile file exists but cannot be read or appears corrupted**, tell the user:

> "The existing profile for [LEADER_NAME] appears unreadable. I'll do a full rebuild."

Then proceed to Step 3 as normal.

---

## Step 3: Auto-Discover Training Data

The goal is to collect past comments by the leader to learn their style.

### 3a. Scan recent Drive files

```bash
python ~/.claude/skills/review-doc/scripts/find_commented_files.py \
  --limit 20 \
  --output /tmp/review-doc-files.json
```

Read `/tmp/review-doc-files.json`. Filter to files where `has_comments` is true.

### 3b. Fetch leader's comments from each file

For each file with comments (up to 15 files to stay within rate limits):

```bash
python ~/.claude/skills/review-doc/scripts/fetch_comments.py \
  --url "<file_url>" \
  --author-email "<LEADER_EMAIL>" \
  --author-name "<LEADER_NAME>" \
  --include-resolved \
  --output /tmp/review-doc-training-N.json
```

Replace `N` with an incrementing number for each file.

Read each output file. Aggregate all comments where `total_comments > 0`.

**Stop early** once you have 30 or more comments across all files.

**Incremental mode (when user chose "Update" in Step 2b):**

1. Load `incorporated_comment_ids` from the existing profile's YAML frontmatter
2. After aggregating all fetched comments, filter out any comment whose `comment_id` is already in `incorporated_comment_ids`
3. If zero new comments remain after filtering:
   > "No new comments found since the last profile update. Using the existing profile."
   Load the existing profile body and go to Step 5.
4. If new comments exist, proceed to Step 4 in **incremental update mode** with only the new comments
5. The user may also provide extra document URLs to broaden coverage — for each, run `fetch_comments.py` as in Step 3c and apply the same dedup filter

### 3c. Fallback if insufficient comments found

If fewer than 5 comments are found across all scanned files, tell the user:

> "I found only [N] comment(s) from [LEADER_NAME] in your recent files. For a better style emulation, please share 2–3 Google Doc or Slides URLs where [LEADER_NAME] has previously left comments."

For each URL the user provides:

```bash
python ~/.claude/skills/review-doc/scripts/fetch_comments.py \
  --url "<provided_url>" \
  --author-email "<LEADER_EMAIL>" \
  --author-name "<LEADER_NAME>" \
  --include-resolved \
  --output /tmp/review-doc-manual-N.json
```

Add these comments to the aggregate.

**If zero comments are found in total (after auto-discovery and any manual URLs), stop execution immediately:**

> "I found no comments from [LEADER_NAME] in any of the scanned documents. Without real examples of their feedback, I cannot emulate their style — generating comments without this data risks producing inaccurate or misleading feedback. Please provide at least one Google Doc or Slides URL where [LEADER_NAME] has left comments, then re-run `/review-doc`."

Do NOT proceed to Step 4 or beyond. Stop here.

**If between 1 and 4 comments are found in total, stop execution:**

> "I only found [N] comment(s) from [LEADER_NAME]. This is not enough to reliably learn their review style — proceeding risks generating feedback that doesn't reflect how they actually comment. Please provide additional Google Doc or Slides URLs where [LEADER_NAME] has left comments (aim for at least 5), then re-run `/review-doc`."

Do NOT proceed to Step 4 or beyond. Stop here.

---

## Step 4: Analyse Leader's Review Style

Using all aggregated comments, produce a **style profile** for the leader. Include:

1. **Focus areas** — what topics does the leader comment on most?
   (data accuracy, clarity, structure, strategic alignment, missing info, grammar, executive summary, audience, etc.)

2. **Tone** — how do they phrase feedback?
   (direct, question-based, instructive, collaborative, encouraging)

3. **Detail level** — high-level strategic or granular line-level?

4. **Comment length** — typical length (one-liners, multi-sentence, paragraphs?)

5. **Recurring patterns** — common phrases, themes, pet peeves

6. **What they anchor to** — what types of content do they highlight?
   (unsupported claims, vague language, missing data, headings, transitions)

Present the style profile to the user:

> "Based on [N] comments across [M] document(s), here is [LEADER_NAME]'s review style:
> [style profile]
>
> Does this look right? You can correct anything before I proceed."

If the user corrects the style profile, update it accordingly. If the user made corrections, set `user_corrections_applied: true` in the profile frontmatter when saving.

**Incremental update mode** — when the user chose "Update" in Step 2b and new comments were found:

1. Read the existing profile body from `PROFILE_PATH`
2. Analyse only the new comments
3. Produce an updated profile that integrates new insights with the existing analysis — do not discard existing observations, only enrich or refine them
4. If `user_corrections_applied: true` in the existing frontmatter, preserve all user corrections — only add new observations, never override corrected sections
5. Present the updated profile for user review/correction as above

**Persistence — all modes** — after the user confirms the style profile:

1. Collect metadata:
   - `leader_email`: `LEADER_EMAIL`
   - `leader_name`: `LEADER_NAME`
   - `created`: current timestamp (ISO 8601, UTC) — preserve existing value if updating
   - `last_updated`: current timestamp (ISO 8601, UTC)
   - `comment_count`: total number of comments the profile is based on
   - `source_document_count`: number of distinct documents used
   - `source_documents`: list of `{url, name, comments_used}` for each source document
   - `incorporated_comment_ids`: list of all `comment_id` values from all comments used
   - `user_corrections_applied`: `true` if user made corrections, otherwise `false`
2. Create the directory:
   ```bash
   mkdir -p ~/.review-doc/profiles/
   ```
3. Write the complete profile file (YAML frontmatter + Markdown body) to `PROFILE_PATH` using the Write tool. Use this structure:
   ```
   ---
   leader_email: "..."
   leader_name: "..."
   created: "..."
   last_updated: "..."
   comment_count: N
   source_document_count: M
   source_documents:
     - url: "..."
       name: "..."
       comments_used: N
   incorporated_comment_ids:
     - "..."
   user_corrections_applied: false
   ---

   # Style Profile: [LEADER_NAME]

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
4. Report to the user: "Style profile saved to `~/.review-doc/profiles/<filename>`"

If the `mkdir` or Write fails, warn the user but continue with the review:

> "Note: Could not save the style profile to disk. The review will continue, but the profile won't be cached for next time."

---

## Step 5: Fetch Target Document

Read the target document content using the pm-fetch script:

```bash
python ~/.claude/commands/pm/pm-fetch.py \
  --url "<TARGET_URL>" \
  --output /tmp/review-doc-target.md
```

If the command writes to stdout instead (no `--output` on pm-fetch), capture it:

```bash
python ~/.claude/commands/pm/pm-fetch.py --url "<TARGET_URL>" > /tmp/review-doc-target.md
```

Read `/tmp/review-doc-target.md` and understand:
- The document title and overall purpose
- The main sections and their content
- Key claims, data points, and recommendations
- Areas that might be weak or need substantiation

---

## Step 6: Generate Review Comments

Using the style profile from Step 4 and the document content from Step 5, generate review comments **as [LEADER_NAME] would write them**.

Rules:
- Generate 5–15 comments (calibrate based on document length and leader's typical volume)
- Each comment must reference a specific part of the document (quote or section name) within the comment text itself
- Match the leader's tone, phrasing style, and detail level
- Cover the types of issues the leader typically raises
- Do NOT write generic comments — every comment should be grounded in the actual document content and the leader's observed patterns

Build the comments JSON internally:
```json
{
  "reviewer_name": "<LEADER_NAME>",
  "comments": [
    {
      "content": "Comment text here"
    }
  ]
}
```

---

## Step 7: Present for Approval

Show the user the generated comments in a clear, readable format:

```
I've generated [N] comments in [LEADER_NAME]'s style. Please review:

Comment 1:
  [LEADER_NAME]: comment text here

Comment 2:
  [LEADER_NAME]: comment text here

...
```

Ask the user:
> "Would you like to approve all comments, edit any, remove any, or request additional ones?"

Handle each response:
- **Approve all** → proceed to Step 8
- **Edit comment N** → ask for the new text, update the comment
- **Remove comment N** → remove it from the list
- **Add more** → generate additional comments and present for approval again
- **Regenerate all** → go back to Step 6 with any user guidance on what to change

---

## Step 8: Post Comments to Document

Write the approved comments to a temp file:

```bash
# Claude writes the approved comments JSON to /tmp/review-doc-approved.json
```

First, do a dry run to validate:

```bash
python ~/.claude/skills/review-doc/scripts/add_comments.py \
  --url "<TARGET_URL>" \
  --comments-file /tmp/review-doc-approved.json \
  --dry-run
```

Show the dry run output to the user and ask for final confirmation:

> "Ready to post [N] comments to [document title]. Shall I proceed?"

On confirmation, post the comments:

```bash
python ~/.claude/skills/review-doc/scripts/add_comments.py \
  --url "<TARGET_URL>" \
  --comments-file /tmp/review-doc-approved.json
```

Report the result:

> "[N] comment(s) posted to [TARGET_URL]. Each comment is prefixed with [[LEADER_NAME]] so they're easy to identify. The document owner will see them as new comments."

---

## Error Handling

| Error | Action |
|-------|--------|
| `AUTH_FAILURE` with scope message | Delete `~/.google-review-doc-token.json` and re-authenticate |
| `NOT_FOUND` on a training file | Skip that file, continue with others |
| `NOT_FOUND` on target document | Ask user to check sharing permissions; document must be shared with the authenticated Google account |
| `AUTH_FAILURE` on target document | Same as NOT_FOUND — check sharing |
| Zero training comments found | Stop execution — tell user to provide document URLs with real comments from the leader |
| Fewer than 5 training comments | Stop execution — tell user the sample is too small to emulate style reliably |
| `add_comments.py` partial failure | Report which comments failed, offer to retry those specific ones |
| `find_commented_files.py` returns 0 files | Skip auto-discovery, go straight to asking user for specific URLs (Step 3c) |
| Profile file unreadable or corrupted | Treat as no profile found; warn user and proceed with full rebuild |
| `~/.review-doc/profiles/` directory creation fails | Warn user that caching is unavailable; continue the review without saving the profile |
