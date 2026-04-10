# Monitor

Check if a name has been newly added to any sanctions list since a
given date. Useful for compliance monitoring — tracking whether
persons or entities in your due diligence pipeline become sanctioned.

## Usage

`/monitor <name> --since YYYY-MM-DD` — check for new listings
`/monitor <name>` — defaults to checking the last 30 days

## Procedure

1. Parse the name and date. If no date provided, default to 30 days ago.

2. Use `sanctions_monitor` with the name and `since` date.

3. If results are returned, use `sanctions_entity` on each to get full
   details including which lists, topics, and related entities.

4. Produce a monitoring report:

```
## Monitoring report: [name]

Period: [since date] to [today]

### Status: [NEW LISTINGS FOUND / NO NEW LISTINGS]

[If new listings found:]

| Date listed | Match | Score | Lists | Topics |
|------------|-------|-------|-------|--------|
| ... | ... | 0.95 | OFAC SDN | sanction |

### Details

[For each new listing: which list, why listed (if available from
properties), connected entities, sanctions programme]

### Recommended action

[If new listings: investigate immediately, check connected entities,
review compliance exposure.
If no new listings: continue monitoring, next check recommended in
30 days.]
```

## Scheduling

This skill runs on demand within a Claude Code session. For persistent
automated monitoring, set up a scheduled task (cron, launchd, or
similar) that calls the OpenSanctions API directly:

```bash
# Example cron entry — check monthly, email on match
0 9 1 * * /path/to/check-sanctions.sh "Subject Name" "2026-01-01" | mail -s "Sanctions check" you@email.com
```

A monitoring script (`scripts/monitor.sh`) that wraps the API call
and sends alerts could be added to this repo as a future enhancement.

## Notes

- Run monthly or when events suggest a subject may be newly sanctioned
- New listings with score > 0.9 are high confidence; 0.7-0.9 verify manually
- OpenSanctions updates continuously — the `changed_since` parameter
  returns only entities modified after the specified date
