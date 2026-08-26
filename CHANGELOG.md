# Changelog

## [2.0.1] - 2026-08-26

### Changed

- Added MIT licensing to the current source snapshot and synchronized frontend package-lock metadata.
- Removed duplicate project-positioning text from the README.
- Aligned Dockerfile project-name comments with `Industrial Maintenance Copilot`.
- Tightened the `master` governance policy to use normal merge commits only.

### Scope

- Repository maintenance only.
- No application behavior changes.
- No API contract changes.
- No ML/model changes.
- No database changes.
- No deployment changes.

## [2.0.0] - 2026-08-26

### Added

- Predictive maintenance research pipeline using Paderborn and XJTU-SY experimental datasets
- Leakage-safe grouped evaluation and model governance (DatasetVersion / TrainingRun / ModelVersion / PredictionRecord lineage)
- Fault classification V2 non-production staging workflow
- RUL evaluation with promotion rejection when quality gates fail
- OPC UA-compatible gateway abstraction and deterministic software simulator
- Polling and DataChange subscription ingestion with event buffering (debounce / batch / dedupe)
- Industrial data-quality validation (missing / NaN / bad status / stale / future timestamp / duplicate)
- Industrial alarm state machine and alarm correlation
- Evidence-bound RCA and RAG retrieval with explicit empty-evidence handling
- Controlled AI agent workflow with orchestrator and per-tool audit trail
- Human Review and OperationApproval safety gates
- End-to-end industrial trace context across the simulated workflow
- Prometheus-compatible runtime metrics and Trace Explorer APIs
- Optional OpenTelemetry instrumentation (disabled by default)
- Unified `/demo` workspace with lightweight operational equipment representation

### Changed

- Expanded the original work-order Copilot into an industrial AI maintenance platform
- Unified project naming under Industrial Maintenance Copilot
- Consolidated architecture, demo, safety, and limitation documentation

### Safety & Governance

- No PLC write path; gateway interaction remains read-only
- No autonomous equipment control
- Human Review remains mandatory for workflow progression where required
- Model promotion gates prevent rejected models from entering higher stages
- RUL model remains rejected by promotion gate

### Known Limitations

- Software OPC UA simulator; no real PLC/SCADA integration
- Lightweight operational representation only; not a high-fidelity physics digital twin
- Fault V2 remains research/non-production staging evidence
- Small independent frozen bearing count and high Development CV variance
- RUL not promoted
- No factory workload validation
- No production deployment was performed for this release.
- Trace propagation is in-process only
- No HA observability backend

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

[2.0.0]: https://github.com/ten10do/industrial-maintenance-copilot/releases/tag/v2.0.0
[2.0.1]: https://github.com/ten10do/industrial-maintenance-copilot/releases/tag/v2.0.1
[1.0.0]: https://github.com/ten10do/industrial-maintenance-copilot/releases/tag/v1.0.0
