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

export const can = {
  write: (r?: Role) => r === "owner" || r === "admin" || r === "editor",
  manageMembers: (r?: Role) => r === "owner" || r === "admin",
  readAudit: (r?: Role) => r === "owner" || r === "admin",
};
