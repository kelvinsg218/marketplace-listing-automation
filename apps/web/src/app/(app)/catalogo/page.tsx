"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Boxes, ChevronLeft, ChevronRight, PackagePlus, Search } from "lucide-react";
import { api, ApiError, can, type Product, type ProductPage } from "@/lib/api";
import { money, STATUS_LABEL } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { draftFrom, type DraftErrors, ProductFields, toPayload } from "@/components/product-form";
import { Alert, Badge, Button, Card, Drawer, EmptyState, Input, PageHeader, Select, Skeleton } from "@/components/ui";

const PAGE = 25;

function PendingBadge({ p }: { p: Product }) {
  const errors = p.pendings.filter((x) => x.severity === "error").length;
  const warnings = p.pendings.filter((x) => x.severity === "warning").length;
  if (errors) return <Badge tone="danger">{errors} {errors === 1 ? "erro" : "erros"}</Badge>;
  if (warnings) return <Badge tone="warn">{warnings} {warnings === 1 ? "aviso" : "avisos"}</Badge>;
  return <Badge tone="ok">Completo</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  return <Badge tone={status === "active" ? "accent" : "neutral"}>{STATUS_LABEL[status]}</Badge>;
}

function CreateDrawer({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (p: Product) => void }) {
  const { org } = useSession();
  const [draft, setDraft] = useState(draftFrom());
  const [errors, setErrors] = useState<DraftErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setDraft(draftFrom()); setErrors({}); setError(null); } }, [open]);

  async function save() {
    const { body, errors } = toPayload(draft);
    setErrors(errors);
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await api<Product>(`/orgs/${org!.id}/products`, { method: "POST", body }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha ao salvar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title="Novo produto"
      footer={<><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button variant="primary" busy={busy} onClick={save}>Salvar produto</Button></>}>
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      <form onSubmit={(e) => { e.preventDefault(); save(); }}>
        <ProductFields draft={draft} onChange={setDraft} errors={errors} />
        <button type="submit" hidden />
      </form>
    </Drawer>
  );
}

function Catalog() {
  const { org, role } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(params.get("novo") === "1");

  useEffect(() => { const t = setTimeout(() => { setQuery(q); setOffset(0); }, 300); return () => clearTimeout(t); }, [q]);
  const qs = new URLSearchParams({ q: query, limit: String(PAGE), offset: String(offset), ...(status ? { status } : {}) });
  const { data, error, loading, reload } = useApi<ProductPage>(org ? `/orgs/${org.id}/products?${qs}` : null);
  const open = (id: string) => router.push(`/catalogo/produto/?id=${id}`);
  const filtered = query || status;

  return (
    <>
      <PageHeader title="Produtos" description="Catálogo mestre da organização, independente de marketplace."
        actions={can.write(role) && <Button variant="primary" onClick={() => setCreating(true)}><PackagePlus className="size-4" />Novo produto</Button>} />

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-faint" aria-hidden />
          <Input aria-label="Buscar produtos" placeholder="Buscar por nome, SKU, marca ou GTIN" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
        </div>
        <Select aria-label="Filtrar por status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">Todos os status</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>

      {error && <Alert>{error}</Alert>}
      <Card className="overflow-hidden">
        {loading && !data ? (
          <div className="p-4 flex flex-col gap-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : data && data.total === 0 ? (
          <EmptyState icon={<Boxes className="size-6" />} title={filtered ? "Nenhum produto encontrado" : "Nenhum produto cadastrado"}
            action={!filtered && can.write(role) && <Button variant="primary" onClick={() => setCreating(true)}>Cadastrar produto</Button>}>
            {filtered ? "Ajuste a busca ou o filtro de status." : "Comece cadastrando um produto. Importação em massa chega na etapa C."}
          </EmptyState>
        ) : data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-faint border-b border-line">
                  <th scope="col" className="font-semibold px-4 py-3">Produto</th>
                  <th scope="col" className="font-semibold px-4 py-3 hidden md:table-cell">SKU</th>
                  <th scope="col" className="font-semibold px-4 py-3 hidden lg:table-cell">Marca</th>
                  <th scope="col" className="font-semibold px-4 py-3 text-right">Preço</th>
                  <th scope="col" className="font-semibold px-4 py-3 text-right hidden sm:table-cell">Estoque</th>
                  <th scope="col" className="font-semibold px-4 py-3 hidden md:table-cell">Status</th>
                  <th scope="col" className="font-semibold px-4 py-3">Qualidade</th>
                </tr>
              </thead>
              <tbody className={loading ? "opacity-60 transition-opacity" : ""}>
                {data.items.map((p) => (
                  <tr key={p.id} onClick={() => open(p.id)} className="border-b border-line last:border-0 hover:bg-card-hover cursor-pointer">
                    <td className="px-4 py-3 max-w-[340px]">
                      <a href={`/catalogo/produto/?id=${p.id}`} onClick={(e) => { e.preventDefault(); open(p.id); }} className="block truncate font-medium hover:text-accent-2">{p.name}</a>
                      <span className="md:hidden font-mono text-xs text-faint">{p.sku}</span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted hidden md:table-cell">{p.sku}</td>
                    <td className="px-4 py-3 text-muted hidden lg:table-cell">{p.brand || "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(p.price_cents)}</td>
                    <td className="px-4 py-3 text-right tabular-nums hidden sm:table-cell">{p.stock}</td>
                    <td className="px-4 py-3 hidden md:table-cell"><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-3"><PendingBadge p={p} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {data && data.total > PAGE && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted">
          <span>{offset + 1}–{Math.min(offset + PAGE, data.total)} de {data.total}</span>
          <div className="flex gap-2">
            <Button size="sm" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)} aria-label="Página anterior"><ChevronLeft className="size-4" /></Button>
            <Button size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} aria-label="Próxima página"><ChevronRight className="size-4" /></Button>
          </div>
        </div>
      )}

      <CreateDrawer open={creating} onClose={() => { setCreating(false); router.replace("/catalogo/"); }}
        onCreated={() => { setCreating(false); router.replace("/catalogo/"); reload(); }} />
    </>
  );
}

export default function CatalogPage() {
  return <Suspense><Catalog /></Suspense>;
}
