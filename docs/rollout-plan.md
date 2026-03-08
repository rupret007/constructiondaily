# Rollout Plan

## Stage 1 - Environment Prep

1. Provision PostgreSQL and configure environment variables.
2. Apply migrations: `python manage.py migrate`.
3. Create admin users and baseline projects.

## Stage 2 - Pilot Deployment

1. Deploy API and web client to internal environment.
2. Assign memberships by role for pilot projects.
3. Execute `docs/uat-checklist.md` during live daily reporting.

## Stage 3 - Hardening Review

1. Review audit events for report create/update/approve/export actions.
2. Validate upload scan statuses and quarantine paths.
3. Confirm session cookie and CSRF behavior in production domain over HTTPS.

## Stage 4 - General Availability

1. Enable all active projects.
2. Provide training handout for superintendent and PM role actions.
3. Monitor pilot metrics for first month:
   - submission completion rates
   - offline queue retries
   - rejection/approval turnaround time
