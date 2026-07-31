## Highlights

- End-to-end industrial maintenance work-order workflow
- AI-assisted fault parsing and Copilot Q&A
- Structured knowledge citations
- Technician execution and supervisor acceptance
- Maintenance reports and knowledge-base candidates
- RBAC, audit trails, migrations and transactional state management
- Full GitHub Actions CI
- Public demo on Netlify, Render and Neon PostgreSQL

## Validation

- Backend: 82 tests passed
- Frontend: 16 suites / 220 tests passed
- Playwright: 21 local E2E tests passed
- Public demo: 1 Smoke Test passed
- TypeScript and ESLint passed
- Next.js production build passed

## Online Demo

- Web: https://industrial-maintenance-copilot.netlify.app
- API: https://industrial-maintenance-copilot-api.onrender.com
- Health: https://industrial-maintenance-copilot-api.onrender.com/health

Demo password: `Demo123456`

- Admin: `admin@example.com`
- Supervisor: `supervisor@example.com`
- Technician: `tech@example.com`

## Security

- The public demo contains synthetic data only
- Mock AI is enabled and no paid model key is configured
- Demo users have no hosting or database platform privileges
- No database reset endpoint is exposed

## Known Limitations

- Public demo uses Mock AI
- Render Free cold starts can delay the first request
- Uploaded files are not guaranteed to persist across Render deploys
- No real PLC/SCADA integration
- No inventory deduction
- No production multi-tenant isolation
