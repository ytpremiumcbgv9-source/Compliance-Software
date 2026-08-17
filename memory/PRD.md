# PRD — ComplyEase (v3 · enterprise-ready)

## Positioning
A PCS practice compliance workspace. What it does well, it does completely. Nothing on the screen is a promise we can't keep.

## Original problem
Replace an Excel-based CACMS-style workbook with a web app that multiple PCS team members can share to track statutory compliance for many client companies.

## What ships (feature-locked)

### Authentication & access control
- Approval-based signup (first user = master owner, others queue for approval).
- JWT cookies with `secure`, `httponly`, `samesite=none`, 8-hour TTL.
- Password minimum 8 characters (signup and change).
- In-memory login rate limiter: 5 wrong attempts in 5 minutes per email → HTTP 429.
- Master owner can approve, reject, suspend, reactivate members and edit their per-user client limit.

### Client workspaces
- Multi-tenant isolation: every list/read/write is scoped to the owning user.
- Per-user client quota enforced on create.
- One-click **demo client** ("Sunrise Innovations Pvt Ltd") seeds directors, shareholders, auditors, a charge, a resolution, financials, and a full FY compliance calendar.

### Compliance register (recurring engine)
- 15-rule statutory library: MGT-7, AOC-4, DIR-3 KYC, ADT-1, DPT-3, MSME-1 (H1+H2), AGM, BM Q1–Q4, CSR-2, MBP-1, IEPF-2.
- **Generate FY** button materialises the full year's obligations idempotently (rerun creates 0).
- Per-obligation fields: assignee, remarks, filed date, SRN, priority, description, recurrence, FY.
- Chip filters for status buckets (Overdue / Ready for review / Due soon / On track / Approved / Completed).
- **Maker-checker**: Submit → status `Ready for review`; Approve / Send-back; the submitter cannot self-approve unless they are the owner.
- **Evidence per obligation**: upload files against a specific obligation, list, remove; cross-client linking blocked at the API.

### Statutory registers
- Members / Charges / Resolutions / Contracts CRUD, plus Directors / Auditors from Master data.
- One-click **CSV export** for every register with the company header block.

### Master data
- Directors / Auditors / Financials CRUD.

### Import wizard
- Multi-sheet Excel preview.
- Auto-suggested column mapping using a shared synonym table (frontend + backend).
- Changing the target dropdown re-runs the mapping suggestion locally.
- One-click apply inserts real records with required-field validation.

### Portfolio & alerts
- Overview dashboard with 6 aggregate metrics + "Upcoming across portfolio" pending list.
- Notifications bell (topbar) with T-30 / T-7 / T-1 / Overdue buckets and per-user dismissal.
- Reminders endpoint sorts all pending obligations by due date across the portfolio.

### Audit trail
- Immutable per-client timeline covering client / obligation / master data / statutory register / evidence / import / maker-checker events.

### Settings
- Profile update (name, practice name).
- Change password (verifies current, min 8, updates hash).

### Onboarding
- 7-step guided product tour with spotlight highlight, dismissible and restartable from the topbar help button.
- Empty-state heroes on Overview and Clients with clear CTAs; Register empty state points to "Generate FY".

## What is deliberately NOT in the product yet
No half-baked features are exposed. The following are not built, and nowhere in the UI do we promise them:

- Email / WhatsApp reminder delivery (in-app bell only).
- PDF register export (CSV only).
- Event-based filing chains (DIR-12, PAS-3, INC-22).
- Client portal / external e-signature.
- LLP compliance forms (Form 8, Form 11, DPIN).
- MCA XML generation / direct MCA integration.
- Detailed role hierarchy beyond owner/member.
- Multi-worker rate limiting (in-memory today; document as single-worker deploy).

## Verified with automated tests
- 30 backend pytest cases · 100% pass on external URL.
- Playwright / screenshot UI verification for auth, dashboard, clients, register (generate + chips + maker-checker + evidence), statutory registers, master data, import wizard, audit trail, team, notifications bell, settings, and the onboarding tour.

## Operational notes
- Backend: FastAPI + Motor + PyMongo (Mongo indexes on users.email, clients.owner_user_id, obligations.client_id, audit_log).
- Frontend: React + Axios + Framer Motion, modular under `src/pages/*` and `src/lib/api.js`.
- Deploy assumption: **single backend worker** (in-memory rate limiter). Move to Redis if scaling out.
- Startup migration deletes legacy pre-rule-engine obligations (missing `code` field).
