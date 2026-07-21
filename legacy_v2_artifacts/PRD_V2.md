# Green Papaya — PRD & Build Log

## Original Problem Statement
Dual-sided collaborative AI tax preparation & validation workspace for Indian taxpayers and Chartered Accountants (CAs). Ingest unstructured financial docs (Form 16, broker P&L, bank statements), parse with multimodal AI, run a deterministic tax engine (Old vs New regime, AY 2026-27 / FY 2025-26), reconcile against AIS/26AS, let CAs validate with immutable audit trails, and compile a schema-compliant ITD offline JSON. Design: Ventriloc editorial light theme.

## Architecture
- **Frontend**: React 19 + Tailwind (Ventriloc tokens: Graphite/Ash/Ivory + Ember-orange accent, Inter Tight display / Inter body), recharts, shadcn/ui.
- **Backend**: FastAPI + MongoDB (Motor). Modules: `server.py` (routes), `tax_engine.py` (deterministic core), `parser.py` (PyMuPDF regex + Gemini vision), `storage.py` (Emergent object storage), `crypto_vault.py` (AES-256-GCM for PAN etc).
- **Auth**: Emergent-managed Google OAuth. Session via httpOnly cookie + Bearer (localStorage `gp_token`). Roles: taxpayer, ca_partner (RBAC).
- **Integrations**: Gemini 2.5-flash vision (Emergent LLM key) for Form 16 extraction with local regex fallback; Emergent object storage; WhatsApp webhook provision (`/api/v1/integrations/whatsapp`, Twilio-ready).

## User Personas
1. **Taxpayer** — uploads docs, explores Old vs New regime sandbox, requests CA verification.
2. **Chartered Accountant** — triages clients, validates in split-pane desk, resolves AIS mismatches, logs justified overrides, compiles ITD JSON.

## Implemented (2026-07-03)
- Google OAuth + role selection; RBAC-protected routes.
- Taxpayer dashboard + per-filing workspace (Documents / Optimize / Reconcile / Export tabs).
- Document upload to object storage + Form 16 parsing (Gemini + PyMuPDF regex fallback, confidence scoring, PAN masking).
- Deterministic tax engine: Old & New slabs, 87A rebate + marginal relief, HRA, 80C/80D caps, capital gains (STCG 20%, LTCG 12.5% over 1.25L), 4% cess, regime recommendation, slab-utilization data.
- CA console: stats, client linking, triage table, split-pane validation desk, field override with mandatory-justification immutable audit logs, lock & compile.
- ITD offline JSON compiler + export; audit trails page.
- WhatsApp intake webhook provision + CA queue view (MOCK — no Twilio yet, by user request).
- Ventriloc editorial UI with charts/infographics.

## Implemented — Production hardening (2026-07-03, iteration 2)
- **Real AIS decryptor** (`ais_decryptor.py`): PBKDF2-HMAC-SHA256 (1000 iters) + AES-CBC/PKCS7, password `pan.lower()+"GQ39%*g"+dob` with fallbacks; accepts encrypted ITD utility export OR plain decrypted JSON; recursive amount extractor → salary/dividend/interest/TDS/CG. Reconciliation now uses the REAL uploaded AIS (no mock); `/reconcile` returns 400 until AIS is provided.
- **Multi-image / multi-page Form 16**: upload multiple files, `parse-documents` sends all to Gemini in one call for a consolidated extraction merged with per-PDF regex.
- **Client-facing computation PDF** (`pdf_report.py`, reportlab): branded income summary, Old-vs-New comparison, slab breakup, reconciliation notes, disclaimer.
- **PDF coordinate highlighting** in CA desk: server renders PDF pages to PNG (`/documents/{id}/page/{n}`), `locate` searches text (Indian digit grouping) and returns pixel rects; frontend overlays highlight boxes with page navigation.
- Verified: 36/36 backend pytest + full frontend E2E (100%/100%).

## Backlog
- **P1**: Real Twilio WhatsApp wiring (needs credentials); real AIS decryptor (`decrypt-ais`) for encrypted ITD AIS JSON; PDF coordinate highlighting in CA desk; automated DPDP purge scheduler.
- **P2**: Multi-employer Form 16 compilation; ITR-3/ITR-4 presumptive schemas; conversational tax Q&A (ita-kg RAG); client-facing computation PDF; split server.py into routers.

## Notes / Constraints
- Gemini LLM budget can intermittently be 0 → parser gracefully falls back to local regex for digital PDFs. If parsing scanned images is needed, top up the Universal Key (Profile → Universal Key → Add Balance).
- App is served same-origin at REACT_APP_BACKEND_URL. Test credentials in `/app/memory/test_credentials.md`.

## Next Tasks
- Await user feedback; wire Twilio when credentials provided; add computation PDF export.
