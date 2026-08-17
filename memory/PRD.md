# PRD — ComplyEase PCS Multi-Client Compliance Suite

## Original problem statement
I have built an excel based compliance software. Basic idea is take from comply relax. Can you use that excel and create a working web based app with same functionality? Its heavy and unusable in excel as its too complicated and boring.

## Architecture decisions
- React frontend with FastAPI and MongoDB backend.
- No sign-in in the first release; PCS users manage multiple client workspaces from one session.
- Workbook concepts become focused screens: dashboard, register, calendar, clients, evidence.
- Mongo responses explicitly exclude internal ObjectIds.

## User personas
- PCS compliance professional managing several company clients.
- Client company stakeholders reviewing obligations, deadlines, ownership, and evidence.

## Core requirements
- Multi-client workspace switching.
- Compliance register with owners, due dates, priority, risk, and status.
- Evidence uploads, audit trail foundation, dashboard metrics, calendar, and CSV export.
- Modern, less intimidating replacement for the CACMS workbook.

## What has been implemented — 2026-08-17
- Live PCS dashboard with portfolio metrics and active client context.
- Client workspace creation and switching backed by MongoDB.
- Seeded obligation register with search, status updates, risk highlighting, and due dates.
- Statutory calendar, client directory, evidence upload endpoint, toast feedback, and CSV export.
- Responsive desktop/mobile layout with testable controls and validated browser flows.

## Prioritized backlog
P0: Add full Excel workbook import/parser preview and map actual workbook rows into obligations.
P0: Add reminder and escalation rules with configurable owner notifications.
P1: Add evidence-to-obligation linking and a visible audit history timeline.
P1: Add People, auditors, directors, and financial inputs screens from the workbook.
P2: Add polished PDF/report generation and role-based sign-in for PCS teams.

## Next tasks
- Convert workbook applicability matrix and threshold engine into server-side rules.
- Build import review screen for CACMS sheets and formulas.
- Add client-level audit history and reminder queue.
