# PRD — ComplyEase PCS Multi-Client Compliance Suite

## Original problem statement
I have built an excel based compliance software. Basic idea is take from comply relax. Can you use that excel and create a working web based app with same functionality? Its heavy and unusable in excel as its too complicated and boring.

## Architecture decisions
- React frontend (split into pages) + FastAPI + MongoDB.
- Approval-based auth: first signup becomes master owner; further signups wait for owner approval; JWT cookies.
- Master-owner controls per-user client limit and can suspend/reactivate members.
- Excel importer maps uploaded workbooks (financials / directors / auditors) into first-class records — not a workbook clone.
- Every state change writes to an immutable audit log per client.

## User personas
- PCS compliance professional owner or member managing several company clients.
- Client company stakeholders reviewing obligations, deadlines, ownership, evidence.

## Modules
- Overview: portfolio metrics + reminders across all clients.
- Clients: create/edit/delete workspaces, quota-aware.
- Register: obligations with assignee, remarks, filed date, SRN, expandable detail.
- Master data: Directors / Auditors / Financials CRUD.
- Import from Excel: preview sheets, auto-suggest mapping, one-click apply per target.
- Audit trail: per-client immutable timeline.
- Team & approvals (owner): pending requests, member list, edit client limit, suspend/reactivate.

## What has been implemented — 2026-08-17
- Approval-based signup/login with JWT cookies; suspended-account guard.
- Owner APIs: requests queue, users list w/ usage, client-limit editor, suspend/reactivate.
- Multi-client workspaces with ownership isolation and 404 for cross-owner access.
- Compliance register with assignee, remarks, filed date, SRN, priority, due-date edits; seed obligations added on first open.
- Master data collections (directors/auditors/financials) with CRUD.
- Excel import: multi-sheet preview, per-sheet target selection, auto-suggested column mapping with synonyms, apply-inserts and per-record required-field validation.
- Portfolio dashboard aggregating clients, obligations, overdue, due-soon, completed and non-overdue coverage %.
- Reminders endpoint sorting all pending obligations by due date across the portfolio.
- Immutable audit log capturing client, obligation, master-data, import and evidence events.
- Modular frontend under `src/pages/*` and `src/lib/api.js` with `data-testid`s on every interactive element.

## Prioritized backlog
- P1: Evidence-to-obligation linking and file preview.
- P1: Statutory calendar view (per-year, per-client) with month grid.
- P1: Notification/reminder delivery (email or in-app queue) once a provider is chosen.
- P1: Editable client details from within the workspace (address, incorporation date).
- P2: PDF/Excel reports (audit pack, due status, client health).
- P2: Import mapping templates + per-user saved mappings.
- P2: Team role expansion (reviewer/reader/admin).

## Next tasks
- Wire evidence uploads visually into the register row and audit log.
- Add a month calendar view driven by `/api/reminders` grouped by month.
- Introduce a "recurring obligation" concept (yearly/quarterly) so seeds regenerate correctly.
