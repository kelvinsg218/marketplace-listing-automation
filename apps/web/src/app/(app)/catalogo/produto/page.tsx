"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, AlertTriangle, ArrowLeft, Info, Trash2 } from "lucide-react";
import { api, ApiError, can, type Product } from "@/lib/api";
import { when } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { draftFrom, type DraftErrors, ProductFields, toPayload } from "@/components/product-form";
import { MercadoLivreCard, PhotosCard, VariantsCard } from "@/components/product-extras";
import { Alert, Button, Card, cx, PageHeader, Skeleton } from "@/components/ui";

const SEVERITY = {
  error: { icon: AlertCircle, cls: "text-danger", label: "Erro" },
  warning: { icon: AlertTriangle, cls: "text-warn", label: "Aviso" },
  info: { icon: Info, cls: "text-info", label: "Informação" },
};

function Editor({ product, onSaved }: { product: Product; onSaved: (p: Product) => void }) {
  const { org, role } = useSession();
  const router = useRouter();
  const [draft, setDraft] = useState(draftFrom(product));
  const [errors, setErrors] = useState<DraftErrors>({});
  const [msg, setMsg] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const readOnly = !can.write(role);
  useEffect(() => setDraft(draftFrom(product)), [product]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(draftFrom(product));

  async function save() {
    const { body, errors } = toPayload(draft);
    setErrors(errors);
    if (!body) return;
    delete body.sku;
    setBusy(true);
    setMsg(null);
    try {
      onSaved(await api<Product>(`/orgs/${org!.id}/products/${product.id}`, { method: "PATCH", body }));
      setMsg({ tone: "ok", text: "Alterações salvas." });
    } catch (err) {
      setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha ao salvar." });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Excluir o produto ${product.sku}? Esta ação não pode ser desfeita.`)) return;
    try {
      await api(`/orgs/${org!.id}/products/${product.id}`, { method: "DELETE" });
      router.replace("/catalogo/");
    } catch (err) {
      setMsg({ tone: "danger", text: err instanceof ApiError ? err.message : "Falha ao excluir." });
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_340px] items-start">
      <Card className="p-6">
        {msg && <div className="mb-5"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
        <form onSubmit={(e) => { e.preventDefault(); save(); }}>
          <ProductFields draft={draft} onChange={setDraft} errors={errors} skuLocked readOnly={readOnly} />
          {!readOnly && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
              <Button type="button" variant="danger" onClick={remove}><Trash2 className="size-4" />Excluir</Button>
              <div className="flex gap-2">
                <Button type="button" variant="ghost" disabled={!dirty} onClick={() => { setDraft(draftFrom(product)); setErrors({}); }}>Descartar</Button>
                <Button type="submit" variant="primary" busy={busy} disabled={!dirty}>Salvar alterações</Button>
              </div>
            </div>
          )}
        </form>
      </Card>

      <div className="flex flex-col gap-4 xl:sticky xl:top-8">
        <Card className="p-5">
          <h2 className="text-sm font-semibold">Pendências do catálogo</h2>
          <p className="mt-1 text-xs text-faint">Regras internas. Os requisitos do Mercado Livre serão validados por template, na etapa D.</p>
          {product.pendings.length === 0 ? (
            <p className="mt-4 text-sm text-ok">Nenhuma pendência.</p>
          ) : (
            <ul className="mt-4 flex flex-col gap-3">
              {product.pendings.map((p) => {
                const s = SEVERITY[p.severity];
                return (
                  <li key={p.field} className="flex gap-2.5 text-sm">
                    <s.icon className={cx("size-4 mt-0.5 shrink-0", s.cls)} aria-label={s.label} />
                    <span>{p.message}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <Card className="p-5 text-sm">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className="text-faint">Criado</dt><dd className="text-right">{when(product.created_at)}</dd>
            <dt className="text-faint">Atualizado</dt><dd className="text-right">{when(product.updated_at)}</dd>
          </dl>
        </Card>
      </div>
    </div>
  );
}

function ProductDetail() {
  const { org, role } = useSession();
  const id = useSearchParams().get("id");
  const { data, error, loading, setData } = useApi<Product>(org && id ? `/orgs/${org.id}/products/${id}` : null);
  return (
    <>
      <Link href="/catalogo/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg mb-4">
        <ArrowLeft className="size-4" />Produtos
      </Link>
      {!id || error ? (
        <Alert>{error ?? "Produto não informado."}</Alert>
      ) : loading && !data ? (
        <Skeleton className="h-96" />
      ) : data && (
        <>
          <PageHeader title={data.name} description={`SKU ${data.sku}${data.brand ? ` · ${data.brand}` : ""}`} />
          <Editor product={data} onSaved={setData} />
          <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_340px] items-start">
            <div className="flex flex-col gap-6 min-w-0">
              <VariantsCard orgId={org!.id} productId={data.id} canWrite={can.write(role)} />
              <PhotosCard orgId={org!.id} productId={data.id} canWrite={can.write(role)} />
            </div>
            <MercadoLivreCard orgId={org!.id} productId={data.id} canWrite={can.write(role)} />
          </div>
        </>
      )}
    </>
  );
}

export default function ProductPage() {
  return <Suspense><ProductDetail /></Suspense>;
}
