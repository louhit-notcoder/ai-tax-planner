# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Green Papaya V3 is a CA-supervised workspace for preparing individual Indian income-tax
returns (AY 2026-27 / FY 2025-26). Its defining constraint: **all tax numbers come from a
deterministic engine over an immutable fact snapshot and pinned rules, are evidence-linked
to source documents, and pass through maker-checker approval before anything is filed.** The
AI assistant can explain and organise but never computes filed figures.

The repo is a monorepo with a Python `backend/` (FastAPI + PostgreSQL) and a `frontend/`
(Vite + React + TypeScript). There is **no root `package.json`** — the `Makefile` is the
entry point for common tasks.

The active code is the V3 tree. `backend/legacy_v2/`, `frontend/legacy_v2/`,
`legacy_v2_artifacts/`, and the many `*_V2.md` / `PUSH_*.sh` files are historical artifacts —
do not extend them.

## Commands

Run these from the repo root (the Makefile sets `PYTHONPATH=backend` for you):

```bash
make test          # backend test suite: pytest backend/tests_v3 (plugin autoload disabled)
make backend       # uvicorn dev server on :8000  (cd backend && uvicorn main:app --reload)
make frontend      # vite dev server on :3000     (cd frontend && npm run dev)
make migrate       # alembic upgrade head
make up / make down# docker compose up --build / down (full stack)
make syntax        # python compileall + node scripts/check_frontend_syntax.js
make secrets       # scripts/verify_no_embedded_secrets.py
make clean         # remove __pycache__, *.pyc, .pytest_cache, frontend/dist
```

Run a single backend test (mirror the Makefile's env — the plugin-autoload flag matters):

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend pytest -q \
  backend/tests_v3/test_engine_golden_v3.py::test_old_regime_80c_cap_and_salary_standard_deduction
```

Frontend build / typecheck (no test runner is configured for the frontend):

```bash
cd frontend && npm run build     # tsc && vite build
```

Rule/schema regeneration (needs configured official sources):
`make schema-sync` (`scripts/sync_official_itr_artifacts.py`) and
`make legal-sync` (`scripts/ingest_official_legal_sources.py`).

## Backend architecture

FastAPI app assembled in [backend/app/main.py](backend/app/main.py): all routers mount under
`/api`, and a single middleware enforces per-IP rate limiting, strict security headers, and a
cross-site origin check on mutating requests. `backend/main.py` re-exports `app.main:app`.

The request path is layered: **`app/api/*_routes.py` (thin HTTP) → `app/services/*` (orchestration)
→ `app/tax_engine`, `app/itr`, `app/legal`, `app/document_adapters` (domain logic)**, with
`app/db_models.py` (SQLAlchemy) as the persistence layer. Pydantic request/response schemas live
in [backend/app/api/schemas.py](backend/app/api/schemas.py).

Key pillars, and why they exist:

- **Deterministic tax engine** ([app/tax_engine/engine.py](backend/app/tax_engine/engine.py)):
  a pure function `compute(facts, rules)` with **no database, network, filesystem, env, or LLM
  access**. It takes a `TaxFactSnapshot` plus a rule bundle and emits a `ComputationResult` with
  per-line traceability (`CalculationLine` links each figure to input facts + rule ids) and a
  `result_hash` for byte-level reproducibility. Both old and new regimes are always computed and
  compared. Do not introduce side effects here.

- **Pinned rule releases**: tax constants live as versioned JSON in
  `backend/rules/releases/` (e.g. `AY2026_27_V3.0.0.json`), loaded via
  [app/tax_engine/rules.py](backend/app/tax_engine/rules.py) with a canonical hash. Change tax
  behaviour by editing/adding a rule release, not by hardcoding numbers in the engine.

- **AI assistant is capability-gated, not trusted**: the model (via
  `OpenRouterModelClient` in [app/services/assistant_service.py](backend/app/services/assistant_service.py),
  configured with `OPENROUTER_*` env vars) can only call an **allowlisted tool gateway**
  (`AssistantToolGateway`). Every tool is mapped to an RBAC permission in `TOOL_PERMISSION` and
  audited. The chat loop in [app/services/chat_service.py](backend/app/services/chat_service.py)
  wires this together; the model has no DB credentials and never produces filed tax figures —
  it reads engine output via `explain_computation`/`compare_regimes`. When adding an assistant
  capability, add a `tool_<name>` handler **and** its `TOOL_PERMISSION` entry.

- **Documents → candidate facts → canonical facts**: format-specific adapters in
  `app/document_adapters/` (Form 16, AIS, 26AS/TIS, brokers, banks, previous ITR) register via
  `registry.py` and produce *candidate* facts. Facts become canonical only through review
  (`fact_routes` / `facts_service`). Uploads flow through `document_security.py` /
  `storage.py` (encrypted, ClamAV scan when enabled).

- **ITR export is fail-closed** ([app/itr/exporter.py](backend/app/itr/exporter.py)): export
  raises unless the computation is `COMPLETE`, a CA reviewer has approved, the form is eligible,
  and a pinned official JSON schema + validator (`schema_registry.py`, `utility_validator.py`)
  are present. Only ITR-1 / ITR-2 are in scope.

- **AuthZ**: role→permission map `ROLE_PERMISSIONS` and helpers (`has_permission`,
  `assert_case_access`) in [app/security.py](backend/app/security.py). Roles: `firm_owner`,
  `ca_partner`, `ca_manager`, `preparer`, `document_operator`, `auditor`, `client_portal`.
  Access is tenant- and case-scoped; privileged roles require MFA when
  `REQUIRE_MFA_FOR_PRIVILEGED_ROLES` is on. Every mutation should append to the audit log
  (`app/audit.py`).

Schema changes: models are in `app/db_models.py`; migrations in `backend/alembic/versions/`
(`make migrate`). `create_all()` runs automatically only in non-production (`main.py` lifespan).

## Frontend architecture

Vite + React 18 + TypeScript, shadcn/ui components (`src/components/ui/`) on Radix + Tailwind.
`@/` aliases `frontend/src/` (see `vite.config.ts` and `tsconfig.json`). The active app is the
**V3** surface: routing in [src/App.tsx](frontend/src/App.tsx) with a `Protected` wrapper and
pages in `src/pages/v3/` (`LoginV3`, `MfaSetupV3`, `DashboardV3`, `CaseWorkspaceV3` — a
chat-first case workspace). `src/features/*` holds feature-scoped UI (assistant, cases,
computation, evidence, review, etc.).

API access goes through the shared axios client in [src/lib/api.ts](frontend/src/lib/api.ts):
base URL from `VITE_BACKEND_URL`, `withCredentials: true` (auth is HTTP-only cookies, not bearer
tokens in JS), with an interceptor that transparently retries once after `POST /auth/refresh`.
Auth state lives in [src/context/AuthContext.tsx](frontend/src/context/AuthContext.tsx).

## Deployment & environment

- **Local**: `make up` (docker-compose full stack) or the Neon-Postgres path in
  [README_LOCAL.md](README_LOCAL.md). Copy `.env.example` → `.env` and replace every `CHANGE_ME`.
- **Backend** deploys to Render ([render.yaml](render.yaml)); **frontend** to Vercel
  (`frontend/vercel.json`). They are different origins, so auth cookies use
  `COOKIE_SAMESITE=none; COOKIE_SECURE=true` and CORS origins are explicit — mind this when
  touching auth or CORS.
- Production config is validated at startup (`Settings.validate` in
  [app/config.py](backend/app/config.py)): it hard-fails if `ALLOW_DEV_BOOTSTRAP` or
  token-exposure is on, secrets are too short, or `APP_BASE_URL` isn't HTTPS.

## Conventions

- Money/tax math uses `Decimal` throughout the engine (`app/tax_engine/math_utils.py`); never
  use floats for financial values.
- The engine surfaces limits it can't safely handle as `blockers`/`warnings` with
  `review_required` rather than guessing — preserve that fail-safe behaviour when extending scope.
- Deeper design docs live in `docs/` (`TAX_SCOPE.md`, `ITR_EXPORT.md`, `SECURITY.md`,
  `API_V3.md`, `PRODUCTION_RUNBOOK.md`). No CA-facing correctness claim is final without the
  external release gates in `docs/EXTERNAL_RELEASE_GATES.md`.
