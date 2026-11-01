// Thin client for the MLA API. Same-origin cookie session; every call sends the CSRF header the API requires.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const msg = (first.msg ?? "Dados inválidos.").replace(/^Value error, /, "");
    return msg;
  }
  return "Não foi possível concluir a operação.";
}

export async function api<T>(path: string, init: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: init.method ?? "GET",
      credentials: "same-origin",
      headers: { "X-MLA-Client": "web", ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: init.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "Sem conexão com o servidor. Verifique se a API está rodando.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, detailMessage((data as { detail?: unknown }).detail));
  return data as T;
}

/** Multipart upload (files). The browser sets the multipart boundary itself. */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method: "POST", credentials: "same-origin", headers: { "X-MLA-Client": "web" }, body: form });
  } catch {
    throw new ApiError(0, "Sem conexão com o servidor.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, detailMessage((data as { detail?: unknown }).detail));
  return data as T;
}

// --- types mirrored from apps/api/src/mla_api/schemas.py ---------------------------------------------------------
export type Role = "owner" | "admin" | "editor" | "viewer";
export interface User { id: string; name: string; email: string }
export interface Org { id: string; name: string; slug: string }
export interface Me { user: User; memberships: { organization: Org; role: Role }[] }
export interface Pending { field: string; message: string; severity: "error" | "warning" | "info" }
export type ProductStatus = "draft" | "active" | "archived";
export interface Product {
  id: string; sku: string; name: string; brand: string; model: string; gtin: string; description: string;
  price_cents: number | null; cost_cents: number | null; stock: number; status: ProductStatus;
  attributes: Record<string, string>; created_at: string; updated_at: string; pendings: Pending[];
}
export interface ProductPage { items: Product[]; total: number; limit: number; offset: number }
export interface AuditEvent {
  id: string; action: string; target_type: string; target_id: string; details: Record<string, unknown>;
  created_at: string; user_name: string | null;
}
export interface Dashboard {
  products_total: number; products_complete: number; products_with_pendings: number;
  products_by_status: Record<ProductStatus, number>;
  batches_total: number | null; exports_total: number | null; validation_errors: number | null;
  recent_activity: AuditEvent[];
}
export interface Member { user: User; role: Role; created_at: string }

// --- catalog media / bulk listing (apps/api/src/mla_api/routers/media.py, listings.py) ---------------------------
export interface Variant { id: string; sku: string; attributes: Record<string, string>; gtin: string; gtin_valid: boolean; price_cents: number | null; stock: number }
export interface ProductImage {
  id: string; position: number; variant_id: string | null; has_file: boolean; content_type: string; size_bytes: number;
  original_name: string; official_url: string; url_problem: string | null;
}
export interface PhotoStatus { product_id: string; sku: string; name: string; images: number; with_url: number; without_url: number; over_group_limit: boolean }
export interface SellerAccount { id: string; marketplace: string; label: string; external_id: string; templates: number }
export interface TemplateSheet { name: string; state: string; is_help: boolean; max_row: number; max_column: number }
export interface Marker { key: string; cell: string; text: string }
export interface SheetReport extends TemplateSheet {
  max_column_letter: string; merged_ranges: number; formula_cells: number; protected: boolean;
  data_validations: { sqref: string; type: string; formula1: string }[]; markers: Marker[];
  header_candidates: { row: number; filled_cells: number; marker_hits: number }[]; preview: string[][];
}
export interface Template {
  id: string; seller_account_id: string; seller_account_label: string; source: string; original_filename: string;
  sha256: string; size_bytes: number; status: "inspected" | "invalid" | "archived"; deadline_text: string;
  deadline_date: string | null; deadline_confirmed: boolean; expired: boolean; sheets: TemplateSheet[]; warnings: string[];
  created_at: string;
  structure?: { comparison?: { previous_template_id: string; previous_filename: string; diff: { breaking: boolean; sheets_added: string[]; sheets_removed: string[]; sheets: Record<string, Record<string, unknown>> } }; sheets: SheetReport[]; help_sheet: string | null; hidden_sheets: string[]; defined_names: string[]; deadline: { text: string; date: string; year_inferred: boolean; cell: string; sheet?: string } | null; warnings: string[] };
}
export interface MappingColumn { col: string; header: string; required: boolean; suggestion: string | null; options?: string[] | null; strict?: boolean; max_length?: number | null; template_default?: string | null; help?: string }
export interface Mapping {
  sheet_name: string; header_row: number; header_row_confirmed: boolean; header_candidates: { row: number }[];
  columns: MappingColumn[]; rules: Record<string, { source: string | null; default: string }>; source_fields: Record<string, string>;
}
export type BatchStatus = "draft" | "needs_fix" | "ready" | "exported" | "sent_external" | "result_received" | "done";
export interface Batch {
  id: string; name: string; status: BatchStatus; seller_account_id: string | null; seller_account_label: string | null;
  template_id: string | null; template_filename: string | null; template_expired: boolean; sheet_name: string; items: number;
  validation: { products?: number; rows?: number; complete?: number; with_errors?: number; with_warnings?: number; errors_total?: number; ready?: boolean; validated_at?: string; writer_available?: boolean };
  history: { at: string; by: string; event: string; [k: string]: unknown }[]; created_at: string; updated_at: string;
}
export interface RuleIssue { code: string; severity: "error" | "warning" | "info"; source: "interna" | "documentacao" | "template" | "hipotese"; message: string; fix: string; field: string; ref: string; sku: string }
export interface Validation {
  summary: Required<Batch["validation"]>;
  template_issues: RuleIssue[]; batch_issues: RuleIssue[];
  products: { product_id: string; sku: string; name: string; rows: number; errors: number; warnings: number; issues: RuleIssue[] }[];
}

export interface ExportRecord { id: string; sheet_name: string; rows: number; sha256: string; size_bytes: number; rules_applied: [string, number][]; checks: Record<string, unknown>; created_at: string }
export type RuleScope = "organization" | "account" | "category" | "template" | "batch";
export interface RuleDefinition { target: string; operation: string; params: Record<string, unknown>; condition: { when: string; field?: string; value?: string } }
export interface Rule { id: string; name: string; scope: RuleScope; scope_ref: string; priority: number; status: "active" | "inactive"; version: number; definition: RuleDefinition; origin: string; origin_text: string; created_at: string; updated_at: string }
export interface RuleVersion { version: number; definition: RuleDefinition; note: string; author: string | null; created_at: string }
export interface Simulation { definition: RuleDefinition; official_conflict: string | null; conflicts: string[]; column: string | null; rows: { sku: string; before: string; after: string; changed: boolean }[]; changed: number; can_apply: boolean }
export interface Interpretation { definition: RuleDefinition | null; scope: RuleScope; scope_ref: string; explanation: string; questions: string[]; confidence: string; engine: string; simulation?: Simulation }
export interface ErrorItem { text: string; column: string | null; required: boolean; message: string | null; proposals: { label: string; definition: RuleDefinition; needs_value?: boolean; options?: string[] }[] }

export const can = {
  write: (r?: Role) => r === "owner" || r === "admin" || r === "editor",
  manageMembers: (r?: Role) => r === "owner" || r === "admin",
  readAudit: (r?: Role) => r === "owner" || r === "admin",
};
