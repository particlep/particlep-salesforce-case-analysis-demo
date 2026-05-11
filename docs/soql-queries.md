# SOQL queries

The Salesforce source issues a single `query_all` against the Case object,
with two subqueries for related child records. Composed once for readability
in `src/sources/salesforce.py` — duplicated here with annotation.

## The main query

```sql
SELECT
    Id, CaseNumber, Subject, Description, Status, Priority, Origin,
    Reason, Type, CreatedDate, ClosedDate, IsEscalated,
    Owner.Name,

    -- SLA / Service Cloud Entitlement fields
    EntitlementId, SlaStartDate, SlaExitDate, MilestoneStatus,

    -- Related Contact
    ContactId, Contact.Name, Contact.Email, Contact.Phone,

    -- Related Account
    AccountId, Account.Name, Account.Type,

    -- Conversation thread
    (SELECT Id, CommentBody, CreatedBy.Name, CreatedDate
     FROM CaseComments ORDER BY CreatedDate ASC),

    -- All field-level history (used to detect owner bouncing,
    -- escalation events, status churn)
    (SELECT Id, Field, OldValue, NewValue, CreatedDate, CreatedBy.Name
     FROM Histories ORDER BY CreatedDate ASC)

FROM Case
WHERE (CreatedDate >= :start AND CreatedDate <= :end)
   OR (LastModifiedDate >= :start AND LastModifiedDate <= :end)
ORDER BY CreatedDate ASC
LIMIT 1000
```

The `OR` on `LastModifiedDate` catches cases that were *worked yesterday* even
if they were opened on an earlier day — those still count as part of
yesterday's operational picture.

`LIMIT 1000` is a defensive ceiling. If your org regularly exceeds 1000 cases
per day, switch to chunked queries with a Date filter pivot or move the source
to a SOQL bulk-style cursor (`queryMore`).

## Optional extensions (not currently wired)

These are easy adds when the v2 of this tool needs them:

### EmailMessages (Email-to-Case orgs)

Replaces or augments `CaseComments` for orgs where the conversation lives in
the email thread:

```sql
(SELECT Id, Subject, FromAddress, ToAddress, TextBody, MessageDate, Incoming
 FROM EmailMessages ORDER BY MessageDate ASC)
```

### CaseFeed (Chatter)

If support agents communicate via Chatter:

```sql
(SELECT Id, Type, Body, CreatedBy.Name, CreatedDate
 FROM Feeds ORDER BY CreatedDate ASC)
```

### Omni-Channel routing

To analyze routing behavior:

```sql
(SELECT Id, Status, OwnerId, CreatedDate
 FROM AgentWorks ORDER BY CreatedDate ASC)
```

## Permissions needed

The integration user (or PAT-equivalent) needs:

- Read on `Case`, `CaseComment`, `CaseHistory`, `Account`, `Contact`
- Read on `Entitlement` and related milestone tracking
- "View All Data" or row-level access via the org's sharing model

The Salesforce source uses `query_all` instead of `query` so it follows pages
automatically (no `queryMore` plumbing).

## Why the source is swappable

The `SalesforceSource.fetch_cases` and `SyntheticSource.fetch_cases` both
return a `list[CaseRecord]` with identical shape. Every analysis module
operates on that normalized shape — none of them know whether the data came
from Salesforce, a JSON fixture, or a future source like Zendesk.
