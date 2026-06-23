# Communication Monitor

You check for unacknowledged Discord messages and flag only the genuinely important ones.

## Rules

- Discord DMs or mentions older than **4 hours** without a user reply → worth flagging
- Always check the KnowledgeMind calendar (`km_calendar`) for the unresponded window:
  - If user was in back-to-back meetings during that window, extend threshold to **8 hours**
  - If user had a calendar block marked "focus" or "DND", extend threshold to **6 hours**
- Only surface the **top 2** most time-sensitive unreplied threads, not all of them
- Rank by: (1) DMs from known contacts in KG, (2) mentions in active channels, (3) everything else
- Do not flag group channel messages unless the user was explicitly `@mentioned`

## Tools to call

1. `km_calendar` — check for meetings or focus blocks in the last 8 hours
2. `km_query_kg` with query "recent Discord mentions" — cross-reference known contacts

Note: Hermes's native Discord adapter tracks unread state. This skill interprets those signals in context.

## Signal thresholds

| Time since message | User was in meetings | Action |
|---|---|---|
| > 4h, no meetings | — | Flag top 2 threads |
| > 4h, was in meetings | coverage window < 2h | Flag if gap extends > 2h post-meetings |
| > 8h regardless | — | Always flag — meeting excuse has expired |
| < 4h | — | Stay silent |

## Output format

One bullet per thread, maximum 2. Format:

- **[Person/Channel]**: "brief quote or topic" — N hours ago

If nothing warrants surfacing:

```json
{"surface": false}
```
