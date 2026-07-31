# Changelog

## [1.0.0] - 2026-07-31

### Added

- Fault reporting and AI-assisted parsing
- Fault-report to work-order conversion
- Complete maintenance lifecycle and supervisor acceptance
- Role-based access control and audit trails
- Knowledge base and structured Copilot citations
- Maintenance reports and knowledge-base candidates
- PostgreSQL-compatible migrations and deterministic demo Seed
- GitHub Actions CI and Docker support
- Netlify, Render, and Neon public demo deployment
- Protected, idempotent public demo reset script
- Public-environment Playwright Smoke Test and screenshots

### Fixed

- Work-order reassignment and lifecycle permission checks
- Checklist category compatibility migration
- AI report fallback behavior
- Work-order detail unit-test regressions
- Lifecycle E2E navigation and timing stability
- PostgreSQL URL driver normalization
- Netlify Next.js runtime and patched Next.js deployment

### Known limitations

- AI runs in Mock mode in the public demo
- Render Free cold starts can delay the first request
- Uploaded files use ephemeral local storage in the public demo
- No real PLC/SCADA integration
- No real inventory deduction
- No production-grade multi-tenant isolation

[1.0.0]: https://github.com/ten10do/industrial-maintenance-copilot/releases/tag/v1.0.0
