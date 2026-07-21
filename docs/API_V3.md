# V3 API workflow

OpenAPI is available at `/docs` when the backend runs.

1. Authenticate and complete MFA: `/api/auth/*`.
2. Create client and case: `POST /api/clients`, `POST /api/cases`.
3. Upload and extract: `POST /api/cases/{id}/documents`, then
   `POST /api/documents/{document_id}/extract`.
4. Review candidate facts: `GET /api/cases/{id}/candidate-facts`,
   `POST /api/candidate-facts/{id}/review`.
5. Inspect canonical facts/evidence/reconciliation/missing items.
6. Run deterministic computation: `POST /api/cases/{id}/computations`.
7. Reviewer approves: `POST /api/computations/{id}/review`.
8. Pin official schemas and configure utility validator.
9. Build and approve immutable export: `POST /api/cases/{id}/exports`,
   `POST /api/exports/{id}/review`.
10. Lock approved case: `POST /api/cases/{id}/lock`.

The AI route `/api/cases/{id}/assistant/tools` accepts only literal allowlisted
operations. The server binds the active authorised case; the model cannot select
an arbitrary client case.
