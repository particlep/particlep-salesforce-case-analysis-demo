# Extending the pipeline (v2, v3)

The current pipeline is one-way: read from Salesforce, summarize, send email.
A natural progression follows.

## v2 — Write findings back to Salesforce

For each clinical flag and high-risk escalation, the v2 pipeline writes:

- A `Case Comment` on the relevant Case with the analyst summary and a tag
  like `[Daily Brief · Clinical Flag · Immediate]`.
- A `Task` on the related Account with subject `"Daily brief flagged this
  case"`, due tomorrow, assigned to the clinical team queue.

### Implementation outline

```python
# inside src/sources/salesforce.py (add a method)

def write_findings(
    self,
    *,
    case_id: str,
    comment_body: str,
    task_owner_queue_id: str | None = None,
) -> None:
    self.sf.CaseComment.create({
        "ParentId": case_id,
        "CommentBody": comment_body,
        "IsPublished": False,  # internal-only
    })

    if task_owner_queue_id:
        case = self.sf.Case.get(case_id)
        self.sf.Task.create({
            "WhatId": case["AccountId"],
            "Subject": "Daily brief flagged this case",
            "Description": comment_body,
            "OwnerId": task_owner_queue_id,
            "ActivityDate": (datetime.now().date() + timedelta(days=1)).isoformat(),
        })
```

### What changes in the orchestrator

After the analysis modules run, the orchestrator iterates clinical flags and
high-risk escalations, calls `source.write_findings(...)` for each, and
appends a note in the email like "Comments and follow-up Tasks have been
created on these cases."

### What to be careful of

- **Idempotency.** Don't write a duplicate comment if the pipeline re-runs
  for the same date. Tag comments with the analysis date and check for an
  existing comment before posting.
- **PHI in comments.** The summaries that go into Case Comments are
  PHI-free by the same contract as the email content. See
  `phi-handling.md`. Even so, Case Comments are visible to anyone with
  Case access — review whether that's acceptable in your org.
- **Permissions.** The integration user needs `Create` on `CaseComment` and
  `Task`. Often this requires a Permission Set Group separate from the
  read-only set used for v1.

## v3 — Package as a Lightning Web Component

Lift the pipeline into the platform so support leads can run it on-demand
inside Service Cloud rather than waiting for the 7am email.

### Shape

- LWC button on a Lightning Page (e.g. Case List view header, or the
  Service Console home).
- Click triggers an Apex method via `@AuraEnabled` that hits a long-running
  Anthropic call via Anthropic's Streaming API + Salesforce's
  Named Credential for outbound TLS.
- Streaming response renders into the LWC as the analysis completes.

### What's reused vs. rewritten

Reused: the prompts (markdown files travel verbatim), the tool definitions
(JSON copies into Apex), the SOQL queries (already authored in Apex syntax).

Rewritten:
- Python orchestrator → Apex queueable
- Anthropic Python SDK → raw HTTP via Apex `HttpRequest`
- Jinja2 HTML template → LWC template (`.html` + `.css` + `.js`)

### Why this works

The Service Cloud platform-native version benefits from in-flow consumption
— a support lead reviewing a Case can ask "give me the operational picture
for the last 24h" without opening a separate email. The Salesforce-native
LWC keeps the data inside the platform's existing access controls, which
matters for orgs where the Anthropic BAA is enough to allow analysis but
not enough to allow exporting PHI to a separate email system.

## Worth noting

These v2 and v3 paths play to the platform-native strength of the Service
Cloud Case model. Anything in Apex that you can do declaratively — like
creating Tasks via Process Builder/Flow off a custom field — is usually
preferable to writing imperative code. The v2 implementation outlined above
is the minimal viable version; in production you'd likely have a flow doing
the Task creation and the integration just writing a custom
`Daily_Brief_Score__c` number that the flow keys off.
