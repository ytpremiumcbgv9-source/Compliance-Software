# PRD — ComplyEase PCS Multi-Client Compliance Suite

## Original problem statement
User has an Excel-based compliance software (CACMS) inspired by ComplyRelax. Requirement is a working web app with full PCS workflow — dashboards, obligation register, master data, imports, audit trail, and paid-tier features (recurring engine, statutory registers, notifications, maker-checker).

## Architecture decisions
- React (pages under `src/pages/*`) + FastAPI + MongoDB.
- Approval-based auth: first signup = master owner; others need approval. JWT cookies.
- Master-owner: per-user quotas and suspend/reactivate.
- Excel importer maps columns to real records (directors/auditors/financials).
- Every state change writes to an immutable audit log per client.

## Modules
- **Overview**: portfolio metrics + upcoming filings across all clients.
- **Clients**: create/edit workspaces, quota-aware, obligations/overdue counts per card.
- **Register**: obligations with assignee, remarks, filed date, SRN, priority, expandable detail; FY selector; **Generate FY** button that materialises 15 recurring statutory obligations for a chosen year; chip filters for status buckets; maker-checker Submit / Approve / Send-back buttons.
- **Statutory registers**: Members / Charges / Resolutions / Contracts CRUD; plus one-click **CSV export** for every register (Directors, Members, Charges, Resolutions, Contracts, Auditors).
- **Master data**: Directors / Auditors / Financials CRUD (also feeds statutory registers).
- **Import from Excel**: preview → per-sheet auto-mapping → apply into real records.
- **Audit trail**: per-client immutable event timeline.
- **Team & approvals** (owner): pending requests, member list, edit client limit, suspend/reactivate.
- **Notifications bell**: topbar dropdown with T-30 / T-7 / T-1 / Overdue buckets, dismiss, jump-to-client.

## Compliance rule library (recurring engine)
15 rules covering MGT-7, AOC-4, DIR-3 KYC, ADT-1, DPT-3, MSME-1 (H1+H2), AGM, four board meetings (Q1–Q4), CSR-2, MBP-1, IEPF-2. Due dates computed from FY (`fy_end+Nd`, `fixed:m-d`, `half1/2:m-d`, `quarter:n:m-d`). Idempotent: re-running the generator for the same FY does not duplicate.

## Maker-checker workflow
Register row → **Submit for review** flips status to `Ready for review` and records `submitted_by`. Reviewer then presses **Approve** (→ `Approved`) or **Send back** (→ `Rework`). Same user cannot approve their own submission unless they are the owner.

## What has been implemented — 2026-08-17 (v2)
- Recurring compliance engine + 15-rule library + FY generator.
- Statutory registers (Members, Charges, Resolutions, Contracts) + Directors/Auditors/Financials with CSV export.
- In-app notifications with T-30/T-7/T-1/Overdue buckets and per-user dismissal.
- Maker-checker workflow with submit / approve / rework and audit-log entries.
- All above verified end-to-end via curl and browser: rules(15), generate 26-27 (created 15, skip 0 on re-run), CSV download, notification bell shows counts and dropdown items with jump-to-client, submit/approve flows.

## Prioritized backlog (post-v2)
- P1: Email/WhatsApp delivery of the reminders queue.
- P1: Evidence-to-obligation linking + file preview.
- P1: PDF export of statutory registers (currently CSV).
- P1: Team-member role hierarchy (partner/manager/article) + per-client assignment.
- P2: XBRL for financials; MCA form prefill exports.
- P2: Client portal for their document uploads.
- P2: LLP module (Form 8 / Form 11 / DPIN).

## Next tasks
- Wire evidence uploads visually into the register row.
- PDF (jsPDF or ReportLab) rendering for MGT-1, MBP-1 with the company header.
- Delivery provider integration for reminders when the user selects one (Resend / SendGrid / SMS).
