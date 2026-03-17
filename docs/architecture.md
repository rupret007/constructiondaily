# Architecture Decision Record

## Chosen Stack

- Frontend: React + TypeScript + Vite + PWA support
- Backend: Django + Django REST Framework
- Database: PostgreSQL (SQLite fallback for local development)
- File storage: S3-compatible object storage with staged scanning lifecycle

## Why This Stack

1. Django accelerates delivery of internal business apps with stable auth/admin patterns.
2. React PWA supports field usage patterns where connectivity is intermittent.
3. PostgreSQL provides robust relational integrity and supports future row-level policies.
4. S3-compatible object storage scales attachment handling and supports secure quarantine flows.

## Security Baseline

- Session cookies configured with strict flags.
- Role-based authorization enforced at API layer for every protected endpoint.
- Upload validation at extension, MIME, and file-signature levels.
- Structured audit events for create/update/status/signature/export actions.

## Workflow Model

`draft -> submitted -> reviewed -> approved -> locked`

Rejection transitions:

`submitted|reviewed -> draft`

Draft is the only mutable report state. Once a report is submitted, all report content, related entries, safety items, weather sync, and file changes are frozen until a rejection sends the report back to draft.
