# Frontend route regression audit

Audit date: 2026-08-03

- `master` page files: 19
- `feat/real-predictive-ml-pipeline` page files: 19
- Removed routes: none
- Added routes: none
- Overwritten legacy pages: none

The Next.js production build's `Generating static pages (17/17)` message counts
static-generation work items. It is not the application route count. The final
route table contains the same 19 application routes as `master` (plus Next.js
`/_not-found`).

The inventory is enforced by `route-regression.test.ts`, while Playwright covers
navigation through equipment, monitoring, predictive maintenance, approvals,
work orders, fault reports, knowledge, and Copilot flows.
