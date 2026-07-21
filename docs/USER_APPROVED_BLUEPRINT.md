execute the below plan, update our plan exactly like below 

Below is the complete production blueprint, built around the source code already reviewed and the new deterministic-engine architecture.
# Green Papaya AI Tax Assistant
## Complete Build-to-Production Plan
**Planning horizon:** 24–30 weeks
**First controlled CA pilot:** approximately week 16
**Limited production launch:** approximately week 24
**Initial market:** Indian CA firms preparing individual income-tax returns
**Initial supported forms:** ITR-1 and selected ITR-2 cases
**Primary product promise:** Every material number is evidence-linked, deterministically calculated, reviewable and reproducible.
---
# 1. Product definition
Green Papaya should not be positioned as a chatbot that knows tax.
It should be positioned as:
> **An AI-assisted tax preparation, reconciliation, computation and review workspace for Chartered Accountants.**
The product converts unstructured client documents and answers into:
1. Structured tax facts.
2. Page-level evidence.
3. Missing-information requests.
4. AIS/Form 26AS reconciliation.
5. Deterministic tax computation.
6. Old-versus-new-regime comparison.
7. CA review and approval.
8. Computation reports.
9. Officially validated ITR export data.
10. A complete audit trail.
The AI assists the CA. It does not independently decide the final tax position, approve evidence, override validation or file a return.
---
# 2. Initial production scope
A 10/10 product does not mean supporting every tax scenario on day one. It means being extremely reliable within a clearly defined scope and blocking unsupported cases safely.
## 2.1 Production V1 supported cases
V1 should support:
| Area               | Supported scope                                                |
| ------------------ | -------------------------------------------------------------- |
| Taxpayer           | Individual                                                     |
| Residential status | Resident and ordinarily resident                               |
| Return forms       | ITR-1 and selected ITR-2                                       |
| Salary             | One or multiple employers                                      |
| Pension            | Standard pension cases                                         |
| House property     | Up to two properties                                           |
| Other sources      | Bank interest, FD interest, dividends                          |
| Capital gains      | Listed Indian equity and selected mutual funds                 |
| Deductions         | Common Chapter VI-A deductions                                 |
| Regime             | Old and new regime                                             |
| Tax credits        | TDS, TCS, advance tax, self-assessment tax                     |
| Reconciliation     | AIS, TIS and Form 26AS                                         |
| Documents          | Form 16, bank certificates/statements, selected broker reports |
| Outputs            | Computation, issue list, evidence report and ITR data export   |
The Income Tax Department currently publishes separate AY 2026–27 schemas, utilities and validation rules. Its common ITR utility for ITR-1 through ITR-4 is currently version 1.2.2, released on July 17, 2026. The product must therefore pin schema and utility versions rather than assume one permanent format. ([Income Tax Department][1])
## 2.2 Expert-review-only cases
The system may collect and organise these cases, but must not mark the computation complete automatically:
* NRI and RNOR.
* Foreign assets.
* Schedule FA, FSI and TR.
* Foreign tax credit and Form 67.
* Foreign ESOPs and RSUs.
* Foreign brokerage accounts.
* Foreign trusts.
* Property capital gains.
* Unlisted shares.
* Virtual digital assets.
* Futures and options.
* Business or professional income.
* Presumptive taxation.
* Complex loss carry-forward.
* Agricultural-income rate integration.
* Clubbing involving complex relationships.
* Trusts, firms and companies.
The interface should display:
> **Expert review required — this scenario is outside the automated production scope.**
Unsupported income must never be represented as zero.
---
# 3. Non-negotiable product principles
## 3.1 The LLM never calculates final tax
The LLM may:
* Summarise documents.
* Explain calculations.
* Identify missing information.
* Propose candidate facts.
* Create draft client questions.
* Retrieve tax-law sources.
* Explain portal procedures.
The LLM may not:
* Approve a fact.
* Modify an approved fact.
* Select a final tax position.
* Change a tax-rule release.
* Override validation.
* Mark a filing final.
* Generate an unreviewed final export.
* File a return.
## 3.2 Every material fact has evidence
A number may enter the computation only when it has:
* A canonical field code.
* A source or approved manual declaration.
* A tax period.
* A validation state.
* An approval state.
* A complete audit history.
## 3.3 Every computation is reproducible
The same:
* Approved fact snapshot.
* Rule-release version.
* Engine version.
* Tax period.
must always produce the same result.
## 3.4 The system fails closed
When facts conflict, rules are unavailable or a scenario is unsupported, the computation becomes:
* `PROVISIONAL`
* `BLOCKED`
* `UNSUPPORTED`
It does not guess.
## 3.5 Legal updates never enter production automatically
Official updates may be detected automatically. Their interpretation, code changes, test cases and activation require human tax review.
## 3.6 CA approval remains mandatory
During V1, every final computation and export must be approved by an authorised CA reviewer.
---
# 4. Target system architecture
```text
┌────────────────────────────────────────────────────────────────────┐
│                          CA WEB APPLICATION                        │
│ Dashboard | Client Case | Assistant | Evidence | Review | Export  │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                         API Gateway / BFF
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
 Authentication          Case Management          AI Tool Gateway
 & Authorization         Service                  Allowlist only
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
 Document Service        Tax Fact Ledger          Tax Law Retrieval
 OCR & extraction        Evidence & approvals     Official sources
        │                        │
        ▼                        ▼
 Object Storage          Fact Snapshot Service
                                 │
                                 ▼
                     Deterministic Tax Engine
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
  Calculation Trace      Form Eligibility       Reconciliation
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 ▼
                         ITR Export Service
                      Schema + validation rules
                                 │
                                 ▼
                       Immutable Export Snapshot
```
---
# 5. Recommended technology stack
The existing React and FastAPI foundation may be retained, but the backend should be modularised and the financial system of record moved to PostgreSQL.
## 5.1 Frontend
* React with TypeScript.
* React Query or equivalent server-state library.
* A typed API client generated from OpenAPI.
* A reliable PDF viewer with coordinate highlighting.
* Accessible component system.
* Form validation through shared schemas.
* Feature flags for unfinished tax modules.
* Error boundaries and session-expiry handling.
## 5.2 Backend
* FastAPI.
* Pydantic strict models.
* SQLAlchemy or equivalent ORM.
* Alembic migrations.
* PostgreSQL.
* Background job queue.
* Redis for short-lived locks and queues, not as financial storage.
* S3-compatible encrypted object storage.
* PostgreSQL full-text search plus vector search for legal retrieval.
* Separate AI tool gateway.
* OpenTelemetry-compatible tracing.
## 5.3 Infrastructure
Recommended production components:
| Component                | Purpose                                          |
| ------------------------ | ------------------------------------------------ |
| Managed PostgreSQL       | Canonical financial and audit data               |
| Encrypted object storage | Source documents, page images and evidence crops |
| Managed Redis            | Jobs, rate limiting and short-lived locks        |
| Container runtime        | Backend and workers                              |
| CDN/WAF                  | Web delivery and perimeter protection            |
| Key-management service   | Encryption key storage and rotation              |
| Secrets manager          | API keys and credentials                         |
| Centralised logs         | Security and application monitoring              |
| Metrics and alerts       | Reliability and operational visibility           |
| Backup vault             | Database and object-storage recovery             |
Prefer an Indian cloud region for the initial deployment unless a documented legal and security review approves another arrangement.
---
# 6. Repository restructuring
The current `server.py` should be decomposed before new product capabilities are added.
```text
backend/app/
├── api/
│   ├── auth_routes.py
│   ├── tenant_routes.py
│   ├── case_routes.py
│   ├── document_routes.py
│   ├── fact_routes.py
│   ├── computation_routes.py
│   ├── assistant_routes.py
│   ├── review_routes.py
│   └── export_routes.py
├── auth/
│   ├── identities.py
│   ├── roles.py
│   ├── permissions.py
│   ├── tenant_policy.py
│   └── case_policy.py
├── tenants/
├── cases/
├── documents/
│   ├── security.py
│   ├── classifier.py
│   ├── pipeline.py
│   └── adapters/
├── evidence/
├── facts/
├── tax_engine/
├── rules/
├── reconciliation/
├── legal_knowledge/
├── assistant/
├── exports/
├── communications/
├── audit/
├── observability/
└── workers/
```
The frontend should similarly move from large pages to feature modules:
```text
frontend/src/
├── app/
├── auth/
├── dashboard/
├── cases/
├── documents/
├── evidence/
├── assistant/
├── computation/
├── reconciliation/
├── review/
├── exports/
└── shared/
```
---
# 7. Multi-tenant security model
Security remediation is the first engineering milestone.
## 7.1 Tenant hierarchy
```text
CA Firm
 ├── Firm Owner
 ├── Partner / Final Reviewer
 ├── Manager
 ├── Preparer
 ├── Document Operator
 ├── Read-only Auditor
 └── Client Portal User
```
Every database record must have a `tenant_id`.
Every client case must have:
* Owning tenant.
* Assigned preparer.
* Assigned reviewer.
* Explicit permitted users.
* Current workflow status.
## 7.2 Remove self-selected roles
Users must never select `ca_partner` or another privileged role themselves.
Role assignment must be performed by:
* Firm owner.
* Authorised administrator.
* Controlled invitation workflow.
## 7.3 Authorization model
Use both role-based and object-level authorization.
Every endpoint must verify:
```text
Is the user authenticated?
Does the user belong to the tenant?
Does the case belong to that tenant?
Is the user assigned or otherwise permitted?
Does the role permit the requested operation?
Is the case state compatible with this action?
```
The permission decision must occur in the backend, not the frontend.
## 7.4 Server-bound AI context
The model must never choose an arbitrary case ID.
```python
class ToolExecutionContext:
    tenant_id: UUID
    user_id: UUID
    active_case_id: UUID
    permissions: frozenset[str]
    request_id: UUID
```
The model calls:
```text
read_case_facts()
```
The server injects the authorised active case internally.
## 7.5 Maker-checker model
A preparer may:
* Upload documents.
* Review extraction.
* Propose corrections.
* Prepare a computation.
A reviewer may:
* Approve high-risk facts.
* Resolve overrides.
* Approve the final computation.
* Approve export generation.
The same user should not prepare and finally approve high-risk cases unless the firm explicitly allows a sole-practitioner mode.
---
# 8. Core data model
## 8.1 Main entities
| Entity               | Purpose                                         |
| -------------------- | ----------------------------------------------- |
| Tenant               | CA firm                                         |
| User                 | Staff or client identity                        |
| Client               | Taxpayer master                                 |
| TaxCase              | One taxpayer for one tax period                 |
| Document             | Uploaded original file                          |
| DocumentVersion      | Revised or replacement document                 |
| ExtractionRun        | One parser/model execution                      |
| EvidenceClaim        | A field candidate anchored to a source location |
| CandidateFact        | Proposed structured tax fact                    |
| CanonicalFact        | Accepted case fact                              |
| FactSnapshot         | Immutable facts used for computation            |
| RuleRelease          | Approved tax-rule bundle                        |
| ComputationRun       | One deterministic computation                   |
| CalculationLine      | Formula-level trace                             |
| ReconciliationItem   | Comparison across AIS, 26AS and documents       |
| MissingItem          | Required unanswered information                 |
| ClientQuestionDraft  | AI or staff-created draft                       |
| DocumentRequestDraft | Requested document draft                        |
| Approval             | Human review decision                           |
| ExportSnapshot       | Immutable ITR export package                    |
| AuditEvent           | Append-only action history                      |
## 8.2 Candidate fact lifecycle
```text
EXTRACTED
   ↓
VALIDATED
   ↓
PENDING_REVIEW
   ├── ACCEPTED → CANONICAL
   ├── REJECTED
   ├── CONFLICTING
   └── SUPERSEDED
```
## 8.3 Canonical fact example
```json
{
  "fact_id": "uuid",
  "tenant_id": "uuid",
  "case_id": "uuid",
  "field_code": "SALARY.GROSS.EMPLOYER",
  "value_type": "money",
  "value": {
    "amount": "1451200.00",
    "currency": "INR"
  },
  "tax_period": "FY_2025_26",
  "status": "APPROVED",
  "source_evidence_claim_ids": ["uuid"],
  "approved_by": "uuid",
  "approved_at": "2026-07-21T10:00:00Z",
  "version": 3
}
```
Use `Decimal`, never floating-point numbers, for money.
---
# 9. Document ingestion and parsing system
## 9.1 Upload security
Before parsing:
1. Verify file signature and MIME type.
2. Reject unsupported or executable content.
3. Virus-scan.
4. Calculate SHA-256 hash.
5. Detect exact duplicates.
6. Detect password protection.
7. Store immutable original.
8. Strip or disable active content for rendering.
9. Record uploader, timestamp and case.
10. Create an audit event.
## 9.2 Document states
```text
UPLOADED
→ SECURITY_CHECKED
→ CLASSIFIED
→ EXTRACTION_RUNNING
→ EXTRACTED
→ VALIDATION_REQUIRED
→ REVIEWED
→ ACCEPTED
```
Possible failure states:
* `PASSWORD_REQUIRED`
* `UNREADABLE`
* `WRONG_CLIENT`
* `DUPLICATE`
* `UNSUPPORTED_FORMAT`
* `PARSER_FAILED`
## 9.3 Extraction routing
```text
Digital PDF
→ Native text and coordinate extraction
→ Document-specific adapter
Scanned PDF
→ Page rendering
→ OCR and layout detection
→ Document-specific adapter
Spreadsheet/CSV
→ Typed tabular parser
→ Schema detection
Image
→ Image preprocessing
→ OCR/vision extraction
```
## 9.4 Extraction hierarchy
Use:
1. Native digital extraction.
2. Document-specific deterministic parser.
3. Table extraction.
4. OCR fallback.
5. Vision model for difficult fields.
6. Manual review when paths disagree.
The vision model is an extraction assistant, not the sole evidence source.
## 9.5 Evidence structure
Every extracted field retains:
* Document ID.
* Document version.
* Page.
* Bounding box.
* Original text.
* Evidence image crop.
* Extraction method.
* Parser version.
* Model ID where used.
* Extraction timestamp.
* Validation results.
Clicking any computation value should open the exact source location.
## 9.6 Initial document adapters
Build in this order:
1. Form 16 Part A.
2. Form 16 Part B.
3. AIS JSON/utility export.
4. TIS.
5. Form 26AS.
6. Bank interest certificate.
7. SBI statement.
8. HDFC statement.
9. ICICI statement.
10. Zerodha tax P&L.
11. Groww capital-gains report.
12. CAMS report.
13. KFintech report.
14. Previous-year ITR JSON.
15. Previous-year computation Excel/PDF.
Each adapter requires:
* Fixture set.
* Field schema.
* Mandatory signals.
* Numeric validations.
* Duplicate handling.
* Revision detection.
* Supported version list.
* Field-level accuracy metrics.
## 9.7 Multiple-document handling
Never ask the model to “select the most complete value.”
Instead:
```text
Employer A Form 16 → Employment record A
Employer B Form 16 → Employment record B
Revised Form 16 → New version linked to original
Bank account A → Account record A
Bank account B → Account record B
```
Revised documents supersede prior versions only after explicit review.
---
# 10. Deterministic tax engine
## 10.1 Pure core function
```python
def compute_tax(
    facts: TaxFactSnapshot,
    rules: TaxRuleBundle
) -> ComputationResult:
    """
    No database calls.
    No network calls.
    No LLM calls.
    No environment-based behaviour.
    No current-date lookup.
    """
```
Database loading and result storage happen in an orchestration service outside the engine.
## 10.2 Engine pipeline
The production order should be:
1. Validate taxpayer profile and tax period.
2. Determine residential status.
3. Determine regime and election validity.
4. Compute salary income.
5. Compute house-property income.
6. Compute capital gains transaction by transaction.
7. Compute income from other sources.
8. Compute business income when that module is later enabled.
9. Apply clubbing provisions.
10. Apply intra-head set-off.
11. Apply inter-head set-off.
12. Apply brought-forward losses.
13. Calculate Gross Total Income.
14. Apply eligible deductions and restrictions.
15. Calculate Total Income.
16. Allocate normal and special-rate income.
17. Calculate tax by bucket.
18. Apply section 87A rebate and its applicable marginal relief.
19. Calculate surcharge.
20. Apply surcharge marginal relief.
21. Calculate cess.
22. Apply relief under applicable provisions.
23. Calculate interest and fees.
24. Reconcile TDS, TCS and tax payments.
25. Calculate refund or payable.
26. Apply statutory rounding.
27. Produce schedule-ready computation data.
28. Run product validation and blocker rules.
## 10.3 Tax buckets
Each bucket must retain more than a total:
```python
class TaxBucket:
    code: TaxBucketCode
    gross_amount: Decimal
    current_year_loss_setoff: Decimal
    brought_forward_loss_setoff: Decimal
    exemption_amount: Decimal
    taxable_amount: Decimal
    source_fact_ids: list[UUID]
    rule_ids: list[str]
    calculation_line_ids: list[UUID]
```
Initial bucket types include:
* Normal-rate income.
* Section 111A income.
* Section 112A income.
* Other short-term gains.
* Other long-term gains.
* Lottery and similar income.
* Virtual digital assets.
* Foreign special-rate income.
* Agricultural income for rate integration.
## 10.4 Calculation trace
Every line records:
```json
{
  "line_code": "SALARY_NET_EMPLOYER_A",
  "formula": "gross_salary - eligible_exemptions - professional_tax",
  "input_fact_ids": ["fact-1", "fact-2"],
  "input_line_ids": [],
  "rule_ids": ["AY2026_27_SALARY_001"],
  "result": "1316200.00"
}
```
This trace powers:
* Human-readable explanation.
* Review.
* Debugging.
* Regression testing.
* Audit.
* Calculation comparison.
## 10.5 Engine result states
```text
COMPLETE
PROVISIONAL
BLOCKED
UNSUPPORTED
FAILED
```
A result also contains:
* Facts used.
* Facts not used.
* Missing information.
* Warnings.
* Blocking issues.
* Assumptions.
* Rule-release hash.
* Fact-snapshot hash.
* Engine commit.
* Result hash.
---
# 11. Tax-rule release system
## 11.1 Separate the two legal namespaces
The platform must support:
```text
Income-tax Act, 1961
→ Earlier periods through AY 2026–27
Income-tax Act, 2025
→ Tax Year 2026–27 onward
```
Official transition guidance confirms that the “tax year” concept applies from April 1, 2026 for income earned during FY 2026–27, while periods through AY 2026–27 remain governed by the earlier framework. ([Etds][2])
## 11.2 Rule-release lifecycle
```text
DETECTED
→ DRAFT
→ TAX_EXPERT_REVIEW
→ IMPLEMENTATION
→ TESTING
→ APPROVED
→ ACTIVE
```
A release contains:
* Applicable tax period.
* Act namespace.
* Source documents.
* Rule definitions.
* Code commit.
* Test-case changes.
* Reviewer identities.
* Approval timestamp.
* Release hash.
## 11.3 Daily legal update process
Every day:
1. Check official CBDT, Income Tax Department and Gazette sources.
2. Detect new or changed documents.
3. Download and hash the source.
4. Compare against previous version.
5. Identify possibly affected provisions.
6. Create an internal update ticket.
7. Notify the tax-rule owner.
8. Do not change production calculations.
Official instructions explicitly state that schemas, utilities and validations may be updated after approval, making a controlled update and version-pinning process essential. ([Income Tax Department][3])
---
# 12. AI assistant architecture
## 12.1 Allowed AI capabilities
```text
tax_law:search
case_facts:read
missing_information:read
candidate_fact:create
computation:explain
document_request_draft:create
client_question_draft:create
portal_guide:read
regime_comparison:read
discrepancies:read
```
Everything else is denied by default.
The AI service account must not possess direct database access.
## 12.2 Tool gateway
Every tool execution performs:
1. Schema validation.
2. Authentication.
3. Tenant authorization.
4. Active-case authorization.
5. Permission check.
6. Case-state validation.
7. Rate limiting.
8. Idempotency check.
9. Execution.
10. Audit logging.
11. Output filtering.
## 12.3 Safe AI tools
### `search_tax_law`
Returns only indexed, approved official sources.
### `read_case_facts`
Returns a minimised view of authorised case facts.
### `list_missing_information`
Reads deterministic missing-item rules.
### `propose_fact`
Creates a candidate fact referencing existing evidence claims.
### `explain_computation`
Reads stored calculation lines. It never recalculates tax.
### `create_document_request_draft`
Creates a reviewable draft but sends nothing.
### `create_client_question_draft`
Creates a draft but sends nothing.
### `show_portal_guide`
Returns versioned, approved procedural content.
### `compare_regimes`
Returns existing deterministic old/new computation results.
### `summarise_discrepancies`
Summarises stored reconciliation items.
## 12.4 Structured AI output
```python
class AssistantResponse:
    response_type: ResponseType
    status: VerifiedStatus
    summary: str
    findings: list[Finding]
    evidence: list[EvidenceReference]
    tax_impact: str | None
    missing_information: list[MissingItem]
    assumptions: list[str]
    required_actions: list[Action]
    legal_citations: list[LegalCitation]
    ca_review_required: bool
    ca_review_reason: str | None
    candidate_fact_ids_created: list[UUID]
```
## 12.5 Prompt-injection controls
Documents, emails and client messages are untrusted data.
The system must:
* Label all retrieved content as untrusted.
* Never treat document text as an instruction.
* Prevent documents from selecting tools.
* Keep tool permissions outside the model.
* Allowlist outbound destinations.
* Reject generic URL fetching.
* Redact unnecessary personal information.
* Scan model outputs for unsupported citations.
* Test indirect prompt injection continuously.
OWASP identifies both direct and indirect prompt injection as major risks, including malicious instructions hidden inside documents processed by an LLM. ([OWASP Foundation][4])
---
# 13. Tax-law retrieval system
## 13.1 Source hierarchy
Only approved sources enter the production legal knowledge base:
1. Income-tax Acts.
2. Income-tax Rules.
3. Finance Acts.
4. Gazette notifications.
5. CBDT notifications.
6. CBDT circulars.
7. Official ITR instructions.
8. Official schemas.
9. Official validation rules.
10. DTAA and protocol texts.
11. Official portal manuals.
12. Official FAQs.
Third-party websites may help the research team but should not be cited as authoritative production law.
## 13.2 Legal document metadata
Each passage stores:
* Official title.
* Source type.
* Act namespace.
* Section or rule.
* Publication date.
* Effective date.
* Applicable tax periods.
* Superseded status.
* Source hash.
* Human-review status.
* Official source location.
## 13.3 Retrieval behaviour
The assistant must:
* Filter by tax period.
* Filter by Act namespace.
* Prioritise primary sources.
* Refuse to invent a section.
* Distinguish law from portal guidance.
* Identify when a source is superseded.
* State when legal review is required.
---
# 14. AIS and Form 26AS reconciliation
Do not merge AIS values directly into tax computation.
Create a reconciliation ledger:
| Category            | Taxpayer document |    AIS/TIS | Form 26AS | Accepted fact | Status                |
| ------------------- | ----------------: | ---------: | --------: | ------------: | --------------------- |
| Salary – Employer A |        ₹14,51,200 | ₹14,51,200 |         — |    ₹14,51,200 | Matched               |
| Employer TDS        |         ₹1,05,000 |  ₹1,05,000 | ₹1,05,000 |     ₹1,05,000 | Matched               |
| Bank interest       |           ₹18,500 |    ₹17,900 |         — |       ₹18,500 | Difference            |
| Share sale proceeds |         ₹8,40,000 |  ₹8,40,000 |         — |       Pending | Broker report missing |
Reconciliation statuses:
```text
MATCHED
PARTIAL_MATCH
DIFFERENCE
MISSING_IN_AIS
MISSING_IN_CLIENT_DOCS
DUPLICATE
INFORMATION_ONLY
REVIEW_REQUIRED
RESOLVED
```
The CA chooses the accepted fact with an explanation where sources differ.
---
# 15. Return-form eligibility engine
Return selection must be independent from tax computation.
The engine evaluates:
* Residential status.
* Taxpayer category.
* Total income.
* Number of properties.
* Type and size of capital gains.
* Business income.
* Foreign assets.
* Directorship.
* Unlisted shares.
* Brought-forward losses.
* Other official eligibility conditions.
Output:
```json
{
  "eligible_forms": ["ITR_1", "ITR_2"],
  "recommended_form": "ITR_1",
  "reasons": ["..."],
  "disqualifiers": [],
  "rule_release": "FORM_ELIGIBILITY_AY2026_27_V1"
}
```
---
# 16. ITR export architecture
## 16.1 Separate services
```text
Tax computation
→ Form eligibility
→ Schedule mapping
→ Official schema exporter
→ Official validation
→ Export snapshot
```
## 16.2 Export requirements
Each form receives its own mapper:
* `ITR1Exporter`
* `ITR2Exporter`
Later:
* `ITR3Exporter`
* `ITR4Exporter`
Each exporter pins:
* Assessment year.
* Official form schema version.
* Validation-rule version.
* Exporter code version.
* Rule-release version.
* Fact snapshot.
* Computation snapshot.
## 16.3 Export states
```text
NOT_READY
READY_FOR_VALIDATION
VALIDATION_FAILED
READY_FOR_CA_REVIEW
APPROVED
EXPORTED
SUPERSEDED
```
## 16.4 Final export gate
Export is blocked when:
* Any required field is missing.
* A material fact is unresolved.
* The computation is provisional.
* Official validation fails.
* The form is unsupported.
* Reviewer approval is absent.
---
# 17. CA interface design
## 17.1 Firm dashboard
Display:
* Cases by status.
* Assigned preparer.
* Assigned reviewer.
* Missing documents.
* High-risk discrepancies.
* Returns awaiting approval.
* Export failures.
* Filing deadlines.
* Team workload.
## 17.2 Client case workspace
```text
┌──────────────────────────────────────────────────────────────────┐
│ Client | Tax period | Form | Status | Preparer | Reviewer       │
├────────────────────────────┬─────────────────────────────────────┤
│ Assistant                  │ Computation | Evidence | Issues     │
│                            │ Reconciliation | Export | History   │
│ Conversation               │                                     │
│ Document upload            │ Salary                     ₹...      │
│ Missing questions          │ House property             ₹...      │
│ Portal guidance            │ Capital gains              ₹...      │
│ Draft client requests      │ Deductions                 ₹...      │
│                            │ Tax payable/refund          ₹...      │
└────────────────────────────┴─────────────────────────────────────┘
```
## 17.3 Right-pane statuses
Avoid vague confidence scores as the primary signal.
Use:
* Verified.
* Matched.
* Client-confirmed.
* CA-approved.
* Extracted—review needed.
* Conflicting.
* Missing.
* Blocked.
* Unsupported.
## 17.4 Evidence viewer
The CA clicks a value and sees:
* Source document.
* Exact page.
* Highlighted region.
* Original text.
* Alternative extraction.
* Validation checks.
* Correction history.
* Acceptance status.
## 17.5 Review desk
Provide a dedicated queue for:
* Conflicting values.
* Low-confidence extraction.
* Overrides.
* Unsupported scenarios.
* High-value transactions.
* Foreign indicators.
* Revised documents.
* Form eligibility issues.
* Export validation failures.
---
# 18. Client portal
The first production release may keep client communication within the CA firm. A client portal can follow once the internal workbench is stable.
The portal should allow clients to:
* Upload requested documents.
* Answer structured questions.
* View pending requests.
* Confirm factual declarations.
* Download approved summaries.
* Consent to data processing.
* Request correction or deletion where applicable.
Clients must not:
* Edit final computations.
* Approve tax positions.
* View internal CA notes.
* Access another family member or client without explicit permission.
---
# 19. Data protection and compliance
Green Papaya will process highly sensitive financial and identity information.
The DPDP Rules, 2025 and their enforcement materials have been officially published by MeitY. The product therefore needs privacy notices, purpose controls, retention processes, security safeguards and data-principal workflows as first-class features. ([MeitY][5])
## 19.1 Required privacy work
Before production:
* Define Green Papaya’s role versus the CA firm’s role.
* Draft the CA firm agreement.
* Draft data-processing terms.
* Create a privacy notice.
* Record processing purposes.
* Define document retention periods.
* Create deletion and correction workflows.
* Create account export workflows.
* Document subprocessors.
* Review cross-border data transfers.
* Create a breach-response process.
* Establish grievance handling.
* Obtain specialist Indian privacy counsel review.
## 19.2 Encryption
* TLS in transit.
* Managed encryption at rest.
* Field-level encryption for PAN and sensitive identifiers.
* Encryption-key IDs on encrypted records.
* Key rotation.
* No automatically generated fallback key.
* Production startup fails when keys are unavailable.
* Sensitive search through keyed tokens rather than raw hashes.
## 19.3 Logging
Logs must never contain:
* Full PAN.
* Full bank-account number.
* Full document contents.
* Raw LLM prompts containing unrestricted client data.
* Authentication tokens.
* Encryption keys.
Maintain security logs and an incident-response process consistent with applicable CERT-In directions. CERT-In maintains formal cyber-incident reporting directions and related logging requirements for covered organisations. ([CERT-In][6])
## 19.4 Operational security controls
* MFA for firm users.
* Session expiry.
* Device and login history.
* Rate limiting.
* WAF.
* Brute-force protection.
* CSRF protection.
* Secure cookies.
* Content security policy.
* Secrets manager.
* Dependency scanning.
* Static application security testing.
* Dynamic security testing.
* Container-image scanning.
* Software bill of materials.
* Annual penetration test.
* Pre-launch penetration test.
* Vendor-security review.
---
# 20. Model and provider strategy
## 20.1 Do not build around one model
Create a model abstraction with approved routes:
| Workload              | Model class                           |
| --------------------- | ------------------------------------- |
| Intent classification | Small economical model                |
| Case assistant        | Strong tool-use model                 |
| Complex explanation   | Strong reasoning model                |
| Vision extraction     | Approved document vision model        |
| Legal summarisation   | Model with retrieved official context |
| Embeddings            | Stable retrieval model                |
## 20.2 Production provider requirements
A provider must support:
* Contractual data protections.
* No training on submitted data.
* Zero-data-retention option where required.
* Fixed model identifiers.
* Regional and subprocessor transparency.
* Usage logging controls.
* Enterprise access control.
* Reliable limits.
* Incident notification.
* Cost and latency visibility.
Free public models may be used with synthetic or irreversibly redacted cases during development. They should not process production taxpayer documents without a completed vendor-security and privacy review.
## 20.3 Model evaluation
Every model candidate is tested on:
* Tool-selection accuracy.
* Unsupported-claim rate.
* Citation accuracy.
* Candidate-fact schema compliance.
* Prompt-injection resistance.
* Refusal behaviour.
* Tax explanation fidelity.
* Document extraction accuracy.
* Latency.
* Cost.
Model changes require evaluation and staged deployment.
---
# 21. Testing and accuracy programme
## 21.1 Golden tax cases
Create a CA-reviewed test library.
Initial target:
| Case type                 | Minimum cases |
| ------------------------- | ------------: |
| Salary-only               |           100 |
| Multiple employers        |            75 |
| Interest and dividends    |            75 |
| House property            |           100 |
| Old/new regime            |           100 |
| Listed equity gains       |           150 |
| Mutual-fund gains         |           100 |
| Loss set-off              |            75 |
| TDS/TCS and tax payments  |            75 |
| Boundary conditions       |           200 |
| Unsupported-case blockers |           100 |
Every case contains:
* Structured input facts.
* Expected income-head values.
* Expected deduction values.
* Expected total income.
* Expected tax.
* Expected interest.
* Expected refund/payable.
* Expected form.
* Expected schedule values.
## 21.2 Differential testing
Compare against:
1. Income Tax Department utility.
2. Official validation rules.
3. CA firm’s current trusted software.
4. Independent CA-reviewed computation.
Any difference is classified and resolved.
## 21.3 Boundary testing
For every threshold:
```text
Threshold - ₹1
Threshold
Threshold + ₹1
```
Test:
* Slab boundaries.
* Rebate boundaries.
* Surcharge thresholds.
* Marginal relief.
* Deduction limits.
* Holding periods.
* Capital-gain exemptions.
* Form eligibility.
* Senior-citizen age tests.
* Interest dates.
## 21.4 Property-based tests
Examples:
* Same facts and rules always produce the same result.
* Calculation totals equal their component lines.
* Removing unused evidence cannot change tax.
* Changing an unapproved candidate fact cannot change tax.
* Locking a snapshot prevents mutation.
* Tax credits do not alter gross tax.
* Unsupported modules never default to zero.
## 21.5 Document-parser tests
Measure per field:
* Exact numeric match.
* Character accuracy.
* Date accuracy.
* PAN/TAN accuracy.
* Table row precision.
* Table row recall.
* False-positive rate.
* Manual-review rate.
* Correction time.
A document is not considered “accurately parsed” simply because some text was extracted.
## 21.6 Security tests
Required automated tests:
* Cross-tenant case access.
* Cross-case document attachment.
* Privilege escalation.
* Self-selected role attacks.
* ID enumeration.
* Locked-case mutation.
* Unauthorised export.
* Unauthorised evidence access.
* Prompt injection.
* Indirect prompt injection in PDFs.
* Tool-name invention.
* Tool-argument tampering.
* Large-file attacks.
* Malformed PDF attacks.
* Malware upload.
* Session fixation.
* Token replay.
## 21.7 Load tests
Test:
* Concurrent document uploads.
* Large broker reports.
* OCR worker saturation.
* Computation bursts.
* Firm dashboard queries.
* Export generation.
* Recovery after queue failure.
---
# 22. DevOps and release engineering
## 22.1 Environments
Maintain:
* Local development.
* Shared development.
* Test.
* Staging.
* Production.
Never copy unredacted production data into non-production environments.
## 22.2 Infrastructure as code
All infrastructure must be reproducible through code:
* Networks.
* Databases.
* Storage.
* IAM.
* Key management.
* Secrets.
* Compute.
* Monitoring.
* Backup policies.
* WAF rules.
## 22.3 Deployment pipeline
```text
Pull request
→ Lint and type checks
→ Unit tests
→ Tax golden tests
→ Parser regression tests
→ Security scans
→ Build signed image
→ Deploy test
→ Integration tests
→ Deploy staging
→ Acceptance tests
→ Human approval
→ Production canary
→ Full deployment
```
## 22.4 Database migrations
* Reviewed migrations.
* Backward-compatible rollout.
* Dry run against staging copy.
* Automated backup before material migration.
* Rollback or forward-fix plan.
* No manual production schema edits.
## 22.5 Feature flags
Use flags for:
* New document adapters.
* New tax modules.
* New rule releases.
* New model routes.
* New exporters.
* Cross-border features.
---
# 23. Reliability and operations
## 23.1 Initial service objectives
| Metric                      | Target                                   |
| --------------------------- | ---------------------------------------- |
| Application availability    | 99.9% during filing season               |
| Standard API response       | p95 under 1 second                       |
| Chat response               | p95 under 8 seconds, excluding long jobs |
| Digital Form 16 processing  | p95 under 60 seconds                     |
| Large broker report         | Asynchronous with visible progress       |
| Computation                 | p95 under 2 seconds                      |
| Error-rate alert            | Under 1%                                 |
| Cross-tenant data incidents | Zero                                     |
## 23.2 Backup objectives
Recommended initial targets:
* Database RPO: 15 minutes or better.
* Database RTO: 4 hours or better.
* Object-storage versioning.
* Daily backup verification.
* Quarterly restore test.
* Pre-filing-season disaster-recovery exercise.
## 23.3 Monitoring
Alert on:
* Login anomalies.
* Permission failures.
* Cross-tenant policy failures.
* Parser error spikes.
* Computation differences.
* Export-validation failures.
* AI tool-call denials.
* Model latency and cost.
* Queue backlog.
* Database saturation.
* Backup failure.
* Key-management failure.
---
# 24. Product analytics
Track workflow value rather than chat volume.
## Primary metrics
* Median preparation time per return.
* Percentage of facts auto-extracted.
* Percentage of extracted facts accepted without correction.
* Time spent resolving discrepancies.
* Number of missing-item follow-ups.
* Cases completed per preparer.
* Tax variance versus reference software.
* Export-validation pass rate.
* Reviewer correction rate.
* User retention per CA firm.
* Cost per completed case.
## Quality metrics
* Material computation errors.
* Incorrect form selection.
* Unsupported case incorrectly accepted.
* Hallucinated citation rate.
* Cross-client retrieval rate.
* Evidence-link completeness.
* Parser exact-match rate.
---
# 25. Team required
A realistic core team:
| Role                     |                Number |
| ------------------------ | --------------------: |
| Product/engineering lead |                     1 |
| Senior backend engineers |                     2 |
| Frontend engineer        |                   1–2 |
| Document/ML engineer     |                     1 |
| QA automation engineer   |                     1 |
| DevOps/security engineer |                 0.5–1 |
| Product designer         |                 0.5–1 |
| CA tax-domain lead       |                     1 |
| Additional CA reviewers  |         1–2 part-time |
| Privacy/security counsel | Specialist engagement |
Do not attempt production tax accuracy using only generalist developers and prompts. The CA tax-domain lead must own rule interpretation and golden-case approval.
---
# 26. Complete delivery roadmap
## Phase 0 — Product contract and scope
**Weeks 1–2**
Deliver:
* V1 supported-case matrix.
* Unsupported-case matrix.
* Field dictionary.
* Document inventory.
* Legal-source hierarchy.
* Accuracy definitions.
* Pilot success criteria.
* Current-code deprecation plan.
* Security threat model.
* CA advisory group.
Exit gate:
* Scope signed by product, engineering and CA tax lead.
* At least 100 anonymised historical pilot cases secured.
* No claim that current tax output is production ready.
---
## Phase 1 — Security and tenant foundation
**Weeks 2–5**
Build:
* PostgreSQL foundation.
* Tenant and user model.
* Secure invitation workflow.
* Role and permission system.
* Case assignments.
* Object-level authorization.
* MFA.
* Secrets management.
* Production encryption model.
* Append-only audit logs.
* Secure upload pipeline.
* Basic monitoring.
Remove:
* Self-selected CA role.
* Generic cross-case access.
* Random encryption-key fallback.
* Direct unauthorised document URLs.
Exit gate:
* All access-control tests pass.
* External security review finds no critical object-level access flaw.
* No user can access another tenant’s data.
---
## Phase 2 — Canonical tax ledger and evidence
**Weeks 4–8**
Build:
* Document records and versions.
* Extraction runs.
* Evidence claims.
* Candidate facts.
* Canonical facts.
* Conflict workflow.
* Fact approval.
* Fact snapshots.
* Evidence viewer.
* Correction history.
* Duplicate/revised-document handling.
Exit gate:
* Every accepted fact is evidence-linked or manually declared.
* Candidate facts cannot affect computation.
* Snapshots are immutable.
---
## Phase 3 — Deterministic tax engine foundation
**Weeks 6–12**
Build:
* Typed engine inputs.
* Decimal arithmetic.
* Rule-release registry.
* Calculation-line trace.
* Salary module.
* Other-sources module.
* House-property module.
* Common deductions.
* Old/new regime.
* TDS/TCS and payments.
* Refund/payable.
* Blocking and unsupported states.
* Initial form eligibility.
Exit gate:
* Exact match on approved salary and basic property golden cases.
* No LLM calls in engine.
* Same snapshot always produces the same hash and result.
---
## Phase 4 — Document adapters
**Weeks 7–14**
Build:
* Form 16 A/B.
* AIS/TIS.
* Form 26AS.
* Interest certificates.
* Three major banks.
* Two brokers.
* Previous-year return import.
* Document-field validation.
* Disagreement workflow.
* Parser metrics dashboard.
Exit gate:
* Field-level accuracy thresholds achieved.
* Low-confidence and conflicting fields reliably enter review.
* Reprocessing is idempotent.
---
## Phase 5 — Capital-gains engine
**Weeks 10–16**
Build:
* Transaction-level gain model.
* Listed-equity rules.
* Selected mutual-fund rules.
* Holding-period determination.
* Section 111A bucket.
* Section 112A bucket.
* Grandfathering fields.
* Capital-loss set-off.
* Broker-summary reconciliation.
* High-risk blockers.
Exit gate:
* Exact match on capital-gain golden cases.
* Unsupported asset types are blocked.
* No broker summary is treated as final without transaction or approved aggregate support.
---
## Phase 6 — CA workbench
**Weeks 10–16**
Build:
* Firm dashboard.
* Client case workspace.
* Split assistant/computation view.
* Evidence viewer.
* Missing-items panel.
* Reconciliation panel.
* Review queue.
* Override workflow.
* Maker-checker approvals.
* Computation-version comparison.
* Audit history.
Exit gate:
* A CA can complete a supported case without administrative database access.
* Every final number can be traced from UI to evidence and rule.
---
## Phase 7 — AI assistant and legal retrieval
**Weeks 13–18**
Build:
* AI tool gateway.
* Strict tool schemas.
* Official legal-source ingestion.
* Time-aware retrieval.
* Structured assistant responses.
* Computation explanation.
* Missing-information assistance.
* Draft document requests.
* Draft client questions.
* Portal guides.
* Prompt-injection defences.
* Model evaluation harness.
Exit gate:
* AI cannot approve facts or alter computations.
* AI cannot access another case.
* Legal citations resolve to approved sources.
* Injection red-team suite passes.
---
## Phase 8 — ITR export and official validation
**Weeks 15–20**
Build:
* ITR-1 eligibility and exporter.
* Selected ITR-2 eligibility and exporter.
* Schedule mapper.
* Official schema pinning.
* Published validation-rule implementation.
* Export snapshot.
* Validation-error UI.
* Export approval workflow.
Exit gate:
* Supported golden cases pass the pinned official schema and validation rules.
* Export can be regenerated from its immutable snapshot.
* Unsupported schedules block export.
---
## Phase 9 — Security, privacy and operational hardening
**Weeks 18–22**
Complete:
* Privacy documentation.
* Data-retention jobs.
* Data export/deletion workflows.
* Vendor reviews.
* Penetration test.
* Disaster-recovery test.
* Backup restore.
* Load tests.
* WAF tuning.
* Runbooks.
* Incident-response tabletop.
* Support tooling.
* Model-provider failure handling.
Exit gate:
* No open critical or high security issue.
* Restore test completed.
* Incident process approved.
* Production monitoring operational.
---
## Phase 10 — Controlled CA pilot
**Weeks 20–24**
Pilot structure:
* Two or three CA firms.
* Five to ten users.
* 100–300 supported returns.
* Mandatory parallel calculation in existing software.
* Mandatory reviewer approval.
* Daily issue review.
* Weekly model/parser review.
* No direct filing automation.
* Immediate rollback capability.
Pilot success criteria:
* Zero material undetected tax errors.
* 100% material-value evidence coverage.
* 100% supported exports pass validation.
* At least 40% reduction in preparation/review time.
* Fewer than 5% of accepted parser fields require correction, subject to document type.
* No tenant-isolation incident.
* No unsupported case marked complete.
---
## Phase 11 — Limited production launch
**Weeks 24–30**
Launch only the proven scope.
Production controls:
* Firm-level onboarding.
* Approved document-type list.
* Supported-case checker before work begins.
* Usage limits.
* Human final approval.
* Live support.
* Daily operational review during filing season.
* Feature flags for every risky module.
* Production rollback process.
Do not market Schedule FA, complex capital gains or business-income automation until those modules independently pass the same process.
---
# 27. Go-live checklist
## Tax accuracy
* Golden-case suite passes.
* Boundary tests pass.
* Differential tests pass.
* Capital-gain tests pass.
* Old/new-regime tests pass.
* TDS/refund tests pass.
* Form selection tests pass.
* Unsupported cases block correctly.
## Export
* ITR-1 export passes official validation.
* Supported ITR-2 export passes official validation.
* Schema version is visible.
* Export snapshot is immutable.
* Reviewer approval is recorded.
## Security
* No self-assigned privileged roles.
* Every endpoint has object-level authorization.
* Penetration test passed.
* MFA enabled.
* Encryption keys managed.
* Secrets removed from repository.
* Production logging redacted.
* Backup restore tested.
* Incident runbook tested.
## AI
* Only allowlisted tools exposed.
* Case context server-controlled.
* Candidate facts require evidence.
* Tool arguments strictly validated.
* Prompt-injection tests pass.
* Unsupported citation tests pass.
* AI provider privacy controls verified.
* Model fallback cannot change permissions.
## Operations
* Monitoring enabled.
* On-call owner named.
* Support workflow active.
* Status page prepared.
* Vendor contacts documented.
* Backup alerts enabled.
* Filing-season capacity tested.
## Legal and privacy
* Customer agreement approved.
* Privacy notice approved.
* Data-processing terms approved.
* Retention policy implemented.
* Deletion workflow tested.
* Subprocessor register completed.
* Incident-notification process documented.
---
# 28. Commercial launch plan
## 28.1 Pilot offer
Offer the first firms:
* Fixed supported scope.
* Assisted onboarding.
* Historic-case import.
* Parallel-computation validation.
* Weekly product session.
* Founder-level support.
* Clear statement that the CA remains final reviewer.
## 28.2 Pricing model to test
A suitable model is:
```text
Base firm subscription
+ included users
+ included return volume
+ per-completed-return overage
+ premium advanced-tax modules later
```
Do not price primarily by AI messages. CAs pay for completed and reviewed work, not chat tokens.
## 28.3 Value proposition
Demonstrate:
* Reduced document organisation time.
* Faster missing-information follow-up.
* Reduced manual data entry.
* Evidence-linked review.
* Better AIS reconciliation.
* Faster old/new regime comparison.
* Reduced review risk.
* Faster junior-preparer onboarding.
* Consistent firm-wide process.
---
# 29. Estimated delivery investment
For a serious 6–8 month build with the proposed team, a broad planning estimate is:
| Category                       | Indicative share |
| ------------------------------ | ---------------: |
| Engineering                    |           45–55% |
| Tax-domain and validation      |           15–20% |
| Security, privacy and legal    |            8–12% |
| Cloud and model usage          |            5–10% |
| QA and test data               |           10–15% |
| Design, onboarding and support |            5–10% |
A lean outsourced build may appear cheaper but creates unacceptable risk if tax-domain review, automated testing and security are removed.
The most expensive failure would be launching early with an incorrect tax engine or broken tenant isolation.
---
# 30. First 30-day execution plan
## Week 1
* Freeze the current tax engine for real use.
* Remove production-readiness claims.
* Create supported-scope document.
* Appoint CA tax lead.
* Collect anonymised golden cases.
* Create threat model.
* Create architecture decision records.
* Establish new PostgreSQL schema.
## Week 2
* Implement tenants and secure roles.
* Remove role self-selection.
* Implement case assignments.
* Add authorization policies.
* Add secure secrets and encryption startup checks.
* Add audit events.
* Add CI checks.
## Week 3
* Create document, evidence and candidate-fact models.
* Build immutable object-storage pathing.
* Add upload security.
* Build evidence viewer prototype.
* Define tax field registry.
* Implement candidate-fact state machine.
## Week 4
* Build fact approval and snapshot service.
* Create rule-release model.
* Write typed tax-engine interfaces.
* Add Decimal-based calculation-line model.
* Convert the first 25 golden cases.
* Implement the first pure salary calculation module.
At the end of day 30, the product should have a secure tenant foundation, evidence-linked candidate facts and the first deterministic calculation slice. The AI chat should not yet be the main development priority.
---
# 31. Definition of production ready
Green Papaya is production ready only when:
1. Every supported computation is deterministic.
2. Every material imported fact is evidence-linked.
3. Unsupported cases are blocked.
4. Official export validation passes.
5. Cross-tenant access is technically prevented.
6. AI cannot approve or modify final tax data.
7. Golden and boundary cases pass.
8. A CA reviewer approves each final case.
9. Backups and restores have been tested.
10. Security and privacy controls are operational.
11. The pilot demonstrates time savings without material tax variance.
12. Every output can be reproduced from an immutable snapshot.
The final product moat will not be one prompt or model. It will be the combination of:
* A versioned Indian tax-rule engine.
* A canonical tax-fact ledger.
* Evidence-linked document adapters.
* A CA-reviewed golden-case library.
* Firm workflow and audit controls.
* Corrections and learning data accumulated from real CA review.
The immediate engineering milestone is **Phase 1 and Phase 2: tenant security, canonical facts and evidence**, followed by rebuilding the tax engine as a pure deterministic service.
[1]: https://www.incometax.gov.in/iec/foportal/downloads/income-tax-returns?utm_source=chatgpt.com "Downloads - Income Tax Department"
[2]: https://incometaxindia.gov.in/documents/81799/11848482/Updated-FQAs-on-Interplay%26Transitions.pdf/e10ad2b6-9495-de90-58d3-20606d8954ae?t=1775128640970&utm_source=chatgpt.com "FAQs on Interplay and Transition - Central Board of Direct Taxes"
[3]: https://www.incometax.gov.in/iec/foportal/downloads/income-tax-returns/read-general-instrutions?utm_source=chatgpt.com "Read General Instructions Income Tax Returns"
[4]: https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf?utm_source=chatgpt.com "OWASP Top 10 for LLM Applications 2025"
[5]: https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025686cadad39.pdf&utm_source=chatgpt.com "Digital Personal Data Protection Rules 2025 - Ministry of Electronics ..."
[6]: https://www.cert-in.org.in/Directions70B.jsp?utm_source=chatgpt.com "Cert-In - Directions70B"