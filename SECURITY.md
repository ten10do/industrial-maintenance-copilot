# Security Policy

## Scope

This repository is an industrial AI maintenance research and demonstration
platform. It runs against a deterministic software OPC UA simulator and is not
connected to real factory PLCs or production industrial networks.

## Reporting a Vulnerability

Please do **not** publicly disclose:

- credentials or API keys
- private certificates
- database passwords
- sensitive infrastructure details

Use GitHub private vulnerability reporting when available; otherwise contact
the repository maintainer privately before any public disclosure.

## Industrial Safety Boundary

- No real PLC/SCADA production integration is claimed or provided.
- The OPC UA workflow is read-only for device interaction; there is no PLC
  write path.
- There is no autonomous industrial control: AI outputs are recommendations
  only.
- Human approval gates (Human Review / OperationApproval) must not be
  bypassed by any workflow, demo, or tooling.

## Secrets

Real secrets must never be committed to this repository. Configuration uses
`.env.example` placeholders and environment-provided values; CI credentials
are synthetic test-only values.
