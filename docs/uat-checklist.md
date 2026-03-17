# UAT Checklist

## Pilot Scope

- Pilot projects: 1-2 active jobs with one superintendent and one PM each.
- Pilot duration: 2 weeks.
- Daily success metric: reports submitted by end-of-day with less than 5 minutes average edit time.

## Functional Validation

- Create draft report for selected project/date.
- Update location and summary.
- Submit report from field role.
- Verify submitted report rejects further edits, attachments, and entry changes until rejection.
- Review and approve report as PM.
- Lock report as admin.
- Export approved/locked report to PDF.

## Offline Validation

- Open app, disconnect network, create report edits.
- Confirm app shows offline queued state.
- Reconnect network and verify queue flush.
- Validate server-side record matches queued local changes.
- Validate stale revision returns conflict and requires manual refresh.

## Security Validation

- Verify non-member cannot create reports for project.
- Verify locked report rejects updates.
- Verify invalid file extension or bad signature is rejected.
- Verify uploaded file remains pending until scan result updates status.
- Verify session endpoint responds consistently without revealing sensitive state.

## Sign-Off Criteria

- No critical defects in workflow or data loss scenarios.
- Pilot users confirm adoption readiness.
- PM confirms report quality acceptable for project communication.
