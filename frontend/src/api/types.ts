export type Role = "firm_owner" | "ca_partner" | "ca_manager" | "preparer" | "document_operator" | "auditor" | "client";
export interface SessionUser { id: string; email?: string | null; full_name?: string | null; tenant_id: string; role: Role; mfa_enabled: boolean; mfa_verified: boolean; permissions?: string[]; }
export interface SessionResponse { access_token?: string; refresh_token?: string; token_type: "bearer" | "cookie"; expires_in: number; user: SessionUser; }
export interface ClientRecord { id: string; display_name: string; email?: string | null; status?: string; }
export interface TaxCaseRecord { id: string; client_name: string; tax_period: string; assessment_year: string; status: string; selected_regime: "OLD" | "NEW"; rule_release_id: string; latest_computation?: ComputationResult | null; }
export interface CandidateFact { id: string; field_code: string; value: unknown; status: string; evidence_claim_ids: string[]; }
export interface CanonicalFact { id: string; field_code: string; entity_key: string; value: unknown; version: number; }
export interface DocumentRecord { id: string; filename: string; document_type: string; state: string; }
export interface RegimeResult { gross_total_income: string; deductions: string; total_income: string; total_tax_liability: string; tax_paid: string; payable: string; refund: string; }
export interface ComputationResult { status: string; selected_regime: string; recommended_regime?: string | null; selected_result?: RegimeResult | null; blockers?: unknown[]; warnings?: unknown[]; result_hash?: string; calculation_lines?: unknown[]; form_eligibility?: {recommended_form?: string | null}; }
